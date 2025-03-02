import os
import requests
import json
import time
import subprocess
import re
from flask import Flask, request, jsonify
from flask_cors import CORS
from dotenv import load_dotenv, set_key
from pathlib import Path
from datetime import datetime
import platform
import glob
import asyncio
import time
import argparse
import sys
import threading

def engine ()
    autopilot_mode = args.autopilot
    cleanup_previous_assembled_scripts()
    print_instructions_once_per_day()
    stop_event = threading.Event()
    # Start the animated loading in a separate thread
    loading_thread = threading.Thread(target=animated_loading, args=(stop_event, True, "Processing", 0.2))
    if query:
        loading_thread.start()
        process_input_in_autopilot_mode(query, autopilot_mode)
        stop_event.set()
        loading_thread.join()  # Wait for the animation thread to finish

    else:
        stop_event.clear()  # Reset the stop_event for reuse
        stop_event.set()

    # If no query is provided, enter the standard command loop

        while True:
            if command_mode:
                command = input("\033[92mCMD>\033[0m ").strip().lower()
                if command == 'quit':
                    break
                elif command == 'reset':
                    reset_conversation()
                    print("\033[94mThe conversation has been reset.\033[0m")
                elif command == 'save':
                    file_path = input("Enter the file path to save the last response: ")
                    with open(file_path, "w") as file:
                        file.write(last_response)
                    print(f"Response saved to {file_path}")
                elif command == 'autopilot':
                    autopilot_mode = not autopilot_mode
                    print(f"Autopilot mode {'enabled' if autopilot_mode else 'disabled'}.")
                elif command == 'script':
                    if last_response:
                        scripts = extract_script_from_response(last_response)
                        if scripts:
                            final_script = assemble_final_script(scripts)
                            auto_handle_script_execution(final_script)  # Call the revised function here
                        else:
                            print("No script found in the last response.")
                    else:
                        print("No last response to process.")

                elif command == 'model':
                    new_model = input("Enter the model to switch to: ")
                    if new_model in models:
                        current_model = new_model
                        print(f"Model switched to {current_model}")
                    else:
                        print("Invalid model")
                elif command == 'list_models':
                    print("Available models:")
                    for model in models.keys():
                        print(model)
                elif command == 'config':
                    print(f"Current configuration: Model = {current_model}, Server Port = {server_port}")
#               elif command == 'server':
                    action = input("Enter server action (up, down): ")
                    if action.lower() == 'up':
                        app.run(port=server_port)
                    elif action.lower() == 'down':
                        print("Server stopping is manually handled; please use Ctrl+C.")
                    else:
                        print("Invalid server action")
                command_mode = False
            elif llm_suggestions:
                # Process the LLM suggestions
                print(f"{CYAN}Processing LLM suggestion:{RESET} {llm_suggestions}")
                user_input = llm_suggestions  # Treat the suggestion as user input
                llm_suggestions = None  # Reset the suggestions to ensure it's processed only once                 
            else:
                stop_event.set()  # Signal the thread to stop
                sys.stdout.flush()  # Ensure all output has been flushed to the console
                user_input = input(f"{YELLOW}@:{RESET} ").strip()
                if user_input.upper() == 'CMD':
                    command_mode = True 
                    
                elif autopilot_mode:
                    llm_response = chat_with_model(user_input, autopilot=True)
                    scripts = extract_script_from_response(llm_response)
                    if scripts:
                        for script, file_extension, _ in scripts:
                            if file_extension == "py":
                                final_script = assemble_final_script([(script, file_extension, "python")], api_key)
                                # Execute only Python scripts with error handling and consultation
                                execute_script_with_repl_and_consultation(final_script, api_key)
                            else:
                                print(f"Bypassing repl test and executing in local environment: {script[:30]}...")
                                process_input_in_autopilot_mode(user_input, autopilot_mode)
                                stop_event.set()
                            
                            print("Enter another task or press ctrl+z to quit.")
                            
                    else:
                        print("No executable script found in the LLM response.")
                else:
                    # Non-autopilot mode processing
                    last_response = chat_with_model(user_input, autopilot=False)
                    print_streamed_message(last_response, CYAN)
                    


    print("Operation completed.")
    stop_event.set()

if __name__ == "__main__"
engine()