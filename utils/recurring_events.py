"""
Recurring events helper functions for handling RRULE expansion and management.
"""

from datetime import datetime, timedelta
import calendar
import uuid


def expand_rrule(start_datetime_str, end_datetime_str, rrule_str, max_instances=730):
    """Expand an RRULE into individual event instances.
    
    Args:
        start_datetime_str: Start datetime string (YYYY-MM-DD HH:MM:SS)
        end_datetime_str: End datetime string (YYYY-MM-DD HH:MM:SS)
        rrule_str: RRULE string (e.g., 'FREQ=WEEKLY;BYDAY=MO,WE;COUNT=10')
        max_instances: Maximum instances to generate (safety limit)
    
    Returns:
        List of (start_datetime_str, end_datetime_str) tuples
    """
    # Parse start and end datetime
    start_dt = datetime.strptime(start_datetime_str, '%Y-%m-%d %H:%M:%S')
    end_dt = datetime.strptime(end_datetime_str, '%Y-%m-%d %H:%M:%S')
    duration = end_dt - start_dt
    
    # Parse RRULE
    rrule_parts = {}
    for part in rrule_str.split(';'):
        if '=' in part:
            key, value = part.split('=', 1)
            rrule_parts[key.strip()] = value.strip()
    
    freq = rrule_parts.get('FREQ', 'DAILY').upper()
    interval = int(rrule_parts.get('INTERVAL', 1))
    count = int(rrule_parts.get('COUNT', 0)) if 'COUNT' in rrule_parts else None
    until_str = rrule_parts.get('UNTIL')
    byday = rrule_parts.get('BYDAY', '').split(',') if 'BYDAY' in rrule_parts else []
    bymonthday = [int(d) for d in rrule_parts.get('BYMONTHDAY', '').split(',') if d] if 'BYMONTHDAY' in rrule_parts else []
    
    # Parse UNTIL date
    until_dt = None
    if until_str:
        # Handle both date and datetime formats
        if 'T' in until_str:
            until_dt = datetime.strptime(until_str.replace('Z', ''), '%Y%m%dT%H%M%S')
        else:
            until_dt = datetime.strptime(until_str, '%Y%m%d')
    
    # Generate instances
    instances = []
    current_dt = start_dt
    instance_count = 0
    
    # Map day abbreviations to weekday numbers (0=Monday, 6=Sunday)
    day_map = {'MO': 0, 'TU': 1, 'WE': 2, 'TH': 3, 'FR': 4, 'SA': 5, 'SU': 6}
    
    while True:
        # Check limits
        if count and instance_count >= count:
            break
        if until_dt and current_dt > until_dt:
            break
        if instance_count >= max_instances:
            break
        
        # Check if current date matches the pattern
        include_instance = False
        
        if freq == 'DAILY':
            include_instance = True
        elif freq == 'WEEKLY':
            if byday:
                # Check if current day is in BYDAY list
                current_weekday = current_dt.weekday()
                for day in byday:
                    if day.strip().upper() in day_map and day_map[day.strip().upper()] == current_weekday:
                        include_instance = True
                        break
            else:
                include_instance = True
        elif freq == 'MONTHLY':
            if bymonthday:
                if current_dt.day in bymonthday:
                    include_instance = True
            else:
                # Same day of month as original
                if current_dt.day == start_dt.day:
                    include_instance = True
        elif freq == 'YEARLY':
            if current_dt.month == start_dt.month and current_dt.day == start_dt.day:
                include_instance = True
        
        if include_instance:
            instance_end_dt = current_dt + duration
            instances.append((
                current_dt.strftime('%Y-%m-%d %H:%M:%S'),
                instance_end_dt.strftime('%Y-%m-%d %H:%M:%S')
            ))
            instance_count += 1
        
        # Move to next candidate date
        if freq == 'DAILY':
            current_dt += timedelta(days=interval)
        elif freq == 'WEEKLY':
            if byday and include_instance:
                # For weekly with BYDAY, increment by 1 day until we find the next matching day
                current_dt += timedelta(days=1)
                days_checked = 1
                while days_checked < 7 * interval:
                    current_weekday = current_dt.weekday()
                    found = False
                    for day in byday:
                        if day.strip().upper() in day_map and day_map[day.strip().upper()] == current_weekday:
                            found = True
                            break
                    if found:
                        break
                    current_dt += timedelta(days=1)
                    days_checked += 1
            else:
                current_dt += timedelta(weeks=interval)
        elif freq == 'MONTHLY':
            # Add months
            month = current_dt.month + interval
            year = current_dt.year
            while month > 12:
                month -= 12
                year += 1
            try:
                current_dt = current_dt.replace(year=year, month=month)
            except ValueError:
                # Handle day overflow (e.g., Jan 31 -> Feb 31)
                # Move to last day of target month
                last_day = calendar.monthrange(year, month)[1]
                current_dt = current_dt.replace(year=year, month=month, day=last_day)
        elif freq == 'YEARLY':
            current_dt = current_dt.replace(year=current_dt.year + interval)
    
    return instances


