import mysql.connector
import os
from dotenv import load_dotenv

load_dotenv()

conn = mysql.connector.connect(
    host=os.getenv('DB_HOST'),
    user=os.getenv('DB_USER'),
    password=os.getenv('DB_PASSWORD'),
    database=os.getenv('DB_NAME')
)
c = conn.cursor()

migrations = [
    "ALTER TABLE purchase_orders MODIFY COLUMN cin_number VARCHAR(25)",
    "ALTER TABLE purchase_orders MODIFY COLUMN gst_number VARCHAR(25)",
    "ALTER TABLE purchase_orders MODIFY COLUMN delivery_type VARCHAR(20) DEFAULT 'single'",
    "ALTER TABLE purchase_orders MODIFY COLUMN test_certificate VARCHAR(10) DEFAULT 'Yes'",
]

for sql in migrations:
    try:
        c.execute(sql)
        print(f"OK: {sql}")
    except Exception as e:
        print(f"ERROR on [{sql}]: {e}")

conn.commit()
print("Migration complete.")
conn.close()
