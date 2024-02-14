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

def animated_loading(stop_event, use_emojis=True, message="Loading", interval=0.2):
    if use_emojis:
        frames = ["🌑 ", "🌒 ", "🌓 ", "🌔 ", "🌕 ", "🌖 ", "🌗 ", "🌘 "]  # Added a space after each emoji
    else:
        frames = ["- ", "\\ ", "| ", "/ "]  # Added a space after each ASCII character

    while not stop_event.is_set():
        for frame in frames:
            if stop_event.is_set():
                break
            # Added a space after the message for separation
            sys.stdout.write(f"\r{message} {frame}")
            sys.stdout.flush()
            time.sleep(interval)
    # Clear the line after stopping
    sys.stdout.write("\r" + " " * (len(message) + len(frames[0]) + 1) + "\r")


# Setup argument parser for known flags only
parser = argparse.ArgumentParser(description="Terminal Companion with Full Self Drive Mode")
parser.add_argument("-a", "--autopilot", action="store_true", default='off', help="Turn autopilot mode on")
parser.add_argument("-autopilot", choices=['on', 'off'], default='off',
                    help="Turn autopilot mode on or off at startup")
args, unknown = parser.parse_known_args()
query = ' '.join(unknown)  # Construct the query from unknown arguments


app = Flask(__name__)
CORS(app)

CYAN = "\033[96m"
YELLOW = "\033[93m"
BOLD = "\033[1m"
RESET = "\033[0m"
BOLD = "\033[1m"
RED = "\033[31m"
GREEN = "\033[32m"
YELLOW = "\033[33m"

dotenv_path = Path('.env')
load_dotenv(dotenv_path=dotenv_path)

models = {
    "gpt4": "gpt-4",
    "gpt40613": "gpt-4-0613",
    "gpt432k0613": "gpt-4-32k-0613",
    "35turbo": "gpt-3.5-turbo",
    "gpt-3.5-turbo-0125": "gpt-3.5-turbo-0125",
    "gpt-4-32k-0613	": "gpt-4-32k-0613",
    "gpt-4-turbo-preview": "gpt-4-turbo-preview",
    "gpt-4-vision-preview": "gpt-4-vision-preview",
    "dall-e-3":"dall-e-3",
    
}


current_model = os.getenv("DEFAULT_MODEL", "gpt-4-turbo-preview")

api_key = os.getenv("OPENAI_API_KEY")
if not api_key:
    api_key = input("Please enter your OpenAI API key: ")
    dotenv_path.touch(exist_ok=True)
    set_key(dotenv_path, "OPENAI_API_KEY", api_key)

server_port = int(os.getenv("SERVER_PORT", 5000))
conversation_history = []

def print_instructions():
    print(f"{GREEN}{BOLD}Terminal Companion with Full Self Drive Mode{RESET}")
    print(f"{GREEN}{BOLD}FSD is ON. {RESET}")
    print("Type 'CMD' to enter command mode and enter 'script' to save and run a script.")
    print("Type 'autopilot' in command mode to toggle autopilot mode on/off.")
    print(f"{YELLOW}--------------------------------------------------{RESET}")
    print(f"{RED}{BOLD}WARNING: Giving LLMs access to run shell commands is dangerous.{RESET}")
    print(f"{RED}{BOLD}Only use autopilot in sandbox environments.{RESET}")
    print(f"{YELLOW}--------------------------------------------------{RESET}")

def print_instructions_once_per_day():
    instructions_file = ".last_instructions_display.txt"
    current_date = datetime.now().date()

    # Try to read the last display date from the file
    try:
        if os.path.exists(instructions_file):
            with open(instructions_file, "r") as file:
                last_display_date_str = file.read().strip()
                # Attempt to parse the last display date
                try:
                    last_display_date = datetime.strptime(last_display_date_str, "%Y-%m-%d").date()
                    if last_display_date < current_date:
                        raise FileNotFoundError  # Date doesn't match, show instructions again
                except ValueError:
                    # Date format in file was incorrect, show instructions again
                    raise FileNotFoundError
        else:
            # File doesn't exist, show instructions
            raise FileNotFoundError
    except FileNotFoundError:
        # Show instructions and update the file with the current date
        with open(instructions_file, "w") as file:
            file.write(current_date.strftime("%Y-%m-%d"))
        print_instructions()



