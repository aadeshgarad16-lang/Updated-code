import mysql.connector
import os
from dotenv import load_dotenv

load_dotenv()

try:
    conn = mysql.connector.connect(
        host=os.getenv('DB_HOST', '127.0.0.1'),
        user=os.getenv('DB_USER', 'root'),
        password=os.getenv('DB_PASSWORD', 'Admin@123'),
        database=os.getenv('DB_NAME', 'sasons_erp')
    )
    cursor = conn.cursor()
    
    columns_to_add = {
        "sku_no": "VARCHAR(100) DEFAULT NULL",
        "hsn_code": "VARCHAR(100) DEFAULT NULL",
        "pattern": "VARCHAR(100) DEFAULT NULL",
        "image_url": "TEXT DEFAULT NULL"
    }
    
    cursor.execute("DESCRIBE store_garments")
    existing_cols = [row[0] for row in cursor.fetchall()]
    
    for col, datatype in columns_to_add.items():
        if col not in existing_cols:
            cursor.execute(f"ALTER TABLE store_garments ADD COLUMN {col} {datatype}")
            print(f"✅ Added column: {col}")
        else:
            print(f"ℹ️ Column already exists: {col}")
            
    conn.commit()
    print("🚀 Database structural patch complete!")
except Exception as e:
    print(f"❌ Error updating database: {e}")
finally:
    if 'conn' in locals() and conn.is_connected():
        cursor.close()
        conn.close()
