import os
import json
from flask import Flask, jsonify, request
from flask_cors import CORS
from werkzeug.security import generate_password_hash, check_password_hash
from dotenv import load_dotenv
from datetime import datetime
from dateutil import parser

def format_db_date(date_str):
    if not date_str:
        return None
    try:
        parsed_date = parser.parse(date_str)
        return parsed_date.strftime('%Y-%m-%d')
    except Exception:
        try:
            return datetime.fromisoformat(date_str.replace('Z', '')).strftime('%Y-%m-%d')
        except Exception:
            return date_str

# IMPORT YOUR DATABASE CONNECTION FUNCTION FROM YOUR OTHER FILE
from Main import get_db_connection

# Load key variables from your .env file
load_dotenv()

from datetime import date, datetime
from flask.json.provider import DefaultJSONProvider

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*", "allow_headers": ["Content-Type", "X-API-Key", "X-User-Contact"]}})

# =====================================================================
# ISO-8601 STANDARDIZATION PROVIDER
# =====================================================================
class CustomJSONProvider(DefaultJSONProvider):
    def default(self, obj):
        if isinstance(obj, (datetime, date)):
            return obj.isoformat()
        return super().default(obj)

app.json = CustomJSONProvider(app)

# =====================================================================
# STAGE NORMALIZATION ARCHITECTURE
# =====================================================================
VALID_ORDER_STAGES = [
    'Initiation', 'Order Initiation', 'Specifications', 'Order Specifications', 
    'Stock Check', 'BOM Calculation', 'Inventory Check', 'Material Allocation', 
    'Procurement', 'Material Release', 'Production', 'Quality & Packing', 'Dispatched'
]
STAGE_MAP = {stage.lower(): stage for stage in VALID_ORDER_STAGES}

def normalize_stage(raw_stage, default='Specifications'):
    """
    Sanitizes, trims, and normalizes the stage string against strict ENUM boundaries.
    Defaults to 'Specifications' if invalid or empty.
    """
    if not raw_stage:
        return default
    
    clean_stage = str(raw_stage).strip().lower()
    return STAGE_MAP.get(clean_stage, default)


