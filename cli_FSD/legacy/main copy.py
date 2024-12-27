# Version 1.8 (Merged from 1.6 and 1.7)
# Added third box in TUI for terminal outputs
# Added TUI with stashed requests and output command display
# Included countdown timer when autopilot mode is enabled
# Fixed command mode and curses error, reintroduced status messages
# Enabled quitting the script
# Commands execute and display output in the TUI unless spacebar is pressed
# In autopilot mode, script exits after execution

import os
import sys
import time
import json
import shlex
import queue
import curses
import glob
import httpx
import base64
import asyncio
import urllib.parse
import platform
import requests
import subprocess
import threading
import argparse
from pathlib import Path
from datetime import datetime, date
from dotenv import load_dotenv, set_key
from flask import Flask, request, jsonify
from flask_cors import CORS
from .resources.assembler import AssemblyAssist  # Included as per original script
import ollama
from ollama import Client
from groq import Groq as GroqClient

global llm_suggestions
global replicate_suggestions
replicate_suggestions = ""
global groq_client

suggestions_queue = queue.Queue()

# ANSI color codes
CYAN = "\033[96m"
YELLOW = "\033[93m"
BOLD = "\033[1m"
RESET = "\033[0m"
RED = "\033[31m"
GREEN = "\033[32m"

dotenv_path = Path('.env')
load_dotenv(dotenv_path=dotenv_path)

models = {
    "gpt-4o": "gpt-4o",
    "gpt4": "gpt-4",
    "gpt40613": "gpt-4-0613",
    "gpt432k0613": "gpt-4-32k-0613",
    "35turbo": "gpt-3.5-turbo",
    "gpt-3.5-turbo-0125": "gpt-3.5-turbo-0125",
    "gpt-4-32k-0613": "gpt-4-32k-0613",
    "gpt-4-turbo-preview": "gpt-4-turbo-preview",
    "gpt-4-vision-preview": "gpt-4-vision-preview",
    "dall-e-3": "dall-e-3",
    "o1-preview": "o1-preview"
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

    try:
        if os.path.exists(instructions_file):
            with open(instructions_file, "r") as file:
                last_display_date_str = file.read().strip()
                try:
                    last_display_date = datetime.strptime(last_display_date_str, "%Y-%m-%d").date()
                    if last_display_date == current_date:
                        return
                except ValueError:
                    pass
        with open(instructions_file, "w") as file:
            file.write(current_date.strftime("%Y-%m-%d"))
        print_instructions()
    except Exception as e:
        print_instructions()

def execute_shell_command(command, api_key, stream_output=True, safe_mode=False, scriptreviewer_on=False):
    global llm_suggestions

    if command.startswith('./'):
        os.chmod(command[2:], 0o755)

    if safe_mode:
        user_confirmation = input(f"Do you want to execute the following command: {command}? (yes/no): ").strip()
        if user_confirmation.lower() != "yes":
            print("Command execution aborted by the user.")
            return

    try:
        process = subprocess.Popen(command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True, bufsize=1)
        output_lines = []
        for line in iter(process.stdout.readline, ''):
            output_lines.append(line)
        process.stdout.close()
        return_code = process.wait()

        if return_code != 0:
            error_context = "".join(output_lines)
            if scriptreviewer_on:
                resolution = consult_openai_for_error_resolution(error_context, get_system_info())
            else:
                resolution = consult_llm_for_error_resolution(error_context, api_key)
            scripts = extract_script_from_response(resolution)
            for script in scripts:
                execute_resolution_script(script)
                llm_suggestions = None
            return error_context
        else:
            return "".join(output_lines)
    except Exception as e:
        return str(e)

def chat_with_model(system_info, message, autopilot=False, use_claude=False, use_ollama=False, ollama_client=None, use_groq=False, groq_client=None, scriptreviewer_on=False):
    dotenv_path = Path('.env')
    load_dotenv(dotenv_path=dotenv_path)
    scriptreviewer_on = scriptreviewer_on
    groq_client = groq_client
    system_info = get_system_info()
    if use_ollama:
        if not ollama_client:
            return "Ollama client missing."

        system_prompt = (f"Generate bash commands for tasks. "
                         "Comment minimally, you are expected to produce code that is runnable. "
                         f"You are part of a chain. System info: {system_info}")

        try:
            response = ollama_client.chat(
                model='llama3',
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": message},
                ]
            )
            if 'message' in response and 'content' in response['message']:
                assistant_message = response['message']['content']
                return assistant_message
            else:
                return "Unexpected response format."
        except Exception as e:
            return f"Error: {e}"

    if use_groq:
        model_response = chat_with_groq(message, groq_client, system_info)
        return model_response

    if use_claude:
        anthropic_api_key = os.getenv("ANTHROPIC_API_KEY")
        if not anthropic_api_key:
            return "Anthropic API key missing."
        headers = {
            "x-api-key": f"{anthropic_api_key}",
            "Content-Type": "application/json",
            "Anthropic-Version": "2023-06-01"
        }
        data = {
            "model": "claude-3-opus-20240229",
            "system": "Generate bash commands for tasks. Comment minimally, you are expected to produce code that is runnable. You are part of a chain.",
            "messages": [
                {"role": "user", "content": message},
            ],
            "max_tokens": 4096,
            "temperature": 0.7
        }
        endpoint = "https://api.anthropic.com/v1/messages"
    else:
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}"
        }
        data = {
            "model": models.get(current_model, "gpt-4"),
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
    except Exception as err:
        model_response = f"Other error occurred: {err}"

    return model_response

def extract_script_from_response(response):
    if not isinstance(response, str):
        return []
    matches = re.findall(r"```(?:bash|sh|python)?\n(.*?)```", response, re.DOTALL)
    scripts = []
    for match in matches:
        if 'python' in match:
            scripts.append((match, "py", "python"))
        else:
            scripts.append((match, "sh", "bash"))
    return scripts

def execute_resolution_script(script):
    global llm_suggestions
    process = subprocess.run(script, shell=True, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if process.returncode == 0:
        llm_suggestions = None
    else:
        llm_suggestions = None

def save_script(script, file_extension):
    filename = input("Enter a filename for the script (without extension): ").strip()
    full_filename = f"{filename}.{file_extension}"
    with open(full_filename, "w") as file:
        file.write(script)
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
        print("No script found in the last response.")

def consult_llm_for_error_resolution(error_message, api_key):
    global llm_suggestions
    system_info = get_system_info()
    prompt_message = f"System Info: {system_info}\n Error: '{error_message}'. \n Provide code that resolves the error. Do not comment, only use code."

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}"
    }
    data = {
        "model": "gpt-4",
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
            suggestion = chat_response['choices'][0]['message']['content'].strip()
            llm_suggestions = suggestion
            return suggestion
        else:
            return None
    except requests.exceptions.RequestException as e:
        return None

def consult_openai_for_error_resolution(error_message, system_info=""):
    instructions = "You are a code debugging assistant. Provide debugging advice."
    scriptReviewer = AssemblyAssist(instructions)
    system_info = get_system_info()

    api_key = os.getenv("OPENAI_API_KEY")
    llm_suggestion = llm_suggestions if llm_suggestions else "No previous LLM suggestion."
    if not llm_suggestion:
        return

    full_message = f"Error encountered: {error_message}.\nSystem Info: {system_info}\nLLM Suggestion: {llm_suggestion}. How can I resolve it?"

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}"
    }
    data = {
        "model": "gpt-4",
        "messages": [
            {"role": "system", "content": "You are a code debugging assistant. Provide debugging advice."},
            {"role": "user", "content": full_message}
        ]
    }

    try:
        response = requests.post("https://api.openai.com/v1/chat/completions", headers=headers, json=data)
        response.raise_for_status()
        chat_response = response.json()
        if chat_response['choices'] and chat_response['choices'][0]['message']['content']:
            response_text = chat_response['choices'][0]['message']['content'].strip()
            return response_text
        else:
            pass
    except Exception as e:
        pass

