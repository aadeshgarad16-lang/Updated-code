import sys

API_CODE = """
@app.route('/api/bom/calculate-from-db', methods=['POST'])
def calculate_bom_from_db():
    try:
        data = request.json
        garment_type = data.get('garmentType')
        selected_sizes = data.get('selectedSizes', [])

        if not garment_type or not selected_sizes:
            return jsonify({"success": False, "error": "Missing garmentType or selectedSizes"}), 400

        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        sizes = [str(s.get('size')) for s in selected_sizes]
        if not sizes:
            return jsonify({"success": False, "error": "No valid sizes provided"}), 400

        format_strings = ','.join(['%s'] * len(sizes))
        query = f"SELECT * FROM garment_bom_calculations WHERE item_name = %s AND size IN ({format_strings})"
        cursor.execute(query, [garment_type] + sizes)
        bom_rows = cursor.fetchall()

        if not bom_rows:
            return jsonify({"success": False, "error": f"No BOM found for {garment_type} with sizes {sizes}"}), 404

        cursor.execute("SELECT material_name, available_qty, unit_price, unit FROM store_materials")
        inventory = {row['material_name'].lower(): row for row in cursor.fetchall()}

        import re
        def parse_numeric(val):
            if val is None:
                return 0.0
            val_str = str(val).strip()
            match = re.search(r'[\d\.]+', val_str)
            if match:
                try:
                    return float(match.group())
                except:
                    return 0.0
            return 0.0
        
        def extract_unit(val):
            if val is None:
                return 'units'
            val_str = str(val).strip().lower()
            if 'm' in val_str and 'cm' not in val_str:
                return 'meters'
            if 'cm' in val_str:
                return 'cm'
            if 'inch' in val_str:
                return 'inch'
            if 'pc' in val_str:
                return 'pcs'
            return 'units'

        materials_dict = {}
        material_columns = [
            'fabric', 'fabric_full_sleeve', 'fabric_half_sleeve', 'linning', 'cuff', 'thread', 
            'placket', 'collar', 'size_label', 'washcare_label', 'main_label', 'brand_label', 
            'overlock_thread', 'buttons', 'polybag', 'box', 'print_embroidery', 'hook', 
            'fusing', 'gripper', 'loopes_fusing', 'reflector', 'lace', 'zip', 'clip'
        ]

        for req_size in selected_sizes:
            s_val = str(req_size.get('size'))
            qty = int(req_size.get('quantity', 0))

            row = next((r for r in bom_rows if str(r['size']) == s_val), None)
            if not row:
                continue

            for col in material_columns:
                val = row.get(col)
                if val is not None and str(val).strip() != '':
                    per_piece_qty = parse_numeric(val)
                    if per_piece_qty > 0:
                        wastage_pct = 5.0
                        total_qty_inc_wastage = qty * per_piece_qty * (1 + wastage_pct / 100.0)
                        mat_name_normalized = col.replace('_', ' ').title()
                        inv_key = mat_name_normalized.lower()
                        
                        inv_data = None
                        for k, v in inventory.items():
                            if k == inv_key or k in inv_key or inv_key in k:
                                inv_data = v
                                break
                        
                        db_unit_price = float(inv_data['unit_price']) if inv_data and inv_data.get('unit_price') is not None else 0.0
                        available_qty = int(inv_data['available_qty']) if inv_data and inv_data.get('available_qty') is not None else 0
                        final_price = total_qty_inc_wastage * db_unit_price
                        unit_str = inv_data['unit'] if inv_data else extract_unit(val)

                        if mat_name_normalized not in materials_dict:
                            materials_dict[mat_name_normalized] = {
                                "materialName": mat_name_normalized,
                                "unit": unit_str,
                                "sizes": [],
                                "totalRequired": 0.0,
                                "availableQty": available_qty,
                                "unitPrice": db_unit_price,
                                "totalPrice": 0.0
                            }
                        
                        materials_dict[mat_name_normalized]['sizes'].append({
                            "size": s_val,
                            "garmentQty": qty,
                            "perPiece": per_piece_qty,
                            "totalForSize": total_qty_inc_wastage,
                            "priceForSize": final_price
                        })
                        materials_dict[mat_name_normalized]['totalRequired'] += total_qty_inc_wastage
                        materials_dict[mat_name_normalized]['totalPrice'] += final_price

        result_materials = []
        for mat_name, mdata in materials_dict.items():
            shortage = max(0, mdata['totalRequired'] - mdata['availableQty'])
            mdata['shortage'] = shortage
            result_materials.append(mdata)

        return jsonify({
            "success": True,
            "garmentType": garment_type,
            "materials": result_materials
        }), 200
        
    except Exception as e:
        print(f"Error in calculate-from-db: {e}")
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        if 'cursor' in locals() and cursor: cursor.close()
        if 'conn' in locals() and conn: conn.close()
"""

with open('App.py', 'r', encoding='utf-8') as f:
    content = f.read()

if 'if __name__ == ' in content:
    idx = content.rfind("if __name__ ==")
    new_content = content[:idx] + API_CODE + "\n" + content[idx:]
else:
    new_content = content + "\n" + API_CODE

with open('App.py', 'w', encoding='utf-8') as f:
    f.write(new_content)

print("Injected successfully!")
