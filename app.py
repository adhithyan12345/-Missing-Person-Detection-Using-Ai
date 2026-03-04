# -*- coding: utf-8 -*-
import os
import mysql.connector
import pickle
import cv2
import numpy as np
import base64
import threading
import queue
import random
import string
import time
import requests
from datetime import datetime, time, timedelta
from flask import Flask, render_template, request, redirect, url_for, flash, Response, jsonify, session
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
from itsdangerous import URLSafeTimedSerializer
from config import Config
from utils.ai_engine import get_face_encoding, find_match, get_face_encoding_from_frame, get_all_face_encodings
from utils.report_generator import generate_case_report
from utils.poster_generator import generate_poster
from flask import send_file
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from geopy.geocoders import Nominatim
from flask_mail import Mail
from utils.notification_service import NotificationManager

app = Flask(__name__)
app.config.from_object(Config)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'


app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = 'your-email@gmail.com'
app.config['MAIL_PASSWORD'] = 'your-app-password'
app.config['MAIL_DEFAULT_SENDER'] = 'noreply@missingpersons.com'
app.config['TWILIO_ACCOUNT_SID'] = 'your_sid'
app.config['TWILIO_AUTH_TOKEN'] = 'your_token'
app.config['TWILIO_PHONE_NUMBER'] = '+1234567890'

mail = Mail(app)
notification_manager = NotificationManager(app, mail)
serializer = URLSafeTimedSerializer(app.config['SECRET_KEY'])

class User(UserMixin):
    def __init__(self, id, full_name, email, password_hash, role='user'):
        self.id = id
        self.full_name = full_name
        self.email = email
        self.password_hash = password_hash
        self.role = role

@login_manager.user_loader
def load_user(user_id):
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM users WHERE id = %s", (user_id,))
        user_data = cursor.fetchone()
        cursor.close()
        conn.close()
        if user_data:
            return User(user_data['id'], user_data['full_name'], user_data['email'], user_data['password_hash'], user_data.get('role', 'user'))
    except Exception as e:
        print(f"Error loading user: {e}")
    return None



KNOWN_FACES_CACHE = {}
LATEST_MATCH = {'timestamp': 0}
LAST_LOGGED = {}
LOG_COOLDOWN = 60
LAST_CASE_UPDATE = {}
CASE_UPDATE_COOLDOWN = 300
LOCATION_CACHE = {}

def get_location_name(lat, lon):
    if not lat or not lon:
        return "Unknown Location"

    key = f"{lat},{lon}"
    if key in LOCATION_CACHE:
        return LOCATION_CACHE[key]

    try:
        geolocator = Nominatim(user_agent="missing_persons_app")
        location = geolocator.reverse(f"{lat}, {lon}")
        address = location.address if location else "Unknown Location"
        LOCATION_CACHE[key] = address
        return address
    except Exception as e:
        print(f"Geocoding error: {e}")
        return "Unknown Location"

def get_db_connection():
    return mysql.connector.connect(
        host=app.config['MYSQL_HOST'],
        user=app.config['MYSQL_USER'],
        password=app.config['MYSQL_PASSWORD'],
        database=app.config['MYSQL_DB']
    )

def refresh_face_cache():
    """Loads all missing person encodings into memory from person_photos table."""
    global KNOWN_FACES_CACHE
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)


        cursor.execute("SELECT id, full_name FROM missing_persons WHERE status IN ('Missing', 'Found')")
        persons = cursor.fetchall()

        cache = {}
        for p in persons:
            pid = p['id']

            cursor.execute("SELECT face_encoding FROM person_photos WHERE missing_person_id = %s", (pid,))
            photos = cursor.fetchall()

            encodings = [photo['face_encoding'] for photo in photos if photo['face_encoding']]

            if encodings:
                cache[pid] = {
                    'encodings': encodings,
                    'name': p['full_name']
                }

        KNOWN_FACES_CACHE = cache
        cursor.close()
        conn.close()
        print(f"Loaded faces for {len(KNOWN_FACES_CACHE)} people into cache.")
    except Exception as e:
        print(f"Error loading cache: {e}")


refresh_face_cache()

@app.route('/')
@login_required
def index():
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM missing_persons WHERE status='Missing' ORDER BY created_at DESC LIMIT 6")
        recent_cases = cursor.fetchall()
        cursor.close()
        conn.close()
    except Exception as e:
        recent_cases = []

    return render_template('index.html', recent_cases=recent_cases)

def check_cross_match(new_encoding, target_status):
    """
    Checks if new_encoding matches any person in the DB with target_status.
    Returns a list of matched person dictionaries.
    """
    matches = []
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        # Get all persons with the target status
        cursor.execute("SELECT id, full_name, ticket_id, contact_phone FROM missing_persons WHERE status=%s", (target_status,))
        candidates = cursor.fetchall()
        
        for cand in candidates:
            cursor.execute("SELECT face_encoding FROM person_photos WHERE missing_person_id=%s", (cand['id'],))
            photos = cursor.fetchall()
            for photo in photos:
                if photo['face_encoding']:
                    known_enc = pickle.loads(photo['face_encoding'])
                    # Euclidean distance
                    dist = np.linalg.norm(new_encoding - known_enc)
                    if dist < 0.55: # Threshold for cross-match
                        matches.append(cand)
                        break
        cursor.close()
        conn.close()
    except Exception as e:
        print(f"Cross-match error: {e}")
    return matches

