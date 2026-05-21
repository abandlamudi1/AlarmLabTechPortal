import os
import sqlite3

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB = os.path.join(BASE_DIR, "inventory.db")

with sqlite3.connect(DB) as conn:
    cur = conn.cursor()
    cur.execute("SELECT name, quantity, min_stock FROM items WHERE quantity <= min_stock")
    low_items = cur.fetchall()

if not low_items:
    print("✅ All stock levels are OK.")
else:
    print("⚠️ Low Stock Alert:")
    for name, qty, min_stock in low_items:
        print(f"- {name}: {qty} remaining (min: {min_stock})")