# =====================================================================
# DIAGNOSTIC TOOL: Test Database Connection
# =====================================================================
@app.route('/api/test-db', methods=['GET'])
def test_db():
    try:
        conn = get_db_connection()
        conn.close()
        return jsonify({"message": "Database Connected Successfully!"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# =====================================================================
# DIAGNOSTIC TOOL: Reset/Clear Database
# =====================================================================
@app.route('/api/reset-database', methods=['POST'])
def reset_database():
    if not verify_write_key('User Management'): 
        return "Unauthorized: Invalid Write API Key", 401
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SET FOREIGN_KEY_CHECKS = 0;")
        cursor.execute("TRUNCATE TABLE specifications;")
        cursor.execute("TRUNCATE TABLE bill_of_materials;")
        cursor.execute("TRUNCATE TABLE procurement;")
        cursor.execute("TRUNCATE TABLE purchase_orders;")
        cursor.execute("SET FOREIGN_KEY_CHECKS = 1;")
        conn.commit()
        cursor.close(); conn.close()
        return jsonify({"success": True, "message": "Database reset successfully!"}), 200
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# --- SECURITY INTERCEPTORS ---
def verify_access_detailed(module_name=None, is_write=False):
    client_key = request.headers.get('X-API-Key')
    expected_key = os.environ.get("ERP_WRITE_API_KEY", "sasons_write_only_key_2026_xyz") if is_write else os.environ.get("ERP_READ_API_KEY", "sasons_read_only_key_2026_abc")
    
    # Fallback to write key if read key fails (write key has higher privilege)
    if client_key != expected_key and not (not is_write and client_key == os.environ.get("ERP_WRITE_API_KEY", "sasons_write_only_key_2026_xyz")):
        return False, f"Missing or Invalid {'Write' if is_write else 'Read'} API Key"
        
    if module_name:
        contact = request.headers.get('X-User-Contact')
        if not contact:
            return False, "Missing X-User-Contact header. Please re-login."
        conn = None
        cursor = None
        try:
            conn = get_db_connection()
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT * FROM users WHERE contact_number = %s OR email_id = %s OR username = %s", (contact, contact, contact))
            user = cursor.fetchone()
            
            if not user:
                # Auto-migrate legacy user into the Users table to preserve their access
                is_email = '@' in contact
                email_val = contact if is_email else f"{contact}@sasons.local"
                contact_val = contact[:10] if not is_email else '9999999999'
                hashed_pw = generate_password_hash('Admin@123')
                
                print(f"Auto-migrating legacy user {contact} into the Users table...")
                cursor.execute("""
                    INSERT INTO users (full_name, contact_number, email_id, designation, role, username, password_hash, modules_access, status) 
                    VALUES ('Test Case', %s, %s, 'System Administrator', 'Super Admin', %s, %s, '[]', 'Active')
                """, (contact_val, email_val, contact_val, hashed_pw))
                conn.commit()
                
                user = {'role': 'Super Admin', 'modules_access': '[]'}
                
            if user['role'] == 'Super Admin':
                return True, ""
            modules = []
            if user.get('modules_access'):
                modules = json.loads(user['modules_access']) if isinstance(user['modules_access'], str) else user['modules_access']
            if module_name in modules:
                return True, ""
            else:
                return False, f"Insufficient permissions for module: {module_name}"
        except Exception as e:
            if conn: conn.rollback()
            return False, f"Database error in authorization: {str(e)}"
        finally:
            if cursor: cursor.close()
            if conn: conn.close()
    return True, ""

def verify_write_access_detailed(module_name=None):
    return verify_access_detailed(module_name, is_write=True)

def verify_read_access_detailed(module_name=None):
    return verify_access_detailed(module_name, is_write=False)

def verify_write_key(module_name=None):
    is_auth, _ = verify_write_access_detailed(module_name)
    return is_auth
    
def verify_read_key(module_name=None):
    is_auth, _ = verify_read_access_detailed(module_name)
    return is_auth

# =====================================================================
# MODULE 0: USERS (RBAC)
# =====================================================================

@app.route('/api/users/list', methods=['GET', 'OPTIONS'])
@app.route('/users/view', methods=['GET', 'OPTIONS'])
def get_users():
    if request.method == 'OPTIONS':
        return '', 200
    if not verify_read_key('User Management'):
        return jsonify({"success": False, "error": "Unauthorized"}), 401
    
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT user_id, full_name, contact_number, email_id, designation, role, username, modules_access, status, last_login, created_at FROM users")
        results = cursor.fetchall()
        for res in results:
            if res.get('modules_access'):
                res['modules_access'] = json.loads(res['modules_access']) if isinstance(res['modules_access'], str) else res['modules_access']
            if res.get('last_login'):
                res['last_login'] = str(res['last_login'])
            if res.get('created_at'):
                res['created_at'] = str(res['created_at'])
        return jsonify(results)
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        if cursor: cursor.close()
        if conn: conn.close()

@app.route('/users/view/<int:user_id>', methods=['GET', 'OPTIONS'])
def get_user_by_id(user_id):
    if request.method == 'OPTIONS':
        return '', 200
    if not verify_read_key('User Management'):
        return jsonify({"success": False, "error": "Unauthorized"}), 401
    
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT user_id, full_name, contact_number, email_id, designation, role, username, modules_access, status, last_login, created_at, updated_at FROM users WHERE user_id = %s", (user_id,))
        user = cursor.fetchone()
        
        if not user:
            return jsonify({"success": False, "error": "User not found."}), 404
            
        if user.get('modules_access'):
            user['modules_access'] = json.loads(user['modules_access']) if isinstance(user['modules_access'], str) else user['modules_access']
        if user.get('last_login'):
            user['last_login'] = str(user['last_login'])
        if user.get('created_at'):
            user['created_at'] = str(user['created_at'])
        if user.get('updated_at'):
            user['updated_at'] = str(user['updated_at'])
            
        return jsonify({"success": True, "user": user})
    except Exception as e:
        return jsonify({"success": False, "error": "Unable to load user details."}), 500
    finally:
        if cursor: cursor.close()
        if conn: conn.close()

@app.route('/users/add', methods=['POST', 'OPTIONS'])
def add_user():
    if request.method == 'OPTIONS':
        return '', 200
        
    print("\n" + "="*50)
    print("=== INCOMING REQUEST: POST /users/add ===")
    print("=== HEADERS ===")
    for key, value in request.headers.items():
        print(f"{key}: {value}")
        
    is_auth, err_msg = verify_write_access_detailed('User Management')
    if not is_auth:
        print(f"=== AUTHORIZATION FAILED ===\nReason: {err_msg}")
        return jsonify({"success": False, "message": err_msg}), 401
        
    data = request.json or {}
    print("=== REQUEST BODY ===")
    print(json.dumps(data, indent=2))
    try:
        import traceback
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        email = data.get('email_id')
        if email and email.strip():
            cursor.execute("SELECT * FROM users WHERE contact_number = %s OR email_id = %s OR username = %s", 
                           (data.get('contactNumber'), email, data.get('username')))
        else:
            cursor.execute("SELECT * FROM users WHERE contact_number = %s OR username = %s", 
                           (data.get('contactNumber'), data.get('username')))
            
        if cursor.fetchone():
            err_msg = "User with this contact number, email, or username already exists"
            return jsonify({"success": False, "error": err_msg, "message": err_msg}), 400            
        
        password = data.get('password')
        hashed_password = generate_password_hash(password) if password else generate_password_hash('default123')
        role = data.get('role', '')
        submitted_modules = data.get('modulesAccess')
        
        ALLOWED_MODULES = [
            "Dashboard", "Order Initiation", "Specifications", "Stock Check",
            "BOM Calculation", "Inventory Check", "Material Allocation", "Procurement",
            "Production", "Quality & Packing", "Logistics", "Accounts",
            "Store", "Reports", "System Logs", "User Management"
        ]
        
        if submitted_modules is None:
            if role == 'Super Admin':
                submitted_modules = ALLOWED_MODULES.copy()
            elif role == 'Admin':
                submitted_modules = ["Dashboard", "Reports", "Inventory Check", "Accounts", "User Management"]
            elif 'Manager' in role:
                submitted_modules = ["Dashboard", "Order Initiation", "Production", "Reports"]
            elif 'User' in role or role in ["Operator", "Viewer"]:
                submitted_modules = ["Dashboard", "Order Initiation"]
            else:
                submitted_modules = []
                
        # Validate final set of permissions
        final_modules = [m for m in submitted_modules if m in ALLOWED_MODULES]
        modules_json = json.dumps(final_modules)
        
        # Handle optional email uniqueness constraint
        final_email = email.strip() if email and email.strip() else f"no-email-{data.get('contactNumber')}@sasons.local"
        
        query = """INSERT INTO users (full_name, contact_number, email_id, designation, role, username, password_hash, modules_access, status) 
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)"""
        params = (data.get('fullName'), data.get('contactNumber'), final_email, data.get('designation', ''), data.get('role'), data.get('username'), hashed_password, modules_json, data.get('status', 'Active'))
        
        print("=== SQL EXECUTION ===")
        print("Executing SQL:", query)
        print("With parameters:", params)
        
        cursor.execute(query, params)
        conn.commit()
        cursor.close(); conn.close()
        
        print("=== RESPONSE STATUS: 201 Created ===")
        print("="*50 + "\n")
        return jsonify({"success": True, "message": "User created successfully"}), 201
    except Exception as e:
        import traceback
        traceback.print_exc()
        if conn: conn.rollback()
        
        err_response = {"success": False, "error": str(e), "message": str(e)}
        print("=== RESPONSE STATUS: 500 Internal Server Error ===")
        print(json.dumps(err_response, indent=2))
        print("="*50 + "\n")
        return jsonify(err_response), 500

@app.route('/users/update/<int:user_id>', methods=['PUT', 'OPTIONS'])
def update_user(user_id):
    if request.method == 'OPTIONS':
        return '', 200
    is_auth, err_msg = verify_write_access_detailed('User Management')
    if not is_auth:
        return jsonify({"success": False, "message": err_msg}), 401
    data = request.json or {}
    try:
        import traceback
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        # 1. Fetch the existing user
        cursor.execute("SELECT * FROM users WHERE user_id = %s", (user_id,))
        existing_user = cursor.fetchone()
        if not existing_user:
            return jsonify({"success": False, "message": "User not found"}), 404
            
        # 2. Extract values, defaulting to existing if not provided
        full_name = data.get('fullName') if 'fullName' in data and data.get('fullName') is not None else existing_user.get('full_name')
        contact_number = data.get('contactNumber') if 'contactNumber' in data and data.get('contactNumber') is not None else existing_user.get('contact_number')
        email_id = data.get('email_id') if 'email_id' in data and data.get('email_id') is not None else existing_user.get('email_id')
        designation = data.get('designation') if 'designation' in data and data.get('designation') is not None else existing_user.get('designation')
        role = data.get('role') if 'role' in data and data.get('role') is not None else existing_user.get('role')
        username = data.get('username') if 'username' in data and data.get('username') is not None else existing_user.get('username')
        status = data.get('status') if 'status' in data and data.get('status') is not None else existing_user.get('status')
        
        ALLOWED_MODULES = [
            "Dashboard", "Order Initiation", "Specifications", "Stock Check",
            "BOM Calculation", "Inventory Check", "Material Allocation", "Procurement",
            "Production", "Quality & Packing", "Logistics", "Accounts",
            "Store", "Reports", "System Logs", "User Management"
        ]

        if 'modulesAccess' in data and data.get('modulesAccess') is not None:
            submitted_modules = data.get('modulesAccess')
            if not isinstance(submitted_modules, list):
                submitted_modules = []
        else:
            if role == 'Super Admin':
                submitted_modules = ALLOWED_MODULES.copy()
            elif role == 'Admin':
                submitted_modules = ["Dashboard", "Reports", "Inventory Check", "Accounts", "User Management"]
            elif 'Manager' in role:
                submitted_modules = ["Dashboard", "Order Initiation", "Production", "Reports"]
            elif 'User' in role or role in ["Operator", "Viewer"]:
                submitted_modules = ["Dashboard", "Order Initiation"]
            else:
                existing_modules = existing_user.get('modules_access')
                submitted_modules = json.loads(existing_modules) if isinstance(existing_modules, str) else (existing_modules or [])

        # Validate final set of permissions
        final_modules = [m for m in submitted_modules if m in ALLOWED_MODULES]
        modules_json = json.dumps(final_modules)
            
        # Check duplicates for other users
        if email_id and isinstance(email_id, str) and email_id.strip():
            cursor.execute("SELECT * FROM users WHERE (contact_number = %s OR email_id = %s OR username = %s) AND user_id != %s", 
                           (contact_number, email_id, username, user_id))
        else:
            cursor.execute("SELECT * FROM users WHERE (contact_number = %s OR username = %s) AND user_id != %s", 
                           (contact_number, username, user_id))
                           
        if cursor.fetchone():
            err_msg = "User with this contact number, email, or username already exists"
            return jsonify({"success": False, "error": err_msg, "message": err_msg}), 400
            
        final_email = email_id.strip() if email_id and isinstance(email_id, str) and email_id.strip() else f"no-email-{contact_number}@sasons.local"
        
        # 3. Handle password
        password_hash = existing_user.get('password_hash')
        if data.get('password') and data.get('password').strip():
            password_hash = generate_password_hash(data.get('password'))

        query = """UPDATE users SET full_name=%s, contact_number=%s, email_id=%s, designation=%s, role=%s, 
                   username=%s, password_hash=%s, modules_access=%s, status=%s WHERE user_id=%s"""
        params = (full_name, contact_number, final_email, designation, role, username, password_hash, modules_json, status, user_id)
        
        print("Executing SQL:", query)
        print("With parameters:", params)
        cursor.execute(query, params)
            
        conn.commit()
        cursor.close(); conn.close()
        return jsonify({"success": True, "message": "User updated successfully"}), 200
    except Exception as e:
        import traceback
        traceback.print_exc()
        if conn: conn.rollback()
        return jsonify({"success": False, "error": str(e), "message": str(e)}), 500

@app.route('/users/delete/<int:user_id>', methods=['DELETE', 'OPTIONS'])
def delete_user(user_id):
    if request.method == 'OPTIONS':
        return '', 200
    is_auth, err_msg = verify_write_access_detailed('User Management')
    if not is_auth:
        return jsonify({"success": False, "message": err_msg}), 401
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("DELETE FROM users WHERE user_id = %s", (user_id,))
        
        # Reset AUTO_INCREMENT safely after deletion
        cursor.execute("SELECT COALESCE(MAX(user_id), 0) + 1 AS next_id FROM users")
        row = cursor.fetchone()
        next_id = row['next_id'] if row else 1
        cursor.execute(f"ALTER TABLE users AUTO_INCREMENT = {next_id}")
        
        conn.commit()
        cursor.close(); conn.close()
        return jsonify({"success": True, "message": "User deleted successfully"}), 200
    except Exception as e:
        if conn: conn.rollback()
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/users/login', methods=['POST', 'OPTIONS'])
def login_user():
    if request.method == 'OPTIONS':
        return '', 200
        
    data = request.json or {}
    contact = data.get('contactNumber') or data.get('contactNo') or data.get('email')
    password = data.get('password')
    
    try:
        import traceback
        
        # Log variables before processing
        print("=== LOGIN API DEBUG ===")
        print(f"data: {data}")
        print(f"contact: {contact}")
        print(f"password: {'***' if password else None}")
        
        if not contact or not password:
            return jsonify({"success": False, "error": "Invalid username or password"}), 401
            
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM users WHERE contact_number = %s OR email_id = %s OR username = %s", (contact, contact, contact))
        user = cursor.fetchone()
        
        print(f"user found in DB: {bool(user)}")
        
        if not user:
            cursor.close(); conn.close()
            return jsonify({"success": False, "error": "User does not exist."}), 404
                
        try:
            is_valid_password = check_password_hash(user['password_hash'], password)
        except Exception as e:
            traceback.print_exc()
            cursor.close(); conn.close()
            return jsonify({"success": False, "error": f"Password verification failed: {str(e)}"}), 500
            
        if not is_valid_password:
            cursor.close(); conn.close()
            return jsonify({"success": False, "error": "Incorrect password."}), 401
            
        if user.get('status') == 'Disabled':
            cursor.close(); conn.close()
            return jsonify({
                "success": False, 
                "message": "Your account has been deactivated. Please contact your Super Admin."
            }), 403
            
        cursor.execute("UPDATE users SET last_login = CURRENT_TIMESTAMP WHERE user_id = %s", (user['user_id'],))
        conn.commit()
        
        if user.get('modules_access'):
            user['modules_access'] = json.loads(user['modules_access']) if isinstance(user['modules_access'], str) else user['modules_access']
        else:
            user['modules_access'] = []
            
        if 'password_hash' in user:
            del user['password_hash']
        
        # FIX FOR LEGACY FRONTEND AUTH CONTEXT MAPPING
        user['contact_no'] = user.get('contact_number')
        user['email'] = user.get('email_id')
        user['id'] = user.get('user_id')
        
        cursor.close(); conn.close()
        return jsonify({"success": True, "user": user}), 200
    except Exception as e:
        import traceback
        import os
        
        print("\n" + "="*50)
        print("=== LOGIN EXCEPTION CAUGHT ===")
        print(f"Request Payload: {data}")
        print(f"Database Selected: {os.getenv('DB_NAME')}")
        print("Table Used: users")
        print("Exception Traceback:")
        traceback.print_exc()
        print("="*50 + "\n")
        
        return jsonify({"success": False, "error": "Internal server error. Please check backend logs."}), 500


# =====================================================================
# MODULE 1: CUSTOMERS (FULLY INSTALLED WITH ALL 8 COLUMNS)
# =====================================================================

@app.route('/customers/view', methods=['GET'])
def get_customers():
    if not verify_read_key('Order Initiation'): 
        return "Unauthorized: Invalid View API Key", 401
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM customers")
    results = cursor.fetchall()
    cursor.close(); conn.close()
    return jsonify(results)

@app.route('/customers/add', methods=['POST'])
def add_customer():
    if not verify_write_key('Sales'): 
        return "Unauthorized: Invalid Write API Key or RBAC", 401
    
    try:
        data = request.json
        if not data:
            return jsonify({"success": False, "error": "Request body must be valid JSON"}), 400
            
        # Ensure name is provided as required by your DB schema
        if not data.get('customer_name'):
            return jsonify({"success": False, "error": "customer_name is required"}), 400

        conn = get_db_connection()
        cursor = conn.cursor()
        
        # SQL execution map including all 8 descriptive columns matching your MySQL schema
        query = """
            INSERT INTO customers (
                customer_name, contact_person, phone, email, 
                shipping_address, billing_address, gst_number, cin_number
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """
        
        values = (
            data.get('customer_name'),
            data.get('contact_person') or 'Default Contact',
            data.get('phone') or '',
            data.get('email') or '',
            data.get('shipping_address') or '',
            data.get('billing_address') or '',
            data.get('gst_number') or '',
            data.get('cin_number') or ''
        )
        
        cursor.execute(query, values)
        conn.commit()
        
        new_customer_id = cursor.lastrowid
        cursor.close(); conn.close()
        
        return jsonify({
            "success": True,
            "message": "Customer saved directly to database successfully!",
            "customer_id": new_customer_id
        }), 201

    except Exception as e:
        return jsonify({"success": False, "error": f"Database insertion error: {str(e)}"}), 500

@app.route('/api/customers/validate_address', methods=['POST'])
def validate_customer_address():
    if not verify_read_key('Order Initiation') and not verify_read_key('Sales'): 
        return "Unauthorized", 401
    
    data = request.json
    address = data.get('address')
    pin = data.get('pin_code')
    
    if not address or not pin:
        return jsonify({"exists": False, "error": "Address and pin code required"}), 400
        
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT customer_name FROM customers WHERE delivery_address = %s AND pin_code = %s", (address, pin))
    match = cursor.fetchone()
    cursor.close()
    conn.close()
    
    if match:
        return jsonify({"exists": True, "data": match})
    return jsonify({"exists": False})

@app.route('/api/customers/update_address', methods=['POST'])
def update_customer_address():
    if not verify_write_key('Order Initiation') and not verify_write_key('Sales'): 
        return "Unauthorized", 401
    
    data = request.json
    customer_name = data.get('customer_name')
    address = data.get('address')
    pin_code = data.get('pin_code')
    
    if not customer_name:
        return jsonify({"success": False, "error": "customer_name is required"}), 400
        
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        # Update both fields as a single transaction block
        cursor.execute(
            "UPDATE customers SET delivery_address = %s, pin_code = %s WHERE customer_name = %s",
            (address, pin_code, customer_name)
        )
        conn.commit()
        return jsonify({"success": True, "message": "Address updated successfully"}), 200
    except Exception as e:
        conn.rollback()
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        cursor.close()
        conn.close()


# =====================================================================
# MODULE 2: PURCHASE ORDERS
# =====================================================================

@app.route('/purchase_orders/view', methods=['GET'])
def get_purchase_orders():
    if not verify_read_key('Order Initiation'):
        return jsonify({"success": False, "error": "Unauthorized: Invalid View API Key"}), 401
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM purchase_orders ORDER BY created_at DESC")
    results = cursor.fetchall()
    
    unique_results = []
    seen_pos = set()
    for row in results:
        po = row.get("po_number")
        if po and po not in seen_pos:
            unique_results.append(row)
            seen_pos.add(po)
            
    cursor.close(); conn.close()
    return jsonify(unique_results)

@app.route('/api/orders', methods=['GET'])
def get_orders_by_stage():
    import urllib.parse
    stage = request.args.get('stage')
    if stage:
        stage = urllib.parse.unquote(stage).strip()
    if not stage:
        return jsonify([]), 200
    
    if not verify_read_key('Order Initiation'):
        return jsonify([]), 200
        
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        # Filter by stage and exclude completed orders (status != 'COMPLETED')
        query = "SELECT po_number, order_date, delivery_date, customer_name, status, stage FROM purchase_orders WHERE stage = %s AND status != 'COMPLETED'"
        cursor.execute(query, (stage,))
        results = cursor.fetchall()
        
        if not results:
            results = []
            
        # Clean dates for consistency
        for row in results:
            if row.get('order_date'):
                row['order_date'] = clean_mysql_date(str(row['order_date']))
            if row.get('delivery_date'):
                row['delivery_date'] = clean_mysql_date(str(row['delivery_date']))
                
        return jsonify(results), 200
    except Exception as e:
        print(f"Error in /api/orders: {e}")
        return jsonify({"success": False, "orders": [], "message": str(e)}), 200
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@app.route('/purchase_orders/po-numbers', methods=['GET'])
def get_existing_po_numbers():
    """Returns a list of all PO numbers already saved in the database.
    Used by the frontend to prevent generating duplicate PO numbers."""
    if not verify_read_key('Order Initiation'):
        return jsonify({"success": False, "error": "Unauthorized"}), 401
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT DISTINCT po_number FROM purchase_orders WHERE po_number IS NOT NULL")
    results = cursor.fetchall()
    cursor.close(); conn.close()
    
    # Use a Python set to ensure absolute uniqueness before jsonifying
    unique_pos = list(set([r["po_number"] for r in results]))
    return jsonify({"success": True, "po_numbers": unique_pos})

@app.route('/purchase_orders/details/<string:po_number>', methods=['GET'])
def get_purchase_order_details(po_number):
    if not verify_read_key('Order Initiation'):
        return jsonify({"success": False, "error": "Unauthorized"}), 401
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        # 1. Fetch main PO details (This contains the real total value/pieces)
        cursor.execute("SELECT * FROM purchase_orders WHERE po_number = %s", (po_number,))
        po_data = cursor.fetchone()
        
        if not po_data:
            cursor.close(); conn.close()
            return jsonify({"success": False, "error": "Purchase order not found"}), 404
            
        if po_data.get('order_date'):
            po_data['order_date'] = clean_mysql_date(str(po_data['order_date']))
            
        if po_data.get('delivery_date'):
            po_data['delivery_date'] = clean_mysql_date(str(po_data['delivery_date']))
            
        # 2. Fetch specifications
        cursor.execute("SELECT * FROM specifications WHERE po_number = %s", (po_number,))
        specs = cursor.fetchall()
        
        # CORE FIX: If the specification row is missing a quantity, 
        # pull the quantity or pieces directly from the parent purchase order!
        fallback_qty = po_data.get('total_pieces') or po_data.get('quantity') or 100 # DO NOT fallback to total_value
        
        for spec in specs:
            if not spec.get('quantity') or spec['quantity'] == 0:
                spec['quantity'] = fallback_qty  # Force the 0 to become the real order size!
                
            # Calculate dynamic stock available based on SKU, sizes, and colors
            garment_desc = str(spec.get('item_description') or '').strip()
            sizes = [sz.strip() for sz in str(spec.get('size') or '').split(',') if sz.strip() and sz.strip() != 'Standard']
            colors = [c.strip() for c in str(spec.get('color') or '').split(',') if c.strip()]
            
            stock_query = "SELECT SUM(available_qty) as total, SUM(min_required) as total_min, MAX(description) as g_desc FROM store_garments WHERE is_deleted = 0 AND (LOWER(sku_no) = LOWER(%s) OR LOWER(description) LIKE LOWER(%s))"
            params = [garment_desc, f"%{garment_desc}%"]
            
            if sizes:
                placeholders = ','.join(['%s'] * len(sizes))
                stock_query += f" AND size IN ({placeholders})"
                params.extend(sizes)
                
            if colors:
                placeholders = ','.join(['%s'] * len(colors))
                stock_query += f" AND color IN ({placeholders})"
                params.extend(colors)
                
            cursor.execute(stock_query, tuple(params))
            res = cursor.fetchone()
            stock_available = float(res['total'] or 0) if res else 0
            min_req = float(res['total_min'] or 0) if res else 0
            
            spec['stock_available'] = stock_available
            spec['garment_name'] = res['g_desc'] if res and res.get('g_desc') else garment_desc
            
            if stock_available <= 0:
                stock_status = "Out of Stock"
            elif stock_available <= min_req:
                stock_status = "Low Stock"
            else:
                stock_status = "Available"
                
            spec['stockStatus'] = stock_status
            
            # Persist accurate stock status in the database
            if spec.get('spec_id'):
                cursor.execute("UPDATE specifications SET stock_available = %s, stock_status = %s WHERE spec_id = %s", (stock_available, stock_status, spec['spec_id']))
                conn.commit()
            
            # Log the complete matching process as requested
            print(f"--- MATCHING PROCESS LOG ---")
            print(f"Selected PO: {po_number}")
            print(f"Garment ID/SKU: {garment_desc}")
            print(f"Size: {sizes}")
            print(f"Color: {colors}")
            print(f"Required Qty: {spec['quantity']}")
            print(f"Store Available Qty: {stock_available}")
            print(f"Store Min Required Qty: {min_req}")
            print(f"Final Status: {stock_status}")
            print(f"----------------------------")
                
            # Explicitly separate physical count from financial totals for the frontend
            spec['required_qty'] = spec['quantity']
            spec['total_cost_value'] = po_data.get('total_value', 0.0)
            
            desc_str = str(spec.get('item_description') or '').lower()
            name_str = str(spec.get('garment_name') or '').lower()
            cat_str = str(spec.get('category') or '').lower()
            
            if ('uniform' in desc_str or 'uniform' in name_str) and cat_str in ['shirt', 'pant']:
                spec['is_uniform'] = True
            else:
                spec['is_uniform'] = False
        
        po_data["specs"] = specs
        
        # 3. Fetch BOM calculations
        cursor.execute(
            """
            SELECT 
                bom.*, 
                bom.final_qty AS required_qty,
                bom.amount AS total_cost_value,
                mat.material_name, 
                mat.unit, 
                mat.unit_price,
                mat.available_qty,
                mat.min_required
            FROM bill_of_materials bom
            JOIN store_materials mat ON bom.material_id = mat.material_id
            WHERE bom.po_number = %s
            """, (po_number,)
        )
        
        bom_calcs = cursor.fetchall()
        for item in bom_calcs:
            # Cast numerical fields explicitly to eliminate frontend string comparison glitches
            req_qty = float(item.get('required_qty') or 0)
            avail_qty = float(item.get('available_qty') or 0)
            min_req = float(item.get('min_required') or 0)
            
            item['required_qty'] = req_qty
            item['available_qty'] = avail_qty
            
            # Status rules: Base Availability
            if avail_qty <= 0:
                item['status'] = "Out of Stock"
            elif avail_qty <= min_req:
                item['status'] = "Low Stock"
            else:
                item['status'] = "Available"
                
            # Allocation Status (BOM Check)
            if avail_qty >= req_qty:
                item['allocation_status'] = "Fully Available"
            else:
                item['allocation_status'] = "Shortage"
                
            if item.get('bom_id'):
                cursor.execute("UPDATE bill_of_materials SET material_status = %s, allocation_status = %s WHERE bom_id = %s", (item['status'], item['allocation_status'], item['bom_id']))
                
        conn.commit()
                
        po_data["bom_calculations"] = bom_calcs
        
        cursor.close(); conn.close()
        
        # Frontend expects the PO object returned directly at the top level
        po_data['success'] = True
        po_data['poNumber'] = po_data.get('po_number')
        return jsonify(po_data)

    except Exception as e:
        if cursor: cursor.close()
        if conn: conn.close()
        return jsonify({"success": False, "orders": [], "message": str(e)}), 200


def clean_mysql_date(date_string):
    """
    Robust wrapper leveraging format_db_date (dateutil.parser) to ensure incoming strings
    from the frontend (e.g., ISO formats) are strictly cast to YYYY-MM-DD for MySQL storage.
    """
    return format_db_date(date_string)


@app.route('/purchase_orders/add', methods=['POST'])
def add_purchase_order():
    if not verify_write_key('Order Initiation'):
        return jsonify({"success": False, "orders": [], "message": str(e)}), 200
    data = request.json
    if not data:
        return jsonify({"success": False, "error": "No JSON body received"}), 400
        
    # DIAGNOSTIC PRINT: Check your terminal to see what the frontend sent!
    print("--- RECEIVED FRONTEND DATA ---")
    print(data)
    print("------------------------------")
        
    if data.get('status') == 'SUBMITTED':
        if not data.get('total_value') or not data.get('order_date'):
            return jsonify({"success": False, "error": "Missing required fields for submission."}), 400

    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        po_num = data.get('poNumber') or data.get('po_number')
        
        # Look across all possible naming variations from the frontend
        cust_input = (
            data.get('customerName') or 
            data.get('customer_id') or 
            data.get('customer_name') or 
            data.get('customer')
        )
        
        # =====================================================================
        # BULLETPROOF NESTED CUSTOMER HANDLING
        # =====================================================================
        final_customer_id = None

        if cust_input:
            cust_input = str(cust_input).strip()

        # If customer input is missing, default to a fallback string row
        if not cust_input or cust_input == "":
            cust_input = "Default Walk-in Customer"

        # If it is a name string rather than an ID integer, process the logic
        if not str(cust_input).isdigit():
            # Check if this customer already exists to avoid duplicate rows
            cursor.execute("SELECT customer_id FROM customers WHERE customer_name = %s", (str(cust_input),))
            existing_cust = cursor.fetchone()
            
            if existing_cust:
                final_customer_id = existing_cust[0]
            else:
                # Dynamically create the parent customer record first
                c_person = data.get('contactPerson') or data.get('contact_person') or 'Default Contact'
                c_phone = data.get('contactPhone') or data.get('contact_phone') or '0000000000'
                c_email = data.get('contactEmail') or data.get('contact_email') or 'info@customer.com'
                
                cust_query = """
                    INSERT INTO customers (customer_name, contact_person, phone, email) 
                    VALUES (%s, %s, %s, %s)
                """
                cursor.execute(cust_query, (str(cust_input), c_person, c_phone, c_email))
                final_customer_id = cursor.lastrowid
        else:
            final_customer_id = int(cust_input)

        # Check if this PO number already exists
        cursor.execute("SELECT po_number FROM purchase_orders WHERE po_number = %s", (po_num,))
        existing = cursor.fetchone()

        status = data.get('status') or 'DRAFT'
        tot_val = data.get('poAmount') or data.get('total_value') or 0
        
        formatted_order_date = clean_mysql_date(data.get('poDate') or data.get('order_date'))
        o_date = formatted_order_date
        
        # New delivery_date logic
        del_date = clean_mysql_date(data.get('deliveryDate') or data.get('delivery_date'))
        
        c_person = data.get('contactPerson') or data.get('contact_person') or data.get('contact_name') or ''
        c_phone = data.get('contactPhone') or data.get('contact_phone') or ''
        c_email = data.get('contactEmail') or data.get('contact_email') or ''
        d_type = data.get('deliveryType') or data.get('delivery_type') or ''
        d_addr = data.get('deliveryAddress') or data.get('delivery_address') or ''
        d_pin = data.get('deliveryPin') or data.get('delivery_pin') or ''
        b_comp = data.get('billTo') or data.get('billing_company') or ''
        b_addr = data.get('billingAddress') or data.get('billing_address') or ''
        b_pin = data.get('billingPin') or data.get('billing_pin') or ''
        gst = data.get('gstNo') or data.get('gst_number') or data.get('gst_no') or ''
        cin = data.get('cinNo') or data.get('cin_number') or data.get('cin_no') or ''
        tc = data.get('testCertificate') or data.get('test_certificate')
        t_cost = data.get('transportCost') or data.get('transport_cost')
        adv = data.get('advancedAmount') or data.get('advance_amount') or 0
        stg = normalize_stage(data.get('stage'))
        pt = data.get('paymentTerm') or data.get('payment_term')

        if existing:
            cursor.execute(
                """
                UPDATE purchase_orders SET 
                customer_id=%s, status=%s, total_value=%s, order_date=%s, delivery_date=%s, contact_person=%s, contact_phone=%s, contact_email=%s, delivery_type=%s, delivery_address=%s, delivery_pin=%s, billing_company=%s, billing_address=%s, billing_pin=%s, gst_number=%s, cin_number=%s, test_certificate=%s, transport_cost=%s, advance_amount=%s, stage=%s, payment_term=%s 
                WHERE po_number=%s
                """,
                (final_customer_id, status, tot_val, o_date, del_date, c_person, c_phone, c_email, d_type, d_addr, d_pin, b_comp, b_addr, b_pin, gst, cin, tc, t_cost, adv, stg, pt, po_num)
            )
        else:
            cursor.execute(
                """
                INSERT INTO purchase_orders (po_number, customer_id, status, total_value, order_date, delivery_date, contact_person, contact_phone, contact_email, delivery_type, delivery_address, delivery_pin, billing_company, billing_address, billing_pin, gst_number, cin_number, test_certificate, transport_cost, advance_amount, stage, payment_term) 
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (po_num, final_customer_id, status, tot_val, o_date, del_date, c_person, c_phone, c_email, d_type, d_addr, d_pin, b_comp, b_addr, b_pin, gst, cin, tc, t_cost, adv, stg, pt)
            )
        conn.commit()

        # Fetch the complete freshly generated order object
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM purchase_orders WHERE po_number = %s", (po_num,))
        order_record = cursor.fetchone()

        return jsonify({"success": True, "message": "Purchase Order updated successfully", "data": order_record}), 201
    except Exception as e:
        if conn:
            conn.rollback()
        err_str = str(e)
        if '1048' in err_str or 'ER_BAD_NULL_ERROR' in err_str or '23502' in err_str or 'constraint failed' in err_str.lower():
            return jsonify({"success": False, "orders": [], "message": str(e)}), 200
        return jsonify({"success": False, "error": err_str}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

# =====================================================================
# ALLOCATE PARTIAL
# =====================================================================
@app.route('/api/orders/allocate-partial', methods=['POST'])
def allocate_partial():
    if not verify_write_key('Stock Check'):
        return jsonify({"success": False, "error": "Unauthorized: Invalid Write API Key or RBAC"}), 401
    
    data = request.json
    if not data:
        return jsonify({"success": False, "error": "No JSON body received"}), 400
        
    po_number = data.get('poNumber')
    req_type = data.get('type')
    
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        if req_type == 'quality_packing':
            allocations = data.get('allocations', [])
            for alloc in allocations:
                garment_id = alloc.get('garment_id')
                allocate_qty = alloc.get('allocate_qty', 0)
                spec_id = alloc.get('spec_id')
                
                # Update store_garments by subtracting allocated_qty
                cursor.execute(
                    "UPDATE store_garments SET available_qty = GREATEST(0, available_qty - %s), blocked_qty = COALESCE(blocked_qty, 0) + %s WHERE garment_id = %s",
                    (allocate_qty, allocate_qty, garment_id)
                )
                
                # Update the allocated quantity persistently in specifications
                if spec_id:
                    cursor.execute(
                        "UPDATE specifications SET allocated_qty = COALESCE(allocated_qty, 0) + %s WHERE spec_id = %s",
                        (allocate_qty, spec_id)
                    )
            # Update PO stage to 'Quality & Packing'
            cursor.execute(
                "UPDATE purchase_orders SET stage = 'Quality & Packing' WHERE po_number = %s",
                (po_number,)
            )
        elif req_type == 'bom_calculation':
            # Update PO stage to 'BOM Calculation'
            cursor.execute(
                "UPDATE purchase_orders SET stage = 'BOM Calculation' WHERE po_number = %s",
                (po_number,)
            )
            
        conn.commit()
        return jsonify({"success": True, "message": "Allocation successful"}), 200
        
    except Exception as e:
        if conn:
            conn.rollback()
        return jsonify({"success": False, "orders": [], "message": str(e)}), 200
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


# =====================================================================
# MODULE 3: INVENTORY
# =====================================================================

@app.route('/inventory/view', methods=['GET'])
def get_inventory():
    if not verify_read_key('Store'): 
        return "Unauthorized: Invalid View API Key", 401
    
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM inventory")
        results = cursor.fetchall()
        
        if not results:
            results = []
            
        for res in results:
            qty = float(res.get('current_stock') or 0)
            price = float(res.get('unit_price') or 0)
            res['total_price'] = qty * price
            
        return jsonify(results), 200
    except Exception as e:
        print(f"Error in /inventory/view: {e}")
        return jsonify([]), 200
    finally:
        if cursor: cursor.close()
        if conn: conn.close()

@app.route('/inventory/add', methods=['POST'])
def add_inventory():
    if not verify_write_key('Store'): 
        return "Unauthorized: Invalid Write API Key", 401
    data = request.json
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO inventory (material_name, current_stock, min_threshold, unit, hsn_code, description, blocked_qty, min_required, unit_price, total_price, status) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
        (data['material_name'], data['current_stock'], data['min_threshold'], data['unit'], data['hsn_code'], data.get('description', ''), data['blocked_qty'], data['min_required'], data['unit_price'], data['total_price'], data['status'])
    )
    conn.commit()
    cursor.close(); conn.close()
    return "Inventory item added successfully"


# =====================================================================
# MODULE 4: SPECIFICATIONS
# =====================================================================

@app.route('/specifications/view', methods=['GET'])
def get_specifications():
    if not verify_read_key('Order Specifications'): 
        return "Unauthorized: Invalid View API Key", 401
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM specifications")
    results = cursor.fetchall()
    cursor.close(); conn.close()
    return jsonify(results)

@app.route('/specifications/add', methods=['POST'])
def add_specification():
    if not verify_write_key('Order Specifications'):
        return jsonify({"success": False, "error": "Unauthorized: Invalid Write API Key or RBAC"}), 401
    data = request.json
    if not data:
        return jsonify({"success": False, "error": "No JSON body received"}), 400
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO specifications (po_number, fabric_type, size, color, style, remarks, item_description, pattern, stock_available, unit_price, photo_name, use_existing_stock) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
            (
                data.get('po_number'), data.get('fabric_type'), data.get('size'),
                data.get('color'), data.get('style', 'Regular'), data.get('remarks', ''),
                data.get('item_description'), data.get('pattern', ''),
                data.get('stock_available', 0), data.get('unit_price', 0),
                data.get('photo_name', ''), data.get('use_existing_stock', 0)
            )
        )
        conn.commit()
        return jsonify({"success": True, "message": "Specification added successfully"}), 201
    except Exception as e:
        if conn:
            conn.rollback()
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


# =====================================================================
# MODULE 5: BILL OF MATERIALS (BOM)
# =====================================================================

@app.route('/bill_of_materials/view', methods=['GET'])
def get_bom():
    if not verify_read_key('Production'): 
        return "Unauthorized: Invalid View API Key", 401
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM bill_of_materials")
    results = cursor.fetchall()
    cursor.close(); conn.close()
    return jsonify(results)

@app.route('/bill_of_materials/add', methods=['POST'])
def add_bom():
    if not verify_write_key('Production'): 
        return "Unauthorized: Invalid Write API Key", 401
    data = request.json
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO bill_of_materials (po_number, material_id, per_piece_qty, final_qty, amount) VALUES (%s, %s, %s, %s, %s)",
        (data['po_number'], data['material_id'], data['per_piece_qty'], data['final_qty'], data['amount'])
    )
    conn.commit()
    cursor.close(); conn.close()
    return "Bill of Materials added successfully"


# =====================================================================
# MODULE 5.5: UNIFIED STORE ITEMS
# =====================================================================
@app.route('/store_items/view', methods=['GET', 'OPTIONS'])
def get_store_items():
    if request.method == 'OPTIONS':
        return '', 200
    if not verify_read_key('Store'): 
        return jsonify({"success": False, "error": "Unauthorized"}), 401
    try:
        page = int(request.args.get('page', 1))
        limit = int(request.args.get('limit', 10))
        offset = (page - 1) * limit
        search = request.args.get('search', '')
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        query = """
            SELECT 'Material' as type, material_id as id, hsn_code, material_name as name, description, category, unit, 
                   NULL as pattern, NULL as gender, NULL as size, NULL as color, NULL as image_url,
                   available_qty, blocked_qty, min_required, unit_price, total_price, status 
            FROM store_materials 
            WHERE is_deleted = 0
            UNION ALL
            SELECT 'Garment' as type, garment_id as id, hsn_code, sku_no as name, description, category, NULL as unit, 
                   pattern, gender, size, color, image_url,
                   available_qty, blocked_qty, min_required, unit_price, total_price, status 
            FROM store_garments 
            WHERE is_deleted = 0
        """
        params = []
        if search:
            query = f"SELECT * FROM ({query}) as combined WHERE name LIKE %s OR category LIKE %s OR hsn_code LIKE %s"
            params.extend([f"%{search}%", f"%{search}%", f"%{search}%"])
        else:
            query = f"SELECT * FROM ({query}) as combined"
            
        cursor.execute(f"SELECT COUNT(*) as count FROM ({query}) as t", tuple(params))
        total_records = cursor.fetchone()['count']
        query += " ORDER BY id DESC LIMIT %s OFFSET %s"
        params.extend([limit, offset])
        cursor.execute(query, tuple(params))
        items = cursor.fetchall()
        return jsonify({
            "success": True,
            "data": items,
            "totalRecords": total_records,
            "totalPages": (total_records + limit - 1) // limit,
            "currentPage": page
        }), 200
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        if 'cursor' in locals() and cursor: cursor.close()
        if 'conn' in locals() and conn: conn.close()

# =====================================================================
# MODULE 6: STORE MATERIALS
# =====================================================================

@app.route('/api/inventory/available-materials', methods=['GET', 'OPTIONS'])
def get_available_materials():
    if request.method == 'OPTIONS':
        return '', 200
    if not verify_read_key('Store'):
        return jsonify({"success": False, "error": "Unauthorized"}), 401
        
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        query = """
        SELECT 
            s.material_name AS MATERIAL_NAME,
            COALESCE(SUM(b.final_qty), 0) AS REQUIRED_QTY,
            s.available_qty AS AVAILABLE_QTY,
            (s.available_qty - s.min_required) AS ALLOCATABLE_QTY
        FROM store_materials s
        LEFT JOIN bill_of_materials b ON s.material_id = b.material_id
        WHERE s.is_deleted = 0
        GROUP BY s.material_id, s.material_name, s.available_qty, s.min_required
        """
        cursor.execute(query)
        results = cursor.fetchall()
        
        for r in results:
            alloc = float(r['ALLOCATABLE_QTY'] or 0)
            req = float(r['REQUIRED_QTY'] or 0)
            
            r['ALLOCATABLE_QTY'] = alloc
            r['REQUIRED_QTY'] = req
            r['AVAILABLE_QTY'] = float(r['AVAILABLE_QTY'] or 0)
            
            r['STATUS'] = 'Available' if alloc >= req else 'Shortage'
            
        return jsonify(results)
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

@app.route('/store_materials/view', methods=['GET', 'OPTIONS'])
def get_store_materials():
    if request.method == 'OPTIONS':
        return '', 200
    if not verify_read_key('Store'): 
        return jsonify({"success": False, "error": "Unauthorized: Invalid View API Key"}), 401
        
    try:
        page = int(request.args.get('page', 1))
        limit = int(request.args.get('limit', 10))
        search = request.args.get('search', '').strip()
        category = request.args.get('category', 'all')
        status = request.args.get('status', 'all')
        sort_by = request.args.get('sortBy', 'material_name')
        sort_order = request.args.get('sortOrder', 'asc').upper()

        offset = (page - 1) * limit

        query = "SELECT * FROM store_materials WHERE is_deleted = 0"
        count_query = "SELECT COUNT(*) as total FROM store_materials WHERE is_deleted = 0"
        params = []

        if search:
            search_clause = " AND (material_name LIKE %s OR hsn_code LIKE %s OR description LIKE %s)"
            query += search_clause
            count_query += search_clause
            params.extend([f"%{search}%", f"%{search}%", f"%{search}%"])

        if category != 'all':
            query += " AND category = %s"
            count_query += " AND category = %s"
            params.append(category)

        if status == 'available':
            query += " AND available_qty > 0 AND available_qty > min_required"
            count_query += " AND available_qty > 0 AND available_qty > min_required"
        elif status == 'low':
            query += " AND available_qty > 0 AND available_qty <= min_required"
            count_query += " AND available_qty > 0 AND available_qty <= min_required"
        elif status == 'out':
            query += " AND available_qty <= 0"
            count_query += " AND available_qty <= 0"

        allowed_sorts = {
            'materialName': 'material_name', 'category': 'category',
            'availableQty': 'available_qty', 'unitPrice': 'unit_price',
            'created_at': 'created_at', 'updated_at': 'updated_at'
        }
        db_sort = allowed_sorts.get(sort_by, 'material_id')
        if sort_order not in ['ASC', 'DESC']: sort_order = 'DESC'

        query += f" ORDER BY {db_sort} {sort_order} LIMIT %s OFFSET %s"
        params.extend([limit, offset])

        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        cursor.execute(count_query, params[:-2] if params else [])
        total_records = cursor.fetchone()['total']

        cursor.execute(query, params)
        results = cursor.fetchall()
        
        for res in results:
            if res.get('created_at'): res['created_at'] = str(res['created_at'])
            if res.get('updated_at'): res['updated_at'] = str(res['updated_at'])
            
            # Dynamically calculate total valuation strictly on available qty (not blocked)
            avail = float(res.get('available_qty', 0))
            price = float(res.get('unit_price', 0))
            res['total_price'] = avail * price
                
        return jsonify({"data": results, "totalRecords": total_records})
    except Exception as e:
        print(f"Error in /store_materials/view: {e}")
        return jsonify({"data": [], "totalRecords": 0, "success": False, "message": str(e)}), 200
    finally:
        if 'cursor' in locals() and cursor: cursor.close()
        if 'conn' in locals() and conn: conn.close()

@app.route('/store_materials/dashboard', methods=['GET'])
def get_store_materials_dashboard():
    if not verify_read_key('Store'): return jsonify({"success": False, "error": "Unauthorized"}), 401
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT 
                COUNT(*) as total,
                SUM(IF(available_qty > 0 AND available_qty > min_required, 1, 0)) as available,
                SUM(IF(available_qty > 0 AND available_qty <= min_required, 1, 0)) as low_stock,
                SUM(IF(available_qty <= 0, 1, 0)) as out_of_stock
            FROM store_materials WHERE is_deleted = 0
        """)
        metrics = cursor.fetchone()
        for k, v in metrics.items(): metrics[k] = int(v) if v else 0
        return jsonify(metrics)
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        if 'cursor' in locals() and cursor: cursor.close()
        if 'conn' in locals() and conn: conn.close()

@app.route('/store_materials/filters', methods=['GET'])
def get_store_materials_filters():
    if not verify_read_key('Store'): return jsonify({"success": False}), 401
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT DISTINCT category FROM store_materials WHERE is_deleted = 0 AND category IS NOT NULL AND category != ''")
        categories = [row[0] for row in cursor.fetchall()]
        cursor.execute("SELECT DISTINCT hsn_code FROM store_materials WHERE is_deleted = 0 AND hsn_code IS NOT NULL AND hsn_code != ''")
        hsn_codes = [row[0] for row in cursor.fetchall()]
        cursor.execute("SELECT DISTINCT material_name FROM store_materials WHERE is_deleted = 0 AND material_name IS NOT NULL AND material_name != ''")
        material_names = [row[0] for row in cursor.fetchall()]
        return jsonify({"categories": categories, "hsn_codes": hsn_codes, "material_names": material_names})
    except Exception as e:
        return jsonify({"success": False}), 500
    finally:
        if 'cursor' in locals() and cursor: cursor.close()
        if 'conn' in locals() and conn: conn.close()


@app.route('/store_materials/add', methods=['POST'])
def add_store_material():
    if not verify_write_key('Store'): 
        return jsonify({"success": False, "error": "Unauthorized: Invalid Write API Key or RBAC"}), 401
    
    data = request.json
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Calculate total_price automatically safely
        qty = float(data.get('available_qty', 0) or 0)
        price = float(data.get('unit_price', 0) or 0)
        total_price = qty * price

        query = """
            INSERT INTO store_materials 
            (hsn_code, material_name, description, category, unit, available_qty, blocked_qty, min_required, unit_price, total_price, status) 
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """
        values = (
            data.get('hsn_code'),
            data.get('material_name'),
            data.get('description'),
            data.get('category', 'Chemicals'),
            data.get('unit'),
            qty,
            float(data.get('blocked_qty', 0) or 0),
            float(data.get('min_required', 0) or 0),
            price,
            total_price,
            data.get('status', 'Available')
        )
        
        cursor.execute(query, values)
        conn.commit()
        cursor.close(); conn.close()
        return jsonify({"success": True, "message": "Material saved successfully"}), 201
        
    except Exception as e:
        print(f"!!! DB WRITE CRASH: {str(e)}")
        if 'conn' in locals() and conn.is_connected():
            conn.rollback()
            cursor.close(); conn.close()
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/store_materials/edit/<int:item_id>', methods=['PUT'])
def edit_store_material(item_id):
    if not verify_write_key('Store'): 
        return jsonify({"success": False, "error": "Unauthorized"}), 401
    data = request.json
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        contact = request.headers.get('X-User-Contact')
        is_super_admin = False
        if contact:
            cursor.execute("SELECT role FROM users WHERE contact_number = %s OR email_id = %s OR username = %s", (contact, contact, contact))
            user = cursor.fetchone()
            # `fetchone()` returns tuple if not dict cursor, but we didn't specify dictionary=True for this cursor initially!
            # Wait! `cursor = conn.cursor()` returns a tuple! 
            # I must use index [0] if it's a tuple. 
            # Let me just create a separate dict cursor for safety, or just check role carefully.
            if user:
                # If tuple, role is user[0]
                role = user[0] if isinstance(user, tuple) else user.get('role')
                if role == 'Super Admin':
                    is_super_admin = True
                
        min_req = float(data.get('min_required', 0) or 0)
        if not is_super_admin:
            cursor.execute("SELECT min_required FROM store_materials WHERE material_id = %s", (item_id,))
            existing = cursor.fetchone()
            if existing:
                min_req = float(existing[0] if isinstance(existing, tuple) else existing.get('min_required', 0) or 0)

        qty = float(data.get('available_qty', 0) or 0)
        price = float(data.get('unit_price', 0) or 0)
        total_price = qty * price
        
        cursor.execute(
            "UPDATE store_materials SET hsn_code=%s, material_name=%s, description=%s, category=%s, unit=%s, available_qty=%s, blocked_qty=%s, min_required=%s, unit_price=%s, total_price=%s, status=%s WHERE material_id=%s",
            (data.get('hsn_code'), data.get('material_name'), data.get('description', ''), data.get('category'), data.get('unit'), qty, float(data.get('blocked_qty', 0) or 0), min_req, price, total_price, data.get('status'), item_id)
        )
        conn.commit()
        cursor.close(); conn.close()
        return jsonify({"success": True, "message": "Store Material updated successfully"}), 200
    except Exception as e:
        print(f"!!! CRITICAL DATABASE ERROR ON EDIT MATERIAL: {str(e)}")
        if 'conn' in locals() and conn.is_connected():
            conn.rollback()
            cursor.close()
            conn.close()
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/store_materials/delete/<int:item_id>', methods=['PUT'])
def delete_store_material(item_id):
    if not verify_write_key('Store'): 
        return jsonify({"success": False, "error": "Unauthorized"}), 401
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE store_materials SET is_deleted = 1 WHERE material_id = %s", (item_id,))
        conn.commit()
        cursor.close(); conn.close()
        return jsonify({"success": True, "message": "Material removed from dashboard view."}), 200
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# =====================================================================
# MODULE 7: DELIVERY ADDRESSES
# =====================================================================

@app.route('/delivery_addresses/view', methods=['GET'])
def get_delivery_addresses():
    if not verify_read_key('Logistics'): 
        return "Unauthorized: Invalid View API Key", 401
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM delivery_addresses")
    results = cursor.fetchall()
    cursor.close(); conn.close()
    return jsonify(results)

@app.route('/delivery_addresses/add', methods=['POST'])
def add_delivery_address():
    if not verify_write_key('Sales'): 
        return "Unauthorized: Invalid Write API Key", 401
    data = request.json
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO delivery_addresses (po_number, address_line, pin_code, location_type, contact_person, contact_phone) VALUES (%s, %s, %s, %s, %s, %s)",
        (data['po_number'], data['address_line'], data['pin_code'], data['location_type'], data['contact_person'], data['contact_phone'])
    )
    conn.commit()
    cursor.close(); conn.close()
    return "Delivery Address added successfully"


# =====================================================================
# MODULE 8: STORE TRANSACTIONS (Audit logs)
# =====================================================================

@app.route('/store_transactions/view', methods=['GET'])
def get_store_transactions():
    if not verify_read_key('Store'): 
        return "Unauthorized: Invalid View API Key", 401
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM store_transactions ORDER BY transaction_date DESC")
    results = cursor.fetchall()
    cursor.close(); conn.close()
    return jsonify(results)

@app.route('/store_transactions/add', methods=['POST'])
def add_store_transaction():
    if not verify_write_key('Store'): 
        return "Unauthorized: Invalid Write API Key", 401
    data = request.json
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO store_transactions (item_type, item_id, transaction_type, quantity, remarks) VALUES (%s, %s, %s, %s, %s)",
        (data['item_type'], data['item_id'], data['transaction_type'], data['quantity'], data.get('remarks', ''))
    )
    conn.commit()
    cursor.close(); conn.close()
    return "Store Transaction added successfully"


