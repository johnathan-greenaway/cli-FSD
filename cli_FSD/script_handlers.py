# script_handlers.py

import re
import os
import subprocess
import tempfile
import json
from datetime import datetime
from .utils import print_streamed_message, get_system_info, animated_loading, save_script, use_mcp_tool
from .chat_models import chat_with_model
from .resources.assembler import AssemblyAssist
import threading
import importlib.util

# Check if requests is available and import it
requests = None
if importlib.util.find_spec("requests"):
    import requests
else:
    print("Warning: requests package not installed. Some features may be limited.")

from .configuration import Config
from .linting.code_checker import CodeChecker
from .agents.context_agent import ContextAgent

def evaluate_response(query: str, response: str, config, chat_models) -> bool:
    """
    Use LLM to evaluate if a response adequately answers the user's query.
    Returns True if the response is adequate, False otherwise.
    """
    evaluation = chat_with_model(
        message=(
            f"User Query: {query}\n\n"
            f"Response: {response}\n\n"
            "Does this response adequately answer the user's question? Consider:\n"
            "1. Does it directly address what was asked?\n"
            "2. Does it provide actionable information?\n"
            "3. Is it specific enough to be useful?\n"
            "4. For CLI commands, does it provide the correct command?\n"
            "5. For search results, does it provide relevant information?\n"
            "Respond with ONLY 'yes' if adequate, or 'no' if inadequate."
        ),
        config=config,
        chat_models=chat_models,
        system_prompt=(
            "You are a response quality evaluator. Be strict in your evaluation. "
            "Only accept responses that truly answer the user's question. "
            "For CLI commands, ensure they are correct and complete. "
            "For search results, ensure they provide relevant information."
        )
    )
    return evaluation.strip().lower() == 'yes'

def get_fallback_response(query: str, original_response: str, config, chat_models) -> str:
    """Get a more helpful response from the fallback LLM."""
    return chat_with_model(
        message=(
            f"Original query: {query}\n"
            f"Previous response: {original_response}\n"
            "This response was deemed inadequate. Please provide a more helpful response that:\n"
            "1. Directly addresses the user's question\n"
            "2. Provides specific, actionable information\n"
            "3. Draws from your knowledge to give accurate details\n"
            "4. For CLI commands, provides the exact command needed\n"
            "5. For general queries, provides comprehensive information"
        ),
        config=config,
        chat_models=chat_models,
        system_prompt=(
            "You are a helpful expert assistant. Provide detailed, accurate responses "
            "that directly address the user's needs. If the query is about software or "
            "system operations, include specific steps or commands when appropriate."
        )
    )

def process_response(query: str, response: str, config, chat_models) -> str:
    """
    Process a response through evaluation and fallback if needed.
    Returns the final response to use.
    """
    if not evaluate_response(query, response, config, chat_models):
        print(f"{config.YELLOW}Initial response was inadequate. Getting better response...{config.RESET}")
        return get_fallback_response(query, response, config, chat_models)
    return response

def handle_cli_command(query: str, config, chat_models) -> str:
    """Handle CLI command generation and evaluation."""
    response = chat_with_model(
        query,
        config=config,
        chat_models=chat_models,
        system_prompt=(
            "You are a CLI expert. If this request can be handled with CLI commands, "
            "provide the appropriate command wrapped in ```bash\n[command]\n``` markers. "
            "If no CLI command is suitable, respond with 'NO_CLI_COMMAND'."
        )
    )
    
    if "NO_CLI_COMMAND" not in response:
        print(f"{config.CYAN}Generated CLI command, evaluating...{config.RESET}")
        return process_response(query, response, config, chat_models)
    return response

def handle_web_search(query: str, response: str, config, chat_models) -> str:
    """Handle web search result evaluation."""
    print(f"{config.CYAN}Processing search result...{config.RESET}")
    return process_response(query, response, config, chat_models)

def get_search_url(query):
    """Generate a search URL from a query."""
    search_terms = ['search', 'find', 'lookup', 'what is', 'how to']
    if any(term in query.lower() for term in search_terms):
        search_query = query
        for term in search_terms:
            search_query = search_query.replace(term, '').strip()
        return f"https://www.google.com/search?q={search_query}"
    return None

def _validate_query(query: str) -> bool:
    """Validate that the query is not empty and contains actual content."""
    return bool(query and query.strip())

