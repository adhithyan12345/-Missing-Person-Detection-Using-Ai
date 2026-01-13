# -*- coding: utf-8 -*-
import mysql.connector
import os
from dotenv import load_dotenv

load_dotenv()

def check_users():
    try:
        conn = mysql.connector.connect(
            host=os.getenv('MYSQL_HOST', 'localhost'),
            user=os.getenv('MYSQL_USER', 'root'),
            password=os.getenv('MYSQL_PASSWORD', ''),
            database=os.getenv('MYSQL_DB', 'missing_persons_db')
        )
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT id, full_name, email, role FROM users")
        users = cursor.fetchall()
        
        if not users:
            print("No users found in the database.")
        else:
            print(f"Found {len(users)} users:")
            for user in users:
                print(f"ID: {user['id']}, Name: {user['full_name']}, Email: {user['email']}, Role: {user['role']}")
                
        cursor.close()
        conn.close()
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    check_users()