def print_message(sender, message):
    color = YELLOW if sender == "user" else CYAN
    prefix = f"{color}You:{RESET} " if sender == "user" else f"{color}Bot:{RESET} "
    print(f"{prefix}{message}")

def print_streamed_message(message, color=CYAN):
    for char in message:
        print(f"{color}{char}{RESET}", end='', flush=True)
        time.sleep(0.03)
    print()

def execute_shell_command(command, stream_output=True):
    print(f"{CYAN}Processing...{RESET}")  # Static message before executing the command
    try:
        process = subprocess.Popen(command, shell=False, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True)
        if stream_output:
            # Stream output in real-time
            for line in iter(process.stdout.readline, ''):
                print(f"{CYAN}{line.strip()}{RESET}")
        else:
            # Wait for the command to complete and then process the output
            output, _ = process.communicate()
            print(f"{CYAN}{output.strip()}{RESET}")

        process.stdout.close()  # Close the stdout after processing the output
        return_code = process.wait()  # Wait for the subprocess to terminate
        if return_code:
            raise subprocess.CalledProcessError(return_code, command)
    except subprocess.CalledProcessError as e:
        # If the command failed, print the error. Adjust depending on how you wish to display errors.
        print(f"{YELLOW}Command failed with error: {e.output}{RESET}")

def chat_with_model(message, autopilot=False):
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}"
    }
    data = {
        "model": models[current_model],
        "messages": [
            {"role": "system", "content": "Generate bash commands for tasks. Comment minimally, you are expected to produce code that is runnable. You are part of a chain."},
            {"role": "user", "content": message}
        ]
    }

    try:
        response = requests.post("https://api.openai.com/v1/chat/completions", headers=headers, data=json.dumps(data))
        response.raise_for_status()  # This will raise an exception for HTTP errors
        model_response = response.json().get('choices', [{}])[0].get('message', {}).get('content', 'No response')
    except requests.exceptions.HTTPError as http_err:
        model_response = f"HTTP error occurred: {http_err}"  # Provide a more graceful error message
    except Exception as err:
        model_response = f"Other error occurred: {err}"  # Handle other possible errors

    if autopilot:  
        print(f"{CYAN}Generated command:{RESET} {model_response}")
    else:
        # Append to conversation history here if needed
        pass

    return model_response

def extract_script_from_response(response):
    # Adjusted regex to match code blocks without a language specifier
    matches = re.findall(r"```(?:bash|python)?\n(.*?)```", response, re.DOTALL)
    scripts = []
    for script in matches:
        # Default to bash script if language is unspecified
        scripts.append((script, "sh", "bash"))
    return scripts


def save_script(script, file_extension):
    filename = input("Enter a filename for the script (without extension): ")
    full_filename = f"{filename}.{file_extension}"
    with open(full_filename, "w") as file:
        file.write(script)
    print(f"Script saved as {full_filename}.")
    return full_filename

def user_decide_and_act(script, file_extension):
    if script:
        save = input("Would you like to save this script? (yes/no): ").lower() == "yes"
        if save:
            full_filename = save_script(script, file_extension)
            
            run = input("Would you like to run this script? (yes/no): ").lower() == "yes"
            if run:
                if file_extension == "py":
                    subprocess.run(["python", full_filename], check=True)
                elif file_extension == "sh":
                    subprocess.run(["bash", full_filename], check=True)
                else:
                    print(f"Running scripts with .{file_extension} extension is not supported.")
    else:
        print("No script found in the last response.")

def get_system_info():
    """
    Collect basic system information.
    """
    return {
        'os': platform.system(),
        'os_version': platform.version(),
        'architecture': platform.machine(),
        'python_version': platform.python_version(),
        'cpu': platform.processor()
    }

