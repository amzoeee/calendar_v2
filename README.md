# Flask Calendar App

A simple, elegant Flask-based calendar application with daily view and persistent event storage.

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

## Running the Application

1. **Start the Flask development server**
   ```bash
   python app.py
   ```

2. **Open your browser**
   Navigate to: `http://localhost:5002`

3. **Start adding events!**
   - The app will automatically redirect to today's date
   - Use the navigation buttons to move between days
   - Click "Today" to jump back to the current date

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

## Data Persistence

All events are stored in a SQLite database file (`calendar.db`) which is created automatically when you first run the application. This database file persists between server restarts, so your events will always be there when you return!

## Event Tags and Customization

The application supports categorizing events with custom tags and colors.

1.  **Customize Tags**: You can define your own tags in `tags.json`. Each tag has a `name`, a HEX `color`, and an `order` for display:
    ```json
    {
        "tags": [
            {"name": "Work", "color": "#007bff", "order": 1},
            {"name": "Social", "color": "#ffc107", "order": 3}
        ]
    }
    ```
2.  **Auto-Generation**: To ensure the app works out of the box, `create_default_tags.py` automatically generates a default `tags.json` file if one doesn't exist when the server starts.

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
