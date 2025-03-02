#1.4

#fixed command mode
# added gpt-4o as default model

# Added claude-3-opus mode and flag (-c)
# added foundation for OpenAI assistants api routing but it's not working yet 
   
#to-do: resolve response threadID error, fix flag for assistants api (ci) reimplement replicate flow, robust CMD mode and help log           

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
from datetime import datetime,date
from .resources.assembler import AssemblyAssist
import platform
import glob
import asyncio
import time
import argparse
import sys
import threading
import shlex
import queue
import ollama
from ollama import Client
import httpx
import urllib.parse
from groq import Groq as GroqClient
import base64




global llm_suggestions 
global replicate_suggestions  # This will store suggestions from Replicate
replicate_suggestions = ""
global groq_client



suggestions_queue = queue.Queue()

def animated_loading(stop_event, use_emojis=True, message="Loading", interval=0.2):
    frames = ["🌑 ", "🌒 ", "🌓 ", "🌔 ", "🌕 ", "🌖 ", "🌗 ", "🌘 "] if use_emojis else ["- ", "\\ ", "| ", "/ "]
    while not stop_event.is_set():
        for frame in frames:
            if stop_event.is_set():
                break
            sys.stdout.write(f"\r{message} {frame}")
            sys.stdout.flush()
            time.sleep(interval)
    sys.stdout.write("\r" + " " * (len(message) + 4) + "\r")  # Clear the line

# Setup argument parser for known flags only

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
    "gpt-4o": "gpt-4o",
    "gpt4": "gpt-4",
    "gpt40613": "gpt-4-0613",
    "gpt432k0613": "gpt-4-32k-0613",
    "35turbo": "gpt-3.5-turbo",
    "gpt-3.5-turbo-0125": "gpt-3.5-turbo-0125",
    "gpt-4-32k-0613	": "gpt-4-32k-0613",
    "gpt-4-turbo-preview": "gpt-4-turbo-preview",
    "gpt-4-vision-preview": "gpt-4-vision-preview",
    "dall-e-3":"dall-e-3",
    "o1-preview":"o1-preview"
    
}


current_model = os.getenv("DEFAULT_MODEL", "gpt-4o")
api_key = os.getenv("OPENAI_API_KEY")
if not api_key:
    api_key = input("Please enter your OpenAI API key: ")
    dotenv_path.touch(exist_ok=True)
    set_key(dotenv_path, "OPENAI_API_KEY", api_key)


server_port = int(os.getenv("SERVER_PORT", 5000))
conversation_history = []
 
def get_system_info():
    info = {
        'OS': platform.system(),
        'Version': platform.version(),
        'Machine': platform.machine(),
        'Processor': platform.processor(),
    }
    return ", ".join([f"{key}: {value}" for key, value in info.items()])

system_info = get_system_info()
instructions = f"You are a helpful assistant. The system information is as follows: {system_info}. Please review the following script for errors and suggest improvements."
app = Flask(__name__)
CORS(app)

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

def ask_user_to_retry():
    # Ask user if they want to retry the original command after executing the resolution
    user_input = input("Do you want to retry the original command? (yes/no): ").lower()
    return user_input == "yes"

def print_message(sender, message):
    color = YELLOW if sender == "user" else CYAN
    prefix = f"{color}You:{RESET} " if sender == "user" else f"{color}Bot:{RESET} "
    print(f"{prefix}{message}")

def print_streamed_message(message, color=CYAN):
    for char in message:
        print(f"{color}{char}{RESET}", end='', flush=True)
        time.sleep(0.03)
    print()

def process_pending_suggestions():
    while not suggestions_queue.empty():
        suggestion = suggestions_queue.get()
        print(f"{CYAN}Processing LLM suggestion:{RESET} {suggestion}")
        # Execute the suggestion if it's a valid command
        if suggestion.strip().startswith("chmod"):
            subprocess.run(suggestion, shell=True, text=True)
            print(f"{GREEN}Suggestion executed: {suggestion}{RESET}")
        suggestions_queue.task_done()