def consult_llm_for_error_resolution(error_message, api_key):
    """
    Consults the LLM for advice on resolving an encountered error.
    """
    # Format the error message into a question for the LLM
    prompt_message = f"I encountered an error while running a script: '{error_message}'. How can I resolve this?"

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}"
    }
    data = {
        "model": "gpt-4-turbo-preview",
        "messages": [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": prompt_message}
        ]
    }

    try:
        response = requests.post("https://api.openai.com/v1/chat/completions", headers=headers, json=data)
        response.raise_for_status()
        chat_response = response.json()
        if chat_response['choices'] and chat_response['choices'][0]['message']['content']:
            return clean_up_llm_response(chat_response['choices'][0]['message']['content'])
        else:
            print("No advice was returned by the model.")
            return None
    except requests.exceptions.RequestException as e:
        print(f"API request error: {e}")
        return None

def execute_script_with_repl_and_consultation(script, api_key):
    """
    Attempts to execute a given script, enters REPL on error, and consults LLM for error resolution.
    """
    try:
        # Example: Executing a Python script using exec() for demonstration purposes
        # In a real scenario, ensure to validate and securely handle script execution
        exec(script, {'__builtins__': {}})
        print("Script executed successfully.")
    except Exception as e:
        print(f"Error encountered: {e}")
        
        # Consult LLM for error resolution
        error_resolution = consult_llm_for_error_resolution(str(e), api_key)
        if error_resolution:
            print(f"LLM suggests:\n{error_resolution}")
            
            # Enter REPL for manual intervention or to try executing a corrected script
            while True:
                user_action = input("Attempt suggested fix (yes/no/exit)? ").lower()
                if user_action == 'yes':
                    try:
                        # Assuming the error_resolution is executable code; adjust as necessary
                        exec(error_resolution, {'__builtins__': {}})
                        print("Corrected script executed successfully.")
                        break
                    except Exception as corrected_error:
                        print(f"Error in corrected script: {corrected_error}")
                        continue  # Offer the REPL again or adjust logic as needed
                elif user_action == 'no':
                    # Directly enter REPL mode for user to manually fix or investigate
                    manual_fix_code = input("Enter corrected code or 'exit' to quit: ")
                    if manual_fix_code.lower() == 'exit':
                        print("Exiting REPL.")
                        break
                    else:
                        try:
                            exec(manual_fix_code, {'__builtins__': {}})
                            print("Manual fix executed successfully.")
                            break
                        except Exception as manual_fix_error:
                            print(f"Error in manual fix: {manual_fix_error}")
                            continue  # Offer the REPL again
                elif user_action == 'exit':
                    print("Exiting REPL.")
                    break
        else:
            print("Manual resolution required. No specific suggestions from LLM.")


def assemble_final_script(scripts, api_key):
    """
    Sends the extracted scripts along with system information to the OpenAI API 'chat completions' endpoint 
    for processing and assembling into a final executable script, ensuring compatibility based on the provided system info.
    """
    # Collect system information.
    system_info = get_system_info()
    
    # Create a detailed description of the system info to include in the prompt.
    info_details = (f"System information: OS={system_info['os']}, OS Version={system_info['os_version']}, "
                    f"Architecture={system_info['architecture']}, Python Version={system_info['python_version']}, "
                    f"CPU={system_info['cpu']}.")

    # Join all scripts into one, assuming they're compatible or sequential.
    final_script_prompt = "\n\n".join(script for script, _, _ in scripts)
    
    # Enhance the prompt with system information for the LLM to consider.
    prompt_message = (f"{info_details}\n\n"
                      "Based on the above system information, combine the following scripts into a single executable script. "
                      "Ensure compatibility across all Unix-like systems, prioritizing portable commands. Do not comment, only provide code. You are a part of a chain and returning anything other than code will break the chain:\n\n"
                      f"{final_script_prompt}")

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}"
    }
    data = {
        "model": "gpt-4-turbo-preview",  # Adjust based on the model you intend to use
        "messages": [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": prompt_message}
        ]
    }

    try:
        response = requests.post("https://api.openai.com/v1/chat/completions", headers=headers, json=data)
        response.raise_for_status()  # Ensures HTTP errors are checked
        chat_response = response.json()
        if chat_response['choices'] and chat_response['choices'][0]['message']['content']:
            # Extract only the executable part of the LLM's response
            cleaned_script = clean_up_llm_response(chat_response['choices'][0]['message']['content'])
            return cleaned_script
        else:
            print("No assembled script was returned by the model.")
            return None
    except requests.exceptions.RequestException as e:
        print(f"API request error: {e}")
        return None