# =====================================================================
# MODULE 9: STORE GARMENTS
# =====================================================================

@app.route('/api/garments/master-list', methods=['GET'])
def get_garments_master_list():
    if not verify_read_key('Store') and not verify_read_key('Order Initiation'):
        return jsonify({"success": False, "error": "Unauthorized"}), 401
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        # Fetch distinct SKU + Description combos
        cursor.execute("""
            SELECT garment_id, sku_no, description, category, gender, size, color 
            FROM store_garments 
            WHERE is_deleted = 0 AND sku_no IS NOT NULL AND sku_no != ''
        """)
        results = cursor.fetchall()
        return jsonify({"success": True, "data": results}), 200
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        if 'cursor' in locals() and cursor: cursor.close()
        if 'conn' in locals() and conn: conn.close()


@app.route('/store_garments/view', methods=['GET'])
def get_store_garments():
    if not verify_read_key('Store'): 
        return "Unauthorized: Invalid View API Key", 401
    try:
        page = int(request.args.get('page', 1))
        limit = int(request.args.get('limit', 10))
        search = request.args.get('search', '').strip()
        category = request.args.get('category', 'all')
        gender = request.args.get('gender', 'all')
        size = request.args.get('size', 'all')
        colour = request.args.get('colour', 'all')
        status = request.args.get('status', 'all')
        sort_by = request.args.get('sortBy', 'sku_no')
        sort_order = request.args.get('sortOrder', 'asc').upper()

        offset = (page - 1) * limit

        query = "SELECT * FROM store_garments WHERE is_deleted = 0"
        count_query = "SELECT COUNT(*) as total FROM store_garments WHERE is_deleted = 0"
        params = []

        if search:
            search_clause = " AND (sku_no LIKE %s OR category LIKE %s OR color LIKE %s OR hsn_code LIKE %s)"
            query += search_clause
            count_query += search_clause
            params.extend([f"%{search}%", f"%{search}%", f"%{search}%", f"%{search}%"])

        if category != 'all':
            query += " AND category = %s"
            count_query += " AND category = %s"
            params.append(category)
        if gender != 'all':
            query += " AND gender = %s"
            count_query += " AND gender = %s"
            params.append(gender)
        if size != 'all':
            query += " AND size = %s"
            count_query += " AND size = %s"
            params.append(size)
        if colour != 'all':
            query += " AND color = %s"
            count_query += " AND color = %s"
            params.append(colour)

        if status == 'available':
            query += " AND available_qty > 0 AND available_qty > min_required"
            count_query += " AND available_qty > 0 AND available_qty > min_required"
        elif status == 'low':
            query += " AND available_qty > 0 AND available_qty <= min_required"
            count_query += " AND available_qty > 0 AND available_qty <= min_required"
        elif status == 'out':
            query += " AND available_qty <= 0"
            count_query += " AND available_qty <= 0"

        allowed_sorts = {
            'skuNo': 'sku_no', 'category': 'category', 'price': 'unit_price',
            'availableQty': 'available_qty', 'blockedQty': 'blocked_qty',
            'createdDate': 'created_at', 'updatedDate': 'updated_at'
        }
        db_sort = allowed_sorts.get(sort_by, 'garment_id')
        if sort_order not in ['ASC', 'DESC']: sort_order = 'DESC'

        query += f" ORDER BY {db_sort} {sort_order} LIMIT %s OFFSET %s"
        params.extend([limit, offset])

        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        cursor.execute(count_query, params[:-2] if params else [])
        total_records = cursor.fetchone()['total']

        cursor.execute(query, params)
        results = cursor.fetchall()
        
        for res in results:
            if res.get('created_at'): res['created_at'] = str(res['created_at'])
            if res.get('updated_at'): res['updated_at'] = str(res['updated_at'])
            # Map frontend colour expectation
            res['colour'] = res.get('color', '')
            res['availableQty'] = float(res.get('available_qty', 0))
            res['blockedQty'] = float(res.get('blocked_qty', 0))
            res['minRequired'] = res.get('min_required', 0)
            res['unitPrice'] = float(res.get('unit_price', 0))
            # Dynamically calculate total valuation strictly on available qty (not blocked)
            res['totalPrice'] = res['availableQty'] * res['unitPrice']
                
        return jsonify({"data": results, "totalRecords": total_records})
    except Exception as e:
        print(f"Error in /store_garments/view: {e}")
        return jsonify({"data": [], "totalRecords": 0, "success": False, "message": str(e)}), 200
    finally:
        if 'cursor' in locals() and cursor: cursor.close()
        if 'conn' in locals() and conn: conn.close()

