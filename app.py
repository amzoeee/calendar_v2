from flask import Flask, render_template, request, redirect, url_for
from datetime import datetime, timedelta
import database
import json
import os

import create_default_tags
import ics_parser


app = Flask(__name__)
app.secret_key = 'your-secret-key-here-change-in-production'  # Required for flash messages


def load_tags():
    """Load tag configuration from tags.json"""
    # Ensure default tags exist
    create_default_tags.create_default_tags()
    
    tags_file = os.path.join(os.path.dirname(__file__), 'tags.json')
    try:
        with open(tags_file, 'r') as f:
            data = json.load(f)
            return data['tags']
    except (FileNotFoundError, json.JSONDecodeError):
        # Fallback if something goes wrong even after creation attempt
        return [
            {"name": "Work", "color": "#6366f1", "order": 1},
            {"name": "Personal", "color": "#ec4899", "order": 2},
            {"name": "Meeting", "color": "#10b981", "order": 3}
        ]

def get_tag_color(tag_name, tags):
    """Get the color for a specific tag"""
    for tag in tags:
        if tag['name'] == tag_name:
            return tag['color']
    return "#6b7280"  # Default gray

def get_week_range(date_str):
    """Get the Sunday-Saturday range for the week containing the given date
    
    Args:
        date_str: Date string in 'YYYY-MM-DD' format
        
    Returns:
        tuple: (sunday_date, saturday_date) as date objects
    """
    date = datetime.strptime(date_str, '%Y-%m-%d').date()
    # Find the most recent Sunday (0 = Monday, 6 = Sunday in weekday())
    days_since_sunday = (date.weekday() + 1) % 7
    sunday = date - timedelta(days=days_since_sunday)
    saturday = sunday + timedelta(days=6)
    return (sunday, saturday)

def events_overlap(event1, event2):
    """Check if two events overlap in time"""
    start1 = datetime.strptime(event1['start_datetime'], '%Y-%m-%d %H:%M:%S')
    end1 = datetime.strptime(event1['end_datetime'], '%Y-%m-%d %H:%M:%S')
    start2 = datetime.strptime(event2['start_datetime'], '%Y-%m-%d %H:%M:%S')
    end2 = datetime.strptime(event2['end_datetime'], '%Y-%m-%d %H:%M:%S')
    
    return start1 < end2 and start2 < end1

def calculate_overlap_columns(events):
    """Calculate column positions for overlapping events"""
    if not events:
        return events
    
    # Sort events by start time
    sorted_events = sorted(events, key=lambda e: e['start_datetime'])
    
    # Find overlapping groups
    groups = []
    for event in sorted_events:
        # Find which existing groups this event overlaps with
        overlapping_groups = []
        for i, group in enumerate(groups):
            if any(events_overlap(event, e) for e in group):
                overlapping_groups.append(i)
        
        if not overlapping_groups:
            # No overlap, create new group
            groups.append([event])
        else:
            # Merge all overlapping groups and add this event
            merged_group = [event]
            for i in sorted(overlapping_groups, reverse=True):
                merged_group.extend(groups.pop(i))
            groups.append(merged_group)
    
    # Assign columns within each group
    for group in groups:
        # Sort by start time within group
        group.sort(key=lambda e: e['start_datetime'])
        
        # Track which columns are occupied at each time
        columns = []
        for event in group:
            start = datetime.strptime(event['start_datetime'], '%Y-%m-%d %H:%M:%S')
            
            # Find first available column
            col = 0
            while True:
                # Check if this column is free at event start time
                is_free = True
                if col < len(columns):
                    for existing_event in columns[col]:
                        existing_end = datetime.strptime(existing_event['end_datetime'], '%Y-%m-%d %H:%M:%S')
                        if existing_end > start:
                            is_free = False
                            break
                
                if is_free:
                    # Use this column
                    if col >= len(columns):
                        columns.append([])
                    columns[col].append(event)
                    event['overlap_column'] = col
                    event['overlap_total'] = len(columns)
                    break
                col += 1
        
        # Update total columns for all events in group
        total_cols = len(columns)
        for event in group:
            event['overlap_total'] = total_cols
    
    return sorted_events

@app.route('/')
def index():
    """Redirect to today's date."""
    today = datetime.now().strftime('%Y-%m-%d')
    return redirect(url_for('daily_view', date=today))

