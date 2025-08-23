import os
import subprocess
import readline
import sys
import asyncio
from .utils import print_streamed_message
from .script_handlers import extract_script_from_response, assemble_final_script, auto_handle_script_execution
from .chat_models import initialize_chat_models # Import necessary function
from .agents.sequential_thinking_agent import SequentialThinkingAgent
from .command_history import CommandHistory
from .model_manager import ModelManager
from difflib import get_close_matches

def get_user_confirmation(command: str, config=None) -> bool:
    """Get user confirmation before executing a command.
    
    Args:
        command: The command to confirm
        config: Optional configuration object
        
    Returns:
        bool: True if user confirms, False otherwise
    """
    if config and config.autopilot_mode:
        return True
    print(f"\nAbout to execute command:\n{command}")
    response = input("Do you want to proceed? (yes/no): ").strip().lower()
    return response in ['yes', 'y']

def execute_shell_command(command: str, api_key: str = None, stream_output: bool = True, safe_mode: bool = True) -> str:
    """Execute a shell command with proper error handling.
    
    Args:
        command: The shell command to execute
        api_key: Optional API key for authentication
        stream_output: Whether to stream command output
        safe_mode: Whether to run in safe mode
        
    Returns:
        str: Command output or error message
    """
    try:
        # Create a process with appropriate settings
        process = subprocess.Popen(
            command,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            universal_newlines=True
        )
        
        output_lines = []
        error_lines = []
        
        # Stream output if requested
        if stream_output:
            while True:
                output = process.stdout.readline()
                if output == '' and process.poll() is not None:
                    break
                if output:
                    output_lines.append(output.strip())
                    print(output.strip())
            
            # Check for errors
            stderr = process.stderr.read()
            if stderr:
                error_lines.append(stderr.strip())
                print(f"Error: {stderr}")
        
        # Wait for process to complete
        return_code = process.wait()
        
        if return_code != 0:
            error_msg = f"Command failed with return code {return_code}"
            if error_lines:
                error_msg += f"\nErrors:\n" + "\n".join(error_lines)
            return error_msg
            
        return "\n".join(output_lines) if output_lines else "Command executed successfully."
        
    except Exception as e:
        return f"Error executing command: {str(e)}"

