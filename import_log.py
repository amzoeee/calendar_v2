"""
Log Importer for Calendar v2
====================================
Parses a log of activities and automatically imports them as
calendar events, figuring out chronological alignment, AM/PM boundaries,
and predicting tags based on your previous calendar data.

Usage:
  python3 import_log.py --date <YYYY-MM-DD> --file <path_to_log.txt>

Flags:
  --date       (Required) The date to align these events with (format: YYYY-MM-DD).
  --file       (Optional) Path to your text log. If omitted, reads from standard input.
  --user-id    (Optional) The numeric ID of the user account to insert events for (default is 1).
  --dry-run    (Optional) Previews the parsed events in the terminal without inserting them into the database.
"""

import sqlite3
import argparse
import re
from datetime import datetime, timedelta
import sys

# Configure your database name and default user here
DB_NAME = 'calendar.db'
DEFAULT_USER_ID = 1

def parse_shorthand_time(time_str):
    """Convert '1230', '135', '9' into (hour, minute)."""
    if len(time_str) <= 2:
        hour, minute = int(time_str), 0
    elif len(time_str) == 3:
        hour, minute = int(time_str[0]), int(time_str[1:])
    elif len(time_str) == 4:
        hour, minute = int(time_str[0:2]), int(time_str[2:])
    else:
        return None

    # Validate logical 12-hour values
    if 1 <= hour <= 12 and 0 <= minute <= 59:
        return hour, minute
    return None

def get_next_occurrence(base_dt, hour, minute):
    """Find the next occurrence of a 12-hour (hour:minute) after base_dt."""
    # Convert 12-hour to 24-hour variants
    # If hour is 12, the 24h variants are 0 (midnight) and 12 (noon)
    h_am = 0 if hour == 12 else hour
    h_pm = 12 if hour == 12 else hour + 12

    options = []
    # Check today and tomorrow
    for day_offset in range(3):
        cur_date = base_dt.date() + timedelta(days=day_offset)
        options.append(datetime(cur_date.year, cur_date.month, cur_date.day, h_am, minute))
        options.append(datetime(cur_date.year, cur_date.month, cur_date.day, h_pm, minute))
    
    # Filter options > base_dt and sort
    options = [opt for opt in options if opt > base_dt]
    options.sort()
    
    return options[0]

def predict_tag(cursor, title, user_id):
    cursor.execute("""
        SELECT tag 
        FROM events 
        WHERE user_id = ? AND lower(title) = ? AND tag IS NOT NULL AND tag != ''
        ORDER BY start_datetime DESC 
        LIMIT 1
    """, (user_id, title.lower()))
    row = cursor.fetchone()
    return row[0] if row else None

def get_last_event_end_time(cursor, user_id, target_date_str):
    target_dt = datetime.strptime(target_date_str, '%Y-%m-%d')
    midnight = datetime(target_dt.year, target_dt.month, target_dt.day)
    prev_midnight = midnight - timedelta(days=1)
    
    cursor.execute("""
        SELECT end_datetime 
        FROM events 
        WHERE user_id = ? AND end_datetime <= ?
        ORDER BY end_datetime DESC 
        LIMIT 1
    """, (user_id, f"{target_date_str} 23:59:59"))
    row = cursor.fetchone()
    if row:
        dt = datetime.strptime(row[0], '%Y-%m-%d %H:%M:%S')
        # Only use the DB end time if it occurred on the previous day or target day
        if dt >= prev_midnight:
            return dt
    # If no recent event, start at midnight of the target date
    return midnight

def main():
    parser = argparse.ArgumentParser(description="Import discord log into calendar events.")
    parser.add_argument('--date', required=True, help="The target date (YYYY-MM-DD)")
    parser.add_argument('--file', help="Path to the log file (reads from stdin if not provided)")
    parser.add_argument('--user-id', type=int, default=DEFAULT_USER_ID, help="User ID to import events for")
    parser.add_argument('--dry-run', action='store_true', help="Preview events without inserting")
    args = parser.parse_args()

    lines = []
    if args.file:
        with open(args.file, 'r') as f:
            lines = f.readlines()
    else:
        print("Reading from stdin (Press Ctrl+D to finish):")
        lines = sys.stdin.readlines()

    # Parse log lines
    activities = []
    for line in lines:
        line = line.strip()
        if not line or line.startswith('zoe —') or line.startswith('zoe -'):
            continue
        
        # Match standard line starting with 1-4 digits
        match = re.match(r'^(\d{1,4})\s+(.+)$', line)
        if match:
            time_str = match.group(1)
            title = match.group(2)
            # Validate it's actually a valid time shorthand
            parsed = parse_shorthand_time(time_str)
            if parsed is not None:
                activities.append((time_str, title))

    if not activities:
        print("No valid activities found.")
        return

    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    # Find base time from database
    base_time = get_last_event_end_time(cursor, args.user_id, args.date)
    print(f"Starting after previous event end time: {base_time.strftime('%Y-%m-%d %I:%M %p')}\n")

    events_to_insert = []
    current_time = base_time

    print(f"{'Start Time':<22} | {'End Time':<22} | {'Tag':<15} | Title")
    print("-" * 80)

    for time_str, title in activities:
        hour, minute = parse_shorthand_time(time_str)
        end_time = get_next_occurrence(current_time, hour, minute)
        tag = predict_tag(cursor, title, args.user_id)
        
        events_to_insert.append({
            'start': current_time,
            'end': end_time,
            'title': title,
            'tag': tag or ''
        })
        
        print(f"{current_time.strftime('%Y-%m-%d %I:%M %p'):<22} | {end_time.strftime('%Y-%m-%d %I:%M %p'):<22} | {tag or '':<15} | {title}")
        current_time = end_time

    if not args.dry_run:
        print(f"\nFound {len(events_to_insert)} events to insert.")
        confirm = input("Do you want to insert these events? (y/n): ")
        if confirm.lower() == 'y':
            for event in events_to_insert:
                cursor.execute("""
                    INSERT INTO events (start_datetime, end_datetime, title, description, tag, user_id) 
                    VALUES (?, ?, ?, '', ?, ?)
                """, (
                    event['start'].strftime('%Y-%m-%d %H:%M:%S'),
                    event['end'].strftime('%Y-%m-%d %H:%M:%S'),
                    event['title'],
                    event['tag'],
                    args.user_id
                ))
            conn.commit()
            print("Events inserted successfully.")
        else:
            print("Import cancelled.")
    else:
        print("\nDry run complete. No events inserted.")

    conn.close()

if __name__ == "__main__":
    main()
