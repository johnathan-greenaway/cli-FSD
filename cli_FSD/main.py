# main.py

import argparse
import sys
import logging
from datetime import datetime
from . import configuration
from .configuration import initialize_config

from cli_FSD.utils import (
    print_instructions_once_per_day,
    display_greeting,
    cleanup_previous_assembled_scripts
)
from cli_FSD.chat_models import initialize_chat_models
from cli_FSD.command_handlers import handle_command_mode
from cli_FSD.script_handlers import process_input_based_on_mode

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

    args = parse_arguments()
    config = initialize_config(args)
    chat_models = initialize_chat_models(config)

    # Combine the query list into a single string
    query = ' '.join(args.query).strip()

    if query:
        try:
            # Process the input, which handles saving based on mode
            process_input_based_on_mode(query, config, chat_models)
            logging.info(f"Processed query: {query}")
        except Exception as e:
            import traceback
            error_message = f"Error processing query '{query}': {e}"
            print(f"{config.RED}An error occurred while processing your query: {e}{config.RESET}")
            print(f"{config.RED}Full traceback:{config.RESET}")
            traceback.print_exc()
            logging.error(error_message)
            logging.error(traceback.format_exc())
        sys.exit(0)

    # If no query is provided, start the interactive loop
    cleanup_previous_assembled_scripts()
    print_instructions_once_per_day()
    display_greeting()

    while True:
        try:
            # Build a more informative prompt with session status indicators
            prompt_parts = []
            
            # Add model indicator with color coding
            if config.session_model:
                if config.session_model == 'claude':
                    model_indicator = f"{config.GREEN}C{config.RESET}"
                elif config.session_model == 'ollama':
                    model_indicator = f"{config.YELLOW}O{config.RESET}"
                elif config.session_model == 'groq':
                    model_indicator = f"{config.CYAN}G{config.RESET}"
                else:
                    model_indicator = f"{config.RED}?{config.RESET}"
                prompt_parts.append(model_indicator)
            
            # Add mode indicators
            if config.safe_mode:
                prompt_parts.append(f"{config.GREEN}S{config.RESET}")
            if config.autopilot_mode:
                prompt_parts.append(f"{config.RED}A{config.RESET}")
            
            # Add cache indicator if browser content is available
            from .script_handlers import _content_cache
            if _content_cache['raw_content']:
                prompt_parts.append(f"{config.CYAN}🌐{config.RESET}")
                
            # Add history count if available
            if hasattr(config, 'session_history') and config.session_history:
                history_count = len(config.session_history)
                prompt_parts.append(f"{config.YELLOW}[{history_count}]{config.RESET}")
            
            # Build the final prompt
            status_indicators = "".join(prompt_parts)
            
            # Get input with the enhanced prompt
            user_input = input(f"{config.YELLOW}{status_indicators}@{config.SMALL_FONT}(v{config.VERSION}){config.RESET}{config.YELLOW}:{config.RESET} ").strip()

            if not user_input:
                continue  # Skip empty inputs

            # Parse model selection flags if command starts with @
            if user_input.startswith("@"):
                try:
                    # Split into parts but preserve quoted strings
                    parts = []
                    current = []
                    in_quotes = False
                    for char in user_input[1:].strip():  # Skip @ and leading space
                        if char == '"':
                            in_quotes = not in_quotes
                        elif char.isspace() and not in_quotes:
                            if current:
                                parts.append(''.join(current))
                                current = []
                        else:
                            current.append(char)
                    if current:
                        parts.append(''.join(current))
                    
                    # Process flags
                    i = 0
                    flags_changed = False
                    while i < len(parts) and parts[i].startswith("-"):
                        flag = parts[i]
                        if flag == "-o":
                            config.session_model = "ollama"
                            config.use_ollama = True
                            config.use_claude = config.use_groq = False
                            flags_changed = True
                        elif flag == "-c":
                            config.session_model = "claude"
                            config.use_claude = True
                            config.use_ollama = config.use_groq = False
                            flags_changed = True
                        elif flag == "-g":
                            config.session_model = "groq"
                            config.use_groq = True
                            config.use_claude = config.use_ollama = False
                            flags_changed = True
                        elif flag == "-a":
                            config.autopilot_mode = True
                            flags_changed = True
                        elif flag == "-ci":
                            config.scriptreviewer_on = True
                            flags_changed = True
                        elif flag == "-d":
                            # Reset all settings to default
                            config.session_model = None
                            config.use_ollama = config.use_claude = config.use_groq = False
                            config.autopilot_mode = config.scriptreviewer_on = False
                            flags_changed = True
                        else:
                            break
                        i += 1

                    # Save preferences if flags were changed
                    if flags_changed:
                        config.save_preferences()
                        chat_models = initialize_chat_models(config)
                        if config.session_model:
                            print(f"Using model: {config.session_model}")
                        else:
                            print("Using default model settings")
                        if config.autopilot_mode:
                            print("Autopilot mode enabled")

                    # Reconstruct query preserving quotes
                    user_input = " ".join(parts[i:])
                    
                    if not user_input:
                        continue
                        
                except Exception as e:
                    print(f"{config.RED}Error parsing command: {str(e)}{config.RESET}")
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
                try:
                    # Process the input and get the response
                    response = process_input_based_on_mode(user_input, config, chat_models)
                    
                    # Update session history with this interaction
                    if not hasattr(config, 'session_history'):
                        config.session_history = []
                    
                    # Store interaction in session history
                    config.session_history.append({
                        'query': user_input,
                        'response': response if response else "No response generated",
                        'timestamp': datetime.now().isoformat()
                    })
                    
                    # Store last response for reference
                    config.last_response = response if response else "No response generated"
                    logging.info(f"Processed command: {user_input}")
                    
                    # Make sure the response is actually shown to the user if it wasn't already printed
                    if response:
                        # Don't double-print if it was already streamed
                        if not hasattr(config, '_response_was_streamed') or not config._response_was_streamed:
                            print(f"{config.CYAN}{response}{config.RESET}")
                        config._response_was_streamed = False
                    
                    # Always reset this flag for next input
                    config._response_was_streamed = False
                except Exception as e:
                    error_message = f"Error processing command '{user_input}': {e}"
                    print(f"{config.RED}Error processing command: {e}{config.RESET}")
                    logging.error(error_message)

            if hasattr(config, 'llm_suggestions') and config.llm_suggestions:
                print(f"{config.CYAN}Processing LLM suggestion:{config.RESET} {config.llm_suggestions}")
                try:
                    process_input_based_on_mode(config.llm_suggestions, config, chat_models)
                    logging.info(f"Processed LLM suggestion: {config.llm_suggestions}")
                except Exception as e:
                    error_message = f"Error processing LLM suggestion '{config.llm_suggestions}': {e}"
                    print(f"{config.RED}Error processing LLM suggestion: {e}{config.RESET}")
                    logging.error(error_message)
                config.llm_suggestions = None
        except (KeyboardInterrupt, EOFError):
            print("\nExiting cli-FSD...")
            logging.info("cli-FSD exited by user.")
            
            # Handle cleanup of assembled scripts
            from .script_handlers import handle_script_cleanup
            handle_script_cleanup(config)
            
            print("Goodbye!")
            break

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
