from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from datetime import datetime, timedelta
import database
import json
import os
from dotenv import load_dotenv

from utils import ics_parser

# Load environment variables from .env file
load_dotenv()

app = Flask(__name__)
# Use secret key from environment variable, fallback to default for development
app.secret_key = os.getenv('SECRET_KEY', 'your-secret-key-here-change-in-production')

# Setup Flask-Login
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# User class for Flask-Login
class User(UserMixin):
    def __init__(self, id, username):
        self.id = id
        self.username = username

@login_manager.user_loader
def load_user(user_id):
    user_data = database.get_user_by_id(int(user_id))
    if user_data:
        return User(user_data['id'], user_data['username'])
    return None


def load_tags(user_id):
    """Load tag configuration from database"""
    return database.get_all_tags(user_id)

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

# Authentication Routes

@app.route('/login', methods=['GET', 'POST'])
def login():
    """User login"""
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        remember = request.form.get('remember') == 'on'
        
        user_data = database.get_user_by_username(username)
        
        if user_data and database.verify_password(user_data['id'], password):
            user = User(user_data['id'], user_data['username'])
            login_user(user, remember=remember)
            flash(f'Welcome back, {username}!', 'success')
            
            # Redirect to next page or index
            next_page = request.args.get('next')
            return redirect(next_page) if next_page else redirect(url_for('index'))
        else:
            flash('Invalid username or password', 'error')
    
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    """User registration"""
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')
        
        # Validation
        if not username:
            flash('Username is required', 'error')
            return render_template('register.html', username=username)
        elif not password:
            flash('Password is required', 'error')
            return render_template('register.html', username=username)
        elif password != confirm_password:
            flash('Passwords do not match', 'error')
            return render_template('register.html', username=username)
        else:
            try:
                user_id = database.create_user(username, password)
                user = User(user_id, username)
                login_user(user)
                flash(f'Account created successfully! Welcome, {username}!', 'success')
                return redirect(url_for('index'))
            except ValueError as e:
                flash(str(e), 'error')
                return render_template('register.html', username=username)
    
    return render_template('register.html')

@app.route('/logout')
@login_required
def logout():
    """User logout"""
    logout_user()
    flash('You have been logged out', 'success')
    return redirect(url_for('login'))

# Calendar Routes

@app.route('/')
@login_required
def index():
    """Redirect to today's date."""
    today = datetime.now().strftime('%Y-%m-%d')
    return redirect(url_for('daily_view', date=today))

@app.route('/calendar/<date>')
@login_required
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
    
    # Load tags for current user
    tags = load_tags(current_user.id)
    
    # Get events for this date for current user
    events = database.get_events_by_date(date, current_user.id)
    
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
@login_required
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
        
        database.add_event(start_datetime_str, end_datetime_str, title, description, tag, current_user.id)
    
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
    tags = load_tags(current_user.id)
    
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
            
            # Clip to current day boundaries for display
            day_start = datetime.combine(current_day, datetime.min.time())
            day_end = datetime.combine(current_day, datetime.max.time())
            
            clipped_start = max(start_dt, day_start)
            clipped_end = min(end_dt, day_end)
            
            # Skip events that don't overlap with this day
            if clipped_start >= day_end or clipped_end <= day_start:
                continue
            
            # Calculate positioning based on clipped times
            start_minutes = clipped_start.hour * 60 + clipped_start.minute
            end_minutes = clipped_end.hour * 60 + clipped_end.minute
            duration_minutes = end_minutes - start_minutes
            
            # Format times (show original times for display)
            event_dict['start_time'] = start_dt.strftime('%I:%M%p').lstrip('0').lower()
            event_dict['end_time'] = end_dt.strftime('%I:%M%p').lstrip('0').lower()
            
            # For data attributes (use clipped values for positioning)
            event_dict['start_minutes'] = start_minutes
            event_dict['duration'] = duration_minutes
            
            # Get tag color
            if event_dict.get('tag'):
                event_dict['color'] = get_tag_color(event_dict['tag'], tags)
            else:
                event_dict['color'] = '#6b7280'
            
            # Add ISO format for editing (original times, not clipped)
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