@app.route('/report', methods=['GET', 'POST'])
@login_required
def report():
    if request.method == 'POST':
        full_name = request.form['full_name']
        age = request.form['age']
        gender = request.form['gender']
        last_seen_date = request.form['last_seen_date']
        last_seen_location = request.form['last_seen_location']
        description = request.form['description']
        contact_phone = request.form['contact_phone']


        files = request.files.getlist('photos')


        valid_photos = [f for f in files if f.filename != '']
        if not valid_photos:
            flash('No photos uploaded')
            return redirect(request.url)

        try:

            date_str = datetime.now().strftime("%Y%m%d")
            random_str = ''.join(random.choices(string.ascii_uppercase + string.digits, k=4))
            ticket_id = f"MP-{date_str}-{random_str}"

            conn = get_db_connection()
            cursor = conn.cursor()


            latitude = request.form.get('latitude')
            longitude = request.form.get('longitude')


            if not latitude: latitude = None
            if not longitude: longitude = None


            first_file = valid_photos[0]
            first_filename = secure_filename(first_file.filename)
            first_filepath = os.path.join(app.config['UPLOAD_FOLDER'], first_filename)
            first_file.save(first_filepath)


            first_encoding = get_face_encoding(first_filepath)
            first_encoding_blob = pickle.dumps(first_encoding) if first_encoding is not None else None




            if first_encoding is None:
                flash(f'Warning: No face detected in the primary photo {first_filename}.')

            sql = """INSERT INTO missing_persons 
                     (ticket_id, full_name, age, gender, last_seen_date, last_seen_location, description, contact_phone, photo_path, face_encoding, latitude, longitude) 
                     VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"""
            val = (ticket_id, full_name, age, gender, last_seen_date, last_seen_location, description, contact_phone, first_filename, first_encoding_blob, latitude, longitude)
            cursor.execute(sql, val)
            person_id = cursor.lastrowid


            if first_encoding is not None:
                cursor.execute("INSERT INTO person_photos (missing_person_id, photo_path, face_encoding) VALUES (%s, %s, %s)",
                               (person_id, first_filename, first_encoding_blob))


            for i, file in enumerate(valid_photos):
                if i == 0: continue

                filename = secure_filename(file.filename)


                base, ext = os.path.splitext(filename)
                filename = f"{base}_{int(time.time())}_{i}{ext}"

                filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                file.save(filepath)

                encoding = get_face_encoding(filepath)
                if encoding is not None:
                    encoding_blob = pickle.dumps(encoding)
                    cursor.execute("INSERT INTO person_photos (missing_person_id, photo_path, face_encoding) VALUES (%s, %s, %s)",
                                   (person_id, filename, encoding_blob))
                else:
                     print(f"Skipping photo {filename} - no face detected.")

            conn.commit()
            cursor.close()
            conn.close()

            refresh_face_cache()
            
            # Cross-match against 'Found' bodies
            if first_encoding is not None:
                matches = check_cross_match(first_encoding, 'Found')
                if matches:
                    match_names = ", ".join([m['full_name'] or 'Unknown' for m in matches])
                    flash(f"ALERT: Potential match found with reported anonymous persons: {match_names}. Please check 'Found' reports.")
                    # Log match
                    conn = get_db_connection()
                    cursor = conn.cursor()
                    for m in matches:
                         cursor.execute("INSERT INTO case_updates (missing_person_id, update_type, details, source, location) VALUES (%s, %s, %s, %s, %s)",
                                       (person_id, 'Cross-Match', f"Matched with Anonymous Person ID {m['id']}", 'System', 'Database'))
                    conn.commit()
                    cursor.close()
                    conn.close()

            flash(f'Report submitted successfully! Your Ticket ID is: {ticket_id}. Please save this ID to track the case status.')
            return redirect(url_for('index'))
        except Exception as e:
            flash(f"Database error: {e}")
            return redirect(request.url)

    return render_template('report.html')

@app.route('/report_suspicious', methods=['GET', 'POST'])
@login_required
def report_suspicious():
    if request.method == 'POST':
        full_name = request.form.get('full_name') or 'Unknown'
        age = request.form.get('approx_age')
        gender = request.form['gender']
        found_date = request.form['found_date']
        found_location = request.form['found_location']
        description = request.form['description']
        
        files = request.files.getlist('photos')
        valid_photos = [f for f in files if f.filename != '']
        if not valid_photos:
            flash('No photos uploaded. Photo is mandatory for anonymous person reporting.')
            return redirect(request.url)

        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            
            latitude = request.form.get('latitude') or None
            longitude = request.form.get('longitude') or None

            # 1. Process Primary Photo
            first_file = valid_photos[0]
            first_filename = secure_filename(first_file.filename)
            first_filepath = os.path.join(app.config['UPLOAD_FOLDER'], 'suspicious_' + first_filename)
            first_file.save(first_filepath)

            first_encoding = get_face_encoding(first_filepath)
            first_encoding_blob = pickle.dumps(first_encoding) if first_encoding is not None else None

            if first_encoding is None:
                flash(f'Error: No face detected in the photo. Cannot process anonymous person report without a valid face.')
                return redirect(request.url)

            # 2. Insert into DB (Status = 'Found')
            ticket_id = f"FOUND-{int(time.time())}"
            
            sql = """INSERT INTO missing_persons 
                     (ticket_id, full_name, age, gender, last_seen_date, last_seen_location, description, photo_path, face_encoding, latitude, longitude, status) 
                     VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'Found')"""
            val = (ticket_id, full_name, age, gender, found_date, found_location, description, 'suspicious_' + first_filename, first_encoding_blob, latitude, longitude)
            cursor.execute(sql, val)
            person_id = cursor.lastrowid

            cursor.execute("INSERT INTO person_photos (missing_person_id, photo_path, face_encoding) VALUES (%s, %s, %s)",
                           (person_id, 'suspicious_' + first_filename, first_encoding_blob))

            conn.commit()
            cursor.close()
            conn.close()

            # 3. Cross-Match against 'Missing' people
            matches = check_cross_match(first_encoding, 'Missing')
            
            if matches:
                match_names = ", ".join([m['full_name'] for m in matches])
                flash(f"SUCCESS: Match found with Missing Persons: {match_names}! Authorities have been notified.")
                
                # Log update for the matched missing person
                conn = get_db_connection()
                cursor = conn.cursor()
                for m in matches:
                     cursor.execute("INSERT INTO case_updates (missing_person_id, update_type, details, source, location) VALUES (%s, %s, %s, %s, %s)",
                                   (m['id'], 'Found Person Match', f"Matched with Anonymous Person Ticket {ticket_id}", 'System', found_location))
                     
                     # Notify officer (simulated)
                     match_details = {
                        'name': m['full_name'],
                        'confidence': 'High (Physical Match)',
                        'location': found_location,
                        'time': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    }
                     notification_manager.send_email_alert('officer@example.com', match_details)
                
                conn.commit()
                cursor.close()
                cursor = conn.cursor()
                # Also log the update on the Anonymous Person's record
                for m in matches:
                    # Log to the current found person's record too?
                    # Since person_id is the new found person
                    cursor.execute("INSERT INTO case_updates (missing_person_id, update_type, details, source, location) VALUES (%s, %s, %s, %s, %s)",
                                   (person_id, 'Cross-Match', f"Matched with Missing Person: {m['full_name']}", 'System', found_location))
                conn.commit()
                cursor.close()

                conn.close()
            else:
                flash(f'Report submitted. No immediate positive matches with missing persons. Ticket ID: {ticket_id}')

            refresh_face_cache()
            return redirect(url_for('index'))

        except Exception as e:
            flash(f"Database error: {e}")
            print(f"Error: {e}")
            return redirect(request.url)

    return render_template('report_suspicious.html')

