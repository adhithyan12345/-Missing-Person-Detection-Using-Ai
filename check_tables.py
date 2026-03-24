import mysql.connector

try:
    conn = mysql.connector.connect(
        host="localhost",
        user="root",
        password="",
        database="missing_persons_db"
    )
    cursor = conn.cursor()
    cursor.execute("SHOW TABLES;")
    tables = cursor.fetchall()
    print("Tables in missing_persons_db:")
    for table in tables:
        print(table)
    conn.close()
except Exception as e:
    print(f"Error: {e}")
