# script_handlers.py

import re
import os
import subprocess
import tempfile
from datetime import datetime
from .utils import print_streamed_message, get_system_info, animated_loading, save_script
from .chat_models import chat_with_model
import threading
import requests
from .config import Config

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
                user_decide_and_act(query, script, file_extension, config)
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
            
            # Pass the correct parameters: query, script, file_extension, auto_save=False
            full_filename = save_script(query, script, file_extension=file_extension, auto_save=False, config=config)
            if full_filename:
                print(f"Script extracted and saved as {full_filename}.")
                
                if config.safe_mode:
                    user_confirmation = input(f"Do you want to execute the saved script {full_filename}? (yes/no): ").strip().lower()
                    if user_confirmation == "yes":
                        execute_shell_command(f"bash {full_filename}", config)
                    else:
                        print("Script execution aborted by the user.")
            else:
                print("Failed to save the script.")
    else:
        print("No executable script found in the LLM response.")

def process_input_in_autopilot_mode(query, config, chat_models):
    from contextlib import contextmanager
    
    @contextmanager
    def loading_animation():
        stop_event = threading.Event()
        loading_thread = threading.Thread(
            target=animated_loading,
            args=(stop_event,),
            daemon=True  # Ensure thread cleanup on program exit
        )
        try:
            loading_thread.start()
            yield
        finally:
            stop_event.set()
            loading_thread.join(timeout=1.0)  # Prevent hanging
    
    with loading_animation():
        print(f"{config.CYAN}Sending command to LLM...{config.RESET}")
        llm_response = chat_with_model(query, config, chat_models)
        scripts = extract_script_from_response(llm_response)
        
        if not scripts:
            print("No executable script found in the LLM response.")
            return
            
        if final_script := assemble_final_script(scripts, config.api_key):
            auto_handle_script_execution(final_script, config)

# Pre-compile regex pattern at module level for better performance
SCRIPT_PATTERN = re.compile(r"```(?:bash|python)?\n(.*?)```", re.DOTALL)

def extract_script_from_response(response):
    if not isinstance(response, str):
        print("Error: 'response' expected to be a string, received:", type(response))
        return []
    
    # Use pre-compiled pattern and filter empty matches
    matches = SCRIPT_PATTERN.findall(response)
    return [(match.strip(), "sh", "bash") for match in matches if match.strip()]

def assemble_final_script(scripts, api_key):
    # Use cached system info
    info_details = get_cached_system_info()
    
    # Optimize script joining
    final_script_prompt = "\n\n".join(
        script.strip() for script, _, _ in scripts if script.strip()
    )
    
    # Prepare API request
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}"
    }
    
    messages = [
        {
            "role": "system",
            "content": "You are a shell script expert. Combine scripts into a single executable, ensuring Unix compatibility and portability. Return only code, no comments or explanations."
        },
        {
            "role": "user",
            "content": f"System Info: {info_details}\n\nCombine these scripts:\n\n{final_script_prompt}"
        }
    ]
    
    try:
        response = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers=headers,
            json={
                "model": "gpt-4-turbo-preview",
                "messages": messages,
                "temperature": 0.3,  # Lower temperature for more consistent output
                "max_tokens": 2000   # Limit response size
            },
            timeout=30  # Add timeout
        )
        response.raise_for_status()
        
        if content := response.json().get('choices', [{}])[0].get('message', {}).get('content', ''):
            return clean_up_llm_response(content)
            
        print("No assembled script was returned by the model.")
        return None
    except requests.exceptions.RequestException as e:
        print(f"API request error: {e}")
        return None
    except Exception as e:
        print(f"Unexpected error during script assembly: {e}")
        return None

# Track assembled scripts for cleanup
_assembled_scripts = set()

def cleanup_assembled_scripts():
    """Clean up any remaining assembled scripts."""
    global _assembled_scripts
    for script in _assembled_scripts.copy():
        try:
            if os.path.exists(script):
                os.unlink(script)
                _assembled_scripts.remove(script)
        except OSError as e:
            print(f"Warning: Failed to clean up script {script}: {e}")

