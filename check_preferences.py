#!/usr/bin/env python

import os
import json

def check_preferences():
    config_dir = os.path.expanduser("~/.config/cli-FSD")
    preferences_file = os.path.join(config_dir, "preferences.json")
    
    print(f"Checking preferences file at: {preferences_file}")
    
    if not os.path.exists(preferences_file):
        print("Preferences file does not exist!")
        return
    
    try:
        with open(preferences_file, 'r') as f:
            content = f.read()
            print(f"Raw content: {content}")
            
            if not content.strip():
                print("File is empty!")
                return
                
            prefs = json.loads(content)
            print(f"Parsed preferences: {json.dumps(prefs, indent=2)}")
            
            if 'last_ollama_model' in prefs:
                print(f"Found last_ollama_model: {prefs['last_ollama_model']}")
            else:
                print("WARNING: last_ollama_model key not found in preferences!")
                
            # Try writing a test value
            print("\nUpdating preferences file with a test value...")
            prefs['last_ollama_model'] = "test-model-value"
            
            with open(preferences_file, 'w') as f_write:
                json.dump(prefs, f_write)
                
            print("Test value written. Reading back...")
            
            # Read it back
            with open(preferences_file, 'r') as f_read:
                updated_prefs = json.load(f_read)
                print(f"Updated preferences: {json.dumps(updated_prefs, indent=2)}")
                
    except json.JSONDecodeError as e:
        print(f"Error parsing preferences file: {e}")
    except Exception as e:
        print(f"Unexpected error: {e}")

if __name__ == "__main__":
    check_preferences()
