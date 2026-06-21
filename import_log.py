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

Programmatic API (used by the Flask web UI):
  from import_log import parse_log_text, insert_parsed_events
"""

import sqlite3
import argparse
import re
from datetime import datetime, timedelta
import sys

# Configure your database name and default user here
DB_NAME = 'calendar.db'
DEFAULT_USER_ID = 1

def parse_discord_date(line):
    """Parse Discord timestamp line to YYYY-MM-DD string."""
    match = re.match(r'^.*?\s*[-—]\s*(.+)$', line, re.IGNORECASE)
    if not match:
        return None
    
    date_str = match.group(1).strip()
    
    # Must contain at least one: time format (HH:MM), Yesterday, Today, or a date slash
    if not re.search(r'(\d{1,2}:\d{2}|yesterday|today|\d{1,2}/\d{1,2})', date_str, re.IGNORECASE):
        return None
        
    now = datetime.now()
    
    # 1. MM/DD/YY, HH:MM AM/PM
    m = re.search(r'(\d{1,2}/\d{1,2}/\d{2,4})', date_str)
    if m:
        dt_part = m.group(1)
        try:
            fmt = '%m/%d/%y' if len(dt_part.split('/')[-1]) == 2 else '%m/%d/%Y'
            dt = datetime.strptime(dt_part, fmt)
            return dt.strftime('%Y-%m-%d')
        except ValueError:
            pass
            
    # 2. Yesterday
    if 'yesterday' in date_str.lower():
        return (now - timedelta(days=1)).strftime('%Y-%m-%d')
        
    # 3. Today (implicit if just time or explicitly "Today")
    return now.strftime('%Y-%m-%d')

def parse_shorthand_time(time_str, ampm=None):
    """Convert '1230', '135', '9' into (hour, minute, exact_24h)."""
    if len(time_str) <= 2:
        hour, minute = int(time_str), 0
    elif len(time_str) == 3:
        hour, minute = int(time_str[0]), int(time_str[1:])
    elif len(time_str) == 4:
        hour, minute = int(time_str[0:2]), int(time_str[2:])
    else:
        return None

    # Validate logical 12-hour or 24-hour values
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        return None

    exact_24h = None
    if ampm:
        ampm = ampm.lower()
        if ampm == 'am':
            if hour == 12:
                exact_24h = 0
            elif hour < 12:
                exact_24h = hour
            else:
                exact_24h = hour
        elif ampm == 'pm':
            if hour == 12:
                exact_24h = 12
            elif hour < 12:
                exact_24h = hour + 12
            else:
                exact_24h = hour
    elif hour == 0 or hour > 12:
        exact_24h = hour
    elif len(time_str) == 4 and time_str.startswith('0'):
        exact_24h = hour

    return hour, minute, exact_24h

def get_next_occurrence(base_dt, hour, minute, exact_24h=None):
    """Find the next occurrence of a time after base_dt."""
    options = []
    # Check today and tomorrow
    for day_offset in range(3):
        cur_date = base_dt.date() + timedelta(days=day_offset)
        if exact_24h is not None:
            options.append(datetime(cur_date.year, cur_date.month, cur_date.day, exact_24h, minute))
        else:
            # Convert 12-hour to 24-hour variants
            h_am = 0 if hour == 12 else hour
            h_pm = 12 if hour == 12 else hour + 12
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
        SELECT e.tag 
        FROM events e
        LEFT JOIN tags t ON e.tag = t.name AND t.user_id = e.user_id
        WHERE e.user_id = ? AND lower(e.title) = ? AND e.tag IS NOT NULL AND e.tag != ''
          AND (t.is_archived IS NULL OR t.is_archived = 0)
        ORDER BY e.start_datetime DESC 
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

# ---------------------------------------------------------------------------
# Programmatic API — called by the Flask web UI
# ---------------------------------------------------------------------------

def parse_log_text(text, user_id, cursor, date_override=None):
    """Parse a raw log string and return a list of event dicts ready to insert.

    Returns a tuple (events, date_used, warnings) where:
      events    – list of {start, end, title, tag} dicts (datetimes as strings)
      date_used – the YYYY-MM-DD string that was resolved
      warnings  – list of human-readable warning strings
    """
    warnings = []
    lines = text.splitlines(keepends=True)

    # --- Detect separator and extract date ---
    resolved_date = date_override
    last_dash_idx = -1
    for i, line in enumerate(lines):
        if re.search(r'[-\u2014\u2500]{3,}', line):
            last_dash_idx = i

    if last_dash_idx != -1:
        parsed_date = None
        for j in range(last_dash_idx - 1, -1, -1):
            prev_line = lines[j].strip()
            parsed_date = parse_discord_date(prev_line)
            if parsed_date:
                break
        if parsed_date and not resolved_date:
            resolved_date = parsed_date
            warnings.append(f"Detected separator; extracted date: {resolved_date}")
        lines = lines[last_dash_idx + 1:]
    else:
        if not resolved_date:
            for line in lines:
                parsed_date = parse_discord_date(line.strip())
                if parsed_date:
                    resolved_date = parsed_date
                    warnings.append(f"Extracted date from first timestamp: {resolved_date}")
                    break

    if not resolved_date:
        raise ValueError("Could not extract a start date from the log. Provide one manually.")

    # --- Parse activity lines ---
    activities = []
    for line in lines:
        line = line.strip()
        if not line or parse_discord_date(line):
            continue
        match = re.match(r'^(\d{1,4})\s*(am|pm)?\s+(.+)$', line, re.IGNORECASE)
        if match:
            time_str, ampm, title = match.group(1), match.group(2), match.group(3)
            if parse_shorthand_time(time_str, ampm) is not None:
                activities.append((time_str, ampm, title))

    if not activities:
        raise ValueError("No valid activities found in the log.")

    # --- Resolve continue_flag ---
    continue_flag = has_non_repeating_events(cursor, user_id, resolved_date)
    if continue_flag:
        warnings.append("Auto-enabled continue mode: existing events found on this day.")

    base_time = get_last_event_end_time(cursor, user_id, resolved_date, continue_from_latest=continue_flag)
    warnings.append(f"Scheduling starts after: {base_time.strftime('%Y-%m-%d %I:%M %p')}")

    events = []
    current_time = base_time

    for time_str, ampm, title in activities:
        hour, minute, exact_24h = parse_shorthand_time(time_str, ampm)
        end_time = get_next_occurrence(current_time, hour, minute, exact_24h)
        existing_events = get_existing_events_for_range(cursor, user_id, current_time, end_time)
        start_time = current_time
        for e in existing_events:
            if e['start'] < end_time and e['end'] > start_time:
                start_time = max(start_time, min(end_time, e['end']))

        if start_time < end_time:
            tag = predict_tag(cursor, title, user_id)
            events.append({
                'start': start_time.strftime('%Y-%m-%d %H:%M:%S'),
                'end': end_time.strftime('%Y-%m-%d %H:%M:%S'),
                'title': title,
                'tag': tag or '',
            })

        current_time = end_time

    return events, resolved_date, warnings


def insert_parsed_events(events, user_id, cursor):
    """Insert a list of event dicts (from parse_log_text) into the DB.

    The cursor's connection must be committed by the caller.
    """
    for event in events:
        cursor.execute("""
            INSERT INTO events (start_datetime, end_datetime, title, description, tag, user_id)
            VALUES (?, ?, ?, '', ?, ?)
        """, (
            event['start'],
            event['end'],
            event['title'],
            event['tag'],
            user_id,
        ))


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Import discord log into calendar events.")
    parser.add_argument('--date', default=None, help="The target date (YYYY-MM-DD), defaults to extracted date from log")
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

    # Find the last "New Messages" separator (at least 3 dashes)
    last_dash_idx = -1
    for i, line in enumerate(lines):
        if re.search(r'[-—─]{3,}', line):
            last_dash_idx = i

    if last_dash_idx != -1:
        # Search upwards for the nearest timestamp line
        parsed_date = None
        for j in range(last_dash_idx - 1, -1, -1):
            prev_line = lines[j].strip()
            parsed_date = parse_discord_date(prev_line)
            if parsed_date:
                break
                
        if parsed_date:
            args.date = parsed_date
            print(f"Detected new messages marker. Extracted start date: {args.date}")
        
        # Ignore all text above and including the dashes line
        lines = lines[last_dash_idx + 1:]
    else:
        # If no dashes, find the first valid timestamp in the log
        for line in lines:
            parsed_date = parse_discord_date(line.strip())
            if parsed_date:
                args.date = parsed_date
                print(f"No marker found. Extracted start date from first timestamp: {args.date}")
                break

    if not args.date:
        print("Error: Could not extract a start date from the log, and no --date flag was provided.")
        sys.exit(1)

    # Parse log lines
    activities = []
    for line in lines:
        line = line.strip()
        if not line or parse_discord_date(line):
            continue
        
        # Match standard line starting with 1-4 digits, optional am/pm
        match = re.match(r'^(\d{1,4})\s*(am|pm)?\s+(.+)$', line, re.IGNORECASE)
        if match:
            time_str = match.group(1)
            ampm = match.group(2)
            title = match.group(3)
            parsed = parse_shorthand_time(time_str, ampm)
            if parsed is not None:
                activities.append((time_str, ampm, title))

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

    for time_str, ampm, title in activities:
        hour, minute, exact_24h = parse_shorthand_time(time_str, ampm)
        end_time = get_next_occurrence(current_time, hour, minute, exact_24h)
        
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
