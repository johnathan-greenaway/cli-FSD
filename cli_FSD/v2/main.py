import argparse
from config import initialize_config
from utils import print_instructions_once_per_day, display_greeting, cleanup_previous_assembled_scripts
from chat_models import initialize_chat_models
from command_handlers import handle_command_mode
from script_handlers import process_input_based_on_mode


def main():
    args = parse_arguments()
    config = initialize_config(args)
    chat_models = initialize_chat_models(config)
    
    cleanup_previous_assembled_scripts()
    print_instructions_once_per_day()
    display_greeting()

    while True:
        user_input = input(f"{config.YELLOW}@:{config.RESET} ").strip()
        
        if user_input.upper() == 'CMD':
            handle_command_mode(config, chat_models)
        elif user_input.lower() == 'safe':
            config.safe_mode = True
            config.autopilot_mode = False
            print("Switched to safe mode. You will be prompted before executing any commands.")
        elif user_input.lower() == 'autopilot':
            config.safe_mode = False
            config.autopilot_mode = True
            print("Switched to autopilot mode.")
        elif user_input.lower() == 'normal':
            config.safe_mode = False
            config.autopilot_mode = False
            print("Switched to normal mode.")
        else:
            config.last_response = process_input_based_on_mode(user_input, config, chat_models)

        if hasattr(config, 'llm_suggestions') and config.llm_suggestions:
            print(f"{config.CYAN}Processing LLM suggestion:{config.RESET} {config.llm_suggestions}")
            process_input_based_on_mode(config.llm_suggestions, config, chat_models)
            config.llm_suggestions = None

    print("Operation completed.")

def parse_arguments():
    parser = argparse.ArgumentParser(description="Terminal Companion with Full Self Drive Mode")
    parser.add_argument("-s", "--safe", action="store_true", help="Run in safe mode")
    parser.add_argument("-a", "--autopilot", choices=['on', 'off'], default='off',
                        help="Turn autopilot mode on or off at startup")
    parser.add_argument("-c", "--claude", action="store_true", help="Use Claude for processing requests")
    parser.add_argument("-ci", "--assistantsAPI", action="store_true", help="Use OpenAI for error resolution")
    parser.add_argument("-o", "--ollama", action="store_true", help="Use Ollama for processing requests")
    parser.add_argument("-g", "--groq", action="store_true", help="Use Groq for processing requests")
    return parser.parse_args()

if __name__ == "__main__":
    main()