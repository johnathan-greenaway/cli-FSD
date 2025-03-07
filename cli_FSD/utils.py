import sys
import time
import platform
import requests
from datetime import datetime, date
import glob
import os
import re

# Color constants
CYAN = "\033[96m"
YELLOW = "\033[93m"
BOLD = "\033[1m"
RESET = "\033[0m"
RED = "\033[31m"
GREEN = "\033[32m"


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


def get_system_info():
    info = {
        'OS': platform.system(),
        'Version': platform.version(),
        'Machine': platform.machine(),
        'Processor': platform.processor(),
    }
    return ", ".join([f"{key}: {value}" for key, value in info.items()])


def print_instructions():
    from . import configuration
    config = configuration.Config()
    print(f"{GREEN}{BOLD}Terminal Companion with Full Self Drive Mode {config.SMALL_FONT}(v{config.VERSION}){RESET}")
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
                    if last_display_date < current_date:
                        raise FileNotFoundError
                except ValueError:
                    raise FileNotFoundError
        else:
            raise FileNotFoundError
    except FileNotFoundError:
        with open(instructions_file, "w") as file:
            file.write(current_date.strftime("%Y-%m-%d"))
        print_instructions()


def print_streamed_message(message, color=CYAN):
    for char in message:
        print(f"{color}{char}{RESET}", end='', flush=True)
        time.sleep(0.03)
    print()


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
        from . import configuration
        config = configuration.Config()
        weather = get_weather()
        system_info = get_system_info()
        print(f"{BOLD}Terminal Companion with Full Self Drive Mode {config.SMALL_FONT}(v{config.VERSION}){RESET}")
        print(f"{weather}")
        print(f"{system_info}")
        print("What would you like to do today?")

    sys.stdout.flush()


def cleanup_previous_assembled_scripts():
    for filename in glob.glob(".assembled_script_*.sh"):
        try:
            os.remove(filename)
            print(f"Deleted previous assembled script: {filename}")
        except OSError as e:
            print(f"Error deleting file {filename}: {e}")


def clear_line():
    sys.stdout.write("\033[K")  # ANSI escape code to clear the line
    sys.stdout.flush()


def ask_user_to_retry():
    user_input = input("Do you want to retry the original command? (yes/no): ").lower()
    return user_input == "yes"


def print_message(sender, message):
    color = YELLOW if sender == "user" else CYAN
    prefix = f"{color}You:{RESET} " if sender == "user" else f"{color}Bot:{RESET} "
    print(f"{prefix}{message}")


def use_mcp_tool(server_name: str, tool_name: str, arguments: dict) -> str:
    """Use an MCP tool with the specified parameters.
    
    Args:
        server_name: Name of the MCP server
        tool_name: Name of the tool to use
        arguments: Tool arguments as a dictionary
        
    Returns:
        Tool execution result as a string
    """
    try:
        import json
        import subprocess
        from pathlib import Path
        import os
        
        # Get MCP settings from config directory
        try:
            config_dir = Path(__file__).parent / "config_files"
            mcp_settings_file = config_dir / "mcp_settings.json"
            
            with open(mcp_settings_file) as f:
                mcp_settings = json.load(f)
        except Exception as e:
            return f"Error loading MCP settings: {str(e)}"
            
        # Get server config
        server_config = mcp_settings["mcpServers"].get(server_name)
        if not server_config:
            return f"Error: MCP server '{server_name}' not found in settings"
            
        # Format the MCP command
        mcp_command = {
            "jsonrpc": "2.0",
            "method": "call_tool",
            "params": {
                "name": tool_name,
                "arguments": arguments
            },
            "id": 1
        }
        
        # Build command with args from config
        cmd = [server_config["command"]] + server_config["args"]
        
        # Get the current working directory
        cwd = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        
        # Set up environment for subprocess
        env = os.environ.copy()  # Copy current environment
        
        # Add any additional env settings from server_config
        if server_config.get("env"):
            env.update(server_config["env"])
            
        # Ensure PYTHONPATH includes site-packages
        python_path = env.get('PYTHONPATH', '').split(os.pathsep)
        site_packages = os.path.join(os.path.dirname(os.__file__), 'site-packages')
        if site_packages not in python_path:
            python_path.append(site_packages)
        env['PYTHONPATH'] = os.pathsep.join(filter(None, python_path))
        
        # Write command to stdin and read response from stdout
        process = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=env,  # Use our modified environment
            cwd=cwd  # Set the working directory
        )
        
        # Send command and get response
        stdout, stderr = process.communicate(input=json.dumps(mcp_command) + "\n")
        
        if stderr:
            print(f"MCP server error: {stderr}", file=sys.stderr)
            return f"Error: {stderr}"
            
        try:
            response = json.loads(stdout)
            if "error" in response:
                return f"Error: {response['error']['message']}"
            if "result" in response:
                content = response["result"].get("content")
                if isinstance(content, list):
                    return "\n".join(
                        block["text"] for block in content
                        if block["type"] == "text"
                    )
                elif isinstance(content, str):
                    try:
                        # Try to parse as JSON first
                        parsed = json.loads(content)
                        if isinstance(parsed, dict) and "content" in parsed:
                            return parsed["content"]
                        return content
                    except json.JSONDecodeError:
                        return content
                else:
                    return f"Error: Unexpected content format: {content}"
            return "Error: No result in response"
        except json.JSONDecodeError:
            return f"Error: Invalid JSON response from MCP server"
            
    except Exception as e:
        return f"Error using MCP tool: {str(e)}"
    
def save_script(query, script, file_extension="sh", auto_save=False, config=None):
    scripts_dir = "scripts"
    os.makedirs(scripts_dir, exist_ok=True)

    # Create a safe filename by replacing non-alphanumeric characters with underscores
    filename = re.sub(r'[^a-zA-Z0-9_-]', '_', query.lower()) + f".{file_extension}"
    filepath = os.path.join(scripts_dir, filename)

    if auto_save or (config and config.autopilot_mode):
        # Automatically save the script without prompting
        try:
            with open(filepath, 'w') as f:
                f.write(script + "\n")
            print(f"Script saved automatically to {filepath}")
            return filepath
        except Exception as e:
            if config:
                print(f"{config.RED}Failed to save script: {e}{config.RESET}")
            else:
                print(f"Failed to save script: {e}")
            return None
    else:
        # Prompt the user to save the script
        choice = input("Would you like to save this script? (yes/no): ").strip().lower()
        if choice in ['yes', 'y']:
            try:
                with open(filepath, 'w') as f:
                    f.write(script + "\n")
                print(f"Script saved to {filepath}")
                return filepath
            except Exception as e:
                if config:
                    print(f"{config.RED}Failed to save script: {e}{config.RESET}")
                else:
                    print(f"Failed to save script: {e}")
                return None
        else:
            print("Script not saved.")
            return None