@app.route('/search', methods=['GET', 'POST'])
@login_required
def search():
    match_results = []
    if request.method == 'POST':
        if 'photo' not in request.files:
            flash('No photo uploaded')
            return redirect(request.url)
        file = request.files['photo']
        if file.filename == '':
            flash('No photo selected')
            return redirect(request.url)

        if file:
            filename = secure_filename(file.filename)
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], 'search_' + filename)
            file.save(filepath)



            img = cv2.imread(filepath)
            if img is None:
                flash('Error reading image.')
                return redirect(request.url)

            face_encodings_data = get_all_face_encodings(img)

            if not face_encodings_data:
                flash('No faces detected.')
                return redirect(request.url)





            encodings_map = {k: v['encodings'] for k, v in KNOWN_FACES_CACHE.items()}

            found_ids = set()

            for encoding, _ in face_encodings_data:
                match_id, distance = find_match(encoding, encodings_map, tolerance=1.2)

                if match_id and match_id not in found_ids:
                    found_ids.add(match_id)
                    conn = get_db_connection()
                    cursor = conn.cursor(dictionary=True)
                    cursor.execute("SELECT * FROM missing_persons WHERE id = %s", (match_id,))
                    person_data = cursor.fetchone()
                    if person_data:
                        person_data['match_confidence'] = "High" if distance < 0.4 else "Medium"
                        match_results.append(person_data)

                        # LOGGING (New)
                        try:
                            cursor.execute("INSERT INTO case_updates (missing_person_id, update_type, details, source, location) VALUES (%s, %s, %s, %s, %s)",
                                            (match_id, 'Photo Search', f"Match found in uploaded photo: {filename}", 'Photo Search', 'File Upload'))
                            
                            # Optional: Log to detection_logs if you want it on the map too
                            cursor.execute("INSERT INTO detection_logs (person_id, camera_source, location, latitude, longitude) VALUES (%s, %s, %s, %s, %s)",
                                            (match_id, "Photo Upload", "Photo Search Upload", None, None))
                            
                            conn.commit()
                            print(f"Logged photo search match for ID {match_id}")

                            # Notification
                            match_details = {
                                'name': person_data['full_name'],
                                'confidence': "High (Photo)",
                                'location': 'Photo File Upload',
                                'time': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                            }
                            notification_manager.send_email_alert('officer@example.com', match_details)

                        except Exception as e:
                            print(f"Error logging photo search: {e}")

                    cursor.close()
                    conn.close()

            if not match_results:
                flash('No matches found.')
                show_report_option = True
            else:
                show_report_option = False

    return render_template('search.html', match_results=match_results, show_report_option=locals().get('show_report_option', False))