@app.route('/store_garments/dashboard', methods=['GET'])
def get_store_garments_dashboard():
    if not verify_read_key('Store'): return jsonify({"success": False, "error": "Unauthorized"}), 401
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT 
                COUNT(*) as total,
                SUM(IF(available_qty > 0 AND available_qty > min_required, 1, 0)) as available,
                SUM(IF(available_qty > 0 AND available_qty <= min_required, 1, 0)) as low_stock,
                SUM(IF(available_qty <= 0, 1, 0)) as out_of_stock
            FROM store_garments WHERE is_deleted = 0
        """)
        metrics = cursor.fetchone()
        for k, v in metrics.items(): metrics[k] = int(v) if v else 0
        return jsonify(metrics)
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        if 'cursor' in locals() and cursor: cursor.close()
        if 'conn' in locals() and conn: conn.close()

@app.route('/store_garments/filters', methods=['GET'])
def get_store_garments_filters():
    if not verify_read_key('Store'): return jsonify({"success": False}), 401
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("SELECT DISTINCT category FROM store_garments WHERE is_deleted = 0 AND category IS NOT NULL AND category != ''")
        categories = [row[0] for row in cursor.fetchall()]
        
        cursor.execute("SELECT DISTINCT gender FROM store_garments WHERE is_deleted = 0 AND gender IS NOT NULL AND gender != ''")
        genders = [row[0] for row in cursor.fetchall()]

        cursor.execute("SELECT DISTINCT size FROM store_garments WHERE is_deleted = 0 AND size IS NOT NULL AND size != ''")
        sizes = [row[0] for row in cursor.fetchall()]

        cursor.execute("SELECT DISTINCT color FROM store_garments WHERE is_deleted = 0 AND color IS NOT NULL AND color != ''")
        colours = [row[0] for row in cursor.fetchall()]

        return jsonify({"categories": categories, "genders": genders, "sizes": sizes, "colours": colours})
    except Exception as e:
        return jsonify({"success": False}), 500
    finally:
        if 'cursor' in locals() and cursor: cursor.close()
        if 'conn' in locals() and conn: conn.close()


@app.route('/store_garments/add', methods=['POST'])
def add_store_garment():
    if not verify_write_key('Store'): 
        return jsonify({"success": False, "error": "Unauthorized: Invalid Write API Key"}), 401
    
    data = request.json
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Calculate total_price automatically safely
        qty = int(data.get('available_qty', 0) or data.get('availableQty', 0) or 0)
        price = float(data.get('unit_price', 0) or data.get('unitPrice', 0) or 0)
        total_price = qty * price

        sku = data.get('sku_no') or data.get('skuNo') or data.get('sku')
        hsn = data.get('hsn_code') or data.get('hsnCode') or data.get('hsn')
        pat = data.get('pattern')
        img = data.get('image_url') or data.get('imageUrl') or data.get('image')

        query = """
            INSERT INTO store_garments 
            (sku_no, hsn_code, pattern, description, category, gender, size, color, available_qty, blocked_qty, min_required, unit_price, total_price, image_url, status) 
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """
        values = (
            sku,
            hsn,
            pat,
            data.get('description'),
            data.get('category'),
            data.get('gender'),
            data.get('size'),
            data.get('color') or data.get('colour'),
            qty,
            float(data.get('blocked_qty', 0) or data.get('blockedQty', 0) or 0),
            float(data.get('min_required', 0) or data.get('minRequired', 0) or data.get('minimumRequired', 0) or 0),
            price,
            total_price,
            img,
            data.get('status', 'Available')
        )
        
        cursor.execute(query, values)
        new_id = cursor.lastrowid
        conn.commit()
        
        cursor_dict = conn.cursor(dictionary=True)
        cursor_dict.execute("SELECT * FROM store_garments WHERE garment_id = %s", (new_id,))
        new_record = cursor_dict.fetchone()
        
        cursor_dict.close(); cursor.close(); conn.close()
        return jsonify({"success": True, "message": "Garment saved successfully", "data": new_record}), 201
        
    except Exception as e:
        print(f"!!! DB WRITE CRASH: {str(e)}")
        if 'conn' in locals() and conn.is_connected():
            conn.rollback()
            cursor.close(); conn.close()
        return jsonify({"success": False, "message": "Database write fallback engaged"}), 200
@app.route('/store_garments/edit/<int:item_id>', methods=['PUT'])
def edit_store_garment(item_id):
    if not verify_write_key('Store'): 
        return jsonify({"success": False, "error": "Unauthorized"}), 401
    data = request.json
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        contact = request.headers.get('X-User-Contact')
        is_super_admin = False
        if contact:
            cursor.execute("SELECT role FROM users WHERE contact_number = %s OR email_id = %s OR username = %s", (contact, contact, contact))
            user = cursor.fetchone()
            if user:
                role = user[0] if isinstance(user, tuple) else user.get('role')
                if role == 'Super Admin':
                    is_super_admin = True
                
        min_req = float(data.get('min_required', 0) or data.get('minRequired', 0) or data.get('minimumRequired', 0) or 0)
        if not is_super_admin:
            cursor.execute("SELECT min_required FROM store_garments WHERE garment_id = %s", (item_id,))
            existing = cursor.fetchone()
            if existing:
                min_req = float(existing[0] if isinstance(existing, tuple) else existing.get('min_required', 0) or 0)

        qty = int(data.get('available_qty', 0) or data.get('availableQty', 0) or 0)
        price = float(data.get('unit_price', 0) or data.get('unitPrice', 0) or 0)
        total_price = qty * price
        
        sku = data.get('sku_no') or data.get('skuNo') or data.get('sku')
        hsn = data.get('hsn_code') or data.get('hsnCode') or data.get('hsn')
        pat = data.get('pattern')
        img = data.get('image_url') or data.get('imageUrl') or data.get('image')

        cursor.execute(
            "UPDATE store_garments SET sku_no=%s, hsn_code=%s, pattern=%s, description=%s, category=%s, gender=%s, size=%s, color=%s, available_qty=%s, blocked_qty=%s, min_required=%s, unit_price=%s, total_price=%s, image_url=%s, status=%s WHERE garment_id=%s",
            (sku, hsn, pat, data.get('description'), data.get('category'), data.get('gender'), data.get('size'), data.get('color') or data.get('colour'), qty, float(data.get('blocked_qty', 0) or data.get('blockedQty', 0) or 0), min_req, price, total_price, img, data.get('status'), item_id)
        )
        conn.commit()
        cursor.close(); conn.close()
        return jsonify({"success": True, "message": "Store Garment updated successfully"}), 200
    except Exception as e:
        print(f"!!! CRITICAL DATABASE ERROR ON EDIT GARMENT: {str(e)}")
        if 'conn' in locals() and conn.is_connected():
            conn.rollback()
            cursor.close()
            conn.close()
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/store_garments/delete/<int:item_id>', methods=['PUT'])
def delete_store_garment(item_id):
    if not verify_write_key('Store'): 
        return jsonify({"success": False, "error": "Unauthorized"}), 401
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE store_garments SET is_deleted = 1 WHERE garment_id = %s", (item_id,))
        conn.commit()
        cursor.close(); conn.close()
        return jsonify({"success": True, "message": "Garment removed from dashboard view."}), 200
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# =====================================================================
# MODULE 10: PROCUREMENT
# =====================================================================

@app.route('/procurement/view', methods=['GET'])
def get_procurements():
    if not verify_read_key('Procurement'): 
        return "Unauthorized: Invalid View API Key", 401
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM procurement")
    results = cursor.fetchall()
    cursor.close(); conn.close()
    return jsonify(results)

@app.route('/procurement/add', methods=['POST'])
def add_procurement():
    if not verify_write_key('Procurement'): 
        return "Unauthorized: Invalid Write API Key", 401
    data = request.json
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO procurement (po_number, material_id, required_qty, supplier_name, status, supplier_contact, expected_delivery_date, invoice_number) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
        (data['po_number'], data['material_id'], data['required_qty'], data['supplier_name'], data['status'], data.get('supplier_contact', ''), data['expected_delivery_date'], data.get('invoice_number', ''))
    )
    conn.commit()
    cursor.close(); conn.close()
    return "Procurement added successfully"


@app.route('/purchase_orders/save_specifications', methods=['POST'])
def save_po_specifications():
    data = request.json
    if not data or not data.get('po_number'):
        return jsonify({"success": False, "error": "Invalid payload"}), 400
        
    po_number = data.get('po_number')
    specs = data.get('specifications', [])
    stage = data.get('stage', 'Stock Check')
    status = data.get('status', 'SUBMITTED')
    
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Update PO stage to Stock Check safely
        cursor.execute("UPDATE purchase_orders SET stage = %s, status = %s WHERE po_number = %s", (stage, status, po_number))
        
        # Delete existing specifications for this PO to prevent duplicate or orphaned rows
        cursor.execute("DELETE FROM specifications WHERE po_number = %s", (po_number,))
        
        bom_calculations = []
        # Process the specifications loop for database persistence
        if specs and isinstance(specs, list):
            for spec in specs:
                sku_raw = spec.get('sku_no') or spec.get('item_description') or ''
                sku = str(sku_raw).strip()
                
                # Extract quantities safely
                req_qty = float(spec.get('required_qty') or spec.get('requiredQty') or spec.get('quantity') or 0)
                
                # Filter out entirely empty/untouched specification default rows
                if (not sku or sku == 'UNKNOWN_SKU') and req_qty == 0:
                    continue
                    
                avail_qty = float(spec.get('available_qty') or spec.get('availableQty') or spec.get('stock_available') or 0)
                use_existing_stock = int(spec.get('useExistingStock') or spec.get('use_existing_stock') or 0)
                
                fabric_type = spec.get('category') or spec.get('fabric_type') or 'Standard'
                size = spec.get('size') or 'Standard'
                color = spec.get('color') or ''
                style = spec.get('gender') or spec.get('style') or ''
                pattern = spec.get('pattern') or ''
                unit_price = float(spec.get('unitPrice') or spec.get('unit_price') or 0.0)
                photo_name = spec.get('photoName') or spec.get('photo_name') or ''
                
                delivery_address = spec.get('deliveryAddress') or spec.get('delivery_address')
                delivery_pin = spec.get('deliveryPin') or spec.get('delivery_pin')
                
                cursor.execute("""
                    INSERT INTO specifications 
                    (po_number, item_description, quantity, fabric_type, size, color, style, pattern, stock_available, unit_price, photo_name, use_existing_stock, delivery_address, delivery_pin) 
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (po_number, sku, int(req_qty), fabric_type, size, color, style, pattern, int(avail_qty), unit_price, photo_name, use_existing_stock, delivery_address, delivery_pin))
                
                # Calculate deficit (Required - Available)
                deficit = max(0.0, req_qty - avail_qty)
                
                # Extend the spec payload with the deficit calculation
                spec_with_deficit = dict(spec)
                spec_with_deficit['deficit'] = deficit
                bom_calculations.append(spec_with_deficit)
                
        conn.commit()
        return jsonify({
            "success": True, 
            "message": "Specifications saved and BOM processed successfully",
            "bom_payload": bom_calculations
        }), 200
    except Exception as e:
        if conn: conn.rollback()
        return jsonify({"success": False, "orders": [], "message": str(e)}), 200
    finally:
        if cursor: cursor.close()
        if conn: conn.close()