def execute_shell_command(command, api_key, stream_output=True, safe_mode=False, scriptreviewer_on=False):
    global llm_suggestions
    
    if command.startswith('./'):
        os.chmod(command[2:], 0o755)  # Ensure the script is executable

    if safe_mode:
        user_confirmation = input(f"Do you want to execute the following command: {command}? (yes/no): ").strip()
        if user_confirmation.lower() != "yes":
            print("Command execution aborted by the user.")
            return

    try:
        # Redirecting stderr to stdout to capture all output
        process = subprocess.Popen(command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True, bufsize=1)
        
        output_lines = []
        for line in iter(process.stdout.readline, ''):
            if stream_output:
                print(line, end='')  # Print each line of output as it comes
            output_lines.append(line.strip())
        
        process.stdout.close()
        return_code = process.wait()

        if return_code != 0:
            error_context = "\n".join(output_lines)  # Combine all output lines to form the error context
            print(f"{RED}Error encountered executing command: {error_context}{RESET}")
            if scriptreviewer_on:
                resolution = consult_openai_for_error_resolution(error_context, get_system_info())
            else:
                resolution = consult_llm_for_error_resolution(error_context, api_key)
            scripts = extract_script_from_response(resolution)
            for script in scripts:
                execute_resolution_script(script)
                llm_suggestions = None
        else:
            print(f"{GREEN}Command executed successfully.{RESET}")
    except subprocess.CalledProcessError as e:
        print(f"{RED}Command execution failed with error: {e}{RESET}")
    except Exception as e:
        print(f"An error occurred while executing the command: {e}")


def parse_resolution_for_command(resolution):
    """
    Parses the LLM's resolution text to extract an actionable command.
    This is a placeholder for your parsing logic. Adapt this to fit the format of your LLM's suggestions.
    """
    # Example parsing logic (very basic, likely needs to be more sophisticated)
    if "run the command" in resolution:
        # Extract the command following a specific phrase
        start = resolution.find("'''") + len("run the command")
        command = resolution[start:].strip()
        # Safely split the command into a list for subprocess
        return shlex.split(command)
    # Add more parsing rules as needed based on the format of resolutions
    return None

def chat_with_model(system_info, message, autopilot=False, use_claude=False, use_ollama=False, ollama_client=None, use_groq=False, groq_client=None, scriptreviewer_on=False):
    dotenv_path = Path('.env')
    load_dotenv(dotenv_path=dotenv_path)
    scriptreviewer_on=scriptreviewer_on
    groq_client=groq_client
    system_info = get_system_info()
    if use_ollama:
        if not ollama_client:
            print("Ollama client not initialized.")
            return "Ollama client missing."
        
        system_prompt = (f"Generate bash commands for tasks. "
                         "Comment minimally, you are expected to produce code that is runnable. "
                         f"You are part of a chain. System info: {system_info}")

        try:
            # Use the Ollama client to chat, including the system prompt for context
            response = ollama_client.chat(
                model='llama3',
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": message},
                ]
            )

            # Check for the 'content' in the 'message' part of the response
            if 'message' in response and 'content' in response['message']:
                assistant_message = response['message']['content']
                print(f"Ollama responded: {assistant_message}")
                return assistant_message
            else:
                print(f"Unexpected response format: {response}")
                return "Unexpected response format."

        except Exception as e:
            print(f"Error while chatting with Ollama: {e}")
            return f"Error: {e}"
        
    if use_groq:
        model_response = chat_with_groq(message, groq_client, system_info)
        
    if use_claude:
        anthropic_api_key = os.getenv("ANTHROPIC_API_KEY")
        if not anthropic_api_key:
            print("Anthropic API key not found. Ensure it's set in your .env file.")
            return "Anthropic API key missing."
        # Claude-specific setup
        headers = {
            "x-api-key": f"{anthropic_api_key}",
            "Content-Type": "application/json",
            "Anthropic-Version": "2023-06-01"
        }
        data = {
            "model": "claude-3-opus-20240229",
            "system": "Generate bash commands for tasks. Comment minimally, you are expected to produce code that is runnable. You are part of a chain.",  # System prompt at the top level
            "messages": [
                {"role": "user", "content": message},
            ],
            "max_tokens": 4096,
            "temperature": 0.7
        }
        endpoint = "https://api.anthropic.com/v1/messages"
    else:
        # Existing setup for OpenAI
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
        endpoint = "https://api.openai.com/v1/chat/completions"

    try:
        response = requests.post(endpoint, headers=headers, data=json.dumps(data))
        response.raise_for_status()
        if use_claude:
            content_blocks = response.json().get('content', [])
            model_response = ' '.join(block['text'] for block in content_blocks if block['type'] == 'text')
        else:
            model_response = response.json().get('choices', [{}])[0].get('message', {}).get('content', 'No response')

    except requests.exceptions.HTTPError as http_err:
        model_response = f"HTTP error occurred: {http_err}"
    except Exception as err:
        model_response = f"Other error occurred: {err}"
    if autopilot:  
        print(f"{CYAN}Generated command:{RESET} {model_response}")
    else:
        pass  # Append to conversation history here if needed

    return model_response