@app.route('/calendar/<date>')
def daily_view(date):
    """Display the daily calendar view for a specific date."""
    try:
        # Parse the date
        current_date = datetime.strptime(date, '%Y-%m-%d')
    except ValueError:
        # If invalid date, redirect to today
        today = datetime.now().strftime('%Y-%m-%d')
        return redirect(url_for('daily_view', date=today))
    
    # Calculate previous and next day
    prev_day = (current_date - timedelta(days=1)).strftime('%Y-%m-%d')
    next_day = (current_date + timedelta(days=1)).strftime('%Y-%m-%d')
    
    # Load tags
    tags = load_tags()
    
    # Get events for this date
    events = database.get_events_by_date(date)
    
    # Process events for timeline view
    processed_events = []
    for event in events:
        event_dict = dict(event)
        
        # Parse datetimes
        start_dt = datetime.strptime(event['start_datetime'], '%Y-%m-%d %H:%M:%S')
        end_dt = datetime.strptime(event['end_datetime'], '%Y-%m-%d %H:%M:%S')
        
        # Clip to current day boundaries
        day_start = current_date.replace(hour=0, minute=0, second=0)
        day_end = current_date.replace(hour=23, minute=59, second=59)
        
        clipped_start = max(start_dt, day_start)
        clipped_end = min(end_dt, day_end)
        
        # Skip events that don't overlap with this day
        if clipped_start >= day_end or clipped_end <= day_start:
            continue
        
        # Calculate position from midnight (in minutes)
        start_minutes = clipped_start.hour * 60 + clipped_start.minute
        end_minutes = clipped_end.hour * 60 + clipped_end.minute
        duration = end_minutes - start_minutes
        
        event_dict['top_position'] = start_minutes
        event_dict['height'] = duration
        event_dict['duration_minutes'] = duration
        
        # Format display times
        event_dict['start_time'] = start_dt.strftime('%I:%M %p')
        event_dict['end_time'] = end_dt.strftime('%I:%M %p')
        
        # Check if event spans multiple days
        event_dict['multi_day'] = start_dt.date() != end_dt.date()
        event_dict['continues_before'] = start_dt < day_start
        event_dict['continues_after'] = end_dt > day_end
        
        # Get tag color
        tag_value = event['tag'] if event['tag'] else ''
        event_dict['tag_color'] = get_tag_color(tag_value, tags) if tag_value else '#6b7280'
        
        # Format for datetime-local input (for editing)
        event_dict['start_datetime_local'] = start_dt.strftime('%Y-%m-%dT%H:%M')
        event_dict['end_datetime_local'] = end_dt.strftime('%Y-%m-%dT%H:%M')
        
        processed_events.append(event_dict)
    
    # Calculate overlap columns
    processed_events = calculate_overlap_columns(processed_events)
    
    # Format the date for display
    display_date = current_date.strftime('%A, %B %d, %Y')
    
    return render_template('daily.html',
                         date=date,
                         display_date=display_date,
                         prev_day=prev_day,
                         next_day=next_day,
                         events=processed_events,
                         tags=tags)

@app.route('/add_event', methods=['POST'])
def add_event():
    """Add a new event."""
    date = request.form.get('date')
    title = request.form.get('title', '').strip() or '(no name)'
    description = request.form.get('description', '')
    tag = request.form.get('tag', '')
    start_datetime = request.form.get('start_datetime')
    end_datetime = request.form.get('end_datetime')
    
    if date and title and start_datetime and end_datetime:
        # Convert from datetime-local format to database format
        start_dt = datetime.strptime(start_datetime, '%Y-%m-%dT%H:%M')
        end_dt = datetime.strptime(end_datetime, '%Y-%m-%dT%H:%M')
        
        # Ensure end is after start
        if end_dt <= start_dt:
            end_dt = start_dt + timedelta(hours=1)
        
        start_datetime_str = start_dt.strftime('%Y-%m-%d %H:%M:%S')
        end_datetime_str = end_dt.strftime('%Y-%m-%d %H:%M:%S')
        
        database.add_event(start_datetime_str, end_datetime_str, title, description, tag)
    
    return redirect(url_for('daily_view', date=date))

@app.route('/update_event/<int:event_id>', methods=['POST'])
def update_event(event_id):
    """Update an existing event."""
    date = request.form.get('date')
    title = request.form.get('title', '').strip() or '(no name)'
    description = request.form.get('description', '')
    tag = request.form.get('tag', '')
    start_datetime = request.form.get('start_datetime')
    end_datetime = request.form.get('end_datetime')
    view_type = request.form.get('view', 'daily')  # Get which view to return to
    
    if title and start_datetime and end_datetime:
        # Convert from datetime-local format to database format
        start_dt = datetime.strptime(start_datetime, '%Y-%m-%dT%H:%M')
        end_dt = datetime.strptime(end_datetime, '%Y-%m-%dT%H:%M')
        
        # Ensure end is after start
        if end_dt <= start_dt:
            end_dt = start_dt + timedelta(hours=1)
        
        start_datetime_str = start_dt.strftime('%Y-%m-%d %H:%M:%S')
        end_datetime_str = end_dt.strftime('%Y-%m-%d %H:%M:%S')
        
        database.update_event(event_id, start_datetime_str, end_datetime_str, title, description, tag)
    
    if view_type == 'weekly':
        return redirect(url_for('weekly_view', date=date))
    return redirect(url_for('daily_view', date=date))

