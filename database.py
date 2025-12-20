import sqlite3
from datetime import datetime, timedelta

DATABASE_NAME = 'calendar.db'

def get_db_connection():
    """Create and return a database connection."""
    conn = sqlite3.connect(DATABASE_NAME)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Initialize the database with the events table."""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Check if old schema exists and migrate if needed
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='events'")
    table_exists = cursor.fetchone()
    
    if table_exists:
        # Check if we need to migrate from old schema
        cursor.execute("PRAGMA table_info(events)")
        columns = [col[1] for col in cursor.fetchall()]
        
        if 'date' in columns and 'start_datetime' not in columns:
            # Migrate old schema to new schema
            migrate_schema(conn)
    else:
        # Create new schema
        cursor.execute('''
            CREATE TABLE events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                start_datetime TEXT NOT NULL,
                end_datetime TEXT NOT NULL,
                title TEXT NOT NULL,
                description TEXT,
                tag TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        conn.commit()
    
    conn.close()

def migrate_schema(conn):
    """Migrate from old schema (date, time) to new schema (start_datetime, end_datetime)."""
    cursor = conn.cursor()
    
    # Create new table with updated schema
    cursor.execute('''
        CREATE TABLE events_new (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            start_datetime TEXT NOT NULL,
            end_datetime TEXT NOT NULL,
            title TEXT NOT NULL,
            description TEXT,
            tag TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Migrate existing data
    cursor.execute('SELECT id, date, time, title, description, created_at FROM events')
    old_events = cursor.fetchall()
    
    for event in old_events:
        event_id, date, time, title, description, created_at = event
        
        # Convert old format to new format
        if time:
            # Parse time and create start_datetime
            start_datetime = f"{date} {time}:00"
            # Default to 1 hour duration
            start_dt = datetime.strptime(start_datetime, '%Y-%m-%d %H:%M:%S')
            end_dt = start_dt + timedelta(hours=1)
            end_datetime = end_dt.strftime('%Y-%m-%d %H:%M:%S')
        else:
            # All-day event: 9 AM to 5 PM
            start_datetime = f"{date} 09:00:00"
            end_datetime = f"{date} 17:00:00"
        
        cursor.execute('''
            INSERT INTO events_new (id, start_datetime, end_datetime, title, description, tag, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (event_id, start_datetime, end_datetime, title, description, None, created_at))
    
    # Drop old table and rename new table
    cursor.execute('DROP TABLE events')
    cursor.execute('ALTER TABLE events_new RENAME TO events')
    
    conn.commit()

def get_events_by_date(date):
    """Get all events for a specific date (including multi-day events that overlap this date)."""
    conn = get_db_connection()
    
    # Get events where the date falls between start and end datetime
    # We need to consider events that start on this day, end on this day, or span across this day
    date_start = f"{date} 00:00:00"
    date_end = f"{date} 23:59:59"
    
    events = conn.execute('''
        SELECT * FROM events 
        WHERE (start_datetime <= ? AND end_datetime >= ?)
        OR (DATE(start_datetime) = ?)
        OR (DATE(end_datetime) = ?)
        ORDER BY start_datetime
    ''', (date_end, date_start, date, date)).fetchall()
    
    conn.close()
    return events

def add_event(start_datetime, end_datetime, title, description='', tag=''):
    """Add a new event to the database."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        'INSERT INTO events (start_datetime, end_datetime, title, description, tag) VALUES (?, ?, ?, ?, ?)',
        (start_datetime, end_datetime, title, description, tag)
    )
    conn.commit()
    event_id = cursor.lastrowid
    conn.close()
    return event_id

def update_event(event_id, start_datetime, end_datetime, title, description='', tag=''):
    """Update an existing event."""
    conn = get_db_connection()
    conn.execute(
        'UPDATE events SET start_datetime = ?, end_datetime = ?, title = ?, description = ?, tag = ? WHERE id = ?',
        (start_datetime, end_datetime, title, description, tag, event_id)
    )
    conn.commit()
    conn.close()

def delete_event(event_id):
    """Delete an event by ID."""
    conn = get_db_connection()
    conn.execute('DELETE FROM events WHERE id = ?', (event_id,))
    conn.commit()
    conn.close()

def bulk_add_events(events, tag=''):
    """
    Add multiple events to the database in a single transaction.
    
    Args:
        events: List of event dictionaries with keys:
                - title: Event title
                - description: Event description (optional)
                - start_datetime: Start datetime string (YYYY-MM-DD HH:MM:SS)
                - end_datetime: End datetime string (YYYY-MM-DD HH:MM:SS)
        tag: Tag to apply to all events (optional)
        
    Returns:
        int: Number of events successfully imported
    """
    if not events:
        return 0
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    imported_count = 0
    try:
        for event in events:
            title = event.get('title', '(no title)')
            description = event.get('description', '')
            start_datetime = event.get('start_datetime')
            end_datetime = event.get('end_datetime')
            
            if start_datetime and end_datetime:
                cursor.execute(
                    'INSERT INTO events (start_datetime, end_datetime, title, description, tag) VALUES (?, ?, ?, ?, ?)',
                    (start_datetime, end_datetime, title, description, tag)
                )
                imported_count += 1
        
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()
    
    return imported_count

# Initialize the database when the module is imported
init_db()