def handle_command_mode(config, chat_models):
    """Handle command mode interactions."""
    print(f"{config.CYAN}Entering command mode. Type 'exit' to return to normal mode.{config.RESET}")
    
    # Initialize sequential thinking agent and command history
    thinking_agent = SequentialThinkingAgent()
    command_history = CommandHistory()
    
    # Define available commands for fuzzy search
    available_commands = [
        'help', 'exit', 'safe', 'autopilot', 'normal',
        'sequential thinking on', 'sequential thinking off',
        'sequential thinking llm choice on', 'sequential thinking llm choice off',
        'sequential thinking history', 'sequential thinking clear',
        'session', 'session status', 'history', 'recall',
        'model', 'list_models', 'models_table', 'config', 'clear history',
        'file', 'fileint', 'ollama models', 'format on', 'format off', 'format demo'
    ]
    
    # Set up readline for command history
    readline.set_history_length(1000)
    
    def completer(text, state):
        """Command completer for fuzzy search."""
        if not text:
            return None
        
        # Get fuzzy matches from both command history and available commands
        history_matches = command_history.fuzzy_search(text)
        command_matches = get_close_matches(text, available_commands, n=5, cutoff=0.6)
        
        # Combine matches, prioritizing available commands
        all_matches = list(dict.fromkeys(command_matches + history_matches))
        
        if state < len(all_matches):
            return all_matches[state]
        return None
    
    # Set up readline completer and tab completion
    readline.set_completer(completer)
    readline.parse_and_bind('tab: complete')
    readline.parse_and_bind('set show-all-if-ambiguous on')
    readline.parse_and_bind('set completion-ignore-case on')
    
    # Print available commands for reference
    print("\nAvailable commands:")
    print("  help                    - Show this help message")
    print("  exit                    - Exit command mode")
    print("  safe                    - Switch to safe mode")
    print("  autopilot              - Switch to autopilot mode")
    print("  normal                 - Switch to normal mode")
    print("  sequential thinking on  - Enable sequential thinking")
    print("  sequential thinking off - Disable sequential thinking")
    print("  sequential thinking llm choice on  - Enable LLM choice for sequential thinking")
    print("  sequential thinking llm choice off - Disable LLM choice for sequential thinking")
    print("  sequential thinking history - Show thought history")
    print("  sequential thinking clear - Clear thought history")
    print("  session                - Show session status")
    print("  session status         - Show session status")
    print("  history                - Show conversation history")
    print("  recall <index>         - Recall specific history item")
    print("  model                  - Change model")
    print("  list_models            - List available models")
    print("  models_table           - Display models in detailed table format")
    print("  config                 - Show current configuration")
    print("  clear history          - Clear conversation history")
    print("  file                   - Browse and view files")
    print("  fileint                - Advanced file operations")
    print("  ollama models          - Browse and manage Ollama models")
    print("  format on/off          - Toggle enhanced text formatting")
    print("  format demo            - Show formatting examples")
    print("\nType part of a command and press TAB to cycle through matching commands.")
    
    while True:
        try:
            # Get command with history navigation
            command = input(f"{config.YELLOW}CMD>{config.RESET} ").strip()
            
            # Add command to history
            command_history.add_command(command)
            
            # Handle internal commands first
            if command.lower() == 'exit':
                break
            elif command.lower() == 'help':
                print_help()
            elif command.lower() == 'safe':
                config.safe_mode = True
                config.autopilot_mode = False
                config.save_preferences()
                print("Switched to safe mode.")
            elif command.lower() == 'autopilot':
                config.safe_mode = False
                config.autopilot_mode = True
                config.save_preferences()
                print("Switched to autopilot mode.")
            elif command.lower() == 'normal':
                config.safe_mode = False
                config.autopilot_mode = False
                config.save_preferences()
                print("Switched to normal mode.")
            elif command.lower() == 'sequential thinking on':
                config.sequential_thinking_enabled = True
                config.sequential_thinking_llm_choice = False
                config.save_preferences()
                thinking_agent.enable(False)
                print("Sequential thinking enabled.")
            elif command.lower() == 'sequential thinking off':
                config.sequential_thinking_enabled = False
                config.sequential_thinking_llm_choice = False
                config.save_preferences()
                thinking_agent.disable()
                print("Sequential thinking disabled.")
            elif command.lower() == 'sequential thinking llm choice on':
                config.sequential_thinking_enabled = True
                config.sequential_thinking_llm_choice = True
                config.save_preferences()
                thinking_agent.enable(True)
                print("Sequential thinking enabled with LLM choice.")
            elif command.lower() == 'sequential thinking llm choice off':
                config.sequential_thinking_enabled = True
                config.sequential_thinking_llm_choice = False
                config.save_preferences()
                thinking_agent.enable(False)
                print("Sequential thinking enabled without LLM choice.")
            elif command.lower() == 'sequential thinking history':
                if thinking_agent.thought_history:
                    print("\nThought History:")
                    for thought in thinking_agent.get_thought_history():
                        print(thinking_agent._format_thought(thought))
                else:
                    print("No thought history available.")
            elif command.lower() == 'sequential thinking clear':
                thinking_agent.clear_history()
                print("Thought history cleared.")
            elif command.lower() == 'session':
                show_session_status(config)
            elif command.lower() == 'session status':
                show_session_status(config)
            elif command.lower() == 'history':
                show_history(config)
            elif command.lower().startswith('recall '):
                try:
                    index = int(command.replace('recall ', '').strip())
                    recall_item(config, index)
                except ValueError:
                    print(f"{config.YELLOW}Please provide a valid index number.{config.RESET}")
            elif command.lower() == 'model':
                change_model(config, chat_models)
            elif command.lower() == 'list_models':
                list_available_models(config)
            elif command.lower() == 'models_table':
                show_models_table(config)
            elif command.lower() == 'config':
                show_current_config(config)
            elif command.lower() == 'clear history':
                reset_conversation(config)
                print(f"{config.CYAN}History cleared.{config.RESET}")
            elif command.lower().startswith('file'):
                handle_file_command(config)
            elif command.lower().startswith('fileint'):
                handle_file_interaction_command(config)
            elif command.lower() == 'ollama models' or command.lower() == 'ollama':
                handle_ollama_models_command(config)
            elif command.lower() == 'format on':
                config.enhanced_formatting = True
                config.save_preferences()
                print(f"{config.GREEN}✅ Enhanced formatting enabled{config.RESET}")
            elif command.lower() == 'format off':
                config.enhanced_formatting = False
                config.save_preferences()
                print(f"{config.YELLOW}Enhanced formatting disabled{config.RESET}")
            elif command.lower() == 'format demo':
                show_formatting_demo(config)
            else:
                # Execute the command as a shell command only if it's not an internal command
                result = execute_shell_command(command, config.api_key, stream_output=True, safe_mode=config.safe_mode)
                if result.startswith("Error"):
                    print(f"{config.RED}{result}{config.RESET}")
                else:
                    print(f"{config.GREEN}{result}{config.RESET}")
                    
        except KeyboardInterrupt:
            print("\nExiting command mode...")
            break
        except Exception as e:
            print(f"{config.RED}Error: {str(e)}{config.RESET}")

def print_help():
    """Print help information for command mode."""
    print("""
Available commands:
  help                    - Show this help message
  exit                    - Exit command mode
  safe                    - Switch to safe mode
  autopilot              - Switch to autopilot mode
  normal                 - Switch to normal mode
  sequential thinking on  - Enable sequential thinking
  sequential thinking off - Disable sequential thinking
  sequential thinking llm choice on  - Enable LLM choice for sequential thinking
  sequential thinking llm choice off - Disable LLM choice for sequential thinking
  sequential thinking history - Show thought history
  sequential thinking clear - Clear thought history
  model                  - Change model interactively
  list_models            - List available models
  models_table           - Display models in detailed table format
  ollama models          - Browse and manage Ollama models
  <any other command>    - Execute as shell command
""")