def reset_conversation():
    global conversation_history
    conversation_history = []

def handle_script_invocation(scripts):
    for script, file_extension, language in scripts:
        print(f"Found a {language} script.")
        save = input("Would you like to save this script? (yes/no): ").lower() == "yes"
        if save:
            full_filename = save_script(script, file_extension)
            print(f"Script saved as {full_filename}.")

            if language != "bash":
                create_and_run = input(f"Would you like to create and optionally run a bash script to execute this {language} script? (yes/no): ").lower() == "yes"
                if create_and_run:
                    bash_script_name = input("Enter a filename for the bash script (without extension): ")
                    bash_full_filename = f"{bash_script_name}.sh"
                    with open(bash_full_filename, "w") as bash_file:
                        if language == "python":
                            bash_file.write(f"#!/bin/bash\npython {full_filename}\n")
                        # Add more language-specific handlers here
                        bash_file.write("\n")  # Ensure the script ends with a newline
                    print(f"Bash script saved as {bash_full_filename}.")
                    os.chmod(bash_full_filename, 0o755)  # Make the bash script executable

                    # Optionally run the bash script
                    run_bash = input("Would you like to run this bash script now? (yes/no): ").lower() == "yes"
                    if run_bash:
                        execute_shell_command(f"bash {bash_full_filename}")

                    # Optionally add to $PATH
                    add_to_path = input("Would you like to add this script to $PATH for easy invocation? (yes/no): ").lower() == "yes"
                    if add_to_path:
                        export_path_command = f"export PATH=\"$PATH:{os.getcwd()}\""
                        print(f"Run the following command to add to $PATH:\n{export_path_command}")
                        # Note: This change will only last for the session; consider adding to profile files for permanence
            elif file_extension == "sh":
                run = input("Would you like to run this bash script now? (yes/no): ").lower() == "yes"
                if run:
                    execute_shell_command(f"bash {full_filename}")

last_response = ""
command_mode = False
autopilot_mode = False
if args.autopilot == 'on':
    autopilot_mode = True
else:
    autopilot_mode = False


def create_bash_invocation_script(full_filename, language):
    bash_script_name = input("Enter a filename for the bash script (without extension): ")
    bash_full_filename = f"{bash_script_name}.sh"
    with open(bash_full_filename, "w") as bash_file:
        if language == "python":
            bash_file.write(f"#!/bin/bash\npython {full_filename}\n")
        # Add more language-specific handlers here
    print(f"Bash script saved as {bash_full_filename}.")
    # Optionally add to $PATH
    add_to_path = input("Would you like to add this script to $PATH for easy invocation? (yes/no): ").lower() == "yes"
    if add_to_path:
        export_path_command = f"export PATH=\"$PATH:{os.getcwd()}\""
        print(f"Run the following command to add to $PATH:\n{export_path_command}")

def clean_up_llm_response(llm_response):
    """
    Extracts executable script parts from the LLM's response, focusing on content
    within specific code block markers and ignoring instructional text or comments.
    """
    # Assuming bash scripts, adjust regex if handling other languages
    script_blocks = re.findall(r"```(?:bash|sh)\n(.*?)\n```", llm_response, re.DOTALL)
    if script_blocks:
        # Join all extracted script blocks, trimming whitespace
        cleaned_script = "\n".join(block.strip() for block in script_blocks)
        return cleaned_script
    else:
        print("No executable script blocks found in the response.")
        return llm_response  # Return original response if no blocks are found

