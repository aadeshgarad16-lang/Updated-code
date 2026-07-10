import sys
sys.path.append('c:/Users/USER/Pictures/Sasons_ERP')
from App import get_db_connection
import traceback

try:
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    # 2. Active Production (Sum quantity where In Progress or active stage)
    try:
        cursor.execute("""
            SELECT COALESCE(SUM(total_pieces), 0) as active_count
            FROM purchase_orders 
            WHERE status = 'In Progress' 
               OR stage IN ('BOM Calculation', 'Inventory Check', 'Material Allocation', 'Procurement', 'Material Release', 'Production')
        """)
        active_prod_result = cursor.fetchone()
        active_prod = float(active_prod_result.get('active_count', 0) or 0)
    except Exception as e:
        print("Fallback 1")
        cursor.execute("""
            SELECT COALESCE(SUM(quantity), 0) as active_count
            FROM purchase_orders 
            WHERE status = 'In Progress' 
               OR stage IN ('BOM Calculation', 'Inventory Check', 'Material Allocation', 'Procurement', 'Material Release', 'Production')
        """)
        active_prod_result = cursor.fetchone()
        active_prod = float(active_prod_result.get('active_count', 0) or 0)
    
    print('Finished active prod')
except Exception as e:
    traceback.print_exc()
