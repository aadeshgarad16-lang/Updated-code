import os
from Main import get_db_connection

conn = get_db_connection()
cursor = conn.cursor()
try:
    cursor.execute("SELECT DISTINCT stage FROM purchase_orders;")
    rows = cursor.fetchall()
    print("Stages in table:", rows)
except Exception as e:
    print(f"Error: {e}")
cursor.close()
conn.close()