def extract_script_from_response(response):
    if not isinstance(response, str):
        print("Error: 'response' expected to be a string, received:", type(response))
        return []
    # Proceed with extracting scripts from the string 'response'
    matches = re.findall(r"```(?:bash|python)?\n(.*?)```", response, re.DOTALL)
    scripts = [(match, "sh", "bash") for match in matches]  # Adjusted to return a tuple (script, ext, lang)
    return scripts


def execute_resolution_script(script):
    global llm_suggestions
    print("Executing resolution script:\n", script)
    process = subprocess.run(script, shell=True, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if process.returncode == 0:
        print("Resolution script executed successfully:", process.stdout)
        llm_suggestions = None
    else:
        print("Error while executing resolution script:", process.stderr)
        llm_suggestions = None                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        


def save_script(script, file_extension, stop_event = threading.Event()
):
    stop_event = threading.Event()
    # Adding a space after the prompt icon for clarity
    stop_event.set()  # Signal to stop the loading animation
    loading_thread = threading.Thread(target=animated_loading, args=(stop_event,))
    loading_thread.start()


    loading_thread.join()  # Wait for the thread to finish
    filename = input("Enter a filename for the script (without extension): ").strip()  # Ensure to strip any leading/trailing whitespace
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

#def get_system_info():
#    """
#    Collect basic system information.
#    """
#    return {
#        'os': platform.system(),
#        'os_version': platform.version(),
#        'architecture': platform.machine(),
#        'python_version': platform.python_version(),
#        'cpu': platform.processor()
#    }

# Global variable to store LLM suggestions
llm_suggestions = None


def consult_llm_for_error_resolution(error_message, api_key):
    """
    Consults the LLM for advice on resolving an encountered error.
    """
    global llm_suggestions  # Assuming this variable is properly initialized elsewhere
    system_info = get_system_info()
    print(f"{CYAN}Consulting LLM for error resolution:{RESET} {error_message}")
    prompt_message = f"System Info: {system_info}\n Error: '{error_message}'. \n Provide code that resolves the error. Do not comment, only use code."

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}"
    }
    data = {
        "model": "gpt-4-turbo-preview",
        "messages": [
            {"role": "system", "content": "You are responsible for debugging errors in various shell scripts. Only respond using code articulated in markdown (as you normally do). Any natural language response will break the chain and the script. Only respond with code."},
            {"role": "user", "content": prompt_message}
        ]
    }

    try:
        response = requests.post("https://api.openai.com/v1/chat/completions", headers=headers, json=data)
        response.raise_for_status()
        chat_response = response.json()
        if chat_response['choices'] and chat_response['choices'][0]['message']['content']:
            suggestion = chat_response['choices'][0]['message']['content'].strip()  # Assuming clean_up_llm_response does thiss
            llm_suggestions = suggestion  # Store the suggestion globally
            print(f"{CYAN}Processing LLM suggestion:{RESET} {llm_suggestions}")            
#            print("LLM suggests:\n" + suggestion)  # Optionally print suggestion
            return suggestion
        else:
            print("No advice was returned by the model.")
            return None
    except requests.exceptions.RequestException as e:
        print(f"API request error: {e}")
        return None

