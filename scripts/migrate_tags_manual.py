#!/usr/bin/env python3
"""Manually migrate tags from tags.json to database"""
import json
import sqlite3

# Read tags from JSON
with open('tags.json', 'r') as f:
    data = json.load(f)
    tags = data.get('tags', [])

# Connect to database
conn = sqlite3.connect('calendar.db')
cursor = conn.cursor()

# Insert tags
for tag in tags:
    try:
        cursor.execute(
            'INSERT INTO tags (name, color, order_index) VALUES (?, ?, ?)',
            (tag['name'], tag['color'], tag.get('order', 0))
        )
        print(f"Migrated tag: {tag['name']}")
    except sqlite3.IntegrityError:
        print(f"Tag '{tag['name']}' already exists, skipping")

conn.commit()
conn.close()

print(f"\nMigration complete! Migrated {len(tags)} tags.")
