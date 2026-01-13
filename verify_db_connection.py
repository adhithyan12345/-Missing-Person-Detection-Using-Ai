# -*- coding: utf-8 -*-
import mysql.connector
from mysql.connector import Error
import os
from dotenv import load_dotenv

def test_connection():
    load_dotenv()

    print("Testing Database Connection...")
    print(f"Host: {os.getenv('MYSQL_HOST', 'localhost')}")
    print(f"User: {os.getenv('MYSQL_USER', 'root')}")
    print(f"Database: {os.getenv('MYSQL_DB', 'missing_persons_db')}")

    try:
        connection = mysql.connector.connect(
            host=os.getenv('MYSQL_HOST', 'localhost'),
            user=os.getenv('MYSQL_USER', 'root'),
            password=os.getenv('MYSQL_PASSWORD', ''),
            database=os.getenv('MYSQL_DB', 'missing_persons_db')
        )

        if connection.is_connected():
            db_info = connection.get_server_info()
            print(f"\nSUCCESS: Connected to MySQL Server version {db_info}")

            cursor = connection.cursor()
            cursor.execute("SHOW TABLES;")
            tables = cursor.fetchall()

            print("\nFound Tables:")
            if not tables:
                print("  (No tables found. Did you run schema.sql?)")
            else:
                for table in tables:
                    print(f"  - {table[0]}")

            required_tables = {'users', 'missing_persons', 'person_photos', 'case_updates', 'detection_logs'}
            existing_tables = {t[0] for t in tables}

            missing = required_tables - existing_tables
            if missing:
                print(f"\nWARNING: Missing tables: {missing}")
            else:
                print("\nSUCCESS: All required tables and columns are present!")

            cursor.close()
            connection.close()
            return True

    except Error as e:
        print(f"\nERROR: Could not connect to database.")
        print(f"Error code: {e}")
        print("\nTroubleshooting Tips:")
        print("1. Is WampServer/MySQL running? (Icon should be GREEN)")
        print("2. Did you create the database 'missing_persons_db'?")
        print("3. Check your .env file password.")
        return False

if __name__ == "__main__":
    test_connection()