def consult_openai_for_error_resolution(error_message, system_info=""):
    instructions = "You are a code debugging assistant. Provide debugging advice."
    scriptReviewer = AssemblyAssist(instructions) 
    system_info = get_system_info()


    """
    Consults the OpenAI API through the Script Reviewer for advice on resolving an encountered error,
    including system information and previous LLM suggestions.
    """
    # Ensure api_key is defined globally or passed as an argument
    llm_suggestion = llm_suggestions if llm_suggestions else "No previous LLM suggestion."
    if not llm_suggestion:
        print("Failed to get LLM suggestion.")
        return

    # Constructing the full message with system info and LLM suggestions
    full_message = f"Error encountered: {error_message}.\nSystem Info: {system_info}\nLLM Suggestion: {llm_suggestion}. How can I resolve it?"

    # Sending the constructed message to the Script Reviewer's thread
    try:
        # Adding the message to the thread
        if scriptReviewer.add_message_to_thread(full_message):
            # Trigger the assistant to process the thread and wait for a response
            scriptReviewer.run_assistant()
            # Polling for new messages from the assistant, including the response
            response_texts = scriptReviewer.get_messages()
            # Assuming get_messages() now returns a list of messages or an empty list
            if response_texts:
                response_text = " ".join([msg['content']['text']['value'] for msg in response_texts])
                print("Script Reviewer suggests:\n" + response_text)
                return response_text
            else:
                print("No response received from Script Reviewer.")
        else:
            print("Failed to add message to Script Reviewer's thread.")
    except Exception as e:
        print(f"Failed to consult Script Reviewer: {e}")


def handle_error_with_llm_and_replicate(error_message, api_key, replicate_api_key):
    consult_llm_for_error_resolution(error_message, api_key)
    consult_openai_for_error_resolution(error_message, api_key)
    #consult_replicate_for_error_resolution(error_message, replicate_api_key)

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

            print(f"{GREEN}{BOLD}LLM suggests: \n error_resolution{RESET}")
            
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
    #system_info = get_system_info()
    
    #Create a detailed description of the system info to include in the prompt.
    info_details = get_system_info()

    #Join all scripts into one, assuming they're compatible or sequential.
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
                safe_mode = args.safe  # This is already a boolean due to action="store_true"

                run = input("Would you like to run this bash script now? (yes/no): ").lower() == "yes"
                if run:
                    execute_shell_command(f"bash {full_filename}",  api_key, stream_output=True, safe_mode=safe_mode)


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
        return llm_response.strip()

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
    stop_event = threading.Event()

    # Save the final script
    with open(filename, "w") as file:
        file.write(final_script)
    print(f"{CYAN}Final script assembled and saved as {filename}.{RESET}")
    
    # Set executable permissions automatically
    os.chmod(filename, 0o755)

    # Execute the script
    
    stop_event.set()  # Signal to stop the loading animation
    print(f"{CYAN}Executing {filename}...{RESET}")
    execute_shell_command(f"./{filename}", api_key, stream_output=stream_output)
    stop_event.set() 
    print(f"{CYAN}Complete. {filename}...{RESET}")

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

def clear_line():
    sys.stdout.write("\033[K")  # ANSI escape code to clear the line
    sys.stdout.flush()
    
def process_input_in_autopilot_mode(query, autopilot_mode, use_claude, scriptreviewer_on, use_ollama, ollama_client, groq_client, use_groq):
    stop_event = threading.Event()
    loading_thread = threading.Thread(target=animated_loading, args=(stop_event,))
    loading_thread.start()
    print(f"{CYAN}Sending command to LLM...{RESET}")
    llm_response = chat_with_model(query, message=query, autopilot=autopilot_mode, use_claude=use_claude, scriptreviewer_on=scriptreviewer_on, use_ollama=use_ollama, ollama_client=ollama_client, groq_client=groq_client, use_groq=use_groq)
    scripts = extract_script_from_response(llm_response)
    if scripts:
        final_script = assemble_final_script(scripts, api_key)
        auto_handle_script_execution(final_script, autopilot=autopilot_mode, stream_output=True)
        stop_event.clear()  # Reset the stop_event for reuse
        stop_event.set()

    else:
        print("No executable script found in the LLM response.")
    stop_event.clear()  # Reset the stop_event for reuse
    stop_event.set()
    loading_thread.join()
    clear_line()

