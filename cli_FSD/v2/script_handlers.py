import re
import os
import subprocess
import tempfile
from datetime import datetime
from utils import print_streamed_message, get_system_info, animated_loading
from chat_models import chat_with_model
import threading
import requests
from config import Config


def process_input_based_on_mode(query, config, chat_models):
    if config.safe_mode:
        process_input_in_safe_mode(query, config, chat_models)
    elif config.autopilot_mode:
        process_input_in_autopilot_mode(query, config, chat_models)
    else:
        llm_response = chat_with_model(query, config, chat_models)
        print_streamed_message(llm_response, config.CYAN)
        
        scripts = extract_script_from_response(llm_response)
        if scripts:
            for script, file_extension, _ in scripts:
                user_decide_and_act(script, file_extension, config)
        else:
            print("No executable script found in the LLM response.")

def process_input_in_safe_mode(query, config, chat_models):
    llm_response = chat_with_model(query, config, chat_models)
    print_streamed_message(llm_response, config.CYAN)

    scripts = extract_script_from_response(llm_response)
    if scripts:
        for script, file_extension, _ in scripts:
            print(f"Found a {file_extension} script:")
            print(script)
            
            save = input("Would you like to save this script? (yes/no): ").lower()
            if save == 'yes':
                full_filename = save_script(script, file_extension)
                print(f"Script extracted and saved as {full_filename}.")
                if config.safe_mode:
                    user_confirmation = input(f"Do you want to execute the saved script {full_filename}? (yes/no): ").lower()
                    if user_confirmation == "yes":
                        execute_shell_command(f"bash {full_filename}", config)
                    else:
                        print("Script execution aborted by the user.")
                else:
                    execute_shell_command(f"bash {full_filename}", config)
            elif save == 'no':
                run = input("Would you like to run this script without saving? (yes/no): ").lower()
                if run == 'yes':
                    execute_script_directly(script, file_extension, config)
                else:
                    print("Script execution aborted by the user.")
            else:
                print("Invalid input. Script not saved or executed.")
    else:
        print("No executable script found in the LLM response.")

def process_input_in_autopilot_mode(query, config, chat_models):
    stop_event = threading.Event()
    loading_thread = threading.Thread(target=animated_loading, args=(stop_event,))
    loading_thread.start()
    print(f"{config.CYAN}Sending command to LLM...{config.RESET}")
    llm_response = chat_with_model(query, config, chat_models)
    scripts = extract_script_from_response(llm_response)
    if scripts:
        final_script = assemble_final_script(scripts, config.api_key)
        auto_handle_script_execution(final_script, config)
        stop_event.set()
    else:
        print("No executable script found in the LLM response.")
    stop_event.set()
    loading_thread.join()

def extract_script_from_response(response):
    if not isinstance(response, str):
        print("Error: 'response' expected to be a string, received:", type(response))
        return []
    matches = re.findall(r"```(?:bash|python)?\n(.*?)```", response, re.DOTALL)
    scripts = [(match, "sh", "bash") for match in matches]
    return scripts

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
            cleaned_script = clean_up_llm_response(chat_response['choices'][0]['message']['content'])
            return cleaned_script
        else:
            print("No assembled script was returned by the model.")
            return None
    except requests.exceptions.RequestException as e:
        print(f"API request error: {e}")
        return None

def auto_handle_script_execution(final_script, config):
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f".assembled_script_{timestamp}.sh"

    with open(filename, "w") as file:
        file.write(final_script)
    print(f"{config.CYAN}Final script assembled and saved as {filename}.{config.RESET}")
    
    os.chmod(filename, 0o755)

    print(f"{config.CYAN}Executing {filename}...{config.RESET}")
    execute_shell_command(f"./{filename}", config)
    print(f"{config.CYAN}Complete. {filename}...{config.RESET}")

def execute_shell_command(command, config, stream_output=True):
    if command.startswith('./'):
        os.chmod(command[2:], 0o755)  # Ensure the script is executable

    if config.safe_mode:
        user_confirmation = input(f"Do you want to execute the following command: {command}? (yes/no): ").strip()
        if user_confirmation.lower() != "yes":
            print("Command execution aborted by the user.")
            return

    try:
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
            print(f"{config.RED}Error encountered executing command: {error_context}{config.RESET}")
            resolution = consult_llm_for_error_resolution(error_context, config)
            if resolution:
                print(f"{config.CYAN}Suggested resolution:{config.RESET}\n{resolution}")
                if config.safe_mode:
                    user_confirmation = input("Do you want to apply this resolution? (yes/no): ").strip().lower()
                    if user_confirmation == "yes":
                        execute_resolution_script(resolution, config)
                else:
                    execute_resolution_script(resolution, config)
        else:
            print(f"{config.GREEN}Command executed successfully.{config.RESET}")
    except subprocess.CalledProcessError as e:
        print(f"{config.RED}Command execution failed with error: {e}{config.RESET}")
    except Exception as e:
        print(f"An error occurred while executing the command: {e}")


