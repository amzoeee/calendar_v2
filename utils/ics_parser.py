"""
ICS file parser for importing Google Calendar events.
Extracts event data from .ics files and converts to database format.
"""

from icalendar import Calendar
from datetime import datetime
import pytz


def parse_ics_file(file_content):
    """
    Parse an ICS file and extract event data.
    
    Args:
        file_content: Binary content of the .ics file
        
    Returns:
        list: List of event dictionaries with keys:
            - title: Event summary/title
            - description: Event description
            - start_datetime: Start datetime string (YYYY-MM-DD HH:MM:SS)
            - end_datetime: End datetime string (YYYY-MM-DD HH:MM:SS)
            
    Raises:
        ValueError: If the file is not a valid ICS file
    """
    try:
        cal = Calendar.from_ical(file_content)
    except Exception as e:
        raise ValueError(f"Invalid ICS file format: {str(e)}")
    
    events = []
    
    for component in cal.walk():
        if component.name == "VEVENT":
            event = {}
            
            # Extract title (summary)
            summary = component.get('summary')
            event['title'] = str(summary) if summary else '(no title)'
            
            # Extract description
            description = component.get('description')
            event['description'] = str(description) if description else ''
            
            # Extract RRULE for recurring events
            rrule = component.get('rrule')
            if rrule:
                # Convert RRULE to proper RFC 5545 format string
                # rrule.to_ical() returns bytes, decode to string
                event['rrule'] = rrule.to_ical().decode('utf-8')
            else:
                event['rrule'] = None
            
            # Extract start and end datetimes
            dtstart = component.get('dtstart')
            dtend = component.get('dtend')
            
            if not dtstart:
                continue  # Skip events without start time
            
            # Convert to datetime object
            start_dt = dtstart.dt
            
            # Handle all-day events (date objects vs datetime objects)
            if isinstance(start_dt, datetime):
                # Regular event with time
                # Convert to local timezone if needed
                if start_dt.tzinfo is not None:
                    # Convert to local time (system timezone)
                    local_tz = pytz.timezone('America/Los_Angeles')  # Adjust as needed
                    start_dt = start_dt.astimezone(local_tz)
                    # Remove timezone info for database storage
                    start_dt = start_dt.replace(tzinfo=None)
            else:
                # All-day event (date object) - default to 9 AM - 5 PM
                start_dt = datetime.combine(start_dt, datetime.min.time().replace(hour=9))
            
            # Handle end datetime
            if dtend:
                end_dt = dtend.dt
                if isinstance(end_dt, datetime):
                    if end_dt.tzinfo is not None:
                        local_tz = pytz.timezone('America/Los_Angeles')
                        end_dt = end_dt.astimezone(local_tz)
                        end_dt = end_dt.replace(tzinfo=None)
                else:
                    # All-day event
                    end_dt = datetime.combine(end_dt, datetime.min.time().replace(hour=17))
            else:
                # No end time specified, default to 1 hour duration
                from datetime import timedelta
                end_dt = start_dt + timedelta(hours=1)
            
            # Format as strings for database
            event['start_datetime'] = start_dt.strftime('%Y-%m-%d %H:%M:%S')
            event['end_datetime'] = end_dt.strftime('%Y-%m-%d %H:%M:%S')
            
            events.append(event)
    
    return events


def get_event_count(file_content):
    """
    Get the number of events in an ICS file without full parsing.
    
    Args:
        file_content: Binary content of the .ics file
        
    Returns:
        int: Number of events in the file
    """
    try:
        cal = Calendar.from_ical(file_content)
        count = sum(1 for component in cal.walk() if component.name == "VEVENT")
        return count
    except:
        return 0
