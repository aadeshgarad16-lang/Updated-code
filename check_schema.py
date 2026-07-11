import os
from Main import get_db_connection

conn = get_db_connection()
cursor = conn.cursor()
try:
    cursor.execute("SHOW CREATE TABLE purchase_orders;")
    rows = cursor.fetchone()
    print("Schema:", rows[1])
except Exception as e:
    print(f"Error: {e}")
cursor.close()
conn.close()
