# -*- coding: utf-8 -*-
from PIL import Image, ImageDraw, ImageFont
import os

import qrcode

def generate_poster(case_data, output_folder):
    """
    Generates a social media poster for a missing person.
    Returns the filename of the generated image.
    """

    width, height = 1080, 1080
    bg_color = (255, 255, 255)
    text_color = (0, 0, 0)
    alert_color = (255, 0, 0)

    img = Image.new('RGB', (width, height), color=bg_color)
    draw = ImageDraw.Draw(img)


    try:

        title_font = ImageFont.truetype("DejaVuSans-Bold.ttf", 100)
        header_font = ImageFont.truetype("DejaVuSans-Bold.ttf", 60)
        text_font = ImageFont.truetype("DejaVuSans.ttf", 40)
        small_font = ImageFont.truetype("DejaVuSans.ttf", 30)
    except IOError:

        title_font = ImageFont.load_default()
        header_font = ImageFont.load_default()
        text_font = ImageFont.load_default()
        small_font = ImageFont.load_default()


    border_width = 30
    draw.rectangle([(0,0), (width, height)], outline=alert_color, width=border_width)


    draw.text((width/2, 80), "MISSING", font=title_font, fill=alert_color, anchor="mm")


    photo_path = os.path.join(output_folder, case_data['photo_path'])
    try:
        if os.path.exists(photo_path):
            photo = Image.open(photo_path)

            target_h = 500
            aspect_ratio = photo.width / photo.height
            target_w = int(target_h * aspect_ratio)
            photo = photo.resize((target_w, target_h))


            photo_x = (width - target_w) // 2
            photo_y = 160
            img.paste(photo, (photo_x, photo_y))
        else:
            draw.text((width/2, 400), "No Photo Available", font=header_font, fill=text_color, anchor="mm")
    except Exception as e:
        print(f"Error loading photo for poster: {e}")


    details_start_y = 700


    draw.text((width/2, details_start_y), case_data['full_name'].upper(), font=header_font, fill=text_color, anchor="mm")


    info_y = details_start_y + 80
    spacing = 50

    info_lines = [
        f"Age: {case_data['age']} | Gender: {case_data['gender']}",
        f"Last Seen: {case_data['last_seen_date']}",
        f"Location: {case_data['last_seen_location']}",
    ]

    for line in info_lines:
        draw.text((width/2, info_y), line, font=text_font, fill=text_color, anchor="mm")
        info_y += spacing


    try:

        import socket
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:

            s.connect(('10.255.255.255', 1))
            IP = s.getsockname()[0]
        except Exception:
            IP = '127.0.0.1'
        finally:
            s.close()


        app_url = f"http://{IP}:5000"
        case_url = f"{app_url}/case/{case_data['id']}"
        print(f"Generated QR code for: {case_url}")

        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=10,
            border=2,
        )
        qr.add_data(case_url)
        qr.make(fit=True)

        qr_img = qr.make_image(fill_color="black", back_color="white")
        qr_img = qr_img.resize((180, 180))


        img.paste(qr_img, (60, 850))


        draw.text((150, 1040), "SCAN FOR INFO", font=small_font, fill=text_color, anchor="mm")

    except Exception as e:
        print(f"Error generating QR code: {e}")


    footer_y = 950

    draw.text((width - 350, footer_y), "IF SEEN, CALL:", font=text_font, fill=alert_color, anchor="mm")
    draw.text((width - 350, footer_y + 60), case_data['contact_phone'], font=header_font, fill=text_color, anchor="mm")


    filename = f"poster_{case_data['ticket_id']}.jpg"
    save_path = os.path.join(output_folder, filename)
    img.save(save_path)

    return filename