@app.route('/delete_event/<int:event_id>', methods=['POST'])
def delete_event(event_id):
    """Delete an event"""
    date = request.form['date']
    view_type = request.form.get('view', 'daily')
    
    database.delete_event(event_id)
    
    if view_type == 'weekly':
        return redirect(url_for('weekly_view', date=date))
    return redirect(url_for('daily_view', date=date))

@app.route('/weekly/<date>')
def weekly_view(date):
    """Display the weekly calendar view for a week containing the given date."""
    try:
        # Parse the date and get the week range
        sunday, saturday = get_week_range(date)
    except ValueError:
        # If invalid date, redirect to today's week
        today = datetime.now().strftime('%Y-%m-%d')
        return redirect(url_for('weekly_view', date=today))
    
    # Calculate previous and next week (move by 7 days)
    prev_week = (sunday - timedelta(days=7)).strftime('%Y-%m-%d')
    next_week = (sunday + timedelta(days=7)).strftime('%Y-%m-%d')
    
    # Load tags
    tags = load_tags()
    
    # Get events for all 7 days
    week_data = []
    current_day = sunday
    for i in range(7):
        day_str = current_day.strftime('%Y-%m-%d')
        day_name = current_day.strftime('%a')  # Sun, Mon, etc.
        day_display = current_day.strftime('%m/%d')  # 12/17
        
        # Get events for this day
        events = database.get_events_by_date(day_str)
        
        # Process events (similar to daily view)
        processed_events = []
        for event in events:
            event_dict = dict(event)
            
            # Parse datetimes
            start_dt = datetime.strptime(event['start_datetime'], '%Y-%m-%d %H:%M:%S')
            end_dt = datetime.strptime(event['end_datetime'], '%Y-%m-%d %H:%M:%S')
            
            # Calculate positioning
            start_minutes = start_dt.hour * 60 + start_dt.minute
            end_minutes = end_dt.hour * 60 + end_dt.minute
            duration_minutes = end_minutes - start_minutes
            
            # Format times
            event_dict['start_time'] = start_dt.strftime('%I:%M%p').lstrip('0').lower()
            event_dict['end_time'] = end_dt.strftime('%I:%M%p').lstrip('0').lower()
            
            # For data attributes
            event_dict['start_minutes'] = start_minutes
            event_dict['duration'] = duration_minutes
            
            # Get tag color
            if event_dict.get('tag'):
                event_dict['color'] = get_tag_color(event_dict['tag'], tags)
            else:
                event_dict['color'] = '#6b7280'
            
            # Add ISO format for editing
            event_dict['start_datetime_local'] = start_dt.strftime('%Y-%m-%dT%H:%M')
            event_dict['end_datetime_local'] = end_dt.strftime('%Y-%m-%dT%H:%M')
            
            processed_events.append(event_dict)
        
        # Calculate overlap columns for this day's events
        processed_events = calculate_overlap_columns(processed_events)
        
        week_data.append({
            'date': day_str,
            'day_name': day_name,
            'day_display': day_display,
            'events': processed_events
        })
        
        current_day += timedelta(days=1)
    
    return render_template('weekly.html',
                         week_data=week_data,
                         sunday_date=sunday.strftime('%Y-%m-%d'),
                         today=datetime.now().strftime('%Y-%m-%d'),
                         tags=tags,
                         prev_week=prev_week,
                         next_week=next_week)

@app.route('/import_ics', methods=['POST'])
def import_ics():
    """Import events from an uploaded .ics file."""
    from flask import flash
    
    # Get the uploaded file
    if 'ics_file' not in request.files:
        flash('No file uploaded', 'error')
        return redirect(request.referrer or url_for('index'))
    
    file = request.files['ics_file']
    
    # Check if file was selected
    if file.filename == '':
        flash('No file selected', 'error')
        return redirect(request.referrer or url_for('index'))
    
    # Verify it's an .ics file
    if not file.filename.endswith('.ics'):
        flash('Please upload a valid .ics file', 'error')
        return redirect(request.referrer or url_for('index'))
    
    # Get the selected tag
    tag = request.form.get('import_tag', '')
    
    try:
        # Read file content
        file_content = file.read()
        
        # Parse the ICS file
        events = ics_parser.parse_ics_file(file_content)
        
        if not events:
            flash('No events found in the file', 'warning')
            return redirect(request.referrer or url_for('index'))
        
        # Import events to database
        imported_count = database.bulk_add_events(events, tag)
        
        flash(f'Successfully imported {imported_count} events!', 'success')
        
    except ValueError as e:
        flash(f'Error parsing file: {str(e)}', 'error')
    except Exception as e:
        flash(f'Error importing events: {str(e)}', 'error')
    
    return redirect(request.referrer or url_for('index'))

if __name__ == '__main__':
    app.run(debug=True, port=5001)
