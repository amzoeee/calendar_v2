"""ICS file exporter for calendar events"""

from datetime import datetime


def generate_ics(events, calendar_name="My Calendar"):
    """Generate an ICS file from a list of events.
    
    Args:
        events: List of event dictionaries with keys:
                - id, title, start_datetime, end_datetime, description (optional)
        calendar_name: Name for the calendar
    
    Returns:
        str: ICS file content
    """
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        f"PRODID:-//Calendar App//{calendar_name}//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
    ]
    
    for event in events:
        # Parse datetime strings
        start_dt = datetime.strptime(event['start_datetime'], '%Y-%m-%d %H:%M:%S')
        end_dt = datetime.strptime(event['end_datetime'], '%Y-%m-%d %H:%M:%S')
        
        # Format for ICS (YYYYMMDDTHHMMSS)
        start_str = start_dt.strftime('%Y%m%dT%H%M%S')
        end_str = end_dt.strftime('%Y%m%dT%H%M%S')
        
        # Create unique UID
        uid = f"event-{event['id']}@calendar-app"
        
        # Get title and description
        title = event.get('title', 'Untitled Event')
        description = event.get('description', '')
        
        # Escape special characters in text fields
        title = escape_ics_text(title)
        description = escape_ics_text(description)
        
        lines.extend([
            "BEGIN:VEVENT",
            f"UID:{uid}",
            f"DTSTART:{start_str}",
            f"DTEND:{end_str}",
            f"SUMMARY:{title}",
        ])
        
        if description:
            lines.append(f"DESCRIPTION:{description}")
        
        # Add timestamp for when this was created
        now = datetime.now().strftime('%Y%m%dT%H%M%SZ')
        lines.append(f"DTSTAMP:{now}")
        
        lines.append("END:VEVENT")
    
    lines.append("END:VCALENDAR")
    
    # Join with CRLF as per ICS spec
    return '\r\n'.join(lines) + '\r\n'


def escape_ics_text(text):
    """Escape special characters in ICS text fields.
    
    Args:
        text: String to escape
        
    Returns:
        str: Escaped string
    """
    if not text:
        return ''
    
    # Escape backslashes, commas, semicolons, and newlines
    text = text.replace('\\', '\\\\')
    text = text.replace(',', '\\,')
    text = text.replace(';', '\\;')
    text = text.replace('\n', '\\n')
    
    return text
