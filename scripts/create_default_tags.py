import json
import os

def create_default_tags():
    """Create a default tags.json file if it doesn't exist."""
    tags_file = os.path.join(os.path.dirname(__file__), 'tags.json')
    
    if os.path.exists(tags_file):
        return

    default_data = {
        "tags": [
            {"name": "Work", "color": "#007bff", "order": 1},
            {"name": "Personal", "color": "#28a745", "order": 2},
            {"name": "Social", "color": "#ffc107", "order": 3},
            {"name": "Important", "color": "#dc3545", "order": 4}
        ]
    }
    
    try:
        with open(tags_file, 'w') as f:
            json.dump(default_data, f, indent=4)
        print(f"Created default tags.json at {tags_file}")
    except Exception as e:
        print(f"Error creating default tags.json: {e}")

if __name__ == "__main__":
    create_default_tags()
