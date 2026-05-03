"""
Log Importer for Calendar v2
====================================
Parses a log of activities and automatically imports them as
calendar events, figuring out chronological alignment, AM/PM boundaries,
and predicting tags based on your previous calendar data.

Usage:
  python3 import_log.py [--date <YYYY-MM-DD>] --file <path_to_log.txt>

Flags:
  --date       (Optional) The date to align these events with (format: YYYY-MM-DD). Defaults to today.
  --file       (Optional) Path to your text log. If omitted, reads from standard input.
  --user-id    (Optional) The numeric ID of the user account to insert events for (default is 1).
  --dry-run    (Optional) Previews the parsed events in the terminal without inserting them into the database.
  --continue   (Optional) If you already have events on the target day, use this flag to start scheduling immediately after your latest event.
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
    # Strip leading bracketed prefixes for the sake of tag prediction
    search_title = re.sub(r'^\[.*?\]\s*', '', title).strip()
    
    cursor.execute("""
        SELECT tag 
        FROM events 
        WHERE user_id = ? AND lower(title) = ? AND tag IS NOT NULL AND tag != ''
        ORDER BY start_datetime DESC 
        LIMIT 1
    """, (user_id, search_title.lower()))
    row = cursor.fetchone()
    return row[0] if row else None

def get_last_event_end_time(cursor, user_id, target_date_str, continue_from_latest=False):
    target_dt = datetime.strptime(target_date_str, '%Y-%m-%d')
    midnight = datetime(target_dt.year, target_dt.month, target_dt.day)
    prev_midnight = midnight - timedelta(days=1)
    
    # Choose boundary based on whether we're continuing the day or starting fresh
    limit_date_str = f"{target_date_str} 23:59:59" if continue_from_latest else f"{target_date_str} 00:00:00"

    cursor.execute("""
        SELECT end_datetime 
        FROM events 
        WHERE user_id = ? AND start_datetime < ?
        AND (recurrence_id IS NULL OR recurrence_id = '')
        AND (rrule IS NULL OR rrule = '')
        ORDER BY end_datetime DESC 
        LIMIT 1
    """, (user_id, limit_date_str))
    row = cursor.fetchone()
    if row:
        dt = datetime.strptime(row[0], '%Y-%m-%d %H:%M:%S')
        if continue_from_latest:
            return dt
        else:
            # Only use the DB end time if it occurred on the previous day
            if dt >= prev_midnight:
                return dt
    # If no recent event, start at midnight of the target date
    return midnight

def get_existing_events_for_range(cursor, user_id, start_dt, end_dt):
    """Retrieve all existing events overlapping the specified time span to avoid overlapping."""
    start_str = start_dt.strftime('%Y-%m-%d 00:00:00')
    end_str = end_dt.strftime('%Y-%m-%d 23:59:59')
    cursor.execute("""
        SELECT start_datetime, end_datetime 
        FROM events 
        WHERE user_id = ? 
        AND ((start_datetime >= ? AND start_datetime <= ?) OR (end_datetime > ? AND end_datetime <= ?))
        ORDER BY start_datetime
    """, (user_id, start_str, end_str, start_str, end_str))
    return [{'start': datetime.strptime(r[0], '%Y-%m-%d %H:%M:%S'),
             'end': datetime.strptime(r[1], '%Y-%m-%d %H:%M:%S')} for r in cursor.fetchall()]

def has_non_repeating_events(cursor, user_id, target_date_str):
    """Check if there are any non-repeating events on the specified date."""
    cursor.execute("""
        SELECT COUNT(*) 
        FROM events 
        WHERE user_id = ? 
        AND ((start_datetime >= ? AND start_datetime <= ?) OR (end_datetime > ? AND end_datetime <= ?))
        AND (recurrence_id IS NULL OR recurrence_id = '')
        AND (rrule IS NULL OR rrule = '')
    """, (user_id, f"{target_date_str} 00:00:00", f"{target_date_str} 23:59:59", 
          f"{target_date_str} 00:00:00", f"{target_date_str} 23:59:59"))
    return cursor.fetchone()[0] > 0

def main():
    parser = argparse.ArgumentParser(description="Import discord log into calendar events.")
    parser.add_argument('--date', default=datetime.now().strftime('%Y-%m-%d'), help="The target date (YYYY-MM-DD), defaults to today")
    parser.add_argument('--file', help="Path to the log file (reads from stdin if not provided)")
    parser.add_argument('--user-id', type=int, default=DEFAULT_USER_ID, help="User ID to import events for")
    parser.add_argument('--dry-run', action='store_true', help="Preview events without inserting")
    parser.add_argument('--continue', dest='continue_flag', action='store_true', help="Continue scheduling after your latest event on the target day")
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
            parsed = parse_shorthand_time(time_str)
            if parsed is not None:
                activities.append((time_str, title))

    if not activities:
        print("No valid activities found.")
        return

    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    # Automatically set continue_flag if there are already non-repeating events logged for today
    if not args.continue_flag and has_non_repeating_events(cursor, args.user_id, args.date):
        args.continue_flag = True
        print("Note: Automatically enabled continue mode because existing logged activities were found on this day.")

    base_time = get_last_event_end_time(cursor, args.user_id, args.date, continue_from_latest=args.continue_flag)
    print(f"Starting after previous event end time: {base_time.strftime('%Y-%m-%d %I:%M %p')}\n")

    events_to_insert = []
    current_time = base_time

    print(f"{'Start Time':<22} | {'End Time':<22} | {'Tag':<15} | Title")
    print("-" * 80)

    for time_str, title in activities:
        hour, minute = parse_shorthand_time(time_str)
        end_time = get_next_occurrence(current_time, hour, minute)
        
        # Fetch existing events that span the date(s) of this activity
        existing_events = get_existing_events_for_range(cursor, args.user_id, current_time, end_time)
        
        # Compute start time by sliding it forward past any overlapping existing events
        start_time = current_time
        for e in existing_events:
            if e['start'] < end_time and e['end'] > start_time:
                # If existing event entirely consumes the new end time, push start_time to end_time so it is skipped
                start_time = max(start_time, min(end_time, e['end']))
        
        # Output or skip
        if start_time < end_time:
            tag = predict_tag(cursor, title, args.user_id)
            events_to_insert.append({
                'start': start_time,
                'end': end_time,
                'title': title,
                'tag': tag or ''
            })
            print(f"{start_time.strftime('%Y-%m-%d %I:%M %p'):<22} | {end_time.strftime('%Y-%m-%d %I:%M %p'):<22} | {tag or '':<15} | {title}")
        
        # Always advance current_time to the logical end of this task block (as that's the chronological step)
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