# =====================================================================
# API: INVENTORY CHECK ENDPOINT FOR STOCK CHECK PAGE
# =====================================================================

@app.route('/api/check-inventory', methods=['POST'])
def check_inventory():
    """
    Automatic Stock Checking Endpoint.
    Receives PO Number, fetches specs, compares with store_garments, and returns overall status.
    """
    conn = None
    cursor = None
    try:
        data = request.get_json()
        po_number = data.get('poNumber')
        if not po_number:
            return jsonify({"success": False, "error": "poNumber is required"}), 400

        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        # 1. Fetch the BOM for this PO
        cursor.execute("""
            SELECT bom.bom_id, bom.material_id as id, 
                   bom.final_qty as required_qty, 
                   COALESCE(mat.available_qty, 0) as available_qty,
                   COALESCE(mat.material_name, 'Unknown Material') as name,
                   COALESCE(mat.category, 'Unknown') as category,
                   COALESCE(mat.unit, 'units') as unit,
                   COALESCE(mat.min_required, 0) as min_required,
                   COALESCE(mat.status, 'Out of Stock') as original_status
            FROM bill_of_materials bom
            LEFT JOIN store_materials mat ON bom.material_id = mat.material_id
            WHERE bom.po_number = %s
        """, (po_number,))
        
        bom_items = cursor.fetchall()
        
        if not bom_items:
            bom_items = []
            
        status = "AVAILABLE"
        
        for item in bom_items:
            required = float(item.get('required_qty') or 0)
            available = float(item.get('available_qty') or 0)
            min_req = float(item.get('min_required') or 0)
            
            # 1. Base Availability Status
            if available <= 0:
                base_status = "Out of Stock"
            elif available <= min_req:
                base_status = "Low Stock"
            else:
                base_status = "Available"
                
            # 2. Allocation Status (BOM Check)
            allocation_status = "Fully Available"
            if required > available:
                status = "SHORTAGE" # Overall PO status remains SHORTAGE
                allocation_status = "Partially Available" if available > 0 else "Critical Shortage"
                
            item['materialName'] = item.get('name')
            item['requiredQty'] = required
            item['availableQty'] = available
            item['allocatableQty'] = min(required, available)
            item['status'] = base_status
            item['allocationStatus'] = allocation_status
            
            if item.get('bom_id'):
                cursor.execute("UPDATE bill_of_materials SET material_status = %s, allocation_status = %s WHERE bom_id = %s", (base_status, allocation_status, item['bom_id']))
                
        conn.commit()
                    
        return jsonify({
            "success": True,
            "status": status,
            "data": bom_items
        }), 200

    except Exception as e:
        print(f"[ERROR] /api/check-inventory: {str(e)}")
        # Fallback catch block returning [] instead of null
        return jsonify({
            "success": False, 
            "status": "SHORTAGE", 
            "data": [], 
            "error": "Internal database error occurred."
        }), 500
        
    finally:
        if cursor: cursor.close()
        if conn: conn.close()

# =====================================================================
# WORKFLOW ROUTER: STOCK CHECK TO BOM TRANSITION
# =====================================================================

@app.route('/purchase_orders/check-stock-allocation/<string:po_number>', methods=['POST'])
def check_stock_allocation(po_number):
    if not verify_write_key('Stock Check'):
        return jsonify({"success": False, "error": "Unauthorized"}), 401
        
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        # 1. Fetch the materials required for this specific PO from the Bill of Materials
        cursor.execute(
            """
            SELECT bom.material_id, bom.final_qty, mat.available_qty 
            FROM bill_of_materials bom
            JOIN store_materials mat ON bom.material_id = mat.material_id
            WHERE bom.po_number = %s
            """, (po_number,)
        )
        required_items = cursor.fetchall()
        
        # Assume stock is available until proven otherwise
        stock_is_insufficient = False
        
        # 2. Compare what the order needs against what is physically in the store
        for item in required_items:
            if float(item['final_qty']) > float(item['available_qty']):
                stock_is_insufficient = True
                break # We found a shortage, no need to keep checking
                
        # 3. IF stock is missing, update the PO stage so the application advances
        if stock_is_insufficient:
            cursor.execute(
                "UPDATE purchase_orders SET stage = 'BOM Calculation' WHERE po_number = %s",
                (po_number,)
            )
            conn.commit()
            
            cursor.close(); conn.close()
            return jsonify({
                "success": True, 
                "stock_available": False, 
                "redirectTo": "/bom-calculation",
                "message": "Stock insufficient. Order advanced to BOM Calculation stage."
            }), 200
            
        # Otherwise, if everything is in stock, proceed normally
        cursor.close(); conn.close()
        return jsonify({
            "success": True, 
            "stock_available": True, 
            "redirectTo": "/production",
            "message": "All items available in stock!"
        }), 200

    except Exception as e:
        if conn: conn.rollback()
        if cursor: cursor.close()
        if conn: conn.close()
        return jsonify({"success": False, "orders": [], "message": str(e)}), 200




# =====================================================================
# API: STOCK SPLIT & ALLOCATION ENGINE
# =====================================================================

@app.route('/api/orders/split', methods=['POST'])
def split_order():
    if not verify_write_key('Stock Check'):
        return jsonify({"success": False, "error": "Unauthorized"}), 401
        
    data = request.json
    if not data:
        return jsonify({"success": False, "error": "No JSON payload provided"}), 400
        
    po_number = data.get('poNumber')
    route_to = data.get('routeTo')
    
    if not po_number:
        return jsonify({"success": False, "error": "poNumber is required"}), 400
        
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        # 1. Fetch main PO details for fallback quantity
        cursor.execute("SELECT * FROM purchase_orders WHERE po_number = %s", (po_number,))
        po_data = cursor.fetchone()
        
        if not po_data:
            return jsonify({"success": False, "error": "Purchase order not found"}), 404
            
        fallback_qty = po_data.get('total_pieces') or po_data.get('quantity') or 100 
        
        # 2. Retrieve all garment specifications for that Purchase Order
        cursor.execute("SELECT * FROM specifications WHERE po_number = %s", (po_number,))
        specs = cursor.fetchall()
        
        # 3. For each spec, check stock and allocate
        all_fully_allocated = True
        total_overall_allocated = 0
        
        for spec in specs:
            required_qty = float(spec.get('quantity') or 0)
            if required_qty == 0:
                required_qty = float(fallback_qty)
                
            garment_desc = str(spec.get('item_description') or '').strip()
            sizes = [sz.strip() for sz in str(spec.get('size') or '').split(',') if sz.strip() and sz.strip() != 'Standard']
            colors = [c.strip() for c in str(spec.get('color') or '').split(',') if c.strip()]
            
            # Fetch available garments matching criteria
            query = """
                SELECT garment_id, available_qty 
                FROM store_garments 
                WHERE is_deleted = 0 AND available_qty > 0 AND (LOWER(sku_no) = LOWER(%s) OR LOWER(description) LIKE LOWER(%s))
            """
            params = [garment_desc, f"%{garment_desc}%"]
            
            if sizes:
                placeholders = ','.join(['%s'] * len(sizes))
                query += f" AND size IN ({placeholders})"
                params.extend(sizes)
                
            if colors:
                placeholders = ','.join(['%s'] * len(colors))
                query += f" AND color IN ({placeholders})"
                params.extend(colors)
                
            cursor.execute(query, tuple(params))
            garments = cursor.fetchall()
            
            # Allocate across matching garments until required_qty is fulfilled
            remaining_req = required_qty
            total_allocated = 0
            
            for garment in garments:
                if remaining_req <= 0:
                    break
                    
                avail_qty = float(garment['available_qty'] or 0)
                if avail_qty > 0:
                    allocate_qty = min(avail_qty, remaining_req)
                    remaining_req -= allocate_qty
                    total_allocated += allocate_qty
                    
                    # Deduct from store
                    cursor.execute("UPDATE store_garments SET available_qty = GREATEST(0, available_qty - %s), blocked_qty = COALESCE(blocked_qty, 0) + %s, total_price = GREATEST(0, available_qty - %s) * unit_price WHERE garment_id = %s", (allocate_qty, allocate_qty, allocate_qty, garment['garment_id']))
                    
                    # Log transaction
                    cursor.execute(
                        "INSERT INTO store_transactions (item_type, item_id, transaction_type, quantity, remarks) VALUES ('Garment', %s, 'OUT', %s, %s)",
                        (garment['garment_id'], allocate_qty, f"Allocated for PO {po_number}")
                    )
            
            total_overall_allocated += total_allocated
            
            if remaining_req > 0:
                all_fully_allocated = False
            
            if total_allocated > 0:
                try:
                    cursor.execute("UPDATE specifications SET use_existing_stock = %s WHERE spec_id = %s", (total_allocated, spec['spec_id']))
                except Exception:
                    pass
        
        # 4. Route based on frontend request
        new_stage = "BOM Calculation"
        if route_to in ('split-quality-packing', 'split-bom-calculation'):
            if total_overall_allocated == 0 or all_fully_allocated:
                if conn: conn.rollback()
                return jsonify({"success": False, "error": "Order cannot be split. It must be partially available."}), 400
                
            new_po_number = f"{po_number}-Q"
            cursor.execute("SELECT po_number FROM purchase_orders WHERE po_number = %s", (new_po_number,))
            if cursor.fetchone():
                if conn: conn.rollback()
                return jsonify({"success": False, "error": "This order has already been split."}), 400
                
            # Copy purchase_orders row
            po_keys = [k for k in po_data.keys() if k not in ('id', 'created_at', 'updated_at', 'po_number', 'stage')]
            cols = ['po_number', 'stage'] + po_keys
            vals = [new_po_number, 'Quality & Packing'] + [po_data[k] for k in po_keys]
            placeholders = ', '.join(['%s'] * len(cols))
            cursor.execute(f"INSERT INTO purchase_orders ({', '.join(cols)}) VALUES ({placeholders})", tuple(vals))
            
            # Fetch updated specs to split them
            cursor.execute("SELECT * FROM specifications WHERE po_number = %s", (po_number,))
            updated_specs = cursor.fetchall()
            
            for spec in updated_specs:
                allocated = float(spec.get('use_existing_stock') or 0)
                orig_quantity = float(spec.get('quantity') or fallback_qty)
                
                if allocated > 0:
                    spec_keys = [k for k in spec.keys() if k not in ('spec_id', 'created_at', 'updated_at', 'po_number', 'quantity', 'use_existing_stock')]
                    s_cols = ['po_number', 'quantity', 'use_existing_stock'] + spec_keys
                    s_vals = [new_po_number, allocated, allocated] + [spec[k] for k in spec_keys]
                    s_placeholders = ', '.join(['%s'] * len(s_cols))
                    cursor.execute(f"INSERT INTO specifications ({', '.join(s_cols)}) VALUES ({s_placeholders})", tuple(s_vals))
                
                new_orig_qty = orig_quantity - allocated
                if new_orig_qty > 0:
                    cursor.execute("UPDATE specifications SET quantity = %s, use_existing_stock = 0 WHERE spec_id = %s", (new_orig_qty, spec['spec_id']))
                else:
                    cursor.execute("DELETE FROM specifications WHERE spec_id = %s", (spec['spec_id'],))
                    
            cursor.execute("UPDATE purchase_orders SET stage = %s WHERE po_number = %s", ("BOM Calculation", po_number))
            conn.commit()
            return jsonify({"success": True, "message": f"Order split successfully."}), 200
            
        elif route_to == 'quality-packing':
            if not all_fully_allocated:
                if conn: conn.rollback()
                return jsonify({"success": False, "error": "Cannot skip to Quality & Packing. Stock is not fully available for all items."}), 400
            new_stage = "Quality & Packing"
            
            cursor.execute("UPDATE purchase_orders SET stage = %s WHERE po_number = %s", (new_stage, po_number))
        elif route_to == 'calculate-bom':
            if total_overall_allocated > 0:
                if conn: conn.rollback()
                return jsonify({"success": False, "error": "Cannot skip to BOM Calculation. Stock is not 0."}), 400
            new_stage = "BOM Calculation"
            
            cursor.execute("UPDATE purchase_orders SET stage = %s WHERE po_number = %s", (new_stage, po_number))
        elif route_to == 'bom-calculation':
            new_stage = "BOM Calculation"
            cursor.execute("UPDATE purchase_orders SET stage = %s WHERE po_number = %s", (new_stage, po_number))
        conn.commit()
        
        return jsonify({"success": True, "message": f"Order allocated and routed to {new_stage}"}), 200

    except Exception as e:
        if conn: conn.rollback()
        return jsonify({"success": False, "orders": [], "message": str(e)}), 200
        
    finally:
        if cursor: cursor.close()
        if conn: conn.close()