@app.route('/video_search', methods=['GET', 'POST'])
@login_required
def video_search():
    match_found = False
    # Use session to keep track of detections across multiple search steps
    if 'match_details_list' not in session:
        session['match_details_list'] = []
    
    match_details_list = session['match_details_list']

    if request.method == 'POST':
        if 'video' not in request.files:
            flash('No video uploaded')
            return redirect(request.url)
        
        videos = request.files.getlist('video')
        locations = request.form.getlist('location')
        start_times = request.form.getlist('start_time')
        
        if not videos or all(v.filename == '' for v in videos):
            flash('No video selected')
            return redirect(request.url)

        encodings_map = {k: v['encodings'] for k, v in KNOWN_FACES_CACHE.items()}
        # Tracking IDs per SESSION to avoid literal duplicates (same person, same context)
        # But we want to allow same person in DIFFERENT videos

        for file, user_location, start_time in zip(videos, locations, start_times):
            if file.filename == '':
                continue
            
            filename = secure_filename(file.filename)
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(filepath)

            # Use the provided location or fallback
            location_name = user_location if user_location.strip() else f"Video Source ({filename})"

            cap = cv2.VideoCapture(filepath)
            fps = cap.get(cv2.CAP_PROP_FPS)
            if fps == 0: fps = 30 # Fallback
            
            frame_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            frame_count = 0

            while cap.isOpened():
                ret, frame = cap.read()
                if not ret:
                    break

                frame_count += 1
                if frame_count % 30 != 0:
                    continue

                # Calculate Timestamp (Offset)
                total_seconds = frame_count / fps
                minutes = int(total_seconds // 60)
                seconds = int(total_seconds % 60)
                timestamp_str = f"{minutes:02d}:{seconds:02d}"

                # Calculate Actual Real-World Time
                try:
                    h, m = map(int, start_time.split(':'))
                    start_dt = datetime.combine(datetime.today(), time(h, m))
                    actual_dt = start_dt + timedelta(seconds=total_seconds)
                    actual_time_str = actual_dt.strftime("%H:%M:%S")
                except Exception as e:
                    print(f"Error calculating real time: {e}")
                    actual_time_str = timestamp_str

                face_results = get_all_face_encodings(frame)

                for encoding, rect in face_results:
                    match_id, _ = find_match(encoding, encodings_map, tolerance=1.2)

                    if match_id:
                        # Check if this specific sighting (Person + Video + Time) is already logged
                        def parse_time(t):
                            try:
                                h, m, s = map(int, t.split(':'))
                                return h * 3600 + m * 60 + s
                            except: return 0

                        is_duplicate = any(
                            m['id'] == match_id and 
                            m['video_source'] == filename and 
                            abs(parse_time(m['found_at']) - parse_time(actual_time_str)) < 5
                            for m in match_details_list
                        )
                        
                        if is_duplicate:
                            continue
                        match_found = True

                        match_found = True

                        # Calculate Side
                        (x, y, w, h) = rect
                        center_x = x + w / 2
                        if center_x < frame_width / 3:
                            side = "Left"
                        elif center_x < 2 * frame_width / 3:
                            side = "Center"
                        else:
                            side = "Right"

                        conn = get_db_connection()
                        cursor = conn.cursor(dictionary=True)
                        cursor.execute("SELECT * FROM missing_persons WHERE id = %s", (match_id,))
                        person_data = cursor.fetchone()
                        
                        if person_data:
                            person_data['side'] = side
                            person_data['video_source'] = filename
                            person_data['found_at'] = actual_time_str
                            person_data['last_seen_location'] = location_name 
                            
                            # Final check for duplicates in the session list
                            is_dup = False
                            for m in match_details_list:
                                if m['id'] == match_id and m['video_source'] == filename and m['found_at'] == actual_time_str:
                                    is_dup = True
                                    break
                            
                            if not is_dup:
                                match_details_list.append(person_data)
                                session['match_details_list'] = match_details_list
                                session.modified = True
                                match_found = True

                            try:
                                cursor.execute("INSERT INTO case_updates (missing_person_id, update_type, details, source, location) VALUES (%s, %s, %s, %s, %s)",
                                               (match_id, 'Video Search', f"Match found at {actual_time_str} ({side} side) in {location_name}. Video: {filename}", 'Video Search', location_name))
                                
                                cursor.execute("INSERT INTO detection_logs (person_id, camera_source, location, latitude, longitude) VALUES (%s, %s, %s, %s, %s)",
                                               (match_id, f"Video: {filename}", f"Detected at {actual_time_str} ({side} side) at {location_name}", None, None))
                                
                                conn.commit()
                            except Exception as e:
                                print(f"Error logging video search update: {e}")

                            match_details = {
                                'name': person_data['full_name'],
                                'confidence': 'High (Video)',
                                'location': f"{location_name} (Detected at {actual_time_str})",
                                'side': side,
                                'time': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                            }

                            notification_manager.send_email_alert('officer@example.com', match_details)

                        cursor.close()
                        conn.close()

            cap.release()

        if not match_found:
            flash('No match found in the uploaded video(s).')

    return render_template('video_search.html', match_found=match_found, match_details_list=match_details_list)

@app.route('/clear_investigation')
@login_required
def clear_investigation():
    session.pop('match_details_list', None)
    flash('Investigation history cleared.')
    return redirect(url_for('video_search'))

def timeToSeconds(timeStr):
    try:
        parts = timeStr.split(':').reverse()
        seconds = 0
        if parts[0]: seconds += int(parts[0])
        if parts[1]: seconds += int(parts[1]) * 60
        if parts[2]: seconds += int(parts[2]) * 3600
        return seconds
    except:
        return 0

@app.route('/virtual_camera/<location>')
@login_required
def virtual_camera(location):
    return render_template('virtual_camera.html', location=location)

@app.route('/process_frame', methods=['POST'])
@login_required
def process_frame():
    try:
        data = request.json
        if 'image' not in data:
            return jsonify({'error': 'No image data'}), 400

        latitude = data.get('latitude')
        longitude = data.get('longitude')
        location_name = get_location_name(latitude, longitude) if latitude and longitude else "Local Camera (No GPS)"


        image_data = data['image'].split(',')[1]
        image_bytes = base64.b64decode(image_data)
        nparr = np.frombuffer(image_bytes, np.uint8)
        frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

        if frame is None:
            print("Error: Frame is None after decoding")
            return jsonify({'error': 'Invalid image'}), 400


        print(f"Frame received. Shape: {frame.shape}")
        encodings_map = {k: v['encodings'] for k, v in KNOWN_FACES_CACHE.items()}
        face_results = get_all_face_encodings(frame)
        print(f"Faces detected: {len(face_results)}")

        results = []
        for encoding, rect in face_results:
            match_id, distance = find_match(encoding, encodings_map, tolerance=1.25)
            (x, y, w, h) = rect

            name = "Not Found"
            color = "red"

            if match_id:
                name = f"Found: {KNOWN_FACES_CACHE[match_id]['name']} ({distance:.2f})"
                color = "green"
                print(f"Match found: {name}")


                current_time = time.time()
                if match_id not in LAST_CASE_UPDATE or (current_time - LAST_CASE_UPDATE[match_id] > CASE_UPDATE_COOLDOWN):
                    try:
                        conn = get_db_connection()
                        cursor = conn.cursor()
                        cursor.execute("INSERT INTO case_updates (missing_person_id, update_type, details, source, location) VALUES (%s, %s, %s, %s, %s)",
                                       (match_id, 'Live Search', f"Match found at {location_name}", 'Local Camera', location_name))
                        conn.commit()
                        cursor.close()
                        conn.close()
                        LAST_CASE_UPDATE[match_id] = current_time
                        print(f"Logged live search update for ID {match_id}")
                    except Exception as e:
                        print(f"Error logging live search update: {e}")


                if match_id not in LAST_LOGGED or (current_time - LAST_LOGGED[match_id] > 300):
                     match_details = {
                        'name': KNOWN_FACES_CACHE[match_id]['name'],
                        'confidence': f"{distance:.2f}",
                        'location': location_name,
                        'time': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    }
                     notification_manager.send_email_alert('officer@example.com', match_details)



                current_ts = time.time()
                if match_id not in LAST_LOGGED or (current_ts - LAST_LOGGED[match_id] > LOG_COOLDOWN):
                    try:
                        conn = get_db_connection()
                        cursor = conn.cursor()
                        cursor.execute("INSERT INTO detection_logs (person_id, camera_source, location, latitude, longitude) VALUES (%s, %s, %s, %s, %s)",
                                       (match_id, "Local Camera", location_name, latitude, longitude))
                        conn.commit()
                        cursor.close()
                        conn.close()
                        LAST_LOGGED[match_id] = current_ts
                        print(f"Logged detection to DB for ID {match_id}")
                    except Exception as e:
                        print(f"Error logging to DB: {e}")
            else:
                print(f"No match found. Distance: {distance}")

            results.append({
                'rect': [int(x), int(y), int(w), int(h)],
                'name': name,
                'color': color
            })

        return jsonify({'results': results})

    except Exception as e:
        print(f"Error processing frame: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/live_search')
@login_required
def live_search():
    if current_user.role != 'officer':
        flash('Access denied. This feature is restricted to officers only.')
        return redirect(url_for('index'))
    return render_template('live_search.html')

def create_error_frame(message="Camera Error"):
    """Generates a black frame with error text."""
    img = np.zeros((480, 640, 3), dtype=np.uint8)

    font = cv2.FONT_HERSHEY_SIMPLEX
    text_size = cv2.getTextSize(message, font, 1, 2)[0]
    text_x = (img.shape[1] - text_size[0]) // 2
    text_y = (img.shape[0] + text_size[1]) // 2
    cv2.putText(img, message, (text_x, text_y), font, 1, (0, 0, 255), 2)


    ret, buffer = cv2.imencode('.jpg', img)
    return buffer.tobytes()

def gen_frames(source=0, latitude=None, longitude=None):
    print(f"Attempting to open camera source: {source}")

    if isinstance(source, str) and source.isdigit():
        source = int(source)

    camera = cv2.VideoCapture(source)
    if not camera.isOpened():

        if isinstance(source, str) and source.startswith('http') and not source.endswith('/video'):
            print(f"Connection failed. Retrying with /video appended: {source}/video")
            new_source = source.rstrip('/') + "/video"
            camera = cv2.VideoCapture(new_source)
            if camera.isOpened():
                print(f"Successfully opened video source: {new_source}")
                source = new_source

    if not camera.isOpened():
        print(f"Error: Could not open video source {source}")

        while True:
             frame = create_error_frame(f"Connection Failed")
             yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')
             time.sleep(1)
        return

    print(f"Successfully opened video source {source}")
    encodings_map = {k: v['encodings'] for k, v in KNOWN_FACES_CACHE.items()}

    from utils.ai_engine import get_all_face_encodings


    frame_queue = queue.Queue(maxsize=1)
    result_queue = queue.Queue(maxsize=1)
    stop_event = threading.Event()


    last_update_time = {}
    UPDATE_COOLDOWN = 300

    def processing_thread():
        print("Processing thread started")
        while not stop_event.is_set():
            try:

                frame = frame_queue.get(timeout=1)


                height, width = frame.shape[:2]
                target_width = 480
                scale_factor = target_width / float(width)


                if scale_factor < 1.0:
                    small_frame = cv2.resize(frame, (0, 0), fx=scale_factor, fy=scale_factor)
                else:
                    small_frame = frame
                    scale_factor = 1.0


                face_results = get_all_face_encodings(small_frame)

                results = []
                for encoding, rect in face_results:
                    match_id, distance = find_match(encoding, encodings_map, tolerance=1.25)
                    (x, y, w, h) = rect


                    x = int(x / scale_factor)
                    y = int(y / scale_factor)
                    w = int(w / scale_factor)
                    h = int(h / scale_factor)

                    location_name = "Unknown Location"
                    if latitude and longitude:
                        location_name = get_location_name(latitude, longitude)
                    elif source != 0:
                         location_name = f"CCTV/IP Camera ({source})"

                    if match_id:
                        color = (0, 255, 0)
                        name = f"Found: {KNOWN_FACES_CACHE[match_id]['name']} ({distance:.2f})"
                        print(f"Match found in CCTV: {name}")


                        current_time = datetime.now().timestamp()
                        if match_id not in last_update_time or (current_time - last_update_time[match_id] > UPDATE_COOLDOWN):
                            try:
                                conn = get_db_connection()
                                cursor = conn.cursor()
                                source_val = f"CCTV/IP Camera ({source})"
                                cursor.execute("INSERT INTO case_updates (missing_person_id, update_type, details, source, location) VALUES (%s, %s, %s, %s, %s)",
                                               (match_id, 'Live Search', f"Match found at {location_name}", source_val, location_name))
                                conn.commit()
                                cursor.close()
                                conn.close()
                                last_update_time[match_id] = current_time
                                print(f"Logged live search update for ID {match_id}")
                            except Exception as e:
                                print(f"Error logging live search update: {e}")


                        global LATEST_MATCH
                        LATEST_MATCH = {
                            'id': match_id,
                            'name': KNOWN_FACES_CACHE[match_id]['name'],
                            'timestamp': datetime.now().timestamp()
                        }


                        current_ts = time.time()
                        print(f"Checking DB log for {match_id}. Last logged: {LAST_LOGGED.get(match_id, 'Never')}, Cooldown: {LOG_COOLDOWN}")

                        if match_id not in LAST_LOGGED or (current_ts - LAST_LOGGED[match_id] > LOG_COOLDOWN):
                            print(f"Attempting to insert into detection_logs for {match_id}")
                            try:
                                conn = get_db_connection()
                                cursor = conn.cursor()

                                source_name = "Local Camera" if source == 0 else f"CCTV {source}"
                                cursor.execute("INSERT INTO detection_logs (person_id, camera_source, location, latitude, longitude) VALUES (%s, %s, %s, %s, %s)",
                                               (match_id, source_name, location_name, latitude, longitude))
                                conn.commit()
                                cursor.close()
                                conn.close()
                                LAST_LOGGED[match_id] = current_ts
                                print(f"Logged detection to DB for ID {match_id}")
                            except Exception as e:
                                print(f"Error logging to DB: {e}")
                        else:
                            print(f"Skipping DB log for {match_id} due to cooldown.")

                    else:
                        color = (0, 0, 255)
                        dist_str = f"{distance:.2f}" if distance is not None else "N/A"
                        name = f"Not Found ({dist_str})"
                        print(f"No match found. Best distance: {dist_str}")

                    results.append(((x, y, w, h), color, name))


                if not result_queue.empty():
                    try:
                        result_queue.get_nowait()
                    except queue.Empty:
                        pass
                result_queue.put(results)

            except queue.Empty:
                continue
            except Exception as e:
                print(f"Error in processing thread: {e}")
                continue
        print("Processing thread stopped")


    t = threading.Thread(target=processing_thread, daemon=True)
    t.start()

    last_results = []

    try:
        while True:
            success, frame = camera.read()
            if not success:
                print("Failed to read frame from camera")


                if isinstance(source, str) and source.startswith('http'):
                    print("Attempting Snapshot Fallback...")

                    if '/video' in source:
                        snapshot_url = source.replace('/video', '/shot.jpg')
                    else:
                        snapshot_url = source.rstrip('/') + '/shot.jpg'

                    print(f"Snapshot URL: {snapshot_url}")

                    while True:
                        try:

                            resp = requests.get(snapshot_url, timeout=2)
                            if resp.status_code == 200:
                                nparr = np.frombuffer(resp.content, np.uint8)
                                frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
                                if frame is not None:
                                    frame = cv2.resize(frame, (640, 480))
                                    ret, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 70])

                                    yield (b'--frame\r\n'
                                           b'Content-Type: image/jpeg\r\n\r\n' + buffer.tobytes() + b'\r\n')

                                    time.sleep(0.1)
                                    continue

                        except Exception as e:
                            print(f"Snapshot fallback failed: {e}")


                        frame = create_error_frame("Connection Lost")
                        yield (b'--frame\r\n'
                               b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')
                        time.sleep(1)


                else:
                    while True:
                         frame = create_error_frame("Signal Lost")
                         yield (b'--frame\r\n'
                               b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')
                         time.sleep(1)
                break
            else:

                if frame_queue.empty():
                    frame_queue.put(frame)


                if not result_queue.empty():
                    try:
                        last_results = result_queue.get_nowait()
                    except queue.Empty:
                        pass


                for (rect, color, name) in last_results:
                    (x, y, w, h) = rect
                    cv2.rectangle(frame, (x, y), (x+w, y+h), color, 2)
                    cv2.putText(frame, name, (x, y-10), cv2.FONT_HERSHEY_SIMPLEX, 0.9, color, 2)


                frame = cv2.resize(frame, (640, 480))


                ret, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 70])
                frame = buffer.tobytes()
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')


                time.sleep(0.05)
    finally:
        stop_event.set()
        camera.release()
        print("Camera released")