def process_command(command, config, chat_models):
    """Process commands in normal mode."""
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
    elif command == 'models_table':
        show_models_table(config)
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
        reset_conversation(config)
        print(f"{config.CYAN}History cleared.{config.RESET}")
    elif command.startswith('file'):
        handle_file_command(config)
    elif command.startswith('fileint'):
        handle_file_interaction_command(config)
    elif command == 'ollama models' or command == 'ollama':
        handle_ollama_models_command(config)
    elif command == 'format on':
        config.enhanced_formatting = True
        config.save_preferences()
        print(f"{config.GREEN}✅ Enhanced formatting enabled{config.RESET}")
    elif command == 'format off':
        config.enhanced_formatting = False
        config.save_preferences()
        print(f"{config.YELLOW}Enhanced formatting disabled{config.RESET}")
    elif command == 'format demo':
        show_formatting_demo(config)
    # Add sequential thinking commands
    elif command == 'sequential thinking on':
        config.sequential_thinking_enabled = True
        config.sequential_thinking_llm_choice = False
        config.save_preferences()
        print("Sequential thinking enabled.")
    elif command == 'sequential thinking off':
        config.sequential_thinking_enabled = False
        config.sequential_thinking_llm_choice = False
        config.save_preferences()
        print("Sequential thinking disabled.")
    elif command == 'sequential thinking llm choice on':
        config.sequential_thinking_enabled = True
        config.sequential_thinking_llm_choice = True
        config.save_preferences()
        print("Sequential thinking enabled with LLM choice.")
    elif command == 'sequential thinking llm choice off':
        config.sequential_thinking_enabled = True
        config.sequential_thinking_llm_choice = False
        config.save_preferences()
        print("Sequential thinking enabled without LLM choice.")
    elif command == 'sequential thinking history':
        # Initialize thinking agent to show history
        thinking_agent = SequentialThinkingAgent()
        if thinking_agent.thought_history:
            print("\nThought History:")
            for thought in thinking_agent.get_thought_history():
                print(thinking_agent._format_thought(thought))
        else:
            print("No thought history available.")
    elif command == 'sequential thinking clear':
        # Initialize thinking agent to clear history
        thinking_agent = SequentialThinkingAgent()
        thinking_agent.clear_history()
        print("Thought history cleared.")
    else:
        print(f"{config.YELLOW}Unknown command. Type 'session' to see available commands.{config.RESET}")

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
        with open(file_path, "w") as f:
            f.write(config.last_response)
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
    """Change the active model and update related settings with dynamic detection."""
    print(f"{config.CYAN}Loading available models...{config.RESET}")
    
    try:
        model_manager = ModelManager()
        all_models = model_manager.get_all_models()
        
        if not all_models:
            print(f"{config.YELLOW}No models detected. Check your API keys and services.{config.RESET}")
            return
        
        # Create a flat list of all available models with provider info
        available_models = []
        for provider, models in all_models.items():
            for model in models:
                if model.is_available:  # Only show available models for selection
                    available_models.append({
                        'id': model.model_id,
                        'provider': provider,
                        'description': model.display_name,
                        'model_info': model
                    })
        
        if not available_models:
            print(f"{config.YELLOW}No available models found.{config.RESET}")
            return
            
        # Display options in a numbered list for easy selection
        print(f"\n{config.GREEN}Available Models:{config.RESET}")
        print("-" * 60)
        for i, model in enumerate(available_models, 1):
            provider_color = {
                'openai': config.BLUE,
                'anthropic': config.MAGENTA,
                'ollama': config.GREEN, 
                'groq': config.YELLOW
            }.get(model['provider'], config.WHITE)
            
            print(f"{i:2d}. {config.CYAN}{model['id']:<30}{config.RESET} {provider_color}[{model['provider'].upper()}]{config.RESET}")
            if model['description'] and model['description'] != model['id']:
                print(f"    {config.WHITE}{model['description']}{config.RESET}")
        
        print(f"\n{config.CYAN}Current model: {config.current_model}{config.RESET}")
        
        # Get user selection
        selection = input(f"\nEnter model number (1-{len(available_models)}) or model ID: ").strip()
        
        selected_model = None
        
        # Try number selection first
        try:
            model_num = int(selection)
            if 1 <= model_num <= len(available_models):
                selected_model = available_models[model_num - 1]
        except ValueError:
            # Try direct model ID match
            for model in available_models:
                if model['id'].lower() == selection.lower():
                    selected_model = model
                    break
        
        if not selected_model:
            print(f"{config.YELLOW}Invalid selection. Model change cancelled.{config.RESET}")
            return
        
        # Update configuration based on selected model
        config.current_model = selected_model['id']
        provider = selected_model['provider']
        
        # Reset all provider flags
        config.use_claude = config.use_ollama = config.use_groq = False
        
        # Set provider-specific configuration
        if provider == 'anthropic':
            config.session_model = "claude"
            config.use_claude = True
        elif provider == 'ollama':
            config.session_model = "ollama" 
            config.use_ollama = True
            config.last_ollama_model = selected_model['id']
        elif provider == 'groq':
            config.session_model = "groq"
            config.use_groq = True
        else:  # OpenAI or compatible
            config.session_model = None  # Default to OpenAI
            
        print(f"{config.GREEN}✓ Model changed to: {selected_model['id']}{config.RESET}")
        print(f"{config.GREEN}✓ Provider: {provider.upper()}{config.RESET}")
        
        # Save preferences
        config.save_preferences()
        print(f"{config.CYAN}✓ Preferences saved{config.RESET}")
        
        # Re-initialize chat models
        try:
            new_chat_models = initialize_chat_models(config)
            chat_models.clear()
            chat_models.update(new_chat_models)
            print(f"{config.CYAN}✓ Chat models re-initialized{config.RESET}")
        except Exception as e:
            print(f"{config.RED}Error re-initializing chat models: {e}{config.RESET}")
            
    except Exception as e:
        print(f"{config.RED}Error changing model: {str(e)}{config.RESET}")
        print(f"{config.YELLOW}Falling back to configured models.{config.RESET}")
        
        # Fallback to original static model list
        list_available_models(config)
        new_model_key = input("Enter the key of the model to switch to: ").strip()
        
        if new_model_key in config.models:
            config.current_model = new_model_key
            config.save_preferences()
            print(f"{config.GREEN}Model set to: {config.current_model}{config.RESET}")
        else:
            print(f"{config.YELLOW}Invalid model key.{config.RESET}")