def get_weather():
    try:
        # Fetch weather information. Customize the URL with your city or use IP-based location
        response = requests.get('http://wttr.in/?format=3')
        if response.status_code == 200:
            return response.text
        else:
            return "Weather information is currently unavailable."
    except Exception as e:
        return "Failed to fetch weather information."



# Function to display a greeting message
def display_greeting():
    today = date.today()
    last_run_file = ".last_run.txt"
    last_run = None

    # Check if the last run file exists and read the date
    if os.path.exists(last_run_file):
        with open(last_run_file, "r") as file:
            last_run = file.read().strip()
    
    # Write the current date to the file
    with open(last_run_file, "w") as file:
        file.write(str(today))

    # If today is not the last run date, display the greeting
    if str(today) != last_run:
        weather = get_weather()
        system_info = get_system_info()
        print(f"{weather}")
        print(f"{system_info}")
        print("What would you like to do today?")

        # Flush the output to ensure it's displayed before waiting for input
        sys.stdout.flush()

def process_input_in_safe_mode(query, safe_mode, use_claude,scriptreviewer_on, use_groq, use_ollama, groq_client, ollama_client):
    llm_response = chat_with_model(query, message=query, autopilot=False, use_claude=use_claude, use_ollama=use_ollama)
    print_streamed_message(llm_response, CYAN)  # Ensure the LLM's response is printed

    scripts = extract_script_from_response(llm_response)
    if scripts:
        for script, file_extension, _ in scripts:
            full_filename = save_script(script, file_extension)  # This function saves the script and returns the filename
            print(f"Script extracted and saved as {full_filename}.")
            # Ask the user if they want to execute the saved script
            if safe_mode:
                user_confirmation = input(f"Do you want to execute the saved script {full_filename}? (yes/no): ").lower()
                if user_confirmation == "yes":
                    execute_shell_command(f"bash {full_filename}", api_key, safe_mode=safe_mode)
                else:
                    print("Script execution aborted by the user.")
            else:
                execute_shell_command(f"bash {full_filename}", api_key, safe_mode=safe_mode)
    else:
        print("No executable script found in the LLM response.")

def process_input_based_on_mode(query, safe_mode, autopilot_mode, use_claude, scriptreviewer_on, use_ollama, ollama_client, use_groq, groq_client):
    if safe_mode:
        process_input_in_safe_mode(query, safe_mode, use_claude, scriptreviewer_on, use_ollama, ollama_client, use_groq, groq_client)
    elif autopilot_mode:
        process_input_in_autopilot_mode(query, autopilot_mode, use_claude, scriptreviewer_on, use_ollama, ollama_client, use_groq, groq_client)
    else:
        # Normal mode processing
        llm_response = chat_with_model(query, message=query, autopilot=False, use_claude=use_claude, scriptreviewer_on=scriptreviewer_on, use_ollama=use_ollama, ollama_client=ollama_client, groq_client=groq_client, use_groq=use_groq)
        print_streamed_message(llm_response, CYAN)
        
        scripts = extract_script_from_response(llm_response)
        if scripts:
            for script, file_extension, _ in scripts:
                user_decide_and_act(script, file_extension)
        else:
            print("No executable script found in the LLM response.")                                         


def initialize_ollama_client():
    host = 'http://localhost:11434'
    try:
        # Attempt to create a client to verify connectivity
        client = ollama.Client(host=host)
        # Attempt to fetch the list of available models as a connection test
        response = client.list()
        if response:
            print(f"Connected to Ollama at {host}.")
        else:
            print(f"Connected to Ollama at {host}, but no models found.")
        return client
    except Exception as e:
        print(f"Failed to connect to Ollama at {host}: {str(e)}")
    return None

def initialize_groq_client():
    groq_api_key = os.getenv("GROQ_API_KEY")
    if groq_api_key:
        try:
            groq_client = GroqClient(api_key=groq_api_key)
            print("Groq client initialized successfully.")
            return groq_client
        except Exception as e:
            print(f"Failed to initialize Groq client: {e}")
    else:
        print("Groq API key not found.")
    return None

