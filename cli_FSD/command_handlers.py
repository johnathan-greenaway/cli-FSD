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
    elif command.startswith('file'):
        handle_file_command(config)
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

def handle_browse_command(config):
    """Handle the browse command to view web content."""
    print(f"{config.CYAN}Browse mode activated.{config.RESET}")
    
    # Check if we have cached content
    from .script_handlers import _content_cache
    if _content_cache['raw_content']:
        print(f"{config.GREEN}Web content is already loaded.{config.RESET}")
        
        # Show available headlines if any
        if _content_cache['headlines']:
            print(f"{config.CYAN}Available headlines:{config.RESET}")
            for i, headline in enumerate(_content_cache['headlines']):
                print(f"{i+1}: {headline}")
        else:
            print(f"{config.YELLOW}No headlines found in the cached content.{config.RESET}")
        
        # Ask if user wants to view the content
        view_option = input("View content? (y/n): ").strip().lower()
        if view_option == 'y':
            print(f"{config.CYAN}Cached web content:{config.RESET}")
            print(_content_cache['formatted_content'] or _content_cache['raw_content'])
    else:
        url = input("Enter URL to browse: ").strip()
        if url:
            try:
                from .web_fetcher import fetcher
                content = fetcher.fetch_url(url)
                if content:
                    _content_cache['raw_content'] = content
                    _content_cache['formatted_content'] = content  # Simple version, could be enhanced
                    print(f"{config.GREEN}Content fetched successfully.{config.RESET}")
                    print(f"{config.CYAN}Content preview:{config.RESET}")
                    print(content[:500] + "..." if len(content) > 500 else content)
                else:
                    print(f"{config.RED}Failed to fetch content from {url}{config.RESET}")
            except Exception as e:
                print(f"{config.RED}Error fetching URL: {e}{config.RESET}")
        else:
            print(f"{config.YELLOW}No URL provided.{config.RESET}")
    
    print(f"{config.CYAN}Exiting browse mode.{config.RESET}")

def handle_file_command(config):
    """Allow browsing and interacting with files and directories."""
    import os

    path = input("Enter directory path to browse (default '.'): ").strip() or '.'
    try:
        entries = os.listdir(path)
    except Exception as e:
        print(f"{config.RED}Error listing directory '{path}': {e}{config.RESET}")
        return

    print(f"{config.CYAN}Contents of {path}:{config.RESET}")
    for idx, entry in enumerate(entries):
        full = os.path.join(path, entry)
        tag = '<DIR>' if os.path.isdir(full) else '<FILE>'
        print(f"{idx}: {entry} {tag}")

    selection = input("Enter index of item to open or 'exit' to cancel: ").strip().lower()
    if selection in ('exit', ''):
        return

    try:
        idx = int(selection)
        if idx < 0 or idx >= len(entries):
            raise IndexError()
        chosen = entries[idx]
        full_path = os.path.join(path, chosen)
        if os.path.isdir(full_path):
            print(f"{config.CYAN}Contents of directory: {full_path}{config.RESET}")
            sub_entries = os.listdir(full_path)
            for sub in sub_entries:
                sub_full = os.path.join(full_path, sub)
                sub_tag = '<DIR>' if os.path.isdir(sub_full) else '<FILE>'
                print(f"  {sub}: {sub_tag}")
        else:
            print(f"{config.CYAN}Displaying contents of file: {full_path}{config.RESET}")
            try:
                with open(full_path, 'r') as f:
                    print(f.read())
            except Exception as e:
                print(f"{config.RED}Error reading file '{full_path}': {e}{config.RESET}")
    except (ValueError, IndexError):
        print(f"{config.YELLOW}Invalid selection.{config.RESET}")
