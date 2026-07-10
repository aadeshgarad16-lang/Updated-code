import sys
import os
from Main import get_db_connection

def migrate_status_columns():
    conn = get_db_connection()
    if not conn:
        print("Failed to connect to the database.")
        return
        
    cursor = conn.cursor()
    
    tables = ['orders', 'purchase_orders']
    
    for table in tables:
        try:
            # 1. Expand the main status column
            print(f"Migrating {table}.status to VARCHAR(100)...")
            cursor.execute(f"ALTER TABLE {table} MODIFY COLUMN status VARCHAR(100) DEFAULT 'Pending';")
            
            # 2. Expand the active_stage column if it exists
            print(f"Migrating {table}.active_stage to VARCHAR(100)...")
            cursor.execute(f"ALTER TABLE {table} MODIFY COLUMN active_stage VARCHAR(100);")
        except Exception as e:
            print(f"Note on {table}: {e}")

    # 3. Same for production_scheduler
    print("Migrating production_scheduler.status to VARCHAR(100)...")
    try:
        cursor.execute("ALTER TABLE production_scheduler MODIFY COLUMN status VARCHAR(100) DEFAULT 'Pending';")
    except Exception as e:
        print(f"Note on production_scheduler: {e}")

    conn.commit()
    print("Migration completed successfully!")
    cursor.close()
    conn.close()

if __name__ == "__main__":
    migrate_status_columns()