def process_input_based_on_mode(query, config, chat_models):
    """Process user input based on the current mode and query type."""
    # Validate query
    if not _validate_query(query):
        print(f"{config.YELLOW}Please provide a command or question.{config.RESET}")
        return None
        
    # Print current configuration for debugging
    if config.session_model:
        print(f"{config.CYAN}Using model: {config.session_model}{config.RESET}")
    
    # First try CLI commands for system operations
    if any(word in query.lower() for word in ['install', 'setup', 'configure', 'run', 'start', 'stop', 'restart']):
        response = handle_cli_command(query, config, chat_models)
        if "NO_CLI_COMMAND" not in response:
            return response
    
    # Then try web search if it's a search query
    if any(word in query.lower() for word in ['search', 'find', 'lookup', 'what is', 'how to']):
        search_query = query.replace('search', '').replace('find', '').replace('lookup', '').strip()
        url = f"https://www.google.com/search?q={search_query}"
        print(f"{config.CYAN}Searching for: {search_query}{config.RESET}")
        
        try:
            # Use MCP tool for web search
            response = use_mcp_tool(
                server_name="web_search",
                tool_name="search",
                arguments={"url": url}
            )
            
            if response:
                final_response = handle_web_search(query, response, config, chat_models)
                if final_response:
                    print_streamed_message(final_response, config.CYAN)
                return None
        except Exception as e:
            print(f"{config.YELLOW}Web search failed: {str(e)}{config.RESET}")
    
    # If no specific handling, fall back to general LLM processing
    llm_response = chat_with_model(query, config, chat_models)
    final_response = process_response(query, llm_response, config, chat_models)
    print_streamed_message(final_response, config.CYAN)
    return None

def process_input_in_safe_mode(query, config, chat_models):
    """Process input in safe mode with additional checks and confirmations."""
    llm_response = chat_with_model(query, config, chat_models)
    final_response = process_response(query, llm_response, config, chat_models)
    print_streamed_message(final_response, config.CYAN)

def process_input_in_autopilot_mode(query, config, chat_models):
    """Process input in autopilot mode with automatic execution."""
    llm_response = chat_with_model(query, config, chat_models)
    final_response = process_response(query, llm_response, config, chat_models)
    print_streamed_message(final_response, config.CYAN)

# Initialize cache for storing content from MCP tools
_content_cache = {
    'raw_content': None,  # Raw JSON response
    'formatted_content': None,  # Formatted text for summaries
    'headlines': [],  # List of headlines for easy reference
    'paragraphs': []  # List of paragraphs for easy reference
}

# Pre-compile regex patterns for better performance
SCRIPT_PATTERN = re.compile(r"```(?:(bash|sh|python))?\n(.*?)```", re.DOTALL)
CLEANUP_PATTERN = re.compile(r"```(?:bash|sh)\n(.*?)\n```", re.DOTALL)

def assemble_final_script(scripts: list) -> str:
    """
    Assemble multiple script blocks into a final executable script.
    
    Args:
        scripts: List of tuples containing (content, extension, script_type)
    
    Returns:
        str: The assembled script ready for execution
    """
    if not scripts:
        return ""
        
    # If there's only one script, return it directly
    if len(scripts) == 1:
        return scripts[0][0]
        
    # For multiple scripts, combine them with proper separators
    final_script = "#!/bin/bash\n\n"
    
    for content, ext, script_type in scripts:
        if script_type == "python":
            # For Python scripts, wrap in python -c
            escaped_content = content.replace('"', '\\"')
            final_script += f'python3 -c "{escaped_content}"\n\n'
        else:
            # For bash scripts, include directly
            final_script += f"{content}\n\n"
            
    return final_script.strip()

def extract_script_from_response(response):
    """Extract scripts from LLM response with improved language detection."""
    if not isinstance(response, str):
        print("Error: 'response' expected to be a string, received:", type(response))
        return []
    
    scripts = []
    matches = SCRIPT_PATTERN.finditer(response)
    
    for match in matches:
        lang = match.group(1)
        content = match.group(2).strip()
        
        if not content:
            continue
            
        # Add shebang line if not present
        if not content.startswith("#!"):
            if lang == "python":
                content = "#!/usr/bin/env python3\n" + content
                ext = "py"
                script_type = "python"
            else:
                content = "#!/bin/bash\n" + content
                ext = "sh"
                script_type = "bash"
        else:
            # Check for shebang line
            first_line = content.split("\n")[0]
            if "python" in first_line.lower():
                ext = "py"
                script_type = "python"
            else:
                ext = "sh"
                script_type = "bash"
        
        scripts.append((content, ext, script_type))
    
    return scripts

def clean_up_llm_response(llm_response):
    """Clean up LLM response by extracting and formatting script blocks."""
    script_blocks = CLEANUP_PATTERN.findall(llm_response)
    if script_blocks:
        return "\n".join(block.strip() for block in script_blocks if block.strip())
    print("No executable script blocks found in the response.")
    return llm_response.strip()