def list_available_models(config):
    """List all available models from all providers dynamically."""
    print(f"{config.CYAN}Detecting available models...{config.RESET}")
    
    try:
        model_manager = ModelManager()
        all_models = model_manager.get_all_models()
        
        if not all_models:
            print(f"{config.YELLOW}No models detected. Check your API keys and services.{config.RESET}")
            return
            
        # Display models organized by provider
        total_models = 0
        for provider, models in all_models.items():
            if not models:
                continue
                
            print(f"\n{config.GREEN}🔹 {provider.upper()} ({len(models)} models){config.RESET}")
            print("-" * 50)
            
            for model in models:
                status_color = config.GREEN if model.is_available else config.YELLOW
                status_text = "✓ Available" if model.is_available else "⚠ Limited/Deprecated"
                
                print(f"{config.CYAN}{model.model_id:<30}{config.RESET} {status_color}{status_text}{config.RESET}")
                if model.display_name and model.display_name != model.model_id:
                    print(f"  {config.WHITE}{model.display_name}{config.RESET}")
                
                total_models += 1
        
        print(f"\n{config.GREEN}Total models detected: {total_models}{config.RESET}")
        print(f"{config.CYAN}Current model: {config.current_model}{config.RESET}")
        
    except Exception as e:
        print(f"{config.RED}Error detecting models: {str(e)}{config.RESET}")
        print(f"{config.YELLOW}Falling back to configured models:{config.RESET}")
        for model in config.models.keys():
            print(f"  {model}")

def show_models_table(config):
    """Display all models in a detailed table format."""
    print(f"{config.CYAN}Loading model information...{config.RESET}")
    
    try:
        model_manager = ModelManager()
        all_models = model_manager.get_all_models()
        
        # Convert to flat list for table formatting
        all_model_infos = []
        for provider, models in all_models.items():
            all_model_infos.extend(models)
        
        if all_model_infos:
            table_output = model_manager.format_models_table(all_model_infos)
            print(table_output)
            
            print(f"\n{config.GREEN}Total models: {len(all_model_infos)}{config.RESET}")
            print(f"{config.CYAN}Current model: {config.current_model}{config.RESET}")
        else:
            print(f"{config.YELLOW}No models detected. Check your API keys and services.{config.RESET}")
        
    except Exception as e:
        print(f"{config.RED}Error displaying models table: {str(e)}{config.RESET}")
        print(f"{config.YELLOW}Falling back to basic model list:{config.RESET}")
        list_available_models(config)

def show_formatting_demo(config):
    """Show examples of enhanced formatting."""
    from .utils import (
        format_header, format_section, format_status_box,
        format_code_block, format_table, format_progress_bar,
        format_list_items
    )
    
    print(f"\n{config.CYAN}🎨 Enhanced Formatting Demo{config.RESET}")
    print("=" * 50)
    
    # Header demo
    print(format_header("Welcome to CLI-FSD Enhanced Formatting", style='bold'))
    
    # Section demo  
    features = [
        "Beautiful headers and sections",
        "Color-coded status messages",
        "Formatted code blocks with line numbers",
        "Professional tables",
        "Progress bars and lists"
    ]
    print(format_section("✨ New Features", features, color=config.GREEN))
    
    # Status boxes demo
    print(format_status_box('success', 'Enhanced formatting is working perfectly!'))
    print(format_status_box('info', 'This improves readability significantly', 
                           ['Better visual hierarchy', 'Consistent styling', 'Professional appearance']))
    
    # Code block demo
    sample_code = "def enhanced_formatting():\n    print('Much better readability!')\n    return True"
    print(format_code_block(sample_code, 'python'))
    
    # Table demo
    headers = ["Feature", "Status", "Impact"]
    rows = [
        ["Headers", "✅ Complete", "High"],
        ["Code Blocks", "✅ Complete", "High"], 
        ["Tables", "✅ Complete", "Medium"],
        ["Progress Bars", "✅ Complete", "Medium"]
    ]
    print(format_table(headers, rows, title="Feature Status Overview"))
    
    # Progress demo
    print(f"\n{config.CYAN}📊 Progress Indicators:{config.RESET}")
    print(f"Formatting Implementation: {format_progress_bar(100, 100)}")
    print(f"User Experience: {format_progress_bar(95, 100)}")
    
    # List demo
    tips = [
        "Use 'format on' to enable enhanced formatting",
        "Use 'format off' for classic text output",
        "Enhanced formatting works with all responses",
        "Perfect for better readability and professional look"
    ]
    print(format_section("💡 Tips", tips, color=config.BLUE))
    
    print(f"\n{config.GREEN}✨ Enhanced formatting makes CLI-FSD more readable and professional!{config.RESET}")

def show_current_config(config):
    """Display current configuration with enhanced formatting if enabled."""
    if hasattr(config, 'enhanced_formatting') and config.enhanced_formatting:
        from .utils import format_section, format_table
        
        # Display as formatted table
        headers = ["Setting", "Value"]
        rows = [
            ["Model", config.current_model],
            ["Server Port", str(config.server_port)],
            ["Autopilot Mode", "✅ Enabled" if config.autopilot_mode else "❌ Disabled"],
            ["Safe Mode", "✅ Enabled" if config.safe_mode else "❌ Disabled"],
            ["Enhanced Formatting", "✅ Enabled" if config.enhanced_formatting else "❌ Disabled"],
            ["Using Claude", "✅ Yes" if config.use_claude else "❌ No"],
            ["Using Ollama", "✅ Yes" if config.use_ollama else "❌ No"],
            ["Using Groq", "✅ Yes" if config.use_groq else "❌ No"],
            ["Script Reviewer", "✅ Enabled" if config.scriptreviewer_on else "❌ Disabled"]
        ]
        
        if config.use_ollama:
            rows.append(["Ollama Model", config.last_ollama_model])
            
        print(format_table(headers, rows, title="CLI-FSD Configuration"))
    else:
        # Classic display
        print(f"Current configuration:")
        print(f"Model: {config.current_model}")
        print(f"Server Port: {config.server_port}")
        print(f"Autopilot Mode: {'Enabled' if config.autopilot_mode else 'Disabled'}")
        print(f"Safe Mode: {'Enabled' if config.safe_mode else 'Disabled'}")
        print(f"Enhanced Formatting: {'Enabled' if hasattr(config, 'enhanced_formatting') and config.enhanced_formatting else 'Disabled'}")
        print(f"Using Claude: {'Yes' if config.use_claude else 'No'}")
        print(f"Using Ollama: {'Yes' if config.use_ollama else 'No'}")
        if config.use_ollama:
            print(f"Current Ollama Model: {config.last_ollama_model}")
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

def handle_ollama_models_command(config):
    """Browse and manage Ollama models with interactive UI."""
    from .ollama_models import run_ollama_browser

    # Simply run the interactive browser
    asyncio.run(run_ollama_browser(config))

