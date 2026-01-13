# -*- coding: utf-8 -*-
import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-secret-key-change-this'
    MYSQL_HOST = os.environ.get('MYSQL_HOST') or 'localhost'
    MYSQL_USER = os.environ.get('MYSQL_USER') or 'root'
    MYSQL_PASSWORD = (os.environ.get('MYSQL_PASSWORD') or '').strip()
    MYSQL_DB = os.environ.get('MYSQL_DB') or 'missing_persons_db'
    UPLOAD_FOLDER = os.path.join(os.getcwd(), 'static', 'uploads')
    MAX_CONTENT_LENGTH = 500 * 1024 * 1024
    OFFICER_SECRET_CODE = os.environ.get('OFFICER_SECRET_CODE') or 'KAALI_OFFICER_SECURE'