def execute_script(filename, file_extension, config):
    """Execute a saved script with proper error handling."""
    try:
        if file_extension == "py":
            result = subprocess.run(
                ["python", filename],
                capture_output=True,
                text=True,
                check=False
            )
        elif file_extension in ["sh", "bash", ""]:
            try:
                os.chmod(filename, 0o755)
            except OSError as e:
                print(f"{config.RED}Failed to set executable permissions: {e}{config.RESET}")
                return
            
            result = subprocess.run(
                ["bash", filename],
                capture_output=True,
                text=True,
                check=False
            )
        else:
            print(f"{config.RED}Running scripts with .{file_extension} extension is not supported.{config.RESET}")
            return
        
        if result.stdout:
            print(result.stdout)
        if result.stderr:
            print(f"{config.RED}{result.stderr}{config.RESET}")
            
        if result.returncode != 0:
            print(f"{config.RED}Script execution failed with return code {result.returncode}{config.RESET}")
            
            if resolution := consult_llm_for_error_resolution(result.stderr or result.stdout, config):
                if get_user_confirmation("Would you like to apply the suggested fix?", config):
                    execute_resolution_script(resolution, config)
        else:
            print(f"{config.GREEN}Script executed successfully.{config.RESET}")
            
    except Exception as e:
        print(f"{config.RED}An error occurred while executing the script: {e}{config.RESET}")

def execute_script_directly(script, file_extension, config):
    """Execute a script directly with proper cleanup and error handling."""
    temp_file_path = None
    try:
        if file_extension in ["sh", "bash", ""]:
            if not script.startswith("#!"):
                script = "#!/bin/bash\n" + script

        if file_extension == "py":
            with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as temp_file:
                temp_file.write(script)
                temp_file_path = temp_file.name
            
            try:
                result = subprocess.run(
                    ["python", temp_file_path],
                    capture_output=True,
                    text=True,
                    check=False
                )
                if result.returncode != 0:
                    print(f"{config.RED}Python script execution failed:{config.RESET}")
                    if result.stderr:
                        print(result.stderr)
                    return False
                if result.stdout:
                    print(result.stdout)
                return True
            except Exception as e:
                print(f"{config.RED}Error executing Python script: {e}{config.RESET}")
                return False
                
        elif file_extension in ["sh", "bash", ""]:
            with tempfile.NamedTemporaryFile(mode='w', suffix='.sh', delete=False) as temp_file:
                temp_file.write(script)
                temp_file_path = temp_file.name
                
            try:
                os.chmod(temp_file_path, 0o755)
                
                if not config.autopilot_mode and not get_user_confirmation(f"Execute script:\n{script}"):
                    print("Script execution aborted by the user.")
                    return False
                
                result = subprocess.run(
                    ["bash", temp_file_path],
                    capture_output=True,
                    text=True,
                    check=False
                )
                
                if result.stdout:
                    print(result.stdout)
                if result.stderr:
                    print(f"{config.RED}{result.stderr}{config.RESET}")
                
                return result.returncode == 0
                
            except Exception as e:
                print(f"{config.RED}Error executing shell script: {e}{config.RESET}")
                return False
        else:
            print(f"{config.RED}Running scripts with .{file_extension} extension is not supported.{config.RESET}")
            return False
            
    except Exception as e:
        print(f"{config.RED}Error preparing script for execution: {e}{config.RESET}")
        return False
        
    finally:
        if temp_file_path and os.path.exists(temp_file_path):
            try:
                os.unlink(temp_file_path)
            except OSError as e:
                print(f"Warning: Failed to clean up temporary file {temp_file_path}: {e}")

def execute_resolution_script(resolution, config):
    """Execute a resolution script with proper error handling."""
    print(f"{config.CYAN}Executing resolution:{config.RESET}\n{resolution}")
    try:
        subprocess.run(resolution, shell=True, check=True)
        print(f"{config.GREEN}Resolution executed successfully.{config.RESET}")
    except subprocess.CalledProcessError as e:
        print(f"{config.RED}Resolution execution failed with error: {e}{config.RESET}")
    except Exception as e:
        print(f"An error occurred while executing the resolution: {e}")

def get_user_confirmation(command: str, config=None) -> bool:
    """Get user confirmation before executing a command."""
    if config and config.autopilot_mode:
        return True
    print(f"\nAbout to execute command:\n{command}")
    response = input("Do you want to proceed? (yes/no): ").strip().lower()
    return response in ['yes', 'y']

def auto_handle_script_execution(script: str, config) -> bool:
    """
    Automatically handle script execution with proper error handling.
    
    Args:
        script: The script content to execute
        config: Configuration object containing execution settings
        
    Returns:
        bool: True if execution was successful, False otherwise
    """
    if not script:
        print("No script content provided.")
        return False
        
    # Determine script type based on content
    script_type = "python" if script.startswith("#!/usr/bin/env python") else "bash"
    ext = "py" if script_type == "python" else "sh"
    
    return execute_script_directly(script, ext, config)

def consult_llm_for_error_resolution(error_message, config):
    """Consult LLM for error resolution suggestions."""
    system_info = get_system_info()
    print(f"{config.CYAN}Consulting LLM for error resolution:{config.RESET} {error_message}")
    
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
                "temperature": 0.3
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
