#!/usr/bin/env python3
"""
We Out Here 2026 - Set Times Scraper & Update Checker
Fetches the latest schedule from the official website and compares it
with the DATA already in your index.html.
"""

import re
import requests
import json
from datetime import datetime
from collections import defaultdict

# The URL to scrape
URL = "https://weoutherefestival.com/set-times/"

# Stage name mapping (the app uses these exact names)
STAGE_NAMES = [
    "Main Stage", "Lush Life", "Rhythm Corner", "The Grove", "The Bowl",
    "Tomorrow's Warriors Big Top", "Roller Rink", "Love Dancin'",
    "Lemon Lounge", "Brawnswood", "Worldwide FM: WOH Radio", "Carhartt WIP",
    "Beat Hotel x Ilegal Mezcal", "Passenger: Ground Tempo",
    "Near Mint Record Store", "Love-Serve Bar", "Once In A Blue Moon",
    "Talks Tent", "The Knowledge", "BookLove", "Craftwerk",
    "Craftwerk: Outdoors", "Lemon Lounge Workshops", "The Sanctuary",
    "Wellbeing Tent", "Wellness Tent: The Clearing",
    "Near Mint Record Signings", "Action Station"
]

# Stage index mapping (we'll try to infer these from the page)
STAGE_INDEX_MAP = {name: i for i, name in enumerate(STAGE_NAMES)}


def fetch_page():
    """Fetch the set times page."""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
    }
    try:
        response = requests.get(URL, headers=headers, timeout=15)
        response.raise_for_status()
        return response.text
    except requests.RequestException as e:
        print(f"❌ Failed to fetch page: {e}")
        return None


def parse_artist_entries(html):
    """
    Parse artist entries from the page text.
    The page uses a pattern like: "9:20pm - 11:00pm #### HVYWGHT & THE OUTLOOK ORCHESTRA"
    """
    # Extract the main content - the page is mostly plain text
    # Look for time patterns with #### as separators
    pattern = r'(\d{1,2}:\d{2}(?:am|pm))\s*-\s*(\d{1,2}:\d{2}(?:am|pm))\s*####\s*([^#\n]+?)(?=\s*\d{1,2}:\d{2}(?:am|pm)\s*-|$)'
    
    matches = re.findall(pattern, html, re.IGNORECASE)
    
    entries = []
    for start_time, end_time, artist in matches:
        artist = artist.strip()
        # Skip if it looks like a time or header
        if re.match(r'^\d{1,2}:\d{2}', artist):
            continue
        entries.append({
            'start': start_time.strip(),
            'end': end_time.strip(),
            'artist': artist
        })
    
    return entries


def time_to_minutes(time_str):
    """Convert "9:20pm" to minutes since midnight."""
    time_str = time_str.lower().strip()
    is_pm = 'pm' in time_str
    is_am = 'am' in time_str
    # Remove am/pm
    time_str = time_str.replace('am', '').replace('pm', '').strip()
    
    if ':' in time_str:
        h, m = map(int, time_str.split(':'))
    else:
        h = int(time_str)
        m = 0
    
    if is_pm and h != 12:
        h += 12
    if is_am and h == 12:
        h = 0
    
    return h * 60 + m


def convert_to_app_format(entries, day_index=0):
    """
    Convert scraped entries to the app's DATA format.
    Returns a list of events in the format: [start_min, end_min, stage_index, artist_name]
    """
    events = []
    
    # The page doesn't clearly indicate which stage each artist is on.
    # We need to either:
    # 1. Infer from the position in the page (complex)
    # 2. Use a lookup table (maintain manually)
    # 3. Leave stage as a placeholder and let the user map them
    
    # For now, we'll use a simple heuristic:
    # - If the artist appears in your existing DATA, keep their stage
    # - Otherwise, assign a default stage (you'll need to map manually)
    
    # We'll just extract the raw entries and let you map them
    raw_events = []
    for entry in entries:
        try:
            start_mins = time_to_minutes(entry['start'])
            end_mins = time_to_minutes(entry['end'])
            # Handle overnight sets (e.g., 11:00pm - 12:00am)
            if end_mins < start_mins:
                end_mins += 1440
            
            raw_events.append({
                'start': start_mins,
                'end': end_mins,
                'artist': entry['artist'],
                'start_str': entry['start'],
                'end_str': entry['end']
            })
        except Exception as e:
            print(f"⚠️ Could not parse: {entry} - {e}")
    
    return raw_events