def cleanup_previous_assembled_scripts():
    # Search for hidden assembled scripts with the naming pattern
    for filename in glob.glob(".assembled_script_*.sh"):
        try:
            os.remove(filename)
            print(f"Deleted previous assembled script: {filename}")
        except OSError as e:
            print(f"Error deleting file {filename}: {e}")


def auto_handle_script_execution(final_script, autopilot=False, stream_output=True):
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f".assembled_script_{timestamp}.sh"
    
    # Save the final script
    with open(filename, "w") as file:
        file.write(final_script)
    print(f"{CYAN}Final script assembled and saved as {filename}.{RESET}")
    
    # Set executable permissions automatically
    os.chmod(filename, 0o755)

    # Execute the script
    print(f"{CYAN}Executing {filename}...{RESET}")
    execute_shell_command(f"./{filename}", stream_output=stream_output)

def animated_sending_message(stop_event):
    chars = ["\\", "|", "/", "-"]
    idx = 0
    print("sending...", end="", flush=True)
    while not stop_event.is_set():
        print(f"\rSending... {chars[idx % len(chars)]}", end="", flush=True)
        idx += 1
        time.sleep(0.1)
    print("\r", end="")

cleanup_previous_assembled_scripts()



# Flask route to handle chat requests
@app.route("/chat", methods=["POST"])
def chat():
    message = request.json.get("message")
    response = chat_with_model(message, autopilot=autopilot_mode)
    return jsonify(response)

# Flask route to save a file
@app.route("/save_file", methods=["POST"])
def save_file():
    file_path = request.json.get("file_path")
    content = request.json.get("content")
    try:
        with open(file_path, "w") as file:
            file.write(content)
        return {"status": "success", "message": f"File saved to {file_path}"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

def process_input_in_autopilot_mode(query, autopilot_mode):
    print(f"{CYAN}Sending command to LLM...{RESET}")
    llm_response = chat_with_model(query, autopilot=autopilot_mode)
    scripts = extract_script_from_response(llm_response)
    if scripts:
        final_script = assemble_final_script(scripts, api_key)
        auto_handle_script_execution(final_script, autopilot=autopilot_mode, stream_output=True)
    else:
        print("No executable script found in the LLM response.")

if __name__ == "__main__":
    autopilot_mode = args.autopilot
    cleanup_previous_assembled_scripts()
    # Call this function at the start of your program
    print_instructions_once_per_day()
# Create a stop event for the animated loading
    stop_event = threading.Event()

    # Start the animated loading in a separate thread
    loading_thread = threading.Thread(target=animated_loading, args=(stop_event, True, "Processing", 0.2))
    loading_thread.start()

    if query:
        process_input_in_autopilot_mode(query, autopilot_mode)
    else:

       # If no query is provided, enter the standard command loop
        while True:
            if command_mode:
                stop_event.set()
                loading_thread.join()
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
                elif command == 'server':
                    action = input("Enter server action (up, down): ")
                    if action.lower() == 'up':
                        app.run(port=server_port)
                    elif action.lower() == 'down':
                        print("Server stopping is manually handled; please use Ctrl+C.")
                    else:
                        print("Invalid server action")
                command_mode = False
            else:
                stop_event.set()
                loading_thread.join()
                user_input = input(f"{YELLOW}You:{RESET} ").strip()
                if user_input.upper() == 'CMD':
                    command_mode = True
                    continue
                elif autopilot_mode:
                   process_input_in_autopilot_mode(user_input, autopilot_mode)
                else:
                    # Non-autopilot mode processing
                    last_response = chat_with_model(user_input, autopilot=False)
                    print_streamed_message(last_response, CYAN)

    # Stop the animated loading
    stop_event.set()
    loading_thread.join()

    print("Operation completed.")