def assemble_final_script(scripts, api_key):
    info_details = get_system_info()
    final_script_prompt = "\n\n".join(script for script, _, _ in scripts)
    prompt_message = (f"{info_details}\n\n"
                      "Based on the above system information, combine the following scripts into a single executable script. "
                      "Ensure compatibility across all Unix-like systems, prioritizing portable commands. Do not comment, only provide code. You are a part of a chain and returning anything other than code will break the chain:\n\n"
                      f"{final_script_prompt}")

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}"
    }
    data = {
        "model": "gpt-4",
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
            cleaned_script = clean_up_llm_response(chat_response['choices'][0]['message']['content'])
            return cleaned_script
        else:
            return None
    except requests.exceptions.RequestException as e:
        return None

def reset_conversation():
    global conversation_history
    conversation_history = []

def handle_script_invocation(scripts):
    for script, file_extension, language in scripts:
        save = input("Would you like to save this script? (yes/no): ").lower() == "yes"
        if save:
            full_filename = save_script(script, file_extension)
            if language != "bash":
                create_and_run = input(f"Would you like to create and optionally run a bash script to execute this {language} script? (yes/no): ").lower() == "yes"
                if create_and_run:
                    bash_script_name = input("Enter a filename for the bash script (without extension): ")
                    bash_full_filename = f"{bash_script_name}.sh"
                    with open(bash_full_filename, "w") as bash_file:
                        if language == "python":
                            bash_file.write(f"#!/bin/bash\npython {full_filename}\n")
                        bash_file.write("\n")
                    os.chmod(bash_full_filename, 0o755)
                    run_bash = input("Would you like to run this bash script now? (yes/no): ").lower() == "yes"
                    if run_bash:
                        execute_shell_command(f"bash {bash_full_filename}", api_key, stream_output=True)
            elif file_extension == "sh":
                safe_mode = args.safe
                run = input("Would you like to run this bash script now? (yes/no): ").lower() == "yes"
                if run:
                    execute_shell_command(f"bash {full_filename}",  api_key, stream_output=True, safe_mode=safe_mode)

def clean_up_llm_response(llm_response):
    script_blocks = re.findall(r"```(?:bash|sh|python)?\n(.*?)\n```", llm_response, re.DOTALL)
    if script_blocks:
        cleaned_script = "\n".join(block.strip() for block in script_blocks)
        return cleaned_script
    else:
        return llm_response.strip()

def cleanup_previous_assembled_scripts():
    for filename in glob.glob(".assembled_script_*.sh"):
        try:
            os.remove(filename)
        except OSError as e:
            pass

def auto_handle_script_execution(final_script, autopilot=False, stream_output=True):
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f".assembled_script_{timestamp}.sh"

    with open(filename, "w") as file:
        file.write(final_script)

    os.chmod(filename, 0o755)

    if autopilot:
        countdown_time = 5
        for remaining in range(countdown_time, 0, -1):
            sys.stdout.write(f"\rExecuting in {remaining} seconds...")
            sys.stdout.flush()
            time.sleep(1)
        sys.stdout.write("\rExecuting now!                \n")

    output = execute_shell_command(f"./{filename}", api_key, stream_output=False)

    if autopilot:
        sys.exit()

    return output

def process_input_in_autopilot_mode(query, autopilot_mode, use_claude, scriptreviewer_on, use_ollama, ollama_client, groq_client, use_groq):
    llm_response = chat_with_model(get_system_info(), query, autopilot=autopilot_mode, use_claude=use_claude, scriptreviewer_on=scriptreviewer_on, use_ollama=use_ollama, ollama_client=ollama_client, groq_client=groq_client, use_groq=use_groq)
    scripts = extract_script_from_response(llm_response)
    if scripts:
        final_script = assemble_final_script(scripts, api_key)
        output = auto_handle_script_execution(final_script, autopilot=autopilot_mode, stream_output=False)
        return llm_response, output
    else:
        return llm_response, "No executable script found."

def get_weather():
    try:
        response = requests.get('http://wttr.in/?format=3')
        if response.status_code == 200:
            return response.text
        else:
            return "Weather information is currently unavailable."
    except Exception as e:
        return "Failed to fetch weather information."

def display_greeting():
    today = date.today()
    last_run_file = ".last_run.txt"
    last_run = None

    if os.path.exists(last_run_file):
        with open(last_run_file, "r") as file:
            last_run = file.read().strip()

    with open(last_run_file, "w") as file:
        file.write(str(today))

    if str(today) != last_run:
        weather = get_weather()
        system_info = get_system_info()
        print(f"{weather}")
        print(f"{system_info}")
        print("What would you like to do today?")
        sys.stdout.flush()

def process_input_based_on_mode_tui(query, autopilot_mode, use_claude, scriptreviewer_on, use_ollama, ollama_client, use_groq, groq_client):
    outputs = []
    term_outputs = []
    outputs.append("Sending command to LLM...")
    if autopilot_mode:
        countdown_time = 5
        for remaining in range(countdown_time, 0, -1):
            outputs.append(f"Executing in {remaining} seconds...")
            time.sleep(1)
        outputs.append("Executing now!")
        llm_response, term_output = process_input_in_autopilot_mode(
            query, autopilot_mode, use_claude, scriptreviewer_on,
            use_ollama, ollama_client, groq_client, use_groq
        )
        outputs.append("LLM Response:")
        outputs.append(llm_response)
        term_outputs.append(term_output)
    else:
        llm_response = chat_with_model(
            get_system_info(), query, autopilot=False, use_claude=use_claude,
            scriptreviewer_on=scriptreviewer_on, use_ollama=use_ollama,
            ollama_client=ollama_client, groq_client=groq_client, use_groq=use_groq
        )
        outputs.append("LLM suggests:")
        outputs.append(llm_response)
    return "\n".join(outputs), "\n".join(term_outputs)

def initialize_ollama_client():
    host = 'http://localhost:11434'
    try:
        client = ollama.Client(host=host)
        response = client.list()
        return client
    except Exception as e:
        return None

def initialize_groq_client():
    groq_api_key = os.getenv("GROQ_API_KEY")
    if groq_api_key:
        try:
            groq_client = GroqClient(api_key=groq_api_key)
            return groq_client
        except Exception as e:
            pass
    else:
        pass
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

def tui_main(stdscr, autopilot_mode, use_claude, scriptreviewer_on, use_ollama, ollama_client, use_groq, groq_client):
    curses.curs_set(0)
    stdscr.clear()
    height, width = stdscr.getmaxyx()

    win_height = height - 4
    win_width = width // 3

    req_win = curses.newwin(win_height, win_width, 0, 0)
    out_win = curses.newwin(win_height, win_width, 0, win_width)
    term_win = curses.newwin(win_height, width - 2 * win_width, 0, 2 * win_width)
    input_win = curses.newwin(3, width, height - 3, 0)

    requests_list = []
    outputs_list = []
    terminal_outputs_list = []

    while True:
        req_win.clear()
        req_win.box()
        req_win.addstr(0, 2, " Requests ")
        for idx, req in enumerate(requests_list[-(win_height - 2):]):
            req_win.addstr(idx + 1, 1, req[:win_width - 2])
        req_win.refresh()

        out_win.clear()
        out_win.box()
        out_win.addstr(0, 2, " Outputs ")
        for idx, out in enumerate(outputs_list[-(win_height - 2):]):
            out_win.addstr(idx + 1, 1, out[:win_width - 2])
        out_win.refresh()

        term_win.clear()
        term_win.box()
        term_win.addstr(0, 2, " Terminal ")
        term_lines = []
        for output in terminal_outputs_list[-(win_height - 2):]:
            term_lines.extend(output.split('\n'))
        for idx, term_line in enumerate(term_lines[-(win_height - 2):]):
            term_win.addstr(idx + 1, 1, term_line[:term_win.getmaxyx()[1] - 2])
        term_win.refresh()

        input_win.clear()
        input_win.addstr(1, 1, "@: ")
        curses.echo()
        user_input = input_win.getstr(1, 4, width - 5).decode('utf-8')
        curses.noecho()

        if user_input.upper() == 'CMD':
            command_mode = True
            while command_mode:
                input_win.clear()
                input_win.addstr(1, 1, "CMD> ")
                curses.echo()
                cmd_input = input_win.getstr(1, 6, width - 7).decode('utf-8')
                curses.noecho()
                if cmd_input.lower() == 'exit':
                    command_mode = False
                elif cmd_input.lower() == 'quit':
                    sys.exit()
                elif cmd_input.lower() == 'reset':
                    reset_conversation()
                    requests_list.clear()
                    outputs_list.clear()
                    terminal_outputs_list.clear()
                else:
                    pass
        elif user_input.lower() == 'quit':
            sys.exit()
        else:
            requests_list.append(user_input)
            output, term_output = process_input_based_on_mode_tui(
                user_input, autopilot_mode, use_claude, scriptreviewer_on,
                use_ollama, ollama_client, use_groq, groq_client
            )
            outputs_list.append(output)
            terminal_outputs_list.append(term_output)

def main():
    global llm_suggestions, scriptreviewer_on, groq_client, current_model, server_port, args
    last_response = ""
    command_mode = False
    cleanup_previous_assembled_scripts()
    print_instructions_once_per_day()
    display_greeting()
    stop_event = threading.Event()

    parser = argparse.ArgumentParser(description="Terminal Companion with Full Self Drive Mode")
    parser.add_argument("-s", "--safe", action="store_true", help="Run in safe mode")
    parser.add_argument("-a", "--autopilot", choices=['on', 'off'], default='off',
                        help="Turn autopilot mode on or off at startup")
    parser.add_argument("-c", "--claude", action="store_true", help="Use Claude for processing requests")
    parser.add_argument("-ci", "--assistantsAPI", action="store_true", help="Use OpenAI for error resolution")
    parser.add_argument("-o", "--ollama", action="store_true", help="Use Ollama for processing requests")
    parser.add_argument("-g", "--groq", action="store_true", help="Use Groq for processing requests")

    args, unknown = parser.parse_known_args()

    query = ' '.join(unknown)

    ollama_client = initialize_ollama_client() if args.ollama else None
    groq_client = initialize_groq_client() if args.groq else None
    autopilot_mode = args.autopilot == 'on'
    safe_mode = args.safe
    use_claude = args.claude
    scriptreviewer_on = args.assistantsAPI
    use_ollama = args.ollama
    use_groq = args.groq

    if query:
        process_input_based_on_mode_tui(query, autopilot_mode, use_claude, scriptreviewer_on, use_ollama, ollama_client, use_groq, groq_client)
        if autopilot_mode:
            sys.exit()

    curses.wrapper(
        tui_main, autopilot_mode, use_claude, scriptreviewer_on,
        use_ollama, ollama_client, use_groq, groq_client
    )

    stop_event.set()

if __name__ == "__main__":
    main()
