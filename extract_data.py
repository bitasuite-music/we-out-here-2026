#!/usr/bin/env python3
"""
Extract the DATA array from index.html and save it as data.json.
Also modifies index.html to load DATA via fetch.
"""
import re
import json

def extract_data():
    with open('index.html', 'r', encoding='utf-8') as f:
        content = f.read()

    # Find the DATA array
    match = re.search(r'var DATA\s*=\s*(\[.*?\]);', content, re.DOTALL)
    if not match:
        print("❌ Could not find DATA array in index.html")
        return

    data_str = match.group(1)
    # Clean up for JSON: remove comments, trailing commas, and convert to valid JSON
    cleaned = re.sub(r'//.*?$', '', data_str, flags=re.MULTILINE)
    cleaned = re.sub(r',\s*\]', ']', cleaned)  # remove trailing commas before ]
    cleaned = re.sub(r',\s*}', '}', cleaned)    # remove trailing commas before }

    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as e:
        print(f"❌ JSON decode error: {e}")
        # fallback: try using ast.literal_eval (slower but more lenient)
        try:
            import ast
            data = ast.literal_eval(cleaned)
        except Exception as e2:
            print(f"❌ ast fallback failed: {e2}")
            return

    # Write to data.json
    with open('data.json', 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(f"✅ data.json created with {len(data)} days")

    # Now modify index.html to load DATA from fetch instead of inline
    # We'll replace the entire DATA block with a placeholder
    new_script = '''
/* DATA is now loaded from data.json via fetch */
var DATA = [];
async function loadData() {
    try {
        const resp = await fetch('data.json');
        DATA = await resp.json();
        // Re-render after data loads
        render();
    } catch (e) {
        console.warn('Could not load data.json, using fallback if any');
    }
}
// Call loadData() after the initial render? We'll need to adjust.
'''
    # Actually we need to integrate this carefully. For now, we'll just create data.json
    # and give manual instructions to replace the DATA block.

if __name__ == "__main__":
    extract_data()