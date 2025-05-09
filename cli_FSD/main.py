# main.py

import argparse
import sys
import os
import logging
from datetime import datetime
from . import configuration
from .configuration import initialize_config
import readline
from .command_history import CommandHistory

from cli_FSD.utils import (
    print_instructions_once_per_day,
    display_greeting,
    cleanup_previous_assembled_scripts
)
from cli_FSD.chat_models import initialize_chat_models, chat_with_model
from cli_FSD.command_handlers import (
    handle_command_mode, 
    handle_browse_command,
    execute_shell_command,
    get_user_confirmation
)
from cli_FSD.script_handlers import (
    process_input_based_on_mode,
    process_response,
    print_streamed_message,
    display_session_history,
    recall_history_item,
    display_session_status,
    format_browser_response
)

# Initialize response context
_response_context = {
    'browser_attempts': 0,
    'last_response': None,
    'last_operation': None,
    'last_url': None,
    'previous_responses': [],  # List of previous responses
    'collected_info': {},      # Information collected from various tools
    'tolerance_level': 'medium'  # Default tolerance level: 'strict', 'medium', 'lenient'
}

def main():
    # Configure logging
    logging.basicConfig(
        filename='cli_fsd.log',
        filemode='a',
        format='%(asctime)s - %(levelname)s - %(message)s',
        level=logging.DEBUG
    )

    logging.info("cli-FSD started")

    # Initialize web fetcher early
    try:
        from .web_fetcher import fetcher
        logging.info("Initialized WebContentFetcher")
    except Exception as e:
        logging.error(f"Failed to initialize WebContentFetcher: {e}")
        print(f"Warning: WebContentFetcher initialization failed: {e}")

    args = parse_arguments()
    config = initialize_config(args)
    chat_models = initialize_chat_models(config)

    # Initialize command history
    command_history = CommandHistory()
    
    # Set up readline for query history
    readline.set_history_length(1000)
    
    def completer(text, state):
        """Query completer for fuzzy search."""
        if not text:
            return None
        
        # Get fuzzy matches from command history
        matches = command_history.fuzzy_search(text)
        if state < len(matches):
            return matches[state]
        return None
    
    # Set up readline completer
    readline.set_completer(completer)
    readline.parse_and_bind('tab: complete')

    # Display greeting
    display_greeting()

    while True:
        try:
            # Get user input with history navigation
            user_input = input(f"{config.GREEN}You: {config.SMALL_FONT}v{config.VERSION} + @{config.RESET} ").strip()
            
            # Add query to history
            command_history.add_command(user_input)
            
            if not user_input:
                continue
                
            if user_input.upper() == 'CMD':
                handle_command_mode(config, chat_models)
            elif user_input.lower() == 'safe':
                config.safe_mode = True
                config.autopilot_mode = False
                config.save_preferences()
                print("Switched to safe mode. You will be prompted before executing any commands.")
                logging.info("Switched to safe mode.")
            elif user_input.lower() == 'autopilot':
                config.safe_mode = False
                config.autopilot_mode = True
                config.save_preferences()
                print("Switched to autopilot mode.")
                logging.info("Switched to autopilot mode.")
            elif user_input.lower() == 'normal':
                config.safe_mode = False
                config.autopilot_mode = False
                config.save_preferences()
                print("Switched to normal mode.")
                logging.info("Switched to normal mode.")
            else:
                if config.autopilot_mode:
                    process_input_in_autopilot_mode(user_input, config, chat_models)
                else:
                    process_input_based_on_mode(user_input, config, chat_models)
                    
        except KeyboardInterrupt:
            print("\nExiting cli-FSD...")
            logging.info("cli-FSD exited by user.")
            
            # Handle cleanup of assembled scripts
            from .script_handlers import handle_script_cleanup
            handle_script_cleanup(config)
            
            print("Goodbye!")
            break
        except Exception as e:
            error_message = f"Error in main loop: {str(e)}"
            print(f"{config.RED}{error_message}{config.RESET}")
            logging.error(error_message)

    print("Operation completed.")
    logging.info("cli-FSD operation completed.")


def parse_arguments():
    parser = argparse.ArgumentParser(
        description="Terminal Companion with Full Self Drive Mode",
        formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("-s", "--safe", action="store_true", help="Run in safe mode")
    parser.add_argument("-a", "--autopilot", action="store_true", help="Enable autopilot mode")
    parser.add_argument("-c", "--claude", action="store_true", help="Use Claude for processing requests")
    parser.add_argument("-ci", "--assistantsAPI", action="store_true", help="Use OpenAI for error resolution")
    parser.add_argument("-o", "--ollama", action="store_true", help="Use Ollama for processing requests")
    parser.add_argument("-g", "--groq", action="store_true", help="Use Groq for processing requests")
    parser.add_argument("-d", "--default", action="store_true", help="Reset to default model settings")
    parser.add_argument("query", nargs=argparse.REMAINDER, help="User query to process directly")
    return parser.parse_args()

def process_input_based_on_mode(query, config, chat_models):
    """Process user input based on the current mode and query type."""
    import json
    from .agents.web_content_agent import WebContentAgent
    from .agents.context_agent import ContextAgent
    
    # Initialize agents
    web_agent = WebContentAgent()
    context_agent = ContextAgent()
    
    # Reset browser attempts counter for new queries
    _response_context['browser_attempts'] = 0
    
    # Check for session management commands
    if query.lower() == 'history':
        return display_session_history(config)
    elif query.lower().startswith('recall '):
        try:
            index = int(query.lower().replace('recall ', '').strip())
            return recall_history_item(config, index)
        except ValueError:
            print(f"{config.YELLOW}Please provide a valid index number.{config.RESET}")
            return "Invalid recall index. Use 'history' to see available items."
    elif query.lower() == 'session status':
        return display_session_status(config)
    
    # Check for browse/visit commands
    if query.lower().startswith(('browse ', 'visit ')):
        # Extract the target from the command
        target = query[7:].strip() if query.lower().startswith('browse ') else query[6:].strip()
        
        # Use ContextAgent to analyze and execute the browse request
        try:
            # Get the context agent's analysis
            context_analysis = context_agent.analyze_request(target)
            
            if not context_analysis or not isinstance(context_analysis, dict):
                print(f"{config.YELLOW}Failed to generate valid analysis from ContextAgent.{config.RESET}")
                return "Failed to analyze browse request. Please try again."
            
            # Create a tool selection for browsing
            tool_selection = {
                "tool_selection": {
                    "tool": "small_context",
                    "operation": "browse_web",
                    "parameters": {
                        "url": f"https://news.ycombinator.com/" if "hacker news" in target.lower() or "hn" in target.lower() else target
                    }
                }
            }
            
            # Execute the tool selection
            result = context_agent.execute_tool_selection(tool_selection)
            
            if result and not result.get("error"):
                # Format and return the result
                formatted_response = format_browser_response(target, json.dumps(result), config, chat_models)
                
                # If the response is a string, print it directly
                if isinstance(formatted_response, str):
                    print_streamed_message(formatted_response, config.CYAN)
                # If it's a dict, format it nicely
                elif isinstance(formatted_response, dict):
                    if "content" in formatted_response:
                        print_streamed_message(formatted_response["content"], config.CYAN)
                    else:
                        print_streamed_message(json.dumps(formatted_response, indent=2), config.CYAN)
                return formatted_response
            else:
                error_msg = result.get("error", "Unknown error occurred") if result else "No result returned"
                print(f"{config.RED}Error executing browse: {error_msg}{config.RESET}")
                return f"Failed to browse {target}. Error: {error_msg}"
                
        except Exception as e:
            print(f"{config.RED}Error in browse command: {str(e)}{config.RESET}")
            return f"Error processing browse command: {str(e)}"
    
    # Use ContextAgent to analyze the request and determine which tool to use
    try:
        analysis = context_agent.analyze_request(query)
        
        # If the analysis is a direct response (no LLM processing needed)
        if not analysis.get("requires_llm_processing", True):
            if analysis.get("tool") == "command":
                command = analysis.get("command")
                description = analysis.get("description", "Execute command")
                if command:
                    # Show the command to the user
                    print(f"\n{description}:")
                    print(f"```bash\n{command}\n```")
                    
                    if config.autopilot_mode:
                        print(f"{config.CYAN}Executing command in autopilot mode...{config.RESET}")
                        result = execute_shell_command(command, config.api_key, stream_output=True, safe_mode=False)
                        if result.startswith("Error"):
                            print(f"{config.RED}{result}{config.RESET}")
                        else:
                            print(f"{config.GREEN}{result}{config.RESET}")
                        return result
                    else:
                        if get_user_confirmation(command, config):
                            result = execute_shell_command(command, config.api_key, stream_output=True, safe_mode=True)
                            if result.startswith("Error"):
                                print(f"{config.RED}{result}{config.RESET}")
                            else:
                                print(f"{config.GREEN}{result}{config.RESET}")
                            return result
                        return "Command execution cancelled by user."
            return "Error: Invalid direct response format."
        
        # Validate analysis object
        if not analysis or not isinstance(analysis, dict) or "prompt" not in analysis:
            # Fall back to direct LLM processing if analysis fails
            print(f"{config.YELLOW}Failed to generate valid analysis from ContextAgent.{config.RESET}")
            llm_response = chat_with_model(query, config, chat_models)
            final_response = process_response(query, llm_response, config, chat_models, allow_browser_fallback=True)
            print_streamed_message(final_response, config.CYAN)
            return final_response
        
        # Get LLM's tool selection decision with the analysis prompt
        llm_analysis = chat_with_model(analysis["prompt"], config, chat_models)
        
        try:
            # Clean up the response by removing markdown code block markers
            cleaned_response = llm_analysis.replace("```json", "").replace("```", "").strip()
            result = json.loads(cleaned_response)
        except json.JSONDecodeError:
            print(f"{config.YELLOW}Failed to parse LLM analysis response.{config.RESET}")
            print(f"\n{config.CYAN}Raw LLM response for debugging:{config.RESET}")
            print(f"```json\n{llm_analysis}\n```")
            return "Error: Could not parse tool selection response."
        
        # Handle different tool types
        if result.get("tool") == "web_content":
            # Use web content agent
            if result.get("operation") in ["fetch", "browse", "search"]:
                response = web_agent.execute_command(f"{result['operation']} {result['url_or_query']} {result.get('mode', 'basic')}")
                if response.get("error"):
                    print(f"{config.RED}Error: {response['error']}{config.RESET}")
                    return f"Error: {response['error']}"
                
                # Update context with the response
                context_agent.update_context(result['operation'], response)
                return response
                
        elif result.get("tool") == "file_operation":
            # Use file operations
            operation = result.get("operation")
            filepath = result.get("filepath")
            content = result.get("content", "")
            description = result.get("description", "Perform file operation")
            
            if not filepath:
                print(f"{config.RED}Error: No filepath specified for file operation{config.RESET}")
                return "Error: No filepath specified"
            
            # Show the operation to the user
            print(f"\n{description}:")
            print(f"File: {filepath}")
            
            if operation == "write":
                # Create directory if it doesn't exist
                os.makedirs(os.path.dirname(filepath), exist_ok=True)
                
                # Write the content to the file
                try:
                    with open(filepath, 'w') as f:
                        f.write(content)
                    print(f"{config.GREEN}Successfully created file: {filepath}{config.RESET}")
                    return f"Created file: {filepath}"
                except Exception as e:
                    error_msg = f"Error writing to file: {str(e)}"
                    print(f"{config.RED}{error_msg}{config.RESET}")
                    return error_msg
            else:
                error_msg = f"Unsupported file operation: {operation}"
                print(f"{config.RED}{error_msg}{config.RESET}")
                return error_msg
            
        elif result.get("tool") == "command":
            # Handle shell commands
            command = result.get("command")
            description = result.get("description", "Execute command")
            requires_confirmation = result.get("requires_confirmation", True)
            
            if command:
                # Show the command to the user
                print(f"\n{description}:")
                print(f"```bash\n{command}\n```")
                
                if config.autopilot_mode or not requires_confirmation:
                    print(f"{config.CYAN}Executing command...{config.RESET}")
                    result = execute_shell_command(command, config.api_key, stream_output=True, safe_mode=not config.autopilot_mode)
                    if result.startswith("Error"):
                        print(f"{config.RED}{result}{config.RESET}")
                    else:
                        print(f"{config.GREEN}{result}{config.RESET}")
                    return result
                else:
                    if get_user_confirmation(command, config):
                        result = execute_shell_command(command, config.api_key, stream_output=True, safe_mode=True)
                        if result.startswith("Error"):
                            print(f"{config.RED}{result}{config.RESET}")
                        else:
                            print(f"{config.GREEN}{result}{config.RESET}")
                        return result
                    return "Command execution cancelled by user."
        
        # If no specific tool was selected or tool execution failed, fall back to direct LLM processing
        llm_response = chat_with_model(query, config, chat_models)
        final_response = process_response(query, llm_response, config, chat_models, allow_browser_fallback=True)
        print_streamed_message(final_response, config.CYAN)
        return final_response
        
    except Exception as e:
        print(f"{config.RED}Error in process_input_based_on_mode: {str(e)}{config.RESET}")
        # Fall back to direct LLM processing
        llm_response = chat_with_model(query, config, chat_models)
        final_response = process_response(query, llm_response, config, chat_models, allow_browser_fallback=True)
        print_streamed_message(final_response, config.CYAN)
        return final_response

def process_input_in_autopilot_mode(query, config, chat_models):
    """Process input in autopilot mode with automatic execution."""
    # Set autopilot mode in config
    config.autopilot_mode = True
    
    # Process the input
    response = process_input_based_on_mode(query, config, chat_models)
    
    # If response contains a command, execute it
    if isinstance(response, dict) and response.get("command"):
        command = response["command"]
        print(f"{config.CYAN}Executing command in autopilot mode: {command}{config.RESET}")
        execute_shell_command(command, config.api_key, stream_output=True, safe_mode=False)
        return f"Executed command: {command}"
    
    return response

def process_input_in_safe_mode(query, config, chat_models):
    """Process input in safe mode with additional checks and confirmations."""
    # Set safe mode in config
    config.safe_mode = True
    config.autopilot_mode = False
    
    # Process the input
    response = process_input_based_on_mode(query, config, chat_models)
    
    # If response contains a command, ask for confirmation
    if isinstance(response, dict) and response.get("command"):
        command = response["command"]
        if get_user_confirmation(command, config):
            execute_shell_command(command, config.api_key, stream_output=True, safe_mode=True)
            return f"Executed command: {command}"
        else:
            return "Command execution aborted by user."
    
    return response