@app.route('/video_feed')
def video_feed():
    source = request.args.get('source', 0)
    latitude = request.args.get('latitude')
    longitude = request.args.get('longitude')
    return Response(gen_frames(source, latitude, longitude), mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/check_alerts')
def check_alerts():
    """Returns the latest match if it happened recently (within last 3 seconds)."""
    global LATEST_MATCH
    now = datetime.now().timestamp()
    if LATEST_MATCH['timestamp'] > 0 and (now - LATEST_MATCH['timestamp'] < 3):
        return jsonify({'alert': True, 'name': LATEST_MATCH['name']})
    return jsonify({'alert': False})

@app.route('/analytics')
@login_required
def analytics():
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)


        cursor.execute("SELECT status, COUNT(*) as count FROM missing_persons GROUP BY status")
        status_data = cursor.fetchall()


        cursor.execute("SELECT gender, COUNT(*) as count FROM missing_persons WHERE status='Missing' GROUP BY gender")
        gender_data = cursor.fetchall()



        cursor.execute("SELECT age FROM missing_persons WHERE status='Missing'")
        ages = cursor.fetchall()
        age_groups = {'0-18': 0, '19-35': 0, '36-50': 0, '51+': 0}
        for p in ages:
            try:
                age = int(p['age'])
                if age <= 18: age_groups['0-18'] += 1
                elif age <= 35: age_groups['19-35'] += 1
                elif age <= 50: age_groups['36-50'] += 1
                else: age_groups['51+'] += 1
            except:
                pass



        cursor.execute("""
            SELECT DATE_FORMAT(created_at, '%Y-%m') as month, COUNT(*) as count 
            FROM missing_persons 
            GROUP BY month 
            ORDER BY month DESC 
            LIMIT 6
        """)
        timeline_data = cursor.fetchall()

        timeline_data.reverse()

        cursor.close()
        conn.close()

        return render_template('analytics.html',
                               status_data=status_data,
                               gender_data=gender_data,
                               age_groups=age_groups,
                               timeline_data=timeline_data)
    except Exception as e:
        print(f"Analytics error: {e}")
        flash("Error loading analytics data")
        return redirect(url_for('index'))

