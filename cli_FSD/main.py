# main.py

import argparse
import sys
import logging
import asyncio
from . import configuration
from .configuration import initialize_config
from .small_context.server import SmallContextServer
from .small_context.integration import LLMIntegration
from  .utils import cleanup_resources

from cli_FSD.utils import (
    print_instructions_once_per_day,
    display_greeting,
    cleanup_previous_assembled_scripts
)
from cli_FSD.chat_models import initialize_chat_models, initialize_chat_models_async
from cli_FSD.command_handlers import handle_command_mode
from cli_FSD.script_handlers import process_input_based_on_mode
from .script_handlers import handle_interactive_mode, process_input_based_on_mode, handle_script_cleanup

async def initialize_services(config):
    """Initialize required services."""
    small_context_server = SmallContextServer()
    llm_integration = LLMIntegration()
    
    # Initialize LLM integration first
    llm_integration = LLMIntegration()
    
    # Start small context server
    small_context_server = SmallContextServer()
    
    # Create event for server ready state
    ready_event = asyncio.Event()
    
    async def server_ready_callback():
        ready_event.set()
    
    # Start server with callback
    server_task = asyncio.create_task(small_context_server.start(ready_callback=server_ready_callback))
    
    try:
        # Wait for server to be ready
        await asyncio.wait_for(ready_event.wait(), timeout=5.0)
        print(f"{config.GREEN}Small context server initialized successfully{config.RESET}")
    except asyncio.TimeoutError:
        print(f"{config.YELLOW}Small context server initialization taking longer than expected...{config.RESET}")
        # Continue anyway as the server might still initialize
    except Exception as e:
        print(f"{config.RED}Failed to initialize small context server: {e}{config.RESET}")
        # Continue with degraded functionality
    
    return small_context_server, llm_integration

async def process_with_context(user_input: str, config, chat_models, llm_integration) -> str:
    """Process input with context management."""
    try:
        # Process with context
        context_result = await llm_integration.process_conversation(
            [{"role": "user", "content": user_input}]
        )
        
        # Get context if available
        context = context_result.get('context') if context_result else None
        
        # Process input with context
        result = await process_input_based_on_mode(
            user_input, 
            config, 
            chat_models,
            context=context
        )
        
        if result is None:
            # If no result, try processing as a direct command
            result = await process_input_based_on_mode(
                user_input,
                config,
                chat_models
            )
        
        return result
        
    except Exception as e:
        logging.error(f"Context processing error: {e}")
        # Fallback to direct processing
        return await process_input_based_on_mode(
            user_input,
            config,
            chat_models
        )



