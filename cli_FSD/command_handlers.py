import os
from .utils import print_streamed_message
from .script_handlers import extract_script_from_response, assemble_final_script, auto_handle_script_execution
from .chat_models import initialize_chat_models # Import necessary function



def handle_command_mode(config, chat_models):
    while True:
        command = input(f"{config.GREEN}CMD>{config.RESET} ").strip().lower()
        if command == 'quit':
            break
        elif command == 'exit':
            print(f"{config.CYAN}Exited command mode.{config.RESET}")
            break
        else:
            process_command(command, config, chat_models)

def process_command(command, config, chat_models):
    if command == 'reset':
        reset_conversation(config)
        print(f"{config.CYAN}The conversation has been reset.{config.RESET}")
    elif command == 'save':
        save_last_response(config)
    elif command == 'autopilot':
        toggle_autopilot(config)
    elif command == 'script':
        handle_script_command(config)
    elif command == 'model':
        # Pass chat_models so it can be updated
        change_model(config, chat_models) 
    elif command == 'list_models':
        list_available_models(config)
    elif command == 'config':
        show_current_config(config)
    elif command == 'history':
        show_history(config)
    elif command.startswith('recall '):
        try:
            index = int(command.replace('recall ', '').strip())
            recall_item(config, index)
        except ValueError:
            print(f"{config.YELLOW}Please provide a valid index number.{config.RESET}")
    elif command == 'session':
        show_session_status(config)
    elif command == 'clear history':
        clear_history(config)
    else:
        print(f"{config.YELLOW}Unknown command. Type 'exit' to return to normal mode.{config.RESET}")

def reset_conversation(config):
    """Reset the conversation history."""
    # Reset session history
    if hasattr(config, 'session_history'):
        config.session_history = []
    
    # Reset last response
    config.last_response = None
    
    # Reset any cached content
    from .script_handlers import _content_cache
    _content_cache['raw_content'] = None
    _content_cache['formatted_content'] = None
    _content_cache['headlines'] = []
    _content_cache['paragraphs'] = []
    
    print("Conversation history and cache have been reset.")

def save_last_response(config):
    file_path = input("Enter the file path to save the last response: ")
    try:
        with open(file_path, "w") as file:
            file.write(config.last_response)
        print(f"Response saved to {file_path}")
    except Exception as e:
        print(f"Error saving response: {e}")


def toggle_autopilot(config):
    config.autopilot_mode = not config.autopilot_mode
    print(f"Autopilot mode {'enabled' if config.autopilot_mode else 'disabled'}.")

def handle_script_command(config):
    # Assuming last_response is stored somewhere in the config or globally
    last_response = "Last response placeholder"  # Replace with actual last response
    if last_response:
        scripts = extract_script_from_response(last_response)
        if scripts:
            final_script = assemble_final_script(scripts, config.api_key)
            auto_handle_script_execution(final_script, config)
        else:
            print("No script found in the last response.")
    else:
        print("No last response to process.")

def change_model(config, chat_models):
    """Change the active model and update related settings."""
    list_available_models(config) # Show options first
    new_model_key = input("Enter the key of the model to switch to (e.g., 'gpt-4o', 'claude-3.5-sonnet'): ").strip()
    
    if new_model_key in config.models:
        config.current_model = new_model_key # Update the specific model key
        
        # Determine provider and update session_model and use_ flags
        if new_model_key.startswith("claude-"):
            config.session_model = "claude"
            config.use_claude = True
            config.use_ollama = config.use_groq = False
        elif new_model_key == "ollama": # Assuming 'ollama' is a key in config.models for the generic provider
            config.session_model = "ollama"
            config.use_ollama = True
            config.use_claude = config.use_groq = False
            # Optionally, prompt for a specific ollama model or use last_ollama_model
            config.current_model = config.last_ollama_model # Use last known Ollama model
        elif new_model_key == "groq": # Assuming 'groq' is a key for the provider
            config.session_model = "groq"
            config.use_groq = True
            config.use_claude = config.use_ollama = False
            config.current_model = "mixtral-8x7b-32768" # Set Groq default model
        else: # Default to OpenAI compatible
            config.session_model = None # Use default provider (OpenAI)
            config.use_claude = config.use_ollama = config.use_groq = False
            # config.current_model is already set to new_model_key

        print(f"{config.GREEN}Model set to: {config.current_model}{config.RESET}")
        if config.session_model:
            print(f"{config.GREEN}Provider set to: {config.session_model}{config.RESET}")
        else:
             print(f"{config.GREEN}Provider set to: Default (OpenAI){config.RESET}")

        # Save preferences
        config.save_preferences()
        print(f"{config.CYAN}Preferences saved.{config.RESET}")

        # Re-initialize chat models
        try:
            new_chat_models = initialize_chat_models(config)
            # Update the original chat_models dictionary passed from main
            chat_models.clear()
            chat_models.update(new_chat_models)
            print(f"{config.CYAN}Chat models re-initialized.{config.RESET}")
        except Exception as e:
             print(f"{config.RED}Error re-initializing chat models: {e}{config.RESET}")

    else:
        print(f"{config.YELLOW}Invalid model key. Use 'list_models' to see options.{config.RESET}")

def list_available_models(config):
    print("Available models:")
    for model in config.models.keys():
        print(model)

def show_current_config(config):
    print(f"Current configuration:")
    print(f"Model: {config.current_model}")
    print(f"Server Port: {config.server_port}")
    print(f"Autopilot Mode: {'Enabled' if config.autopilot_mode else 'Disabled'}")
    print(f"Safe Mode: {'Enabled' if config.safe_mode else 'Disabled'}")
    print(f"Using Claude: {'Yes' if config.use_claude else 'No'}")
    print(f"Using Ollama: {'Yes' if config.use_ollama else 'No'}")
    print(f"Using Groq: {'Yes' if config.use_groq else 'No'}")
    print(f"Script Reviewer: {'Enabled' if config.scriptreviewer_on else 'Disabled'}")

# Session management helper functions
def show_history(config):
    """Display the session history."""
    from .script_handlers import display_session_history
    display_session_history(config)

def recall_item(config, index):
    """Recall and display a specific history item."""
    from .script_handlers import recall_history_item
    recall_history_item(config, index)

def show_session_status(config):
    """Display current session status."""
    from .script_handlers import display_session_status
    display_session_status(config)

def clear_history(config):
    """Clear the session history."""
    if hasattr(config, 'session_history'):
        config.session_history = []
        print(f"{config.GREEN}Session history has been cleared.{config.RESET}")
    else:
        print(f"{config.YELLOW}No session history to clear.{config.RESET}")
