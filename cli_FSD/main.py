# main.py

import argparse
import sys
import logging
from .config import initialize_config
from .utils import (
    print_instructions_once_per_day,
    display_greeting,
    cleanup_previous_assembled_scripts
)
from .chat_models import initialize_chat_models
from .command_handlers import handle_command_mode
from .script_handlers import process_input_based_on_mode

def main():
    # Configure logging
    logging.basicConfig(
        filename='cli_fsd.log',
        filemode='a',
        format='%(asctime)s - %(levelname)s - %(message)s',
        level=logging.DEBUG
    )

    logging.info("cli-FSD started")

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
            error_message = f"Error processing query '{query}': {e}"
            print(f"{config.RED}An error occurred while processing your query: {e}{config.RESET}")
            logging.error(error_message)
        sys.exit(0)

    # If no query is provided, start the interactive loop
    cleanup_previous_assembled_scripts()
    print_instructions_once_per_day()
    display_greeting()

    while True:
        try:
            user_input = input(f"{config.YELLOW}@:{config.RESET} ").strip()

            if not user_input:
                continue  # Skip empty inputs

            if user_input.upper() == 'CMD':
                handle_command_mode(config, chat_models)
            elif user_input.lower() == 'safe':
                config.safe_mode = True
                config.autopilot_mode = False
                print("Switched to safe mode. You will be prompted before executing any commands.")
                logging.info("Switched to safe mode.")
            elif user_input.lower() == 'autopilot':
                config.safe_mode = False
                config.autopilot_mode = True
                print("Switched to autopilot mode.")
                logging.info("Switched to autopilot mode.")
            elif user_input.lower() == 'normal':
                config.safe_mode = False
                config.autopilot_mode = False
                print("Switched to normal mode.")
                logging.info("Switched to normal mode.")
            else:
                try:
                    config.last_response = process_input_based_on_mode(user_input, config, chat_models)
                    logging.info(f"Processed command: {user_input}")
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
            print("\nExiting cli-FSD. Goodbye!")
            logging.info("cli-FSD exited by user.")
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
    parser.add_argument("query", nargs=argparse.REMAINDER, help="User query to process directly")
    return parser.parse_args()