async def async_main():
    """Async main function that handles the core application logic."""
    try:
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
        chat_models = await initialize_chat_models_async(config)

        await handle_script_cleanup(config)
        
        # Initialize services
        try:
            small_context_server, llm_integration = await initialize_services(config)
        except Exception as e:
            logging.error(f"Failed to initialize services: {e}")
            print(f"{config.RED}Failed to initialize services: {e}{config.RESET}")
            return 1

        # Combine the query list into a single string
        query = ' '.join(args.query).strip()

        if query:
            try:
                # Process the input, which handles saving based on mode
                await process_input_based_on_mode(query, config, chat_models)
                logging.info(f"Processed query: {query}")
            except Exception as e:
                error_message = f"Error processing query '{query}': {e}"
                print(f"{config.RED}An error occurred while processing your query: {e}{config.RESET}")
                logging.error(error_message)
            return 0

        # If no query is provided, start the interactive loop
        await cleanup_previous_assembled_scripts()
        print_instructions_once_per_day()
        await display_greeting()

        while True:
            try:
                user_input = input(f"{config.YELLOW}@:{config.RESET} ").strip()
                sys.stdout.flush()  # Flush after input prompt

                if not user_input:
                    continue  # Skip empty inputs

                if user_input.lower() in ['exit', 'quit', 'q']:
                    print("\nExiting cli-FSD...")
                    break

                # Check for bare @ command first
                if user_input == '@':
                    await handle_interactive_mode(config, chat_models)
                    continue  # Continue main loop instead of breaking

                # Parse model selection flags if command starts with @
                elif user_input.startswith("@"):
                    # Get the command part after @
                    command = user_input[1:].strip()

                    # If command is empty or just whitespace, treat it like bare @
                    if not command:
                        await handle_interactive_mode(config, chat_models)
                        continue  # Continue main loop instead of breaking

                    # If command starts with a flag
                    elif command.startswith("-"):
                        try:
                            # Split into parts but preserve quoted strings
                            parts = []
                            current = []
                            in_quotes = False
                            for char in command:
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
                                chat_models = await initialize_chat_models_async(config)
                                if config.session_model:
                                    print(f"Using model: {config.session_model}")
                                else:
                                    print("Using default model settings")
                                if config.autopilot_mode:
                                    print("Autopilot mode enabled")
                                sys.stdout.flush()

                            # Reconstruct query preserving quotes
                            command = " ".join(parts[i:])
                            
                            # If no command after flags, enter interactive mode
                            if not command:
                                await handle_interactive_mode(config, chat_models)
                                continue  # Continue main loop instead of breaking
                            
                        except Exception as e:
                            print(f"{config.RED}Error parsing command: {str(e)}{config.RESET}")
                            sys.stdout.flush()
                            continue

                    # Process the command (we know it's not empty at this point)
                    if command.startswith("-"):
                        try:
                            # Split into parts but preserve quoted strings
                            parts = []
                            current = []
                            in_quotes = False
                            for char in command:
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
                                chat_models = await initialize_chat_models_async(config)
                                if config.session_model:
                                    print(f"Using model: {config.session_model}")
                                else:
                                    print("Using default model settings")
                                if config.autopilot_mode:
                                    print("Autopilot mode enabled")
                                sys.stdout.flush()

                            # Reconstruct query preserving quotes
                            command = " ".join(parts[i:])
                            
                            # If no command after flags, enter interactive mode
                            if not command:
                                await handle_interactive_mode(config, chat_models)
                                continue  # Continue main loop instead of breaking
                            
                        except Exception as e:
                            print(f"{config.RED}Error parsing command: {str(e)}{config.RESET}")
                            sys.stdout.flush()
                            continue

                    # Process the command
                    try:
                        config.last_response = await process_input_based_on_mode(
                            command,
                            config,
                            chat_models,
                            context=None
                        )
                        if config.last_response:
                            print(config.last_response)
                            sys.stdout.flush()
                        logging.info(f"Processed command: {command}")
                        continue  # Continue to next iteration after processing
                    except Exception as e:
                        error_message = f"Error processing command '{command}': {e}"
                        print(f"{config.RED}Error processing command: {e}{config.RESET}")
                        sys.stdout.flush()
                        logging.error(error_message)
                        continue

                else:
                    if user_input.upper() == 'CMD':
                        await handle_command_mode(config, chat_models)
                    elif user_input.lower() == 'safe':
                        config.safe_mode = True
                        config.autopilot_mode = False
                        config.save_preferences()
                        print("Switched to safe mode. You will be prompted before executing any commands.")
                        sys.stdout.flush()
                        logging.info("Switched to safe mode.")
                    elif user_input.lower() == 'autopilot':
                        config.safe_mode = False
                        config.autopilot_mode = True
                        config.save_preferences()
                        print("Switched to autopilot mode.")
                        sys.stdout.flush()
                        logging.info("Switched to autopilot mode.")
                    elif user_input.lower() == 'normal':
                        config.safe_mode = False
                        config.autopilot_mode = False
                        config.save_preferences()
                        print("Switched to normal mode.")
                        sys.stdout.flush()
                        logging.info("Switched to normal mode.")
                    else:
                        try:
                            # Process input with context management
                            config.last_response = await process_input_based_on_mode(
                                user_input,
                                config,
                                chat_models,
                                context=None
                            )
                            if config.last_response:
                                print(config.last_response)
                                sys.stdout.flush()
                            logging.info(f"Processed command: {user_input}")
                        except Exception as e:
                            error_message = f"Error processing command '{user_input}': {e}"
                            print(f"{config.RED}Error processing command: {e}{config.RESET}")
                            sys.stdout.flush()
                            logging.error(error_message)

                # Handle LLM suggestions if any
                if hasattr(config, 'llm_suggestions') and config.llm_suggestions:
                    print(f"{config.CYAN}Processing LLM suggestion:{config.RESET} {config.llm_suggestions}")
                    sys.stdout.flush()
                    try:
                        await process_input_based_on_mode(config.llm_suggestions, config, chat_models)
                        logging.info(f"Processed LLM suggestion: {config.llm_suggestions}")
                    except Exception as e:
                        error_message = f"Error processing LLM suggestion '{config.llm_suggestions}': {e}"
                        print(f"{config.RED}Error processing LLM suggestion: {e}{config.RESET}")
                        sys.stdout.flush()
                        logging.error(error_message)
                    config.llm_suggestions = None

            except (KeyboardInterrupt, EOFError):
                print("\nExiting cli-FSD...")
                logging.info("cli-FSD exited by user.")
                
                # Handle cleanup of assembled scripts
                await handle_script_cleanup(config)
                
                print("Goodbye!")
                break
            except Exception as e:
                logging.error(f"Error in main loop: {e}")
                print(f"{config.RED}Error: {e}{config.RESET}")
                sys.stdout.flush()
                continue

    except Exception as e:
        logging.error(f"Fatal error: {e}")
        print(f"{config.RED}Fatal error: {e}{config.RESET}")
        return 1
    finally:
        # Cleanup
        try:
            # Clean up chat models
            if 'chat_models' in locals() and chat_models:
                if hasattr(chat_models.get('model'), 'close'):
                    await chat_models['model'].close()
                    logging.info("Chat models cleaned up")

            # Clean up small context server
            if 'small_context_server' in locals():
                await small_context_server.stop()
                logging.info("Small context server stopped")
            
            # Handle script cleanup
            await handle_script_cleanup(config)
            logging.info("Script cleanup completed")
            
            # Handle general resource cleanup
            await cleanup_resources(config)
            logging.info("Resource cleanup completed")
            
            # Only print final goodbye message here
            logging.info("cli-FSD shutdown complete")
            print("Goodbye!")
        except Exception as e:
            logging.error(f"Error during cleanup: {e}")
    
    return 0

def main():
    """Synchronous entry point that runs the async main function."""
    try:
        exit_code = asyncio.run(async_main())
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\nExiting cli-FSD...")
        sys.exit(0)


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

if __name__ == "__main__":
    main()