def load_existing_data():
    """Load the DATA array from your index.html file."""
    try:
        with open('index.html', 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Find the DATA array - it's a large block
        # Look for "var DATA = [" and then find the matching closing bracket
        start_pattern = r'var DATA\s*=\s*\['
        match = re.search(start_pattern, content)
        if not match:
            print("❌ Could not find DATA array in index.html")
            return None
        
        start_pos = match.start()
        # Find the matching closing bracket - we need to count brackets
        bracket_count = 0
        end_pos = None
        in_string = False
        escape = False
        
        for i in range(match.end(), len(content)):
            char = content[i]
            if escape:
                escape = False
                continue
            if char == '\\':
                escape = True
                continue
            if char == '"' or char == "'":
                in_string = not in_string
                continue
            if in_string:
                continue
            if char == '[':
                bracket_count += 1
            elif char == ']':
                if bracket_count == 0:
                    end_pos = i + 1
                    break
                bracket_count -= 1
        
        if end_pos is None:
            print("❌ Could not find end of DATA array")
            return None
        
        data_str = content[start_pos:end_pos]
        # Remove the "var DATA = " prefix
        data_str = data_str.replace('var DATA = ', '', 1)
        
        # Parse the JSON
        try:
            data = json.loads(data_str)
            return data
        except json.JSONDecodeError as e:
            print(f"❌ Could not parse DATA array: {e}")
            # Try a more lenient approach - eval (use with caution)
            try:
                # This is a fallback - the DATA array uses JavaScript syntax
                # which is mostly JSON-compatible except for trailing commas
                # and comments. We'll clean it up.
                import ast
                # Convert JS to Python-compatible format
                cleaned = data_str
                # Remove comments
                cleaned = re.sub(r'//.*?$', '', cleaned, flags=re.MULTILINE)
                # Remove trailing commas
                cleaned = re.sub(r',\s*\]', ']', cleaned)
                cleaned = re.sub(r',\s*}', '}', cleaned)
                data = json.loads(cleaned)
                return data
            except Exception as e2:
                print(f"❌ Fallback parsing failed: {e2}")
                return None
                
    except FileNotFoundError:
        print("❌ index.html not found in current directory")
        return None
    except Exception as e:
        print(f"❌ Error loading index.html: {e}")
        return None


def compare_data(existing, scraped_events):
    """Compare existing DATA with scraped events and report differences."""
    # Flatten existing events into a lookup by artist name
    existing_lookup = {}
    for day in existing:
        for event in day.get('ev', []):
            # event format: [start, end, stage_index, artist_name]
            artist = event[3].lower().strip()
            if artist not in existing_lookup:
                existing_lookup[artist] = []
            existing_lookup[artist].append({
                'start': event[0],
                'end': event[1],
                'stage': event[2],
                'day': day.get('dn', 'Unknown')
            })
    
    # Build a lookup from scraped events
    scraped_lookup = {}
    for event in scraped_events:
        artist = event['artist'].lower().strip()
        scraped_lookup[artist] = {
            'start': event['start'],
            'end': event['end'],
            'start_str': event['start_str'],
            'end_str': event['end_str']
        }
    
    # Find differences
    differences = {
        'added': [],
        'removed': [],
        'time_changed': [],
        'stage_changed': []
    }
    
    # Check for new artists
    for artist, scraped_info in scraped_lookup.items():
        if artist not in existing_lookup:
            differences['added'].append({
                'artist': artist,
                'scraped_time': f"{scraped_info['start_str']} - {scraped_info['end_str']}"
            })
    
    # Check for removed artists
    for artist in existing_lookup:
        if artist not in scraped_lookup:
            differences['removed'].append({'artist': artist})
    
    # Check for time changes
    for artist, scraped_info in scraped_lookup.items():
        if artist in existing_lookup:
            existing_info = existing_lookup[artist][0]  # Take first match
            if existing_info['start'] != scraped_info['start'] or existing_info['end'] != scraped_info['end']:
                differences['time_changed'].append({
                    'artist': artist,
                    'old': f"{existing_info['start']//60:02d}:{existing_info['start']%60:02d} - {existing_info['end']//60:02d}:{existing_info['end']%60:02d}",
                    'new': f"{scraped_info['start_str']} - {scraped_info['end_str']}"
                })
    
    return differences


def main():
    print("🔄 Fetching latest set times from", URL)
    html = fetch_page()
    if not html:
        return
    
    print("📝 Parsing artist entries...")
    entries = parse_artist_entries(html)
    print(f"✅ Found {len(entries)} artist entries")
    
    # Show a sample of what was found
    print("\n📋 Sample entries found:")
    for entry in entries[:10]:
        print(f"  {entry['start']} - {entry['end']}: {entry['artist']}")
    
    if len(entries) > 10:
        print(f"  ... and {len(entries) - 10} more")
    
    # Convert to app format (without stage info for now)
    scraped_events = convert_to_app_format(entries)
    print(f"\n🔄 Converted {len(scraped_events)} events to minutes format")
    
    # Load existing data
    print("\n📂 Loading existing DATA from index.html...")
    existing = load_existing_data()
    if not existing:
        print("⚠️ Could not load existing DATA. Run this script in the same folder as index.html")
        return
    
    # Compare
    print("\n🔍 Comparing with existing DATA...")
    diff = compare_data(existing, scraped_events)
    
    # Report
    print("\n" + "=" * 60)
    print("📊 UPDATE REPORT")
    print("=" * 60)
    
    if diff['added']:
        print(f"\n➕ NEW ARTISTS ADDED ({len(diff['added'])}):")
        for item in diff['added'][:20]:
            print(f"  • {item['artist']} — {item['scraped_time']}")
        if len(diff['added']) > 20:
            print(f"  ... and {len(diff['added']) - 20} more")
    
    if diff['removed']:
        print(f"\n➖ ARTISTS REMOVED ({len(diff['removed'])}):")
        for item in diff['removed'][:20]:
            print(f"  • {item['artist']}")
        if len(diff['removed']) > 20:
            print(f"  ... and {len(diff['removed']) - 20} more")
    
    if diff['time_changed']:
        print(f"\n🕐 TIME CHANGES ({len(diff['time_changed'])}):")
        for item in diff['time_changed'][:20]:
            print(f"  • {item['artist']}: {item['old']} → {item['new']}")
        if len(diff['time_changed']) > 20:
            print(f"  ... and {len(diff['time_changed']) - 20} more")
    
    if not any(diff.values()):
        print("\n✅ No changes detected! Your DATA is up to date.")
    
    # Show how to update
    print("\n" + "=" * 60)
    print("📝 HOW TO UPDATE YOUR APP")
    print("=" * 60)
    print("""
1. The scraped data above shows what's changed.
2. To update your index.html, you'll need to manually edit the DATA array.
3. The DATA array is near the top of index.html, after "var DATA = ["
4. Each event follows this format:
     [start_minutes, end_minutes, stage_index, "Artist Name"]
5. Update the affected entries and commit/push to GitHub.
6. Cloudflare will auto-deploy the changes in 1-2 minutes.
    """)


if __name__ == "__main__":
    main()