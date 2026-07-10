import mysql.connector

def update_schema():
    conn = mysql.connector.connect(
        host="127.0.0.1",
        user="root",
        password="Admin@123",
        database="sasons_erp"
    )
    cursor = conn.cursor()
    
    queries = [
        "ALTER TABLE purchase_orders ADD COLUMN payment_term VARCHAR(255) DEFAULT NULL;",
        "ALTER TABLE purchase_orders ADD COLUMN test_certificate VARCHAR(255) DEFAULT 'No';",
        "ALTER TABLE purchase_orders ADD COLUMN transport_cost VARCHAR(255) DEFAULT NULL;",
        "ALTER TABLE purchase_orders ADD COLUMN advance_amount DECIMAL(10,2) DEFAULT 0;",
        "ALTER TABLE purchase_orders ADD COLUMN delivery_type VARCHAR(255) DEFAULT 'single';",
        "ALTER TABLE specifications ADD COLUMN delivery_address TEXT DEFAULT NULL;",
        "ALTER TABLE specifications ADD COLUMN delivery_pin VARCHAR(50) DEFAULT NULL;"
    ]
    
    for q in queries:
        try:
            cursor.execute(q)
            print(f"Executed: {q}")
        except Exception as e:
            print(f"Skipped (may exist): {q} - {e}")
            
    conn.commit()
    cursor.close()
    conn.close()

if __name__ == "__main__":
    update_schema()
