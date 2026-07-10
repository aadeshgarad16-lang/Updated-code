import re

with open('c:/Users/USER/Pictures/Sasons_ERP/App.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Pattern 1: available_qty - %s
pattern1 = r'UPDATE store_garments SET available_qty = GREATEST\(0, available_qty - %s\), blocked_qty = COALESCE\(blocked_qty, 0\) \+ %s WHERE (.*?)\", \((.*?)\)'
# Replacement: passing %s three times, we need to update the tuple too
def repl1(m):
    where_clause = m.group(1)
    args = m.group(2)
    # The first two args are the qty. We duplicate the first arg.
    # Example args: `req_qty, req_qty, sku_no`
    parts = args.split(',')
    new_args = f"{parts[0].strip()}, {args}"
    return f'UPDATE store_garments SET available_qty = GREATEST(0, available_qty - %s), blocked_qty = COALESCE(blocked_qty, 0) + %s, total_price = GREATEST(0, available_qty - %s) * unit_price WHERE {where_clause}", ({new_args})'

content = re.sub(pattern1, repl1, content)

# Pattern 2: available_qty = 0
pattern2 = r'UPDATE store_garments SET available_qty = 0, blocked_qty = COALESCE\(blocked_qty, 0\) \+ %s WHERE (.*?)\", \((.*?)\)'
def repl2(m):
    where_clause = m.group(1)
    args = m.group(2)
    return f'UPDATE store_garments SET available_qty = 0, blocked_qty = COALESCE(blocked_qty, 0) + %s, total_price = 0 WHERE {where_clause}", ({args})'

content = re.sub(pattern2, repl2, content)

with open('c:/Users/USER/Pictures/Sasons_ERP/App.py', 'w', encoding='utf-8') as f:
    f.write(content)
print("done")
