# Flask Calendar App

A Flask-based, multi-user calendar application with daily, weekly, and stats views and persistent event storage.

## Setup

1. **Clone or navigate to this directory**

2. **Create a virtual environment (optional but recommended)**
   ```bash
   python3 -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

## Using the Application

### Starting the App

1. **Run the local server script**
   ```bash
   ./run_local.sh
   ```
   This starts the Flask server and displays your local IP address for network access.

2. **Access the app**
   - From this computer: `http://localhost:5002`
   - From other devices on your network: `http://[your-ip]:5002`

### First Time Setup

1. **Create an account** - Navigate to the registration page and create a username/password
2. **Login** - Use your credentials to access your personal calendar

### Managing Events

**Creating Events**
- Click on any time slot in the daily or weekly view to create a new event
- Fill in the title, select a tag, and set start/end times
- Events can span multiple days

**Editing Events**
- Click on an existing event to edit its details
- Modify title, tag, or times as needed

**Deleting Events**
- Click on an event and select the delete option to remove it

### Views

**Daily View** - See all events for a single day with hourly time slots
**Weekly View** - View 7 days at once to see your week at a glance  
**Stats View** - Visualize how you spend time across different tags with bar charts
**Settings** - Manage your tags (add, edit, delete, reorder) and import calendar files

### Tag Management

1. Navigate to **Settings**
2. **Add tags** - Create custom tags with names and colors
3. **Edit tags** - Change tag names or colors
4. **Reorder tags** - Drag and drop tags to reorder them
5. **Delete tags** - Remove tags (events with that tag become untagged)

### Importing Calendars

1. Go to **Settings**
2. Click **Import ICS File**
3. Select a `.ics` file from Google Calendar or other calendar apps
4. Choose a tag to assign to all imported events
5. Events will be added to your calendar


## Local Network Access

The app is configured to be accessible from other devices on your local network (e.g., your phone, tablet, or other computers on the same WiFi).

### Quick Start

1. **Run the app**
   ```bash
   ./run_local.sh
   ```
   The script will display your local IP address and access URLs.

2. **Access from other devices**
   - On another device connected to the same WiFi network
   - Open a browser and go to: `http://[YOUR_IP]:5002`
   - Example: `http://192.168.1.100:5002`

### Finding Your IP Address Manually

If you need to find your local IP address manually:

**macOS/Linux:**
```bash
ifconfig | grep "inet " | grep -v 127.0.0.1
```

**Windows:**
```bash
ipconfig
```
Look for "IPv4 Address" under your active network adapter.

### Troubleshooting

- **Can't access from other devices?** Check that:
  - Both devices are on the same WiFi network
  - Your firewall isn't blocking port 5002
  - You're using the correct IP address
  
- **Want external access (outside your network)?**
  - Use ngrok: `brew install ngrok && ngrok http 5002`
  - Or configure port forwarding on your router (more complex)

## Project Structure

```
calendar_v2/
├── app.py              # Main Flask application
├── database.py         # Database operations and schema
├── requirements.txt    # Python dependencies
├── run_local.sh        # Startup script for local network access
├── .env                # Environment variables (SECRET_KEY, PORT)
├── .env.example        # Template for environment variables
├── scripts/            # Utility scripts
│   ├── create_default_tags.py
│   └── migrate_tags_manual.py
├── utils/              # Utility modules
│   ├── __init__.py
│   └── ics_parser.py   # ICS file parser for imports
├── templates/          # HTML templates
│   ├── daily.html
│   ├── weekly.html
│   ├── stats.html
│   └── settings.html
├── static/             # CSS and static assets
│   └── style.css
└── calendar.db         # SQLite database (created on first run)
```

## Technologies Used

- **Flask** - Python web framework
- **SQLite** - Lightweight database for data persistence
- **HTML/CSS** - Frontend with modern styling
- **JavaScript** - Event editing functionality
