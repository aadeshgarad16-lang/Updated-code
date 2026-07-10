import re
with open('c:/Users/USER/Pictures/Sasons_ERP/App.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Pattern 1: available_qty - %s for store_materials
pattern1 = r'UPDATE store_materials\s+SET available_qty = GREATEST\(0, available_qty - %s\),\s+blocked_qty = COALESCE\(blocked_qty, 0\) \+ %s\s+WHERE material_id = %s\s+\", \((.*?)\)'
def repl1(m):
    args = m.group(1)
    parts = args.split(',')
    new_args = f"{parts[0].strip()}, {args}"
    return f'UPDATE store_materials\n                    SET available_qty = GREATEST(0, available_qty - %s),\n                        blocked_qty = COALESCE(blocked_qty, 0) + %s,\n                        total_price = GREATEST(0, available_qty - %s) * unit_price\n                    WHERE material_id = %s\n                ", ({new_args})'

content = re.sub(pattern1, repl1, content)

with open('c:/Users/USER/Pictures/Sasons_ERP/App.py', 'w', encoding='utf-8') as f:
    f.write(content)
print('done')