@app.route('/map_dashboard')
def map_dashboard():
    return render_template('map_dashboard.html')

@app.route('/api/map_data')
def api_map_data():
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)


        cursor.execute("SELECT id, full_name, status, latitude, longitude, photo_path, description FROM missing_persons WHERE latitude IS NOT NULL AND longitude IS NOT NULL")
        persons = cursor.fetchall()


        cursor.execute("""
            SELECT dl.person_id, dl.latitude, dl.longitude, dl.timestamp, mp.full_name, mp.photo_path 
            FROM detection_logs dl
            JOIN missing_persons mp ON dl.person_id = mp.id
            WHERE dl.latitude IS NOT NULL AND dl.longitude IS NOT NULL
            ORDER BY dl.timestamp DESC LIMIT 50
        """)
        detections = cursor.fetchall()

        cursor.close()
        conn.close()

        return jsonify({'persons': persons, 'detections': detections})
    except Exception as e:
        print(f"Error fetching map data: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/history')
@login_required
def history():
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        query = """
            SELECT dl.*, mp.full_name, mp.photo_path, mp.status 
            FROM detection_logs dl
            JOIN missing_persons mp ON dl.person_id = mp.id
            ORDER BY dl.timestamp DESC
        """
        cursor.execute(query)
        logs = cursor.fetchall()
        cursor.close()
        conn.close()
        return render_template('history.html', logs=logs)
    except Exception as e:
        print(f"Error fetching history: {e}")
        flash("Error fetching history logs", "error")
        return redirect(url_for('index'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))

    if request.method == 'POST':
        email = request.form['email'].strip().lower()
        password = request.form['password']


        if not email.endswith('@gmail.com'):
            flash('Only Gmail addresses (@gmail.com) are allowed for login.')
            return render_template('login.html')

        try:
            conn = get_db_connection()
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT * FROM users WHERE email = %s", (email,))
            user_data = cursor.fetchone()
            cursor.close()
            conn.close()

            if user_data and check_password_hash(user_data['password_hash'], password):
                user = User(user_data['id'], user_data['full_name'], user_data['email'], user_data['password_hash'], user_data.get('role', 'user'))
                login_user(user, remember=request.form.get('remember-me'))
                next_page = request.args.get('next')
                return redirect(next_page or url_for('index'))
            else:
                flash('Invalid email or password')
        except Exception as e:
            flash(f"Login error: {e}")

    return render_template('login.html')

@app.route('/forgot_password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        email = request.form['email'].strip().lower()
        try:
            conn = get_db_connection()
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT * FROM users WHERE email = %s", (email,))
            user = cursor.fetchone()
            cursor.close()
            conn.close()

            if user:
                token = serializer.dumps(email, salt='password-reset-salt')
                reset_url = url_for('reset_password', token=token, _external=True)
                notification_manager.send_password_reset_email(email, reset_url)
                # For development/debugging since email might not be configured
                print(f"DEBUG: Password reset token for {email}: {token}")
                
                # Direct redirect as requested by user
                flash('Directly redirecting to reset password page.', 'success')
                return redirect(url_for('reset_password', token=token))
                
            flash('If an account exists with that email, a password reset link has been sent.', 'info')
            return redirect(url_for('login'))
            
        except Exception as e:
            flash(f"Error processing request: {e}", 'error')
            return redirect(url_for('forgot_password'))

    return render_template('forgot_password.html')

@app.route('/reset_password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    try:
        email = serializer.loads(token, salt='password-reset-salt', max_age=3600)
    except Exception as e:
        flash('The password reset link is invalid or has expired.', 'error')
        return redirect(url_for('login'))

    if request.method == 'POST':
        password = request.form['password']
        confirm_password = request.form['confirm_password']

        if password != confirm_password:
            flash('Passwords do not match.', 'error')
            return redirect(url_for('reset_password', token=token))

        try:
            hashed_password = generate_password_hash(password)
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute("UPDATE users SET password_hash = %s WHERE email = %s", (hashed_password, email))
            conn.commit()
            cursor.close()
            conn.close()

            flash('Your password has been updated! You can now log in.', 'success')
            return redirect(url_for('login'))
        except Exception as e:
            flash(f"Error updating password: {e}", 'error')
            return redirect(url_for('reset_password', token=token))

    return render_template('reset_password.html', token=token)

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if current_user.is_authenticated:
        return redirect(url_for('index'))

    if request.method == 'POST':
        full_name = request.form['full_name']
        email = request.form['email'].strip().lower()
        password = request.form['password']
        confirm_password = request.form['confirm_password']
        role = request.form.get('role', 'user')


        if not email.endswith('@gmail.com'):
            flash('Only Gmail addresses (@gmail.com) are allowed for signup.')
            return redirect(request.url)

        if password != confirm_password:
            flash('Passwords do not match')
            return redirect(request.url)

        if role == 'officer':
            secret_code = request.form.get('secret_code')
            if secret_code != app.config['OFFICER_SECRET_CODE']:
                flash('Invalid Officer Access Code')
                return redirect(request.url)

        try:
            conn = get_db_connection()
            cursor = conn.cursor(dictionary=True)


            cursor.execute("SELECT id FROM users WHERE email = %s", (email,))
            if cursor.fetchone():
                flash('Email already exists')
                cursor.close()
                conn.close()
                return redirect(request.url)

            hashed_password = generate_password_hash(password)
            cursor.execute("INSERT INTO users (full_name, email, password_hash, role) VALUES (%s, %s, %s, %s)",
                           (full_name, email, hashed_password, role))
            conn.commit()
            cursor.close()
            conn.close()

            flash('Account created successfully! Please log in.')
            return redirect(url_for('login'))
        except Exception as e:
            flash(f"Signup error: {e}")
            return redirect(request.url)

    return render_template('signup.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('index'))

@app.route('/track', methods=['GET', 'POST'])
def track():
    if request.method == 'POST':
        ticket_id = request.form['ticket_id']
        return redirect(url_for('case_status', ticket_id=ticket_id))
    return render_template('track.html')

@app.route('/case_status/<ticket_id>')
def case_status(ticket_id):
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM missing_persons WHERE ticket_id = %s", (ticket_id,))
        case = cursor.fetchone()

        updates = []
        if case:
            cursor.execute("SELECT * FROM case_updates WHERE missing_person_id = %s ORDER BY created_at DESC", (case['id'],))
            updates = cursor.fetchall()

        cursor.close()
        conn.close()

        if case:
            return render_template('case_status.html', case=case, updates=updates)
        else:
            flash('Invalid Ticket ID. Case not found.')
            return redirect(url_for('track'))
    except Exception as e:
        flash(f"Error retrieving case: {e}")
        return redirect(url_for('track'))


@app.route('/download_report/<ticket_id>')
def download_report(ticket_id):
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM missing_persons WHERE ticket_id = %s", (ticket_id,))
        case = cursor.fetchone()

        updates = []
        if case:
            cursor.execute("SELECT * FROM case_updates WHERE missing_person_id = %s ORDER BY created_at DESC", (case['id'],))
            updates = cursor.fetchall()

        cursor.close()
        conn.close()

        if case:

            filename = generate_case_report(case, updates, app.config['UPLOAD_FOLDER'])
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)

            return send_file(filepath, as_attachment=True)
        else:
            flash('Invalid Ticket ID. Case not found.')
            return redirect(url_for('track'))
    except Exception as e:
        flash(f"Error generating report: {e}")
        return redirect(url_for('track'))

@app.route('/download_poster/<ticket_id>')
def download_poster(ticket_id):
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM missing_persons WHERE ticket_id = %s", (ticket_id,))
        case = cursor.fetchone()

        cursor.close()
        conn.close()

        if case:
            filename = generate_poster(case, app.config['UPLOAD_FOLDER'])
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            return send_file(filepath, as_attachment=True)
        else:
            flash('Invalid Ticket ID')
            return redirect(url_for('track'))
    except Exception as e:
        flash(f"Error generating poster: {e}")
        return redirect(url_for('track'))

@app.route('/edit_case/<int:case_id>', methods=['GET', 'POST'])
@login_required
def edit_case(case_id):
    if current_user.role != 'officer':
        flash('Access denied. Only officers can edit cases.')
        return redirect(url_for('index'))

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    if request.method == 'POST':
        full_name = request.form['full_name']
        age = request.form['age']
        gender = request.form['gender']
        last_seen_date = request.form['last_seen_date']
        last_seen_location = request.form['last_seen_location']
        description = request.form['description']
        contact_phone = request.form['contact_phone']
        status = request.form['status']

        try:
            sql = """UPDATE missing_persons 
                     SET full_name=%s, age=%s, gender=%s, last_seen_date=%s, last_seen_location=%s, description=%s, contact_phone=%s, status=%s 
                     WHERE id=%s"""
            val = (full_name, age, gender, last_seen_date, last_seen_location, description, contact_phone, status, case_id)
            cursor.execute(sql, val)
            conn.commit()


            cursor.execute("SELECT ticket_id FROM missing_persons WHERE id = %s", (case_id,))
            case = cursor.fetchone()

            refresh_face_cache()

            flash('Case details updated successfully.')
            return redirect(url_for('case_status', ticket_id=case['ticket_id']))
        except Exception as e:
            flash(f"Error updating case: {e}")
            return redirect(request.url)
        finally:
            cursor.close()
            conn.close()


    cursor.execute("SELECT * FROM missing_persons WHERE id = %s", (case_id,))
    case = cursor.fetchone()
    cursor.close()
    conn.close()

    if case:
        return render_template('edit_case.html', case=case)
    else:
        flash('Case not found.')
        return redirect(url_for('index'))

@app.route('/delete_case/<int:case_id>', methods=['POST'])
@login_required
def delete_case(case_id):
    if current_user.role != 'officer':
        flash('Access denied. Only officers can delete cases.')
        return redirect(url_for('index'))

    try:
        conn = get_db_connection()
        cursor = conn.cursor()


        cursor.execute("DELETE FROM case_updates WHERE missing_person_id = %s", (case_id,))


        cursor.execute("DELETE FROM missing_persons WHERE id = %s", (case_id,))

        conn.commit()
        cursor.close()
        conn.close()

        refresh_face_cache()

        flash('Case deleted successfully.')
        return redirect(url_for('index'))
    except Exception as e:
        flash(f"Error deleting case: {e}")
        return redirect(url_for('index'))

@app.route('/mark_found/<int:case_id>', methods=['POST'])
@login_required
def mark_found(case_id):
    if current_user.role != 'officer':
        flash('Access denied. Only officers can update case status.')
        return redirect(url_for('index'))

    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True) # Use dictionary cursor for select
        
        # Get ticket_id for redirect
        cursor.execute("SELECT ticket_id FROM missing_persons WHERE id = %s", (case_id,))
        case = cursor.fetchone()
        
        if not case:
             flash('Case not found.')
             return redirect(url_for('index'))

        # Update status
        cursor.execute("UPDATE missing_persons SET status = 'Found' WHERE id = %s", (case_id,))
        
        # Log update
        cursor.execute("INSERT INTO case_updates (missing_person_id, update_type, details, source, location) VALUES (%s, %s, %s, %s, %s)",
                       (case_id, 'Status Update', 'Case marked as FOUND by officer.', 'Officer Action', 'N/A'))
        
        conn.commit()
        cursor.close()
        conn.close()

        refresh_face_cache() # Remove from search cache if found? Or keep it? Usually remove or mark.
        # Logic for refresh_face_cache might need check to exclude 'Found' people if we want effectively "Closed".
        # For now, just status update is fine.

        flash('Case marked as Found.')
        return redirect(url_for('case_status', ticket_id=case['ticket_id']))
    except Exception as e:
        flash(f"Error marking case as found: {e}")
        return redirect(url_for('index'))

@app.route('/case/<int:person_id>')
def case_detail(person_id):
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM missing_persons WHERE id = %s", (person_id,))
        person = cursor.fetchone()
        cursor.close()
        conn.close()

        if not person:
            flash('Case not found.')
            return redirect(url_for('index'))

        return render_template('case_detail.html', person=person)
    except Exception as e:
        print(f"Error fetching case detail: {e}")
        flash('Error fetching case details.')
        return redirect(url_for('index'))

@app.route('/submit_tip/<int:person_id>', methods=['POST'])
def submit_tip(person_id):
    try:
        tip_details = request.form['tip_details']
        location = request.form.get('location', '')
        contact_info = request.form.get('contact_info', '')
        ip_address = request.remote_addr

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO case_tips (missing_person_id, tip_details, location, contact_info, ip_address)
            VALUES (%s, %s, %s, %s, %s)
        """, (person_id, tip_details, location, contact_info, ip_address))
        conn.commit()


        cursor.execute("INSERT INTO case_updates (missing_person_id, update_type, details, source, location) VALUES (%s, %s, %s, %s, %s)",
                       (person_id, 'Community Tip', f"New tip received: {tip_details[:50]}...", 'Community Tip', location))
        conn.commit()

        cursor.close()
        conn.close()


        print(f"NEW TIP received for Person ID {person_id}: {tip_details}")

        flash('Thank you! Your tip has been submitted securely.')
        return redirect(url_for('case_detail', person_id=person_id))

    except Exception as e:
        print(f"Error submitting tip: {e}")
        flash('Error submitting tip. Please try again.')
        return redirect(url_for('case_detail', person_id=person_id))







from functools import wraps

def volunteer_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'volunteer_id' not in session:
            flash('Please log in as a volunteer to access this page.', 'warning')
            return redirect(url_for('volunteer_login'))
        return f(*args, **kwargs)
    return decorated_function

@app.route('/volunteer/signup', methods=['GET', 'POST'])
def volunteer_signup():
    if request.method == 'POST':
        full_name = request.form['full_name']
        email = request.form['email']
        password = request.form['password']
        phone = request.form.get('phone')
        location = request.form.get('location')


        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM volunteers WHERE email = %s", (email,))
        if cursor.fetchone():
            flash('Email already registered.')
            return redirect(url_for('volunteer_signup'))

        hashed_pw = generate_password_hash(password)
        cursor.execute("INSERT INTO volunteers (full_name, email, password_hash, phone, location) VALUES (%s, %s, %s, %s, %s)",
                       (full_name, email, hashed_pw, phone, location))
        conn.commit()
        cursor.close()
        conn.close()

        flash('Registration successful! Please login.')
        return redirect(url_for('volunteer_login'))

    return render_template('volunteer_signup.html')

@app.route('/volunteer/login', methods=['GET', 'POST'])
def volunteer_login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']

        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM volunteers WHERE email = %s", (email,))
        volunteer = cursor.fetchone()
        cursor.close()
        conn.close()

        if volunteer and check_password_hash(volunteer['password_hash'], password):
            session['volunteer_id'] = volunteer['id']
            session['volunteer_name'] = volunteer['full_name']
            flash(f"Welcome back, {volunteer['full_name']}!")
            return redirect(url_for('volunteer_dashboard'))
        else:
            flash('Invalid email or password.')

    return render_template('volunteer_login.html')

@app.route('/volunteer/dashboard')
@volunteer_required
def volunteer_dashboard():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)


    cursor.execute("SELECT * FROM missing_persons WHERE status = 'Missing' ORDER BY created_at DESC")
    cases = cursor.fetchall()


    cursor.execute("SELECT * FROM volunteers WHERE id = %s", (session['volunteer_id'],))
    volunteer = cursor.fetchone()

    cursor.close()
    conn.close()

    return render_template('volunteer_dashboard.html', cases=cases, volunteer=volunteer)

@app.route('/volunteer/logout')
def volunteer_logout():
    session.pop('volunteer_id', None)
    session.pop('volunteer_name', None)
    flash('Logged out successfully.')
    return redirect(url_for('index'))

if __name__ == '__main__':

    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    print("Starting server...")
    app.run(debug=True, host='0.0.0.0')