# =====================================================================
# API: STOCK VALIDATION AND ROUTING ENGINE
# =====================================================================

@app.route('/api/orders/validate-stock', methods=['POST'])
def api_validate_stock():
    if not verify_write_key('Stock Check'):
        return jsonify({"success": False, "error": "Unauthorized"}), 401
        
    data = request.json
    if not data:
        return jsonify({"success": False, "error": "No JSON payload provided"}), 400
        
    po_number = data.get('po_number') or data.get('poNumber')
    sku_no = data.get('sku_no') or data.get('skuNo')
    req_qty_raw = data.get('required_qty') or data.get('requiredQty', 0)
    req_qty = float(req_qty_raw) if req_qty_raw else 0.0
    
    if not po_number or not sku_no:
        return jsonify({"success": False, "error": "po_number and sku_no are required"}), 400
        
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        # 1. Fetch pre-stitched stock (mapped to store_garments)
        cursor.execute("SELECT garment_id, available_qty FROM store_garments WHERE sku_no = %s AND is_deleted = 0", (sku_no,))
        garment = cursor.fetchone()
        
        available_qty = float(garment['available_qty']) if garment and garment['available_qty'] else 0.0
        
        # 2. Evaluate Match Scenarios
        if available_qty >= req_qty:
            # SCENARIO A: Full Availability Match
            cursor.execute("UPDATE store_garments SET available_qty = GREATEST(0, available_qty - %s), blocked_qty = COALESCE(blocked_qty, 0) + %s, total_price = GREATEST(0, available_qty - %s) * unit_price WHERE sku_no = %s AND is_deleted = 0", (req_qty, req_qty, req_qty, sku_no))
            cursor.execute("UPDATE purchase_orders SET stage = 'Quality & Packing' WHERE po_number = %s", (po_number,))
            if garment and garment.get('garment_id'):
                cursor.execute("INSERT INTO store_transactions (item_type, item_id, transaction_type, quantity, remarks) VALUES ('Garment', %s, 'OUT', %s, %s)", (garment['garment_id'], int(req_qty), f"Allocated fully for PO {po_number}"))
            conn.commit()
            
            return jsonify({
                "success": True,
                "scenario": "A",
                "message": "Full match available. Order routed to Quality Control.",
                "stage": "Quality & Packing",
                "shortage": 0
            }), 200
            
        else:
            # SCENARIO B: Partial Match / Total Shortage
            # Allocate available stock (which drops it to 0 or keeps it 0)
            if available_qty > 0:
                cursor.execute("UPDATE store_garments SET available_qty = 0, blocked_qty = COALESCE(blocked_qty, 0) + %s, total_price = 0 WHERE sku_no = %s AND is_deleted = 0", (available_qty, sku_no))
                if garment and garment.get('garment_id'):
                    cursor.execute("INSERT INTO store_transactions (item_type, item_id, transaction_type, quantity, remarks) VALUES ('Garment', %s, 'OUT', %s, %s)", (garment['garment_id'], int(available_qty), f"Allocated partially for PO {po_number}"))
                
            shortage = req_qty - available_qty
            
            # Route to BOM Calculation Engine
            cursor.execute("UPDATE purchase_orders SET stage = 'BOM Calculation Engine' WHERE po_number = %s", (po_number,))
            
            # BOM Integration: Cross check raw materials (store_materials) for the shortage
            cursor.execute("""
                SELECT bom.material_id, bom.per_piece_qty, mat.material_name, mat.available_qty
                FROM bill_of_materials bom
                LEFT JOIN store_materials mat ON bom.material_id = mat.material_id
                WHERE bom.po_number = %s
            """, (po_number,))
            
            raw_materials = cursor.fetchall()
            bom_deficits = []
            
            for rm in raw_materials:
                base_rm_qty = float(rm['per_piece_qty'] or 0)
                needed_raw_qty = shortage * base_rm_qty
                avail_raw = float(rm['available_qty'] or 0)
                
                rm_shortage = max(0.0, needed_raw_qty - avail_raw)
                
                bom_deficits.append({
                    "material_name": rm['material_name'] or rm['material_id'],
                    "needed": needed_raw_qty,
                    "available": avail_raw,
                    "shortage": rm_shortage
                })
                
            conn.commit()
            return jsonify({
                "success": True,
                "scenario": "B",
                "message": "Partial/Total shortage. Order routed to BOM Calculation Engine.",
                "stage": "BOM Calculation Engine",
                "shortage": shortage,
                "bom_deficits": bom_deficits
            }), 200
            
    except Exception as e:
        if conn: conn.rollback()
        return jsonify({"success": False, "orders": [], "message": str(e)}), 200
    finally:
        if cursor: cursor.close()
        if conn: conn.close()


# =====================================================================
# API: SPECIFICATION SUBMISSION TO STOCK CHECK
# =====================================================================

@app.route('/api/specifications/submit', methods=['POST'])
def submit_specifications():
    data = request.json
    if not data or not data.get('po_number'):
        return jsonify({"success": False, "error": "po_number is required"}), 400
        
    po_number = data['po_number']
    sku_no = data.get('sku_no', '')
    
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Save specification to DB (e.g. if sku_no is provided)
        if sku_no:
            # We check if a specification already exists, otherwise insert
            cursor.execute("SELECT spec_id FROM specifications WHERE po_number = %s", (po_number,))
            if cursor.fetchone():
                cursor.execute("UPDATE specifications SET item_description = %s WHERE po_number = %s", (sku_no, po_number))
            else:
                cursor.execute("INSERT INTO specifications (po_number, item_description) VALUES (%s, %s)", (po_number, sku_no))
                
        # Transition the PO workflow flag state to "Stock Check"
        cursor.execute("UPDATE purchase_orders SET stage = 'Stock Check' WHERE po_number = %s", (po_number,))
        
        conn.commit()
        return jsonify({"success": True, "message": "Specifications saved, moved to Stock Check stage."}), 200
    except Exception as e:
        if conn: conn.rollback()
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        if cursor: cursor.close()
        if conn: conn.close()


# =====================================================================
# API: PRE-STITCHED STOCK VERIFICATION LOGIC (GET METHOD)
# =====================================================================

@app.route('/api/orders/check-stock', methods=['GET'])
def get_check_stock():
    po_number = request.args.get('poNumber') or request.args.get('po_number')
    if not po_number:
        return jsonify({"success": False, "error": "poNumber is required"}), 400
        
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        # 1. Fetch PO to get the required_qty
        cursor.execute("SELECT total_pieces, quantity, total_value FROM purchase_orders WHERE po_number = %s", (po_number,))
        po = cursor.fetchone()
        
        if not po:
            return jsonify({"success": False, "error": "Purchase order not found"}), 404
            
        required_qty = float(po.get('total_pieces') or po.get('quantity') or po.get('total_value') or 0)
        
        # 2. Get sku_no (using specifications table or assume standard matching)
        cursor.execute("SELECT item_description FROM specifications WHERE po_number = %s LIMIT 1", (po_number,))
        spec = cursor.fetchone()
        sku_no = spec['item_description'] if spec and spec.get('item_description') else "UNKNOWN_SKU"
        
        # 3. Match against pre_stitched_inventory (mapped to store_garments)
        cursor.execute("SELECT garment_id, available_qty, category FROM store_garments WHERE sku_no = %s AND is_deleted = 0", (sku_no,))
        garment = cursor.fetchone()
        
        available_qty = float(garment['available_qty']) if garment and garment.get('available_qty') else 0.0
        
        # --- DYNAMIC WORKFLOW BUTTON LOGIC ---
        routing_action = "PURCHASE_REQUEST"
        payload_available_qty = 0
        payload_purchase_qty = 0
        
        is_shirt_or_pant = False
        if 'shirt' in sku_no.lower() or 'pant' in sku_no.lower():
            is_shirt_or_pant = True
        if garment and garment.get('category') and ('shirt' in garment['category'].lower() or 'pant' in garment['category'].lower()):
            is_shirt_or_pant = True
            
        is_uniform = 'uniform' in sku_no.lower()

        if is_shirt_or_pant and is_uniform:
            # Permanent bypass: directly target manufacturing breakdown
            cursor.execute("UPDATE purchase_orders SET stage = 'BOM Calculation' WHERE po_number = %s", (po_number,))
            conn.commit()
            
            return jsonify({
                "success": True,
                "has_shortage": True,
                "shortage_qty": required_qty,
                "next_step": "bom_calculation",
                "message": "Uniform detected. Routed directly to BOM Calculation.",
                "routingAction": "BOM_CALCULATION",
                "status": "Out of Stock",
                "isUniform": True,
                "availableQty": 0,
                "purchaseRequestQty": 0
            }), 200

        if available_qty >= required_qty:
            routing_action = "QUALITY_PACKING"
        elif available_qty > 0 and available_qty < required_qty:
            routing_action = "PARTIAL_SPLIT"
            payload_available_qty = available_qty
            payload_purchase_qty = required_qty - available_qty
        elif available_qty == 0:
            routing_action = "PURCHASE_REQUEST"
        # -------------------------------------
        
        # 4. CONDITIONAL WORKFLOW ROUTING ENGINE
        if available_qty >= required_qty:
            # Scenario A: Sufficient Pre-Stitched Garments Available
            cursor.execute("UPDATE store_garments SET available_qty = GREATEST(0, available_qty - %s), blocked_qty = COALESCE(blocked_qty, 0) + %s, total_price = GREATEST(0, available_qty - %s) * unit_price WHERE sku_no = %s AND is_deleted = 0", (required_qty, required_qty, required_qty, sku_no))
            cursor.execute("UPDATE purchase_orders SET stage = 'Quality & Packing' WHERE po_number = %s", (po_number,))
            if garment and garment.get('garment_id'):
                cursor.execute("INSERT INTO store_transactions (item_type, item_id, transaction_type, quantity, remarks) VALUES ('Garment', %s, 'OUT', %s, %s)", (garment['garment_id'], int(required_qty), f"Allocated fully for PO {po_number}"))
            conn.commit()
            
            return jsonify({
                "success": True,
                "has_shortage": False,
                "next_step": "quality_packing",
                "message": "100% fulfillment capability. Routed to Quality & Packing.",
                "routingAction": routing_action,
                "isUniform": is_uniform
            }), 200
            
        else:
            # Scenario B: Insufficient / Missing Pre-Stitched Garments (Shortage)
            if available_qty > 0:
                # Allocate available to sub-batch (deduct pool to 0)
                cursor.execute("UPDATE store_garments SET available_qty = 0, blocked_qty = COALESCE(blocked_qty, 0) + %s, total_price = 0 WHERE sku_no = %s AND is_deleted = 0", (available_qty, sku_no))
                if garment and garment.get('garment_id'):
                    cursor.execute("INSERT INTO store_transactions (item_type, item_id, transaction_type, quantity, remarks) VALUES ('Garment', %s, 'OUT', %s, %s)", (garment['garment_id'], int(available_qty), f"Allocated partially for PO {po_number}"))
                
            shortage_qty = required_qty - available_qty
            
            # Update PO workflow flag
            cursor.execute("UPDATE purchase_orders SET stage = 'BOM Calculation' WHERE po_number = %s", (po_number,))
            conn.commit()
            
            return jsonify({
                "success": True,
                "has_shortage": True,
                "shortage_qty": shortage_qty,
                "next_step": "bom_calculation",
                "message": f"Shortage detected ({shortage_qty} units). Routed to BOM Calculation.",
                "routingAction": routing_action,
                "availableQty": payload_available_qty,
                "purchaseRequestQty": payload_purchase_qty,
                "isUniform": is_uniform
            }), 200
            
    except Exception as e:
        if conn: conn.rollback()
        return jsonify({"success": False, "orders": [], "message": str(e)}), 200
    finally:
        if cursor: cursor.close()
        if conn: conn.close()

# =====================================================================
# API: WORKFLOW STATE TRANSITION (BYPASS TO PACKING)
# =====================================================================

@app.route('/purchase_orders/bypass_to_packing', methods=['POST'])
def bypass_to_packing():
    data = request.get_json()
    if not data or not data.get('poNumber'):
        return jsonify({"success": False, "items": [], "message": "poNumber is required"}), 200
        
    po_number = data['poNumber']
    
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        # 1. Update the master workflow tracking status record
        cursor.execute("UPDATE purchase_orders SET stage = 'Quality & Packing' WHERE po_number = %s", (po_number,))
        
        # 2. Log transaction audit entries and adjust stock logs
        # Attempt to deduct from stock safely
        cursor.execute("SELECT item_description, quantity FROM specifications WHERE po_number = %s LIMIT 1", (po_number,))
        spec = cursor.fetchone()
        
        if spec and spec.get('item_description'):
            sku_no = spec['item_description']
            try:
                requested_qty = float(spec.get('quantity') or 0)
            except (ValueError, TypeError):
                requested_qty = 0.0
            
            if requested_qty > 0:
                cursor.execute("SELECT garment_id FROM store_garments WHERE sku_no = %s AND is_deleted = 0", (sku_no,))
                garment = cursor.fetchone()
                if garment:
                    cursor.execute("UPDATE store_garments SET available_qty = GREATEST(0, available_qty - %s), blocked_qty = COALESCE(blocked_qty, 0) + %s, total_price = GREATEST(0, available_qty - %s) * unit_price WHERE sku_no = %s AND is_deleted = 0", (requested_qty, requested_qty, requested_qty, sku_no))
                    cursor.execute("INSERT INTO store_transactions (item_type, item_id, transaction_type, quantity, remarks) VALUES ('Garment', %s, 'OUT', %s, %s)", (garment['garment_id'], int(requested_qty), f"Allocated fully for PO {po_number} (Bypass to Packing)"))
                
        conn.commit()
        return jsonify({"success": True, "message": "State transitioned seamlessly"})
        
    except Exception as e:
        print(f"Error in bypass_to_packing: {str(e)}")
        if conn: conn.rollback()
        return jsonify({"success": False, "orders": [], "message": str(e)}), 200
    finally:
        if cursor: cursor.close()
        if conn: conn.close()

# =====================================================================
# API: PROCESS STOCK ALLOCATION (SINGLE PO WORKFLOW)
# =====================================================================

# =====================================================================
# API: PROCESS STOCK ALLOCATION (DUAL BUTTON SPLIT WORKFLOW)
# =====================================================================