def clean_up_llm_response(llm_response):
    script_blocks = re.findall(r"```(?:bash|sh)\n(.*?)\n```", llm_response, re.DOTALL)
    if script_blocks:
        cleaned_script = "\n".join(block.strip() for block in script_blocks)
        return cleaned_script
    else:
        print("No executable script blocks found in the response.")
        return llm_response.strip()

def save_script(script, file_extension):
    filename = input("Enter a filename for the script (without extension): ").strip()
    full_filename = f"{filename}.{file_extension}"
    with open(full_filename, "w") as file:
        file.write(script)
    print(f"Script saved as {full_filename}.")
    return full_filename

def execute_script(filename, file_extension, config):
    if file_extension == "py":
        subprocess.run(["python", filename], check=True)
    elif file_extension == "sh":
        subprocess.run(["bash", filename], check=True)
    else:
        print(f"Running scripts with .{file_extension} extension is not supported.")

def execute_script_directly(script, file_extension, config):
    if file_extension == "py":
        exec(script, {'__builtins__': None}, {})
    elif file_extension in ["sh", "bash"]:
        with tempfile.NamedTemporaryFile(mode='w', delete=False) as temp_file:
            temp_file.write(script)
            temp_file_path = temp_file.name
        try:
            if config.safe_mode:
                user_confirmation = input(f"Do you want to execute this script? (yes/no): ").lower()
                if user_confirmation == "yes":
                    execute_shell_command(f"bash {temp_file_path}", config)
                else:
                    print("Script execution aborted by the user.")
            else:
                execute_shell_command(f"bash {temp_file_path}", config)
        finally:
            os.unlink(temp_file_path)
    else:
        print(f"Running scripts with .{file_extension} extension is not supported.")



def user_decide_and_act(script, file_extension, config):
    save = input("Would you like to save this script? (yes/no): ").lower()
    if save == 'yes':
        full_filename = save_script(script, file_extension)
        run = input("Would you like to run this script? (yes/no): ").lower()
        if run == 'yes':
            execute_script(full_filename, file_extension, config)
    elif save == 'no':
        run = input("Would you like to run this script without saving? (yes/no): ").lower()
        if run == 'yes':
            execute_script_directly(script, file_extension, config)
    else:
        print("Invalid input. Script not saved or executed.")

def execute_resolution_script(resolution, config):
    print(f"{config.CYAN}Executing resolution:{config.RESET}\n{resolution}")
    try:
        subprocess.run(resolution, shell=True, check=True)
        print(f"{config.GREEN}Resolution executed successfully.{config.RESET}")
    except subprocess.CalledProcessError as e:
        print(f"{config.RED}Resolution execution failed with error: {e}{config.RESET}")
    except Exception as e:
        print(f"An error occurred while executing the resolution: {e}")


def consult_llm_for_error_resolution(error_message, config):
    system_info = get_system_info()
    print(f"{config.CYAN}Consulting LLM for error resolution:{config.RESET} {error_message}")
    prompt_message = f"System Info: {system_info}\nError: '{error_message}'.\nProvide a bash command or script to resolve this error. Only respond with the command or script, no explanations."

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {config.api_key}"
    }
    data = {
        "model": config.current_model,
        "messages": [
            {"role": "system", "content": "You are an expert in debugging shell scripts and providing fix commands. Respond only with the fix command or script, no explanations."},
            {"role": "user", "content": prompt_message}
        ]
    }

    try:
        response = requests.post("https://api.openai.com/v1/chat/completions", headers=headers, json=data)
        response.raise_for_status()
        chat_response = response.json()
        if chat_response['choices'] and chat_response['choices'][0]['message']['content']:
            suggestion = chat_response['choices'][0]['message']['content'].strip()
            config.llm_suggestions = suggestion
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

    llm_suggestion = config.llm_suggestions if config.llm_suggestions else "No previous LLM suggestion."
    if not llm_suggestion:
        print("Failed to get LLM suggestion.")
        return

    full_message = f"Error encountered: {error_message}.\nSystem Info: {system_info}\nLLM Suggestion: {llm_suggestion}. How can I resolve it?"

    try:
        if scriptReviewer.add_message_to_thread(full_message):
            scriptReviewer.run_assistant()
            response_texts = scriptReviewer.get_messages()
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