def create_recurring_event(start_datetime, end_datetime, title, description='', tag='', user_id=None, rrule=''):
    """Create a recurring event series by expanding the RRULE.
    
    Args:
        start_datetime: Start datetime string
        end_datetime: End datetime string
        title: Event title
        description: Event description
        tag: Event tag
        user_id: User ID
        rrule: RRULE string
    
    Returns:
        Tuple: (recurrence_id, num_events_created)
    """
    import database
    
    # Generate unique recurrence ID
    recurrence_id = str(uuid.uuid4())
    
    # Expand RRULE into instances
    instances = expand_rrule(start_datetime, end_datetime, rrule)
    
    # Create events for each instance
    conn = database.get_db_connection()
    cursor = conn.cursor()
    
    for idx, (instance_start, instance_end) in enumerate(instances):
        # First instance gets the RRULE, others reference it
        instance_rrule = rrule if idx == 0 else None
        
        cursor.execute(
            '''INSERT INTO events (start_datetime, end_datetime, title, description, tag, user_id, 
               recurrence_id, rrule, original_start) 
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)''',
            (instance_start, instance_end, title, description, tag, user_id, 
             recurrence_id, instance_rrule, start_datetime)
        )
    
    conn.commit()
    conn.close()
    
    return recurrence_id, len(instances)


def delete_recurring_series(recurrence_id, user_id):
    """Delete all events in a recurring series.
    
    Args:
        recurrence_id: Recurrence ID
        user_id: User ID for security check
    
    Returns:
        Number of events deleted
    """
    import database
    
    conn = database.get_db_connection()
    cursor = conn.cursor()
    
    # Count events to delete
    cursor.execute(
        'SELECT COUNT(*) FROM events WHERE recurrence_id = ? AND user_id = ?',
        (recurrence_id, user_id)
    )
    count = cursor.fetchone()[0]
    
    # Delete all events in series
    cursor.execute(
        'DELETE FROM events WHERE recurrence_id = ? AND user_id = ?',
        (recurrence_id, user_id)
    )
    
    conn.commit()
    conn.close()
    
    return count


def update_recurring_series(recurrence_id, user_id, title, description, tag):
    """Update all events in a recurring series with new title/description/tag.
    
    Args:
        recurrence_id: Recurrence ID
        user_id: User ID for security check
        title: New title
        description: New description
        tag: New tag
    
    Returns:
        Number of events updated
    """
    import database
    
    conn = database.get_db_connection()
    cursor = conn.cursor()
    
    # Update all events in series
    cursor.execute(
        '''UPDATE events 
           SET title = ?, description = ?, tag = ?
           WHERE recurrence_id = ? AND user_id = ?''',
        (title, description, tag, recurrence_id, user_id)
    )
    
    count = cursor.rowcount
    conn.commit()
    conn.close()
    
    return count


def build_rrule_string(freq, interval=1, count=None, until=None, byday=None, bymonthday=None):
    """Build an RRULE string from parameters.
    
    Args:
        freq: Frequency (DAILY, WEEKLY, MONTHLY, YEARLY)
        interval: Interval between occurrences
        count: Number of occurrences (mutually exclusive with until)
        until: End date (YYYYMMDD format)
        byday: List of weekday abbreviations for WEEKLY (e.g., ['MO', 'WE', 'FR'])
        bymonthday: List of day numbers for MONTHLY (e.g., [1, 15])
    
    Returns:
        RRULE string
    """
    parts = [f'FREQ={freq.upper()}']
    
    if interval and interval > 1:
        parts.append(f'INTERVAL={interval}')
    
    if count:
        parts.append(f'COUNT={count}')
    elif until:
        parts.append(f'UNTIL={until}')
    
    if byday:
        parts.append(f'BYDAY={",".join(byday)}')
    
    if bymonthday:
        parts.append(f'BYMONTHDAY={",".join(map(str, bymonthday))}')
    
    return ';'.join(parts)