@app.route('/api/orders/split', methods=['POST'])
def split_purchase_order():
    data = request.get_json()
    if not data or not data.get('poNumber'):
        return jsonify({"success": False, "items": [], "message": "poNumber is required"}), 200
        
    po_number = data.get('poNumber')
    
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        # 1. Fetch main PO details
        cursor.execute("SELECT * FROM purchase_orders WHERE po_number = %s", (po_number,))
        po_data = cursor.fetchone()
        
        if not po_data:
            return jsonify({"success": False, "items": [], "message": "Purchase order not found"}), 200
            
        # 2. Fetch specifications with live stock check
        cursor.execute("""
            SELECT s.*, 
                   COALESCE((SELECT available_qty FROM store_garments sg WHERE sg.sku_no = s.item_description OR sg.description = s.item_description LIMIT 1), 0) AS live_stock_available 
            FROM specifications s 
            WHERE s.po_number = %s
        """, (po_number,))
        specs = cursor.fetchall()
        
        if not specs:
            specs = []
            
        try:
            fallback_qty = float(po_data.get('total_pieces') or po_data.get('quantity') or 100)
        except (ValueError, TypeError):
            fallback_qty = 100.0
        
        stk_po_number = f"{po_number}-STK"
        prd_po_number = f"{po_number}-PRD"
        
        # Create STK Order (Quality & Packing)
        cursor.execute(
            """
            INSERT INTO purchase_orders (po_number, customer_id, status, total_value, order_date, delivery_date, contact_person, contact_phone, contact_email, delivery_type, delivery_address, delivery_pin, billing_company, billing_address, billing_pin, gst_number, cin_number, test_certificate, transport_cost, advance_amount, payment_term, stage) 
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (stk_po_number, po_data.get('customer_id'), po_data.get('status'), po_data.get('total_value'), po_data.get('order_date'), po_data.get('delivery_date'), po_data.get('contact_person'), po_data.get('contact_phone'), po_data.get('contact_email'), po_data.get('delivery_type'), po_data.get('delivery_address'), po_data.get('delivery_pin'), po_data.get('billing_company'), po_data.get('billing_address'), po_data.get('billing_pin'), po_data.get('gst_number'), po_data.get('cin_number'), po_data.get('test_certificate'), po_data.get('transport_cost'), po_data.get('advance_amount'), po_data.get('payment_term'), 'Quality & Packing')
        )
        
        # Create PRD Order (BOM Calculation)
        cursor.execute(
            """
            INSERT INTO purchase_orders (po_number, customer_id, status, total_value, order_date, delivery_date, contact_person, contact_phone, contact_email, delivery_type, delivery_address, delivery_pin, billing_company, billing_address, billing_pin, gst_number, cin_number, test_certificate, transport_cost, advance_amount, payment_term, stage) 
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (prd_po_number, po_data.get('customer_id'), po_data.get('status'), po_data.get('total_value'), po_data.get('order_date'), po_data.get('delivery_date'), po_data.get('contact_person'), po_data.get('contact_phone'), po_data.get('contact_email'), po_data.get('delivery_type'), po_data.get('delivery_address'), po_data.get('delivery_pin'), po_data.get('billing_company'), po_data.get('billing_address'), po_data.get('billing_pin'), po_data.get('gst_number'), po_data.get('cin_number'), po_data.get('test_certificate'), po_data.get('transport_cost'), po_data.get('advance_amount'), po_data.get('payment_term'), 'BOM Calculation')
        )
        
        has_stk = False
        has_prd = False
        
        for spec in specs:
            try:
                req_qty = float(spec.get('quantity') or fallback_qty)
            except (ValueError, TypeError):
                req_qty = fallback_qty
                
            try:
                avail = float(spec.get('live_stock_available') or 0)
            except (ValueError, TypeError):
                avail = 0.0
            
            stk_qty = min(avail, req_qty)
            prd_qty = req_qty - stk_qty
            
            if stk_qty > 0:
                has_stk = True
                cursor.execute(
                    "INSERT INTO specifications (po_number, fabric_type, size, color, style, remarks, item_description, pattern, stock_available, unit_price, photo_name, use_existing_stock, quantity, delivery_address, delivery_pin) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                    (stk_po_number, spec.get('fabric_type'), spec.get('size'), spec.get('color'), spec.get('style'), spec.get('remarks'), spec.get('item_description'), spec.get('pattern'), spec.get('stock_available'), spec.get('unit_price'), spec.get('photo_name'), stk_qty, stk_qty, spec.get('delivery_address'), spec.get('delivery_pin'))
                )
                # Deduct from store_garments
                cursor.execute("UPDATE store_garments SET available_qty = GREATEST(0, available_qty - %s), blocked_qty = COALESCE(blocked_qty, 0) + %s, total_price = GREATEST(0, available_qty - %s) * unit_price WHERE (sku_no = %s OR description = %s) AND is_deleted = 0", (stk_qty, stk_qty, stk_qty, spec.get('item_description'), spec.get('item_description')))
                
            if prd_qty > 0:
                has_prd = True
                cursor.execute(
                    "INSERT INTO specifications (po_number, fabric_type, size, color, style, remarks, item_description, pattern, stock_available, unit_price, photo_name, use_existing_stock, quantity, delivery_address, delivery_pin) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                    (prd_po_number, spec.get('fabric_type'), spec.get('size'), spec.get('color'), spec.get('style'), spec.get('remarks'), spec.get('item_description'), spec.get('pattern'), spec.get('stock_available'), spec.get('unit_price'), spec.get('photo_name'), 0, prd_qty, spec.get('delivery_address'), spec.get('delivery_pin'))
                )
                
        # Mark original PO as Split
        cursor.execute("UPDATE purchase_orders SET stage = 'Split' WHERE po_number = %s", (po_number,))
        
        if not has_stk:
            cursor.execute("DELETE FROM purchase_orders WHERE po_number = %s", (stk_po_number,))
        if not has_prd:
            cursor.execute("DELETE FROM purchase_orders WHERE po_number = %s", (prd_po_number,))
            
        conn.commit()
        return jsonify({"success": True, "message": "Order split successfully", "has_stk": has_stk, "has_prd": has_prd, "stk_po": stk_po_number, "prd_po": prd_po_number})
        
    except Exception as e:
        print(f"Error in split_purchase_order: {str(e)}")
        if conn: conn.rollback()
        return jsonify({"success": False, "orders": [], "message": str(e)}), 200
    finally:
        if cursor: cursor.close()
        if conn: conn.close()
        
# =====================================================================

# API: GENERIC WORKFLOW STAGE UPDATE
# =====================================================================

@app.route('/purchase_orders/update_stage', methods=['POST'])
def update_po_stage():
    data = request.get_json()
    if not data or not data.get('poNumber') or not data.get('stage'):
        return jsonify({"success": False, "error": "poNumber and stage are required"}), 400
        
    po_number = data['poNumber']
    # Enforce stage normalization
    stage = normalize_stage(data['stage'])
    
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("UPDATE purchase_orders SET stage = %s WHERE po_number = %s", (stage, po_number))
        conn.commit()
        
        return jsonify({"success": True, "message": f"Order stage successfully updated to {stage}"})
        
    except Exception as e:
        if conn: conn.rollback()
        return jsonify({"success": False, "orders": [], "message": str(e)}), 200
    finally:
        if cursor: cursor.close()
        if conn: conn.close()


@app.route('/purchase_orders/update_status', methods=['POST'])
def update_po_status():
    conn = None
    cursor = None
    try:
        data = request.get_json() or {}
        po_number = data.get('poNumber')
        new_status = data.get('status', 'In Progress')
        quality_stages = data.get('qualityStages')
        
        if not po_number:
            return jsonify({"success": False, "message": "Missing PO Number"}), 400

        import json
        quality_stages_json = json.dumps(quality_stages) if quality_stages else '[]'

        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute(
            "UPDATE purchase_orders SET status = %s, quality_stages = %s WHERE po_number = %s", 
            (new_status, quality_stages_json, po_number)
        )
        conn.commit()

        cursor.execute("SELECT * FROM purchase_orders WHERE po_number = %s", (po_number,))
        order = cursor.fetchone()

        return jsonify({
            "success": True, 
            "message": "Order status updated successfully",
            "poNumber": po_number,
            "status": new_status,
            "order": order
        }), 200

    except Exception as e:
        print(f"Defensive Override - Caught BOM/Status Exception: {e}")
        if conn: conn.rollback()
        # Secure Fallback: Returns a valid response payload instead of dropping into a 500 crash
        return jsonify({"success": False, "orders": [], "message": str(e)}), 200
    finally:
        if cursor: cursor.close()
        if conn: conn.close()


# =====================================================================
# API: DYNAMIC BOM CALCULATION
# Calculates BOM dynamically based on consumption_formulas and specs
# =====================================================================
@app.route('/api/bom/calculate/<po_number>', methods=['GET'])
def calculate_bom(po_number):
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        # 1. Fetch PO for fallback quantity
        cursor.execute("SELECT * FROM purchase_orders WHERE po_number = %s", (po_number,))
        po_data = cursor.fetchone()
        if not po_data:
            return jsonify({"success": False, "items": [], "message": "Purchase order not found"}), 404
            
        fallback_qty = float(po_data.get('total_pieces') or po_data.get('quantity') or 100)
        
        # 2. Fetch specifications with their category from store_garments
        cursor.execute("""
            SELECT s.*, sg.category as garment_category
            FROM specifications s
            LEFT JOIN store_garments sg ON s.item_description = sg.sku_no
            WHERE s.po_number = %s
        """, (po_number,))
        specs = cursor.fetchall()
        
        if not specs:
            specs = []
            
        # 3. Fetch all active store materials
        cursor.execute("SELECT * FROM store_materials WHERE is_deleted = 0")
        store_materials = cursor.fetchall()
        if not store_materials:
            store_materials = []
            
        mat_groups = {}
        
        # 4. Aggregate required materials across all specs
        for spec in specs:
            req_qty = float(spec.get('quantity') or 0)
            if req_qty == 0:
                req_qty = fallback_qty
            use_existing = float(spec.get('use_existing_stock') or 0)
            prod_qty = max(0, req_qty - use_existing)
            
            if prod_qty <= 0:
                continue
                
            g_cat = str(spec.get('garment_category') or 'default').lower()
            
            cursor.execute("SELECT * FROM consumption_formulas WHERE garment_category = %s", (g_cat,))
            formulas = cursor.fetchall()
            
            if not formulas:
                cursor.execute("SELECT * FROM consumption_formulas WHERE garment_category = 'default'")
                formulas = cursor.fetchall()
                
            if not formulas:
                formulas = []
                
            for formula in formulas:
                try:
                    per_piece = float(formula.get('per_piece_qty', 0))
                except (ValueError, TypeError):
                    per_piece = 0.0
                    
                if per_piece <= 0:
                    continue
                    
                mat_id = formula.get('material_id')
                if not mat_id:
                    continue
                
                matched_mat = next((m for m in store_materials if m.get('material_id') == mat_id), None)
                if not matched_mat:
                    continue
                    
                if mat_id not in mat_groups:
                    mat_groups[mat_id] = {
                        "groupKey": matched_mat.get('category', 'Material'),
                        "material_id": mat_id,
                        "name": matched_mat.get('material_name', 'Unknown'),
                        "unit": matched_mat.get('unit', 'units'),
                        "unitPrice": float(matched_mat.get('unit_price') or 0),
                        "perPiece": 0,
                        "totalBase": 0
                    }
                mat_groups[mat_id]['totalBase'] += per_piece * prod_qty
                mat_groups[mat_id]['perPiece'] = per_piece
                
        # 5. Format output
        calculated_materials = []
        raw_wastage = request.args.get('wastage', '5')
        try:
            wastage_pct = float(raw_wastage)
        except (ValueError, TypeError):
            wastage_pct = 5.0
            
        for mat_id, data in mat_groups.items():
            total_base = data['totalBase']
            wastage_amt = total_base * (wastage_pct / 100)
            final_qty = int(total_base + wastage_amt) + (1 if (total_base + wastage_amt) % 1 > 0 else 0)
            
            calculated_materials.append({
                "groupKey": data['groupKey'],
                "material_id": data['material_id'],
                "name": data['name'],
                "unit": data['unit'],
                "perPiece": data['perPiece'],
                "baseRequired": round(total_base, 2),
                "wastageAmt": round(wastage_amt, 2),
                "finalQty": final_qty,
                "unitPrice": data['unitPrice']
            })
            
        return jsonify({"success": True, "data": calculated_materials}), 200
        
    except Exception as e:
        print(f"Error in BOM Calculation: {str(e)}")
        if conn: conn.rollback()
        return jsonify({"success": False, "orders": [], "message": str(e)}), 200
    finally:
        if cursor: cursor.close()
        if conn: conn.close()


# =====================================================================
# MODULE: BOM SAVE
# Saves BOM calculation lines to the bill_of_materials table and
# advances the PO stage to 'Material Allocation'.
# =====================================================================
@app.route('/api/bom/save', methods=['POST', 'OPTIONS'])
def save_bom():
    if request.method == 'OPTIONS':
        return '', 200
    if not verify_write_key('Production'):
        return jsonify({"success": False, "error": "Unauthorized"}), 401

    data = request.json
    if not data:
        return jsonify({"success": False, "error": "No JSON body received"}), 400

    po_number = data.get('poNumber')
    bom_lines = data.get('bomLines', [])   # [{material_id, per_piece_qty, final_qty, amount}]
    wastage_pct = data.get('wastagePct', 5)

    if not po_number:
        return jsonify({"success": False, "error": "poNumber is required"}), 400

    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # Delete existing BOM lines for this PO before re-inserting
        cursor.execute("DELETE FROM bill_of_materials WHERE po_number = %s", (po_number,))

        for line in bom_lines:
            material_id = line.get('material_id')
            material_name = line.get('material_name', material_id)
            category = line.get('category', 'Material')
            unit = line.get('unit', 'units')
            per_piece_qty = float(line.get('per_piece_qty', 0))
            final_qty = float(line.get('final_qty', 0))
            amount = float(line.get('amount', 0))
            
            if not material_name or final_qty <= 0:
                continue
                
            # Attempt to map by exact material_id or by material_name
            cursor.execute("SELECT material_id FROM store_materials WHERE material_id = %s OR material_name = %s LIMIT 1", (material_id, material_name))
            row = cursor.fetchone()
            
            if not row:
                # Material doesn't exist in DB (it's from frontend mock). Auto-insert it.
                cursor.execute(
                    "INSERT INTO store_materials (material_name, category, unit, available_qty, min_required, unit_price, status, is_deleted) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                    (material_name, category, unit, 0, 0, 1.0, 'Active', 0)
                )
                actual_mat_id = cursor.lastrowid
            else:
                actual_mat_id = row[0]
                
            cursor.execute(
                "INSERT INTO bill_of_materials (po_number, material_id, per_piece_qty, final_qty, amount) VALUES (%s, %s, %s, %s, %s)",
                (po_number, actual_mat_id, per_piece_qty, final_qty, amount)
            )

        # Advance PO stage to Inventory Check
        cursor.execute(
            "UPDATE purchase_orders SET stage = 'Inventory Check' WHERE po_number = %s",
            (po_number,)
        )

        conn.commit()
        return jsonify({"success": True, "message": "BOM saved and stage advanced to Inventory Check"}), 200

    except Exception as e:
        if conn:
            conn.rollback()
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        if cursor: cursor.close()
        if conn: conn.close()


# =====================================================================
# MODULE: BOM MATERIAL ALLOCATION (Hard Reservation Lock)
# Cross-references BOM requirements against store_materials.
# Locks available materials (reduces available_qty, increases blocked_qty).
# Creates procurement rows for shortages.
# Advances PO stage to 'Production' or 'Procurement' depending on result.
# =====================================================================
@app.route('/api/bom/allocate-materials', methods=['POST', 'OPTIONS'])
def allocate_bom_materials():
    if request.method == 'OPTIONS':
        return '', 200
    if not verify_write_key('Production'):
        return jsonify({"success": False, "error": "Unauthorized"}), 401

    data = request.json
    if not data:
        return jsonify({"success": False, "error": "No JSON body received"}), 400

    po_number = data.get('poNumber')
    allocations = data.get('allocations', [])
    # allocations: [{material_id, material_name, required_qty, available_qty, allocate_qty, shortage_qty}]

    if not po_number:
        return jsonify({"success": False, "error": "poNumber is required"}), 400

    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        has_shortage = False
        allocation_results = []

        for alloc in allocations:
            material_id = alloc.get('material_id')
            allocate_qty = float(alloc.get('allocate_qty', 0))
            shortage_qty = float(alloc.get('shortage_qty', 0))
            material_name = alloc.get('material_name', '')
            required_qty = float(alloc.get('required_qty', 0))

            if not material_id:
                continue

            # Hard lock: Deduct allocated quantity from store
            if allocate_qty > 0:
                cursor.execute("""
                    UPDATE store_materials
                    SET available_qty = GREATEST(0, available_qty - %s),
                        blocked_qty = COALESCE(blocked_qty, 0) + %s,
                        total_price = GREATEST(0, available_qty - %s) * unit_price
                    WHERE material_id = %s
                """, (allocate_qty, allocate_qty, allocate_qty, material_id))

            # Handle shortage: push to procurement queue
            if shortage_qty > 0:
                has_shortage = True
                # Check if procurement entry already exists for this PO+material
                cursor.execute("""
                    SELECT procurement_id FROM procurement
                    WHERE po_number = %s AND material_id = %s
                """, (po_number, material_id))
                existing_proc = cursor.fetchone()

                if existing_proc:
                    cursor.execute("""
                        UPDATE procurement
                        SET required_qty = %s, status = 'Pending Procurement'
                        WHERE po_number = %s AND material_id = %s
                    """, (shortage_qty, po_number, material_id))
                else:
                    cursor.execute("""
                        INSERT INTO procurement
                        (po_number, material_id, required_qty, supplier_name, status, supplier_contact, expected_delivery_date, invoice_number)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    """, (po_number, material_id, shortage_qty, 'Auto Assigned (Shortage)', 'Pending Procurement', '', None, ''))

            allocation_results.append({
                "material_id": material_id,
                "allocate_qty": allocate_qty,
                "shortage_qty": shortage_qty,
                "status": "Shortage" if shortage_qty > 0 else "Allocated"
            })

        # Advance PO stage
        next_stage = 'Procurement' if has_shortage else 'Production'
        cursor.execute(
            "UPDATE purchase_orders SET stage = %s WHERE po_number = %s",
            (next_stage, po_number)
        )

        conn.commit()
        return jsonify({
            "success": True,
            "next_stage": next_stage,
            "has_shortage": has_shortage,
            "allocations": allocation_results,
            "message": f"Materials allocated. PO advanced to {next_stage}."
        }), 200

    except Exception as e:
        if conn:
            conn.rollback()
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        if cursor: cursor.close()
        if conn: conn.close()


# =====================================================================
# MODULE: DASHBOARD SUMMARY
# =====================================================================

