# -*- coding: utf-8 -*-
import cv2
import numpy as np
import insightface
from insightface.app import FaceAnalysis
import pickle
import os




app = FaceAnalysis(name='buffalo_s', providers=['CPUExecutionProvider'])
app.prepare(ctx_id=0, det_size=(320, 320))

def get_face_encoding_from_frame(frame):
    """
    Processes a raw OpenCV frame (numpy array) and returns the encoding.
    Returns: (encoding, (x, y, w, h))
    """
    try:



        faces = app.get(frame)

        if not faces:
            return None, None



        faces = sorted(faces, key=lambda x: (x.bbox[2]-x.bbox[0]) * (x.bbox[3]-x.bbox[1]), reverse=True)
        face = faces[0]

        encoding = face.embedding
        encoding = encoding / np.linalg.norm(encoding)


        bbox = face.bbox.astype(int)
        x = bbox[0]
        y = bbox[1]
        w = bbox[2] - bbox[0]
        h = bbox[3] - bbox[1]

        return encoding, (x, y, w, h)

    except Exception as e:
        print(f"Error processing frame: {e}")
        return None, None

def get_all_face_encodings(frame):
    """
    Processes a frame and returns encodings for ALL detected faces.
    Returns: List of (encoding, (x, y, w, h))
    """
    try:
        faces = app.get(frame)

        if not faces:
            return []

        results = []

        for face in faces:
            encoding = face.embedding
            encoding = encoding / np.linalg.norm(encoding)
            bbox = face.bbox.astype(int)
            x = bbox[0]
            y = bbox[1]
            w = bbox[2] - bbox[0]
            h = bbox[3] - bbox[1]
            results.append((encoding, (x, y, w, h)))

        return results
    except Exception as e:
        print(f"Error processing frame for all faces: {e}")
        return []

def get_face_encoding(image_path):
    """
    Wrapper for file-based processing.
    """
    try:
        img = cv2.imread(image_path)
        if img is None:
            return None

        faces = app.get(img)

        if not faces:
            return None


        faces = sorted(faces, key=lambda x: (x.bbox[2]-x.bbox[0]) * (x.bbox[3]-x.bbox[1]), reverse=True)
        encoding = faces[0].embedding
        return encoding / np.linalg.norm(encoding)

    except Exception as e:
        print(f"Error processing image file: {e}")
        return None

def find_match(unknown_encoding, known_encodings_dict, tolerance=1.2):
    """
    Compares the unknown encoding against a dictionary of known encodings.
    known_encodings_dict: {id: [list of raw encodings (bytes)]} OR {id: single raw encoding}
    
    Returns: (match_id, distance) or (None, distance)
    """
    if unknown_encoding is None:
        return None, None

    if not known_encodings_dict:
        return None, None


    known_ids = []
    known_encodings_flat = []

    for k_id, k_val in known_encodings_dict.items():
        if isinstance(k_val, list):
            for enc in k_val:
                if enc:
                     known_ids.append(k_id)
                     known_encodings_flat.append(pickle.loads(enc))
        else:

             if k_val:
                 known_ids.append(k_id)
                 known_encodings_flat.append(pickle.loads(k_val))

    if not known_encodings_flat:
        return None, None


    unknown_encoding = np.array(unknown_encoding)
    known_encodings_arr = np.array(known_encodings_flat)


    norms = np.linalg.norm(known_encodings_arr, axis=1, keepdims=True)
    known_encodings_arr = known_encodings_arr / norms


    diff = known_encodings_arr - unknown_encoding
    distances = np.linalg.norm(diff, axis=1)


    best_match_index = np.argmin(distances)
    best_distance = distances[best_match_index]

    if best_distance <= tolerance:
        return known_ids[best_match_index], float(best_distance)

    return None, float(best_distance)
