from app import app, get_db_connection
from werkzeug.security import generate_password_hash

def create_admin_user():
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        email = 'admin@example.com'
        cursor.execute("SELECT id FROM users WHERE email = %s", (email,))
        if cursor.fetchone():
            print("Admin user already exists.")
            return

        password = 'admin123'
        hashed_password = generate_password_hash(password)
        full_name = 'Admin Officer'
        role = 'officer'

        cursor.execute("INSERT INTO users (full_name, email, password_hash, role) VALUES (%s, %s, %s, %s)",
                       (full_name, email, hashed_password, role))
        conn.commit()
        print(f"Admin user created successfully.\nEmail: {email}\nPassword: {password}")
        
        cursor.close()
        conn.close()
    except Exception as e:
        print(f"Error creating admin user: {e}")

if __name__ == '__main__':
    create_admin_user()