@app.route('/api/dashboard/summary', methods=['GET'])
def get_dashboard_summary():
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        # 1. Total Orders
        cursor.execute("SELECT COUNT(*) as count FROM purchase_orders")
        total_orders = cursor.fetchone().get('count', 0)
        
        # 2. Active Production (Sum quantity where In Progress or active stage)
        try:
            cursor.execute("""
                SELECT COALESCE(SUM(s.quantity), 0) as active_count
                FROM purchase_orders p
                JOIN specifications s ON p.po_number = s.po_number
                WHERE p.status = 'In Progress' 
                   OR p.stage IN ('BOM Calculation', 'Inventory Check', 'Material Allocation', 'Procurement', 'Material Release', 'Production')
            """)
            active_prod_result = cursor.fetchone()
            active_prod = float(active_prod_result.get('active_count', 0) or 0)
        except Exception:
            # Fallback if specification join fails
            cursor.execute("""
                SELECT COUNT(*) as active_count
                FROM purchase_orders 
                WHERE status = 'In Progress' 
                   OR stage IN ('BOM Calculation', 'Inventory Check', 'Material Allocation', 'Procurement', 'Material Release', 'Production')
            """)
            active_prod_result = cursor.fetchone()
            active_prod = float(active_prod_result.get('active_count', 0) or 0)

        # 3. Pending Procurement
        cursor.execute("SELECT COUNT(*) as count FROM purchase_orders WHERE stage = 'Procurement'")
        pending_procurement = cursor.fetchone().get('count', 0)
        
        # 4. Inventory Alerts
        mat_alerts = 0
        gar_alerts = 0
        try:
            cursor.execute("SELECT COUNT(*) as count FROM store_materials WHERE available_qty < min_required AND is_deleted = 0")
            mat_alerts = cursor.fetchone().get('count', 0)
        except Exception:
            pass
        try:
            cursor.execute("SELECT COUNT(*) as count FROM store_garments WHERE available_qty < min_required AND is_deleted = 0")
            gar_alerts = cursor.fetchone().get('count', 0)
        except Exception:
            pass
        inventory_alerts = mat_alerts + gar_alerts
        
        # 5. Recent Orders (limit 5)
        try:
            cursor.execute("""
                SELECT po.*, c.customer_name as c_name
                FROM purchase_orders po
                LEFT JOIN customers c ON po.customer_id = c.customer_id
                ORDER BY po.created_at DESC
                LIMIT 5
            """)
        except Exception:
            # Fallback if created_at doesn't exist
            cursor.execute("""
                SELECT po.*, c.customer_name as c_name
                FROM purchase_orders po
                LEFT JOIN customers c ON po.customer_id = c.customer_id
                ORDER BY po.po_number DESC
                LIMIT 5
            """)
            
        recent_orders_raw = cursor.fetchall()
        recent_orders = []
        from datetime import datetime
        now = datetime.now()
        
        for po in recent_orders_raw:
            del_days = 0
            if po.get('status') not in ['Completed', 'Delivered'] and po.get('delivery_date'):
                try:
                    ddate = po['delivery_date']
                    if isinstance(ddate, str):
                        # Some formats might be YYYY-MM-DD
                        ddate = datetime.strptime(ddate.split(' ')[0].split('T')[0], "%Y-%m-%d")
                    diff = (now.date() - ddate.date()).days if hasattr(ddate, 'date') else (now - ddate).days
                    if diff > 0:
                        del_days = diff
                except Exception:
                    pass
                    
            recent_orders.append({
                "id": po.get('po_number'),
                "poNumber": po.get('po_number'),
                "customerName": po.get('customer_name') or po.get('c_name') or 'Unknown',
                "currentStage": po.get('stage') or po.get('status') or 'Order Initiation',
                "poDate": str(po.get('order_date')) if po.get('order_date') else '',
                "deliveryDate": str(po.get('delivery_date')) if po.get('delivery_date') else '',
                "delayDays": del_days,
                "delayReason": po.get('delay_reason') or '',
                "amount": float(po.get('total_value') or po.get('total_amount') or po.get('advance_amount') or 0)
            })

        return jsonify({
            "success": True,
            "statsData": {
                "totalOrders": total_orders,
                "activeProduction": active_prod,
                "pendingProcurement": pending_procurement,
                "inventoryAlerts": inventory_alerts
            },
            "recentOrders": recent_orders
        }), 200

    except Exception as e:
        print(f"Error in Dashboard Summary: {e}")
        if conn: conn.rollback()
        return jsonify({
            "success": False,
            "statsData": {
                "totalOrders": 0,
                "activeProduction": 0,
                "pendingProcurement": 0,
                "inventoryAlerts": 0
            },
            "recentOrders": []
        }), 200
    finally:
        if cursor: cursor.close()
        if conn: conn.close()

# =====================================================================
# UNIFIED REPORTS API (Dashboard Sub-Pages)
# =====================================================================

@app.route('/api/reports/orders', methods=['GET'])
def report_orders():
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute('''
            SELECT po_number, customer_name, order_date, delivery_date, stage, total_value, total_pieces, status 
            FROM purchase_orders 
            ORDER BY created_at DESC
        ''')
        orders = cursor.fetchall()
        
        results = []
        for o in orders:
            raw_stage = o.get('stage') or o.get('status') or 'Pending'
            raw_stage = raw_stage.lower()
            
            mapped_status = 'Pending'
            if 'progress' in raw_stage or 'production' in raw_stage:
                mapped_status = 'In Production'
            elif 'cut' in raw_stage:
                mapped_status = 'Cutting'
            elif 'deliver' in raw_stage or 'complete' in raw_stage:
                mapped_status = 'Delivered'
            elif 'pend' in raw_stage or 'initiation' in raw_stage or 'draft' in raw_stage:
                mapped_status = 'Pending'
            else:
                mapped_status = 'Pending'
                
            results.append({
                'id': o.get('po_number'),
                'customer': o.get('customer_name') or 'Unknown',
                'items': o.get('total_pieces') or 0,
                'poDate': format_db_date(str(o.get('order_date'))) if o.get('order_date') else '',
                'deliveryDate': format_db_date(str(o.get('delivery_date'))) if o.get('delivery_date') else '',
                'status': mapped_status,
                'amount': float(o.get('total_value') or 0)
            })
            
        return jsonify(results), 200
    except Exception as e:
        print(f"Error in /api/reports/orders: {e}")
        return jsonify({"success": False, "orders": [], "message": str(e)}), 200
    finally:
        if cursor: cursor.close()
        if conn: conn.close()


@app.route('/api/reports/active-production', methods=['GET'])
def report_active_production():
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute('''
            SELECT po_number, customer_name, order_date, delivery_date, stage, status, total_pieces, quantity 
            FROM purchase_orders 
            WHERE status = 'In Progress' OR stage LIKE '%Production%' OR stage = 'In Progress'
        ''')
        orders = cursor.fetchall()
        
        results = []
        for o in orders:
            results.append({
                'poNumber': o.get('po_number'),
                'style': o.get('customer_name') or 'Standard Garment',
                'stage': o.get('stage') or 'In Progress',
                'qty': o.get('total_pieces') or o.get('quantity') or 0,
                'startDate': format_db_date(str(o.get('order_date'))) if o.get('order_date') else '',
                'expectedCompletion': format_db_date(str(o.get('delivery_date'))) if o.get('delivery_date') else ''
            })
            
        return jsonify(results), 200
    except Exception as e:
        print(f"Error in /api/reports/active-production: {e}")
        return jsonify({"success": False, "orders": [], "message": str(e)}), 200
    finally:
        if cursor: cursor.close()
        if conn: conn.close()


@app.route('/api/reports/procurement', methods=['GET'])
def report_procurement():
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute('''
            SELECT p.po_number, m.material_name, p.required_qty, m.unit, 
                   s.supplier_name, p.status, p.order_date
            FROM procurement p
            LEFT JOIN store_materials m ON p.material_id = m.material_id
            LEFT JOIN suppliers s ON p.supplier_id = s.supplier_id
            WHERE p.status IN ('Awaiting Materials', 'Procurement', 'Pending Approval', 'Ordered', 'Delayed', 'In Transit')
        ''')
        proc_data = cursor.fetchall()
        
        results = []
        for p in proc_data:
            results.append({
                'poNumber': p.get('po_number') or 'Unknown',
                'material': p.get('material_name') or 'Unknown Material',
                'requiredQty': p.get('required_qty') or 0,
                'unit': p.get('unit') or 'pcs',
                'supplier': p.get('supplier_name') or 'Unknown Supplier',
                'status': p.get('status') or 'Pending'
            })
            
        return jsonify(results), 200
    except Exception as e:
        print(f"Error in /api/reports/procurement: {e}")
        return jsonify({"success": False, "orders": [], "message": str(e)}), 200
    finally:
        if cursor: cursor.close()
        if conn: conn.close()


@app.route('/api/reports/inventory-alerts', methods=['GET'])
def report_inventory_alerts():
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute('''
            SELECT material_id, material_name, available_qty, min_required, unit
            FROM store_materials 
            WHERE available_qty < min_required AND is_deleted = 0
        ''')
        inventory = cursor.fetchall()
        
        results = []
        for item in inventory:
            avail = float(item.get('available_qty') or 0)
            min_req = float(item.get('min_required') or 0)
            
            if avail <= 0:
                alert = 'Critical'
            elif avail <= (0.5 * min_req):
                alert = 'High'
            else:
                alert = 'Medium'
                
            results.append({
                'materialId': item.get('material_id'),
                'name': item.get('material_name'),
                'currentStock': avail,
                'unit': item.get('unit') or 'pcs',
                'threshold': min_req,
                'status': alert
            })
            
        return jsonify(results), 200
    except Exception as e:
        print(f"Error in /api/reports/inventory-alerts: {e}")
        return jsonify({"success": False, "orders": [], "message": str(e)}), 200
    finally:
        if cursor: cursor.close()
        if conn: conn.close()


# =====================================================================
# REPORTS: Orders Aggregation
# =====================================================================
@app.route('/api/reports/orders', methods=['GET'])
def get_orders_report():
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        # 1. Query the central 'orders' collection to retrieve all active records.
        cursor.execute("SELECT * FROM orders WHERE status != 'Deleted' AND status != 'Archived'")
        orders_data = cursor.fetchall()
        
        stats = {
            "pending": 0,
            "inProduction": 0,
            "cutting": 0,
            "delivered": 0
        }
        
        formatted_orders = []
        
        for order in orders_data:
            # Determine active stage/status
            stage = order.get('active_stage') or order.get('stage') or ''
            status = order.get('status') or ''
            
            # Compute counts for the 4 report summary metrics
            if stage in ['Initiation', 'Order Initiation', 'Specifications', 'Order Specifications', 'Stock Check', 'BOM Calculation'] or status == 'Pending':
                stats['pending'] += 1
            elif stage in ['Inventory Check', 'Material Allocation', 'Procurement', 'Material Release', 'Production', 'Quality & Packing'] or status == 'In Progress':
                stats['inProduction'] += 1
            elif stage == 'Cutting':
                stats['cutting'] += 1
            elif stage == 'Dispatched' or status == 'Delivered':
                stats['delivered'] += 1
                
            # Shape table row keys
            formatted_orders.append({
                "poNumber": order.get('po_number') or order.get('id') or '',
                "customer": order.get('customer_name') or order.get('customer') or '',
                "itemDescription": order.get('item_description') or order.get('description') or '',
                "poDate": format_db_date(order.get('po_date') or order.get('created_at')),
                "deliveryDate": format_db_date(order.get('delivery_date') or order.get('target_date')),
                "activeWorkflowStep": stage if stage else status,
                "totalValue": float(order.get('total_value') or order.get('amount') or 0)
            })
            
        cursor.close()
        conn.close()
        
        return jsonify({
            "success": True,
            "stats": stats,
            "orders": formatted_orders
        }), 200

    except Exception as e:
        print(f"Error in /api/reports/orders: {e}")
        return jsonify({"success": False, "orders": [], "message": str(e)}), 200


# =====================================================================
# INVENTORY: Split Allocation Workflows
# =====================================================================

@app.route('/api/purchase_orders/allocate-partial', methods=['POST'])
def allocate_partial_split():
    conn = None
    cursor = None
    try:
        data = request.get_json() or {}
        po_number = data.get('poNumber')
        allocated_qty = int(data.get('allocatedQty', 0))
        
        if not po_number:
            return jsonify({"success": False, "error": "poNumber is required"}), 200
            
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        # 1. Fetch current order state
        cursor.execute("SELECT * FROM orders WHERE po_number = %s", (po_number,))
        order = cursor.fetchone()
        
        if not order:
            return jsonify({"success": False, "error": "Order not found"}), 200
            
        # Determine current quantities (safely parsing defaults)
        total_qty = int(order.get('total_order_qty') or order.get('quantity') or order.get('total_qty') or 0)
        current_packing = int(order.get('allocated_to_packing', 0) or 0)
        current_bom = int(order.get('allocated_to_bom', 0) or 0)
        
        new_packing_qty = current_packing + allocated_qty
        
        # 2. Deduct from warehouse inventory immediately
        item_desc = order.get('item_description') or order.get('description') or ''
        cursor.execute("""
            UPDATE inventory 
            SET available_quantity = available_quantity - %s 
            WHERE item_name = %s AND available_quantity >= %s
        """, (allocated_qty, item_desc, allocated_qty))
        
        # 3. Final Core Stage Status Transition Verification
        if (new_packing_qty + current_bom) >= total_qty and total_qty > 0:
            # Execute final database save query updating the order status
            new_stage = 'Material Allocation'
            cursor.execute("""
                UPDATE orders 
                SET allocated_to_packing = %s, stage = %s, active_stage = %s 
                WHERE po_number = %s
            """, (new_packing_qty, new_stage, new_stage, po_number))
        else:
            # Keep the core order status at 'Stock Check'
            cursor.execute("""
                UPDATE orders 
                SET allocated_to_packing = %s 
                WHERE po_number = %s
            """, (new_packing_qty, po_number))
            
        conn.commit()
        return jsonify({"success": True, "message": "Partial allocation processed successfully."}), 200
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        if conn: conn.rollback()
        return jsonify({"success": False, "message": str(e)}), 200
    finally:
        if cursor: cursor.close()
        if conn: conn.close()


@app.route('/api/purchase_orders/calculate-bom-shortage', methods=['POST'])
def calculate_bom_shortage():
    conn = None
    cursor = None
    try:
        data = request.json
        po_number = data.get('poNumber')
        shortage_qty = int(data.get('shortageQty', 0))
        
        if not po_number:
            return jsonify({"success": False, "error": "poNumber is required"}), 200
            
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        # 1. Fetch current order state
        cursor.execute("SELECT * FROM orders WHERE po_number = %s", (po_number,))
        order = cursor.fetchone()
        
        if not order:
            return jsonify({"success": False, "error": "Order not found"}), 200
            
        # Determine current quantities
        total_qty = int(order.get('total_order_qty') or order.get('quantity') or order.get('total_qty') or 0)
        current_packing = int(order.get('allocated_to_packing', 0) or 0)
        current_bom = int(order.get('allocated_to_bom', 0) or 0)
        
        new_bom_qty = current_bom + shortage_qty
        
        # 2. Save tracking records into production scheduler tables
        item_desc = order.get('item_description') or order.get('description') or ''
        cursor.execute("""
            INSERT INTO production_scheduler (po_number, item_name, required_quantity, status)
            VALUES (%s, %s, %s, 'Pending BOM')
        """, (po_number, item_desc, shortage_qty))
        
        # 3. Final Core Stage Status Transition Verification
        if (current_packing + new_bom_qty) >= total_qty and total_qty > 0:
            # Move to next stage completely
            new_stage = 'BOM Calculation'
            cursor.execute("""
                UPDATE orders 
                SET allocated_to_bom = %s, stage = %s, active_stage = %s 
                WHERE po_number = %s
            """, (new_bom_qty, new_stage, new_stage, po_number))
        else:
            # Keep in current wizard step
            cursor.execute("""
                UPDATE orders 
                SET allocated_to_bom = %s 
                WHERE po_number = %s
            """, (new_bom_qty, po_number))
            
        conn.commit()
        return jsonify({"success": True, "message": "BOM shortage calculated successfully."}), 200
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        if conn: conn.rollback()
        return jsonify({"success": False, "message": str(e)}), 200
    finally:
        if cursor: cursor.close()
        if conn: conn.close()

# =====================================================================
# STORE MATERIALS API
# =====================================================================
@app.route('/api/store-materials', methods=['GET'])
def fetch_api_store_materials():
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        # Fetch active materials, aligning min_required to required_qty for frontend
        query = """
            SELECT 
                material_id, 
                hsn_code, 
                TRIM(material_name) AS material_name, 
                category, 
                unit, 
                COALESCE(available_qty, 0) AS available_qty, 
                COALESCE(blocked_qty, 0) AS blocked_qty, 
                COALESCE(min_required, 0) AS required_qty
            FROM store_materials 
            WHERE is_deleted = 0
        """
        cursor.execute(query)
        materials = cursor.fetchall()

        # Extra Python-side sanitization to guarantee clean strings
        for m in materials:
            if m.get('material_name'):
                m['material_name'] = str(m['material_name']).strip()
            else:
                m['material_name'] = ""
                
        return jsonify({"success": True, "data": materials}), 200
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        if cursor: cursor.close()
        if conn: conn.close()

@app.route('/api/store-materials/clear-test-data', methods=['DELETE'])
def clear_store_materials_test_data():
    """
    Clears all dummy/test data and validates auto_increment reset.
    """
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Standard delete
        cursor.execute("DELETE FROM store_materials")
        
        # Reset the sequencer to 1 (Validation requested by requirement)
        cursor.execute("ALTER TABLE store_materials AUTO_INCREMENT = 1")
        
        conn.commit()
        return jsonify({"success": True, "message": "Test data cleared and sequencer reset to 1"}), 200
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        if conn: conn.rollback()
        return jsonify({"success": False, "message": str(e)}), 500
    finally:
        if cursor: cursor.close()
        if conn: conn.close()

if __name__ == '__main__':
    app.run(port=5000, debug=True)