def handle_file_interaction_command(config):
    """Advanced file interaction using the file-interaction MCP server."""
    import json
    from .utils import use_mcp_tool
    
    print(f"{config.CYAN}File Interaction Mode{config.RESET}")
    print(f"{config.YELLOW}Available commands:{config.RESET}")
    print("1. list - List files in a directory")
    print("2. read - Read a file")
    print("3. write - Write to a file")
    print("4. modify - Modify parts of a file")
    print("5. delete - Delete a file")
    print("6. search - Search for text in files")
    print("7. mkdir - Create a directory")
    print("8. exit - Exit file interaction mode")
    
    while True:
        cmd = input(f"{config.GREEN}FILEINT>{config.RESET} ").strip().lower()
        
        if cmd == 'exit' or cmd == 'quit':
            print(f"{config.CYAN}Exiting file interaction mode.{config.RESET}")
            break
            
        elif cmd == 'list':
            path = input("Enter directory path (default '.'): ").strip() or '.'
            recursive = input("List recursively? (y/n, default: n): ").strip().lower() == 'y'
            pattern = input("File pattern (default '*'): ").strip() or '*'
            
            try:
                result = use_mcp_tool(
                    server_name="file-interaction",
                    tool_name="list_files",
                    arguments={
                        "path": path,
                        "recursive": recursive,
                        "pattern": pattern
                    }
                )
                
                # Parse the result
                try:
                    data = json.loads(result)
                    if "error" in data:
                        print(f"{config.RED}Error: {data['error']}{config.RESET}")
                    else:
                        files = data.get("files", [])
                        print(f"{config.CYAN}Found {len(files)} items in {path}:{config.RESET}")
                        for item in files:
                            item_type = item.get("type", "unknown")
                            item_path = item.get("path", "")
                            if item_type == "file":
                                size = item.get("size", 0)
                                size_str = f"{size} bytes"
                                if size > 1024:
                                    size_str = f"{size/1024:.1f} KB"
                                if size > 1024*1024:
                                    size_str = f"{size/(1024*1024):.1f} MB"
                                print(f"{config.YELLOW}[FILE]{config.RESET} {item_path} ({size_str})")
                            else:
                                print(f"{config.GREEN}[DIR]{config.RESET} {item_path}")
                except json.JSONDecodeError:
                    print(f"{config.RED}Error parsing response: {result}{config.RESET}")
                except Exception as e:
                    print(f"{config.RED}Error processing response: {str(e)}{config.RESET}")
            except Exception as e:
                print(f"{config.RED}Error listing files: {str(e)}{config.RESET}")
                
        elif cmd == 'read':
            path = input("Enter file path to read: ").strip()
            if not path:
                print(f"{config.YELLOW}No file path provided.{config.RESET}")
                continue
                
            try:
                result = use_mcp_tool(
                    server_name="file-interaction",
                    tool_name="read_file",
                    arguments={
                        "path": path
                    }
                )
                
                # Parse the result
                try:
                    data = json.loads(result)
                    if "error" in data:
                        print(f"{config.RED}Error: {data['error']}{config.RESET}")
                    else:
                        content = data.get("content", "")
                        size = data.get("size", 0)
                        is_binary = data.get("is_binary", False)
                        
                        if is_binary:
                            print(f"{config.YELLOW}Binary file detected. Size: {size} bytes{config.RESET}")
                            print(content)  # This will be a message about binary content
                        else:
                            print(f"{config.CYAN}File: {path} ({size} bytes){config.RESET}")
                            print(f"{config.GREEN}Content:{config.RESET}")
                            print(content)
                except json.JSONDecodeError:
                    print(f"{config.RED}Error parsing response: {result}{config.RESET}")
                except Exception as e:
                    print(f"{config.RED}Error processing response: {str(e)}{config.RESET}")
            except Exception as e:
                print(f"{config.RED}Error reading file: {str(e)}{config.RESET}")
                
        elif cmd == 'write':
            path = input("Enter file path to write: ").strip()
            if not path:
                print(f"{config.YELLOW}No file path provided.{config.RESET}")
                continue
                
            # Use multiline_input function from main.py
            from .main import multiline_input
            print(f"{config.CYAN}Enter content:{config.RESET}")
            content = multiline_input("", show_hint=True)
            requires_approval = input("Require approval before writing? (y/n, default: y): ").strip().lower() != 'n'
            
            try:
                result = use_mcp_tool(
                    server_name="file-interaction",
                    tool_name="write_file",
                    arguments={
                        "path": path,
                        "content": content,
                        "requires_approval": requires_approval
                    }
                )
                
                # Parse the result
                try:
                    data = json.loads(result)
                    if "error" in data:
                        print(f"{config.RED}Error: {data['error']}{config.RESET}")
                    else:
                        message = data.get("message", "")
                        
                        if data.get("requires_approval", False):
                            temp_path = data.get("temp_path", "")
                            print(f"{config.YELLOW}{message}{config.RESET}")
                            print(f"Temporary file created at: {temp_path}")
                            
                            approve = input("Approve this write operation? (y/n): ").strip().lower() == 'y'
                            if approve:
                                # Move the temporary file to the target path
                                import os
                                import shutil
                                try:
                                    full_temp_path = os.path.join(os.getcwd(), temp_path)
                                    full_target_path = os.path.join(os.getcwd(), path)
                                    shutil.move(full_temp_path, full_target_path)
                                    print(f"{config.GREEN}File written to {path}{config.RESET}")
                                except Exception as e:
                                    print(f"{config.RED}Error moving temporary file: {str(e)}{config.RESET}")
                            else:
                                # Delete the temporary file
                                import os
                                try:
                                    full_temp_path = os.path.join(os.getcwd(), temp_path)
                                    os.remove(full_temp_path)
                                    print(f"{config.YELLOW}Write operation cancelled. Temporary file deleted.{config.RESET}")
                                except Exception as e:
                                    print(f"{config.RED}Error deleting temporary file: {str(e)}{config.RESET}")
                        else:
                            print(f"{config.GREEN}{message}{config.RESET}")
                except json.JSONDecodeError:
                    print(f"{config.RED}Error parsing response: {result}{config.RESET}")
                except Exception as e:
                    print(f"{config.RED}Error processing response: {str(e)}{config.RESET}")
            except Exception as e:
                print(f"{config.RED}Error writing file: {str(e)}{config.RESET}")
                
        elif cmd == 'modify':
            path = input("Enter file path to modify: ").strip()
            if not path:
                print(f"{config.YELLOW}No file path provided.{config.RESET}")
                continue
                
            print(f"{config.CYAN}Modification types:{config.RESET}")
            print("1. replace - Replace text")
            print("2. insert - Insert text at start/end/line")
            print("3. delete - Delete text")
            
            operations = []
            while True:
                op_type = input("Enter operation type (or 'done' to finish): ").strip().lower()
                if op_type == 'done':
                    break
                    
                if op_type == 'replace':
                    search = input("Text to search for: ").strip()
                    replace = input("Text to replace with: ").strip()
                    operations.append({
                        "type": "replace",
                        "search": search,
                        "replace": replace
                    })
                elif op_type == 'insert':
                    position = input("Position (start/end/line): ").strip().lower()
                    if position not in ['start', 'end', 'line']:
                        print(f"{config.YELLOW}Invalid position. Using 'end'.{config.RESET}")
                        position = 'end'
                        
                    if position == 'line':
                        try:
                            line_number = int(input("Line number: ").strip())
                        except ValueError:
                            print(f"{config.YELLOW}Invalid line number. Using 0.{config.RESET}")
                            line_number = 0
                    else:
                        line_number = None
                        
                    # Use multiline_input function from main.py
                    from .main import multiline_input
                    print(f"{config.CYAN}Enter content:{config.RESET}")
                    content = multiline_input("", show_hint=True)
                    
                    op = {
                        "type": "insert",
                        "position": position,
                        "content": content
                    }
                    
                    if line_number is not None:
                        op["line_number"] = line_number
                        
                    operations.append(op)
                elif op_type == 'delete':
                    search = input("Text to delete: ").strip()
                    operations.append({
                        "type": "delete",
                        "search": search
                    })
                else:
                    print(f"{config.YELLOW}Unknown operation type: {op_type}{config.RESET}")
            
            if not operations:
                print(f"{config.YELLOW}No operations specified.{config.RESET}")
                continue
                
            requires_approval = input("Require approval before modifying? (y/n, default: y): ").strip().lower() != 'n'
            
            try:
                result = use_mcp_tool(
                    server_name="file-interaction",
                    tool_name="modify_file",
                    arguments={
                        "path": path,
                        "operations": operations,
                        "requires_approval": requires_approval
                    }
                )
                
                # Parse the result
                try:
                    data = json.loads(result)
                    if "error" in data:
                        print(f"{config.RED}Error: {data['error']}{config.RESET}")
                    else:
                        message = data.get("message", "")
                        
                        if data.get("requires_approval", False):
                            temp_path = data.get("temp_path", "")
                            print(f"{config.YELLOW}{message}{config.RESET}")
                            print(f"Temporary file created at: {temp_path}")
                            
                            # Show operation results
                            op_results = data.get("operations", [])
                            for i, op in enumerate(op_results):
                                success = op.get("success", False)
                                op_type = op.get("type", "unknown")
                                if success:
                                    print(f"{config.GREEN}Operation {i+1} ({op_type}): Success{config.RESET}")
                                else:
                                    error = op.get("error", "Unknown error")
                                    print(f"{config.RED}Operation {i+1} ({op_type}): Failed - {error}{config.RESET}")
                            
                            approve = input("Approve these modifications? (y/n): ").strip().lower() == 'y'
                            if approve:
                                # Move the temporary file to the target path
                                import os
                                import shutil
                                try:
                                    full_temp_path = os.path.join(os.getcwd(), temp_path)
                                    full_target_path = os.path.join(os.getcwd(), path)
                                    shutil.move(full_temp_path, full_target_path)
                                    print(f"{config.GREEN}File modified: {path}{config.RESET}")
                                except Exception as e:
                                    print(f"{config.RED}Error moving temporary file: {str(e)}{config.RESET}")
                            else:
                                # Delete the temporary file
                                import os
                                try:
                                    full_temp_path = os.path.join(os.getcwd(), temp_path)
                                    os.remove(full_temp_path)
                                    print(f"{config.YELLOW}Modification cancelled. Temporary file deleted.{config.RESET}")
                                except Exception as e:
                                    print(f"{config.RED}Error deleting temporary file: {str(e)}{config.RESET}")
                        else:
                            print(f"{config.GREEN}{message}{config.RESET}")
                            
                            # Show operation results
                            op_results = data.get("operations", [])
                            for i, op in enumerate(op_results):
                                success = op.get("success", False)
                                op_type = op.get("type", "unknown")
                                if success:
                                    print(f"{config.GREEN}Operation {i+1} ({op_type}): Success{config.RESET}")
                                else:
                                    error = op.get("error", "Unknown error")
                                    print(f"{config.RED}Operation {i+1} ({op_type}): Failed - {error}{config.RESET}")
                except json.JSONDecodeError:
                    print(f"{config.RED}Error parsing response: {result}{config.RESET}")
                except Exception as e:
                    print(f"{config.RED}Error processing response: {str(e)}{config.RESET}")
            except Exception as e:
                print(f"{config.RED}Error modifying file: {str(e)}{config.RESET}")
                
        elif cmd == 'delete':
            path = input("Enter file/directory path to delete: ").strip()
            if not path:
                print(f"{config.YELLOW}No path provided.{config.RESET}")
                continue
                
            requires_approval = input("Require approval before deleting? (y/n, default: y): ").strip().lower() != 'n'
            
            try:
                result = use_mcp_tool(
                    server_name="file-interaction",
                    tool_name="delete_file",
                    arguments={
                        "path": path,
                        "requires_approval": requires_approval
                    }
                )
                
                # Parse the result
                try:
                    data = json.loads(result)
                    if "error" in data:
                        print(f"{config.RED}Error: {data['error']}{config.RESET}")
                    else:
                        message = data.get("message", "")
                        
                        if data.get("requires_approval", False):
                            print(f"{config.YELLOW}{message}{config.RESET}")
                            item_type = data.get("type", "file")
                            size = data.get("size")
                            size_str = f" ({size} bytes)" if size is not None else ""
                            
                            approve = input(f"Approve deleting this {item_type}{size_str}? (y/n): ").strip().lower() == 'y'
                            if approve:
                                # Delete the file/directory
                                import os
                                import shutil
                                try:
                                    full_path = os.path.join(os.getcwd(), path)
                                    if os.path.isdir(full_path):
                                        shutil.rmtree(full_path)
                                    else:
                                        os.remove(full_path)
                                    print(f"{config.GREEN}{item_type.capitalize()} deleted: {path}{config.RESET}")
                                except Exception as e:
                                    print(f"{config.RED}Error deleting {item_type}: {str(e)}{config.RESET}")
                            else:
                                print(f"{config.YELLOW}Delete operation cancelled.{config.RESET}")
                        else:
                            print(f"{config.GREEN}{message}{config.RESET}")
                except json.JSONDecodeError:
                    print(f"{config.RED}Error parsing response: {result}{config.RESET}")
                except Exception as e:
                    print(f"{config.RED}Error processing response: {str(e)}{config.RESET}")
            except Exception as e:
                print(f"{config.RED}Error deleting file: {str(e)}{config.RESET}")
                
        elif cmd == 'search':
            path = input("Enter directory path to search (default '.'): ").strip() or '.'
            pattern = input("Enter regex pattern to search for: ").strip()
            if not pattern:
                print(f"{config.YELLOW}No search pattern provided.{config.RESET}")
                continue
                
            file_pattern = input("File pattern (default '*'): ").strip() or '*'
            recursive = input("Search recursively? (y/n, default: y): ").strip().lower() != 'n'
            context_lines = input("Number of context lines (default: 2): ").strip()
            try:
                context_lines = int(context_lines) if context_lines else 2
            except ValueError:
                print(f"{config.YELLOW}Invalid number. Using default: 2{config.RESET}")
                context_lines = 2
                
            try:
                result = use_mcp_tool(
                    server_name="file-interaction",
                    tool_name="search_files",
                    arguments={
                        "path": path,
                        "pattern": pattern,
                        "file_pattern": file_pattern,
                        "recursive": recursive,
                        "context_lines": context_lines
                    }
                )
                
                # Parse the result
                try:
                    data = json.loads(result)
                    if "error" in data:
                        print(f"{config.RED}Error: {data['error']}{config.RESET}")
                    else:
                        matches = data.get("matches", [])
                        print(f"{config.CYAN}Found matches in {len(matches)} files:{config.RESET}")
                        
                        for file_match in matches:
                            file_path = file_match.get("path", "")
                            file_matches = file_match.get("matches", [])
                            
                            print(f"\n{config.GREEN}File: {file_path} ({len(file_matches)} matches){config.RESET}")
                            
                            for i, match in enumerate(file_matches):
                                line_number = match.get("line_number", 0)
                                match_text = match.get("match", "")
                                context = match.get("context", [])
                                
                                print(f"\n{config.YELLOW}Match {i+1}: Line {line_number} - '{match_text}'{config.RESET}")
                                
                                for ctx in context:
                                    ctx_line = ctx.get("line_number", 0)
                                    ctx_content = ctx.get("content", "")
                                    is_match = ctx.get("is_match", False)
                                    
                                    if is_match:
                                        print(f"{config.RED}{ctx_line:4d}| {ctx_content}{config.RESET}")
                                    else:
                                        print(f"{ctx_line:4d}| {ctx_content}")
                except json.JSONDecodeError:
                    print(f"{config.RED}Error parsing response: {result}{config.RESET}")
                except Exception as e:
                    print(f"{config.RED}Error processing response: {str(e)}{config.RESET}")
            except Exception as e:
                print(f"{config.RED}Error searching files: {str(e)}{config.RESET}")
                
        elif cmd == 'mkdir':
            path = input("Enter directory path to create: ").strip()
            if not path:
                print(f"{config.YELLOW}No path provided.{config.RESET}")
                continue
                
            parents = input("Create parent directories if needed? (y/n, default: y): ").strip().lower() != 'n'
            requires_approval = input("Require approval before creating? (y/n, default: n): ").strip().lower() == 'y'
            
            try:
                result = use_mcp_tool(
                    server_name="file-interaction",
                    tool_name="create_directory",
                    arguments={
                        "path": path,
                        "parents": parents,
                        "requires_approval": requires_approval
                    }
                )
                
                # Parse the result
                try:
                    data = json.loads(result)
                    if "error" in data:
                        print(f"{config.RED}Error: {data['error']}{config.RESET}")
                    else:
                        message = data.get("message", "")
                        
                        if data.get("requires_approval", False):
                            print(f"{config.YELLOW}{message}{config.RESET}")
                            
                            approve = input("Approve creating this directory? (y/n): ").strip().lower() == 'y'
                            if approve:
                                # Create the directory
                                import os
                                try:
                                    full_path = os.path.join(os.getcwd(), path)
                                    if parents:
                                        os.makedirs(full_path, exist_ok=True)
                                    else:
                                        os.mkdir(full_path)
                                    print(f"{config.GREEN}Directory created: {path}{config.RESET}")
                                except Exception as e:
                                    print(f"{config.RED}Error creating directory: {str(e)}{config.RESET}")
                            else:
                                print(f"{config.YELLOW}Directory creation cancelled.{config.RESET}")
                        else:
                            print(f"{config.GREEN}{message}{config.RESET}")
                except json.JSONDecodeError:
                    print(f"{config.RED}Error parsing response: {result}{config.RESET}")
                except Exception as e:
                    print(f"{config.RED}Error processing response: {str(e)}{config.RESET}")
            except Exception as e:
                print(f"{config.RED}Error creating directory: {str(e)}{config.RESET}")
                
        else:
            print(f"{config.YELLOW}Unknown command: {cmd}{config.RESET}")
            print("Type 'exit' to return to command mode.")