#!/usr/bin/env python

import json
import os
from cli_FSD.configuration import Config

def test_ollama_model_persistence():
    # Initialize config
    print("Initializing config...")
    config = Config()
    
    # Print full config details for debugging
    print(f"Config dir: {config.config_dir}")
    print(f"Preferences file: {config.preferences_file}")
    
    # Save the original value
    original_model = config.last_ollama_model
    print(f"Original last_ollama_model: {original_model}")
    
    # Read and print the current preferences file contents
    if os.path.exists(config.preferences_file):
        with open(config.preferences_file, 'r') as f:
            try:
                prefs = json.load(f)
                print(f"Current preferences file content: {json.dumps(prefs, indent=2)}")
            except json.JSONDecodeError:
                print("Error: Preferences file exists but is not valid JSON")
    else:
        print(f"Preferences file does not exist yet at: {config.preferences_file}")
    
    # Set a test value
    test_model = "llama3.1:70b"  # Use a different model
    print(f"Setting last_ollama_model to: {test_model}")
    config.last_ollama_model = test_model
    
    # Save preferences
    config.save_preferences()
    print("Preferences saved")
    
    # Verify the file was saved properly
    if os.path.exists(config.preferences_file):
        with open(config.preferences_file, 'r') as f:
            try:
                saved_prefs = json.load(f)
                print(f"Saved preferences: {json.dumps(saved_prefs, indent=2)}")
                if 'last_ollama_model' in saved_prefs:
                    print(f"Confirmed last_ollama_model was saved as: {saved_prefs['last_ollama_model']}")
                else:
                    print("ERROR: last_ollama_model key not found in saved preferences!")
            except json.JSONDecodeError:
                print("Error: Failed to read preferences file after saving")
    else:
        print(f"ERROR: Preferences file still doesn't exist after saving!")
    
    # Create a new config object to simulate restarting the app
    print("\nReinitializing config to simulate app restart...")
    new_config = Config()
    
    # Check if the value was persisted
    print(f"Loaded last_ollama_model: {new_config.last_ollama_model}")
    
    # Restore original value
    print(f"Restoring original model: {original_model}")
    new_config.last_ollama_model = original_model
    new_config.save_preferences()
    print("Preferences restored")
    
    # Final verification
    with open(new_config.preferences_file, 'r') as f:
        final_prefs = json.load(f)
        print(f"Final preferences: {json.dumps(final_prefs, indent=2)}")

if __name__ == "__main__":
    test_ollama_model_persistence()
