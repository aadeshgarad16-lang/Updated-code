import os
from Main import get_db_connection

conn = get_db_connection()
cursor = conn.cursor()
try:
    cursor.execute("ALTER TABLE purchase_orders MODIFY COLUMN stage ENUM('Initiation', 'Order Initiation', 'Order Specifications', 'Specifications', 'Stock Check', 'BOM Calculation', 'Inventory Check', 'Material Allocation', 'Procurement', 'Material Release', 'Production', 'Quality & Packing', 'Dispatched') DEFAULT 'Initiation';")
    conn.commit()
    print("Column modified successfully")
except Exception as e:
    print(f"Error: {e}")
cursor.close()
conn.close()