def auto_handle_script_execution(final_script, config):
    """Handle script assembly and execution with proper cleanup."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f".assembled_script_{timestamp}.sh"
    
    try:
        # Use tempfile for safer file handling
        with tempfile.NamedTemporaryFile(mode='w', suffix='.sh', delete=False) as temp_file:
            temp_file.write(final_script)
            temp_path = temp_file.name
            
        try:
            # Move temp file to final location
            os.rename(temp_path, filename)
            _assembled_scripts.add(filename)  # Track for cleanup
            
            print(f"{config.CYAN}Final script assembled and saved as {filename}.{config.RESET}")
            os.chmod(filename, 0o755)
            
            print(f"{config.CYAN}Executing {filename}...{config.RESET}")
            success = execute_shell_command(f"./{filename}", config)
            
            if success:
                print(f"{config.GREEN}Script execution completed successfully.{config.RESET}")
            else:
                print(f"{config.RED}Script execution failed.{config.RESET}")
                
            return success
            
        except Exception as e:
            # Clean up temp file if move failed
            try:
                os.unlink(temp_path)
            except OSError:
                pass
            raise e
            
    except Exception as e:
        print(f"{config.RED}Failed to handle script execution: {e}{config.RESET}")
        return False

def execute_shell_command(command, config, stream_output=True):
    """Execute a shell command with proper error handling and output management."""
    if command.startswith('./'):
        try:
            script_path = command[2:]
            os.chmod(script_path, 0o755)
        except OSError as e:
            print(f"{config.RED}Failed to set executable permissions: {e}{config.RESET}")
            return False

    if config.safe_mode and not get_user_confirmation(command):
        return False

    try:
        # Use context manager with timeout
        with subprocess.Popen(
            command,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            universal_newlines=True,
            bufsize=1
        ) as process:
            output_lines = []
            
            # Use select for non-blocking reads with timeout
            from select import select
            while True:
                reads, _, _ = select([process.stdout], [], [], 0.1)
                if not reads:
                    # No output available, check if process is still running
                    if process.poll() is not None:
                        break
                    continue
                    
                line = process.stdout.readline()
                if not line:
                    break
                    
                if stream_output:
                    print(line, end='', flush=True)
                output_lines.append(line.strip())
            
            return_code = process.wait(timeout=300)  # 5 minute timeout

            if return_code != 0:
                error_context = "\n".join(output_lines)
                print(f"{config.RED}Error encountered executing command: {error_context}{config.RESET}")
                
                if resolution := consult_llm_for_error_resolution(error_context, config):
                    print(f"{config.CYAN}Suggested resolution:{config.RESET}\n{resolution}")
                    
                    if not config.safe_mode or get_user_confirmation("Apply suggested resolution?"):
                        return execute_resolution_script(resolution, config)
                return False
                
            return True
            
    except subprocess.TimeoutExpired:
        print(f"{config.RED}Command execution timed out after 5 minutes{config.RESET}")
        return False
    except subprocess.CalledProcessError as e:
        print(f"{config.RED}Command execution failed with error: {e}{config.RESET}")
        return False
    except Exception as e:
        print(f"{config.RED}An error occurred while executing the command: {e}{config.RESET}")
        return False

# Pre-compile additional regex pattern for cleanup
CLEANUP_PATTERN = re.compile(r"```(?:bash|sh)\n(.*?)\n```", re.DOTALL)

def clean_up_llm_response(llm_response):
    script_blocks = CLEANUP_PATTERN.findall(llm_response)
    if script_blocks:
        # Use list comprehension for better performance
        return "\n".join(block.strip() for block in script_blocks if block.strip())
    print("No executable script blocks found in the response.")
    return llm_response.strip()

def execute_script(filename, file_extension, config):
    try:
        if file_extension == "py":
            subprocess.run(["python", filename], check=True)
        elif file_extension == "sh":
            subprocess.run(["bash", filename], check=True)
        else:
            print(f"Running scripts with .{file_extension} extension is not supported.")
    except subprocess.CalledProcessError as e:
        print(f"{config.RED}Script execution failed with error: {e}{config.RESET}")
    except Exception as e:
        print(f"An error occurred while executing the script: {e}")

def execute_script_directly(script, file_extension, config):
    """Execute a script directly with proper cleanup and error handling."""
    if file_extension == "py":
        try:
            # Create a restricted globals dict for safer Python execution
            restricted_globals = {
                '__builtins__': {
                    name: __builtins__[name] 
                    for name in ['print', 'len', 'str', 'int', 'float', 'bool', 'list', 'dict']
                }
            }
            exec(script, restricted_globals, {})
        except Exception as e:
            print(f"{config.RED}Error executing Python script: {e}{config.RESET}")
            return False
            
    elif file_extension in ["sh", "bash"]:
        # Use context manager pattern for better resource management
        try:
            with tempfile.NamedTemporaryFile(mode='w', suffix='.sh', delete=False) as temp_file:
                temp_file.write(script)
                temp_file_path = temp_file.name
                # Set executable permissions within the context
                os.chmod(temp_file_path, 0o755)
                
            try:
                if config.safe_mode and not get_user_confirmation(f"Execute script:\n{script}"):
                    print("Script execution aborted by the user.")
                    return False
                    
                return execute_shell_command(f"bash {temp_file_path}", config)
            finally:
                # Ensure temp file cleanup even if execution fails
                try:
                    os.unlink(temp_file_path)
                except OSError as e:
                    print(f"Warning: Failed to clean up temporary file {temp_file_path}: {e}")
                    
        except (IOError, OSError) as e:
            print(f"{config.RED}Error handling script file: {e}{config.RESET}")
            return False
    else:
        print(f"{config.RED}Running scripts with .{file_extension} extension is not supported.{config.RESET}")
        return False
    
    return True

def user_decide_and_act(query, script, file_extension, config):
    # Determine if autopilot mode is enabled
    auto_save = config.autopilot_mode
    full_filename = save_script(query, script, file_extension=file_extension, auto_save=auto_save, config=config)
    
    if full_filename:
        if auto_save:
            print(f"Script saved automatically to {full_filename}.")
            # Optionally execute the script immediately if in autopilot mode
            execute_shell_command(f"bash {full_filename}", config)
        else:
            print(f"Script saved to {full_filename}.")
            run = input("Would you like to run this script? (yes/no): ").strip().lower()
            if run == 'yes':
                execute_script(full_filename, file_extension, config)
    else:
        run = input("Would you like to run this script without saving? (yes/no): ").strip().lower()
        if run == 'yes':
            execute_script_directly(script, file_extension, config)
        else:
            print("Script execution aborted by the user.")

def execute_resolution_script(resolution, config):
    print(f"{config.CYAN}Executing resolution:{config.RESET}\n{resolution}")
    try:
        subprocess.run(resolution, shell=True, check=True)
        print(f"{config.GREEN}Resolution executed successfully.{config.RESET}")
    except subprocess.CalledProcessError as e:
        print(f"{config.RED}Resolution execution failed with error: {e}{config.RESET}")
    except Exception as e:
        print(f"An error occurred while executing the resolution: {e}")

# Cache system info
_system_info_cache = None

def get_cached_system_info():
    global _system_info_cache
    if _system_info_cache is None:
        _system_info_cache = get_system_info()
    return _system_info_cache

def consult_llm_for_error_resolution(error_message, config):
    system_info = get_cached_system_info()
    print(f"{config.CYAN}Consulting LLM for error resolution:{config.RESET} {error_message}")
    
    # Reuse headers and base message structure
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {config.api_key}"
    }
    
    messages = [
        {
            "role": "system",
            "content": "You are an expert in debugging shell scripts and providing fix commands. Respond only with the fix command or script, no explanations."
        },
        {
            "role": "user",
            "content": f"System Info: {system_info}\nError: '{error_message}'.\nProvide a bash command or script to resolve this error. Only respond with the command or script, no explanations."
        }
    ]

    try:
        response = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers=headers,
            json={
                "model": config.current_model,
                "messages": messages,
                "temperature": 0.3  # Lower temperature for more focused responses
            }
        )
        response.raise_for_status()
        
        if suggestion := response.json().get('choices', [{}])[0].get('message', {}).get('content', '').strip():
            config.llm_suggestions = suggestion
            return suggestion
            
        print("No advice was returned by the model.")
        return None
    except requests.exceptions.RequestException as e:
        print(f"API request error: {e}")
        return None

def consult_openai_for_error_resolution(error_message, system_info=""):
    """Consult OpenAI for error resolution with improved error handling and caching."""
    try:
        # Use cached system info
        system_info = get_cached_system_info()
        
        # Get current LLM suggestion with proper fallback
        llm_suggestion = getattr(config, 'llm_suggestions', None) or "No previous LLM suggestion."
        
        instructions = {
            "role": "system",
            "content": "You are a code debugging assistant specializing in shell scripts and system commands. Provide concise, practical solutions."
        }
        
        message = {
            "role": "user",
            "content": f"""
Error: {error_message}
System: {system_info}
Previous Suggestion: {llm_suggestion}
Provide a solution command or script.
"""
        }
        
        scriptReviewer = AssemblyAssist(instructions)
        
        if not scriptReviewer.add_message_to_thread(message["content"]):
            print(f"{config.RED}Failed to initialize error resolution.{config.RESET}")
            return None
            
        scriptReviewer.run_assistant()
        response_texts = scriptReviewer.get_messages()
        
        if not response_texts:
            print(f"{config.RED}No response received from error resolution.{config.RESET}")
            return None
            
        # Extract and format the solution
        solution = " ".join(
            msg['content']['text']['value']
            for msg in response_texts
            if msg.get('content', {}).get('text', {}).get('value')
        )
        
        if solution:
            print(f"{config.CYAN}Suggested solution:{config.RESET}\n{solution}")
            return solution.strip()
            
        return None
        
    except Exception as e:
        print(f"{config.RED}Error resolution failed: {e}{config.RESET}")
        return None
