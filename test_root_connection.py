import mysql.connector

try:
    print("Attempting to connect as root...")
    conn = mysql.connector.connect(
        host="localhost",
        user="root",
        password=""
    )
    print("Connected successfully as root!")
    cursor = conn.cursor()
    cursor.execute("SHOW DATABASES;")
    for db in cursor:
        print(db)
    conn.close()
except Exception as e:
    print(f"Failed to connect as root: {e}")
