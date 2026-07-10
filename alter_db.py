import Main

conn = Main.get_db_connection()
cursor = conn.cursor()
cursor.execute("ALTER TABLE purchase_orders MODIFY COLUMN stage ENUM('Initiation', 'Inventory Check', 'Procurement', 'Quality & Packing', 'Dispatched') DEFAULT 'Initiation'")
conn.commit()
print('Table altered successfully.')
cursor.close()
conn.close()