@app.route('/stats/<date>')
def stats_view(date):
    """Display weekly tag statistics."""
    try:
        # Parse the date and get the week range
        sunday, saturday = get_week_range(date)
    except ValueError:
        # If invalid date, redirect to today's week
        today = datetime.now().strftime('%Y-%m-%d')
        return redirect(url_for('stats_view', date=today))
    
    # Calculate previous and next week
    prev_week = (sunday - timedelta(days=7)).strftime('%Y-%m-%d')
    next_week = (sunday + timedelta(days=7)).strftime('%Y-%m-%d')
    
    # Load tags
    tags = load_tags(current_user.id)
    
    # Get tag hours for the week
    start_date = sunday.strftime('%Y-%m-%d')
    end_date = (saturday + timedelta(days=1)).strftime('%Y-%m-%d')  # End is exclusive
    tag_hours = database.get_tag_hours_for_week(start_date, end_date)
    
    # Build day data with tag hours
    week_data = []
    current_day = sunday
    all_tags_set = set()
    max_hours = 0
    
    for i in range(7):
        day_str = current_day.strftime('%Y-%m-%d')
        day_name = current_day.strftime('%a')
        
        day_hours = tag_hours.get(day_str, {})
        total_hours = sum(day_hours.values())
        max_hours = max(max_hours, total_hours)
        
        # Track all tags
        all_tags_set.update(day_hours.keys())
        
        week_data.append({
            'date': day_str,
            'day_name': day_name,
            'hours': day_hours,
            'total': total_hours
        })
        
        current_day += timedelta(days=1)
    
    # Calculate weekly averages per tag
    tag_averages = {}
    for tag in all_tags_set:
        total = sum(day['hours'].get(tag, 0) for day in week_data)
        tag_averages[tag] = total / 7.0
    
    # Create tag color lookup dict
    tag_colors = {}
    for tag_obj in tags:
        tag_colors[tag_obj['name']] = tag_obj['color']
    tag_colors['Untagged'] = '#6b7280'  # Default gray for untagged
    
    # Order all_tags based on tags.json order (reversed) with Untagged at bottom
    tag_order = [tag['name'] for tag in tags]
    tag_order.reverse()  # Reverse so higher order numbers appear lower on stats
    all_tags_ordered = [tag for tag in tag_order if tag in all_tags_set]
    # Add any tags not in tags.json (like 'Untagged') at the bottom
    all_tags_ordered.extend([tag for tag in all_tags_set if tag not in tag_order])
    
    # Round max_hours up to next whole number for scale
    max_scale = int(max_hours) + 1 if max_hours > 0 else 24
    
    return render_template('stats.html',
                         week_data=week_data,
                         tags=tags,
                         all_tags=all_tags_ordered,
                         tag_averages=tag_averages,
                         tag_colors=tag_colors,
                         max_scale=max_scale,
                         sunday_date=sunday.strftime('%Y-%m-%d'),
                         today=datetime.now().strftime('%Y-%m-%d'),
                         prev_week=prev_week,
                         next_week=next_week)


@app.route('/import_ics', methods=['POST'])
@login_required
def import_ics():
    """Import events from an ICS file."""
    
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
        flash('Please upload a .ics file', 'error')
        return redirect(request.referrer or url_for('index'))
    
    # Get the selected tag
    tag = request.form.get('import_tag', '')
    
    try:
        # Read and parse the ICS file
        ics_content = file.read().decode('utf-8')
        events = ics_parser.parse_ics(ics_content)
        
        # Import each event with the current user's ID
        imported_count = 0
        for event in events:
            database.add_event(
                event['start_datetime'],
                event['end_datetime'],
                event['title'],
                event.get('description', ''),
                tag,
                current_user.id  # Assign to current user
            )
            imported_count += 1
        
        flash(f'Successfully imported {imported_count} events!', 'success')
        
    except Exception as e:
        flash(f'Error importing file: {str(e)}', 'error')
    
    return redirect(request.referrer or url_for('index'))

@app.route('/settings')
@login_required
def settings_view():
    """Render settings page with current tags"""
    tags = load_tags(current_user.id)
    return render_template('settings.html', tags=tags, today=datetime.now().strftime('%Y-%m-%d'))

@app.route('/settings/tags/add', methods=['POST'])
@login_required
def add_tag_route():
    """Add a new tag"""
    name = request.form.get('name', '').strip()
    color = request.form.get('color', '#6b7280')
    
    if not name:
        flash('Tag name is required', 'error')
        return redirect(url_for('settings_view'))
    
    try:
        database.add_tag(name, color, current_user.id)
        flash(f'Tag "{name}" added successfully!', 'success')
    except ValueError as e:
        flash(str(e), 'error')
    
    return redirect(url_for('settings_view'))

@app.route('/settings/tags/<int:tag_id>/update', methods=['POST'])
def update_tag_route(tag_id):
    """Update a tag's name and color"""
    name = request.form.get('name', '').strip()
    color = request.form.get('color', '#6b7280')
    
    if not name:
        flash('Tag name is required', 'error')
        return redirect(url_for('settings_view'))
    
    try:
        database.update_tag(tag_id, name, color)
        flash(f'Tag updated successfully!', 'success')
    except ValueError as e:
        flash(str(e), 'error')
    
    return redirect(url_for('settings_view'))

@app.route('/settings/tags/<int:tag_id>/delete', methods=['POST'])
def delete_tag_route(tag_id):
    """Delete a tag"""
    result = database.delete_tag(tag_id)
    
    if result['success']:
        if result.get('event_count', 0) > 0:
            flash(f'Tag deleted successfully! {result["event_count"]} event(s) set to untagged.', 'success')
        else:
            flash('Tag deleted successfully!', 'success')
    else:
        flash(result.get('error', 'Failed to delete tag'), 'error')
    
    return redirect(url_for('settings_view'))

@app.route('/settings/tags/reorder', methods=['POST'])
def reorder_tags_route():
    """Reorder tags"""
    tag_ids = request.get_json().get('tag_ids', [])
    
    try:
        database.reorder_tags(tag_ids)
        return {'success': True}
    except Exception as e:
        return {'success': False, 'error': str(e)}, 400

@app.route('/api/events')
def get_events_api():
    """API endpoint to get events, optionally filtered by tag"""
    tag = request.args.get('tag')
    
    if tag:
        events = database.get_events_by_tag(tag)
    else:
        events = database.fetch_all_events()
    
    return jsonify({'events': events})

if __name__ == '__main__':
    # Get port from environment variable, default to 5002
    port = int(os.getenv('PORT', 5002))
    # Bind to 0.0.0.0 to allow external connections (local network access)
    # Set debug=False in production for security
    app.run(host='0.0.0.0', port=port, debug=True)
