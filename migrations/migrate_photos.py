utf-8
import mysql.connector
from config import Config
import pickle

def get_db_connection():
    return mysql.connector.connect(
        host=Config.MYSQL_HOST,
        user=Config.MYSQL_USER,
        password=Config.MYSQL_PASSWORD,
        database=Config.MYSQL_DB
    )

def migrate():
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)


        with open('migrations/create_person_photos.sql', 'r') as f:
            sql = f.read()

            for statement in sql.split(';'):
                if statement.strip():
                    cursor.execute(statement)
        conn.commit()
        print("Table person_photos checked/created.")


        cursor.execute("SELECT id, photo_path, face_encoding FROM missing_persons WHERE photo_path IS NOT NULL")
        persons = cursor.fetchall()

        migrated_count = 0
        for p in persons:

            cursor.execute("SELECT id FROM person_photos WHERE missing_person_id = %s AND photo_path = %s", (p['id'], p['photo_path']))
            if not cursor.fetchone():
                cursor.execute("INSERT INTO person_photos (missing_person_id, photo_path, face_encoding) VALUES (%s, %s, %s)",
                               (p['id'], p['photo_path'], p['face_encoding']))
                migrated_count += 1

        conn.commit()
        print(f"Successfully migrated {migrated_count} photos to person_photos table.")

        cursor.close()
        conn.close()
    except Exception as e:
        print(f"Migration failed: {e}")

if __name__ == "__main__":
    migrate()