def chat_with_groq(message, groq_client, system_info):
    system_prompt = (f"Generate bash commands for terminal tasks. "
                     "Comment minimally, you are expected to produce code that is runnable. "
                     f"You are part of a chain. System info: {system_info}")
    try:
        chat_completion = groq_client.chat.completions.create(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": message}
            ],
            model="mixtral-8x7b-32768",
        )
        return chat_completion.choices[0].message.content
    except Exception as e:
        return f"Error while chatting with Groq: {e}"
    
def main():
    global llm_suggestions, scriptreviewer_on, groq_client, current_model, server_port
    last_response = ""
    command_mode = False
    cleanup_previous_assembled_scripts()
    print_instructions_once_per_day()
    display_greeting()
    stop_event = threading.Event()

    # Setup argument parser
    parser = argparse.ArgumentParser(description="Terminal Companion with Full Self Drive Mode")
    parser.add_argument("-s", "--safe", action="store_true", help="Run in safe mode")
    parser.add_argument("-a", "--autopilot", choices=['on', 'off'], default='off',
                        help="Turn autopilot mode on or off at startup")
    parser.add_argument("-c", "--claude", action="store_true", help="Use Claude for processing requests")
    parser.add_argument("-ci", "--assistantsAPI", action="store_true", help="Use OpenAI for error resolution")
    parser.add_argument("-o", "--ollama", action="store_true", help="Use Ollama for processing requests")
    parser.add_argument("-g", "--groq", action="store_true", help="Use Groq for processing requests")

    args, unknown = parser.parse_known_args()

    # If additional arguments are provided, join them into a single string
    query = ' '.join(unknown)
    
    # Initialize clients and set modes
    ollama_client = initialize_ollama_client() if args.ollama else None
    groq_client = initialize_groq_client() if args.groq else None
    autopilot_mode = args.autopilot == 'on'
    safe_mode = args.safe
    use_claude = args.claude
    scriptreviewer_on = args.assistantsAPI
    use_ollama = args.ollama
    use_groq = args.groq

    if query:
        process_input_based_on_mode(query, safe_mode, autopilot_mode, use_claude, scriptreviewer_on, use_ollama, ollama_client, groq_client, use_groq)

    while True:
        if command_mode:
            command = input(f"{GREEN}CMD>{RESET} ").strip().lower()
            if command == 'quit':
                break
            elif command == 'exit':
                command_mode = False
                print(f"{CYAN}Exited command mode.{RESET}")
            elif command == 'reset':
                reset_conversation()
                print(f"{CYAN}The conversation has been reset.{RESET}")
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
                        final_script = assemble_final_script(scripts, api_key)
                        auto_handle_script_execution(final_script, autopilot=autopilot_mode)
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
            else:
                print(f"{YELLOW}Unknown command. Type 'exit' to return to normal mode.{RESET}")
        else:
            user_input = input(f"{YELLOW}@:{RESET} ").strip()

            if user_input.upper() == 'CMD':
                command_mode = True
                print(f"{CYAN}Entered command mode. Type 'exit' to return to normal mode.{RESET}")
                continue

            if user_input.lower() == 'safe':
                safe_mode = True
                autopilot_mode = False
                print("Switched to safe mode. You will be prompted before executing any commands.")
            elif user_input.lower() == 'autopilot':
                safe_mode = False
                autopilot_mode = True
                print("Switched to autopilot mode.")
            elif user_input.lower() == 'normal':
                safe_mode = False
                autopilot_mode = False
                print("Switched to normal mode.")
            else:
                process_input_based_on_mode(user_input, safe_mode, autopilot_mode, use_claude, scriptreviewer_on, use_ollama, ollama_client, use_groq, groq_client)

        if llm_suggestions:
            print(f"{CYAN}Processing LLM suggestion:{RESET} {llm_suggestions}")
            process_input_based_on_mode(llm_suggestions, safe_mode, autopilot_mode, use_claude, scriptreviewer_on, use_ollama, ollama_client, use_groq, groq_client)
            llm_suggestions = None

    print("Operation completed.")
    stop_event.set()

if __name__ == "__main__":
    main()
