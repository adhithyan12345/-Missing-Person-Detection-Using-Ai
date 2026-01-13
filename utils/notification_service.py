# -*- coding: utf-8 -*-
from flask_mail import Message
from flask import render_template_string
from twilio.rest import Client
import threading

class NotificationManager:
    def __init__(self, app, mail):
        self.app = app
        self.mail = mail
        self.twilio_client = None


        try:
            sid = app.config.get('TWILIO_ACCOUNT_SID')
            token = app.config.get('TWILIO_AUTH_TOKEN')
            if sid and token:
                self.twilio_client = Client(sid, token)
        except Exception as e:
            print(f"Twilio initialization failed: {e}")

    def send_email_alert(self, recipient, match_details):
        """Sends an email alert asynchronously."""
        def _send_async_email(app, recipient, match_details):
            with app.app_context():
                try:
                    subject = f"URGENT: Missing Person Match Found - {match_details['name']}"


                    html_body = f"""
                    <h2>Missing Person Match Found!</h2>
                    <p><strong>Name:</strong> {match_details['name']}</p>
                    <p><strong>Match Confidence:</strong> {match_details.get('confidence', 'N/A')}</p>
                    <p><strong>Location:</strong> {match_details.get('location', 'Unknown')}</p>
                    <p><strong>Time:</strong> {match_details.get('time', 'Just now')}</p>
                    <hr>
                    <p>Please log in to the portal to view full details and CCTV footage.</p>
                    """

                    msg = Message(subject, recipients=[recipient], html=html_body)
                    self.mail.send(msg)
                    print(f"Email sent to {recipient}")
                except Exception as e:
                    print(f"Failed to send email: {e}")


        thr = threading.Thread(target=_send_async_email, args=(self.app, recipient, match_details))
        thr.start()

    def send_sms_alert(self, phone_number, match_details):
        """Sends an SMS alert asynchronously."""
        def _send_async_sms():
            try:
                from_number = self.app.config.get('TWILIO_PHONE_NUMBER')
                if not self.twilio_client or not from_number:
                    print("Twilio not configured.")
                    return

                body = f"URGENT: Match found for {match_details['name']} at {match_details.get('location', 'Unknown')}. Check portal immediately."

                message = self.twilio_client.messages.create(
                    body=body,
                    from_=from_number,
                    to=phone_number
                )
                print(f"SMS sent to {phone_number}: {message.sid}")
            except Exception as e:
                print(f"Failed to send SMS: {e}")

        thr = threading.Thread(target=_send_async_sms)
        thr.start()

    def send_password_reset_email(self, recipient, reset_url):
        """Sends a password reset email asynchronously."""
        def _send_async_reset_email(app, recipient, reset_url):
            with app.app_context():
                try:
                    subject = "Password Reset Request - FindThem"
                    html_body = f"""
                    <h2>Password Reset Request</h2>
                    <p>Unless you initiated this request, please ignore this email.</p>
                    <p>Click the link below to reset your password:</p>
                    <a href="{reset_url}" style="padding: 10px 20px; background-color: #4F46E5; color: white; text-decoration: none; border-radius: 5px;">Reset Password</a>
                    <p>Or copy this link:</p>
                    <p>{reset_url}</p>
                    <p>This link will expire in 1 hour.</p>
                    """
                    msg = Message(subject, recipients=[recipient], html=html_body)
                    self.mail.send(msg)
                    print(f"Password reset email sent to {recipient}")
                except Exception as e:
                    print(f"Failed to send password reset email: {e}")
                    # Fallback for development/demo if email fails
                    print(f"DEBUG: Reset Link for {recipient}: {reset_url}")

        thr = threading.Thread(target=_send_async_reset_email, args=(self.app, recipient, reset_url))
        thr.start()
