import asyncio
from .utils import print_streamed_message
from .script_handlers import extract_script_from_response, assemble_final_script, auto_handle_script_execution

async def handle_command_mode(config, chat_models):
    while True:
        command = input(f"{config.GREEN}CMD>{config.RESET} ").strip().lower()
        if command == 'quit':
            break
        elif command == 'exit':
            await print_streamed_message(f"{config.CYAN}Exited command mode.{config.RESET}")
            break
        else:
            await process_command(command, config, chat_models)

async def process_command(command, config, chat_models):
    if command == 'reset':
        await reset_conversation()
        await print_streamed_message(f"{config.CYAN}The conversation has been reset.{config.RESET}")
    elif command == 'save':
        await save_last_response(config)
    elif command == 'autopilot':
        await toggle_autopilot(config)
    elif command == 'script':
        await handle_script_command(config)
    elif command == 'model':
        await change_model(config)
    elif command == 'list_models':
        await list_available_models(config)
    elif command == 'config':
        await show_current_config(config)
    else:
        await print_streamed_message(f"{config.YELLOW}Unknown command. Type 'exit' to return to normal mode.{config.RESET}")

async def reset_conversation():
    # This function should be implemented to reset the conversation history
    # If you're not maintaining conversation history, this can be a placeholder
    await print_streamed_message("Conversation reset functionality not implemented.")

async def save_last_response(config):
    file_path = input("Enter the file path to save the last response: ")
    try:
        with open(file_path, "w") as file:
            file.write(config.last_response)
        await print_streamed_message(f"Response saved to {file_path}")
    except Exception as e:
        await print_streamed_message(f"Error saving response: {e}")

async def toggle_autopilot(config):
    config.autopilot_mode = not config.autopilot_mode
    await print_streamed_message(f"Autopilot mode {'enabled' if config.autopilot_mode else 'disabled'}.")

async def handle_script_command(config):
    # Assuming last_response is stored somewhere in the config or globally
    last_response = "Last response placeholder"  # Replace with actual last response
    if last_response:
        scripts = extract_script_from_response(last_response)
        if scripts:
            final_script = await assemble_final_script(scripts, config.api_key)
            if final_script:
                await auto_handle_script_execution(final_script, config)
        else:
            await print_streamed_message("No script found in the last response.")
    else:
        await print_streamed_message("No last response to process.")

async def change_model(config):
    new_model = input("Enter the model to switch to: ")
    if new_model in config.models:
        config.current_model = new_model
        await print_streamed_message(f"Model switched to {config.current_model}")
    else:
        await print_streamed_message("Invalid model")

async def list_available_models(config):
    await print_streamed_message("Available models:")
    for model in config.models.keys():
        await print_streamed_message(model)

async def show_current_config(config):
    await print_streamed_message(f"Current configuration:")
    await print_streamed_message(f"Model: {config.current_model}")
    await print_streamed_message(f"Server Port: {config.server_port}")
    await print_streamed_message(f"Autopilot Mode: {'Enabled' if config.autopilot_mode else 'Disabled'}")
    await print_streamed_message(f"Safe Mode: {'Enabled' if config.safe_mode else 'Disabled'}")
    await print_streamed_message(f"Using Claude: {'Yes' if config.use_claude else 'No'}")
    await print_streamed_message(f"Using Ollama: {'Yes' if config.use_ollama else 'No'}")
    await print_streamed_message(f"Using Groq: {'Yes' if config.use_groq else 'No'}")
    await print_streamed_message(f"Script Reviewer: {'Enabled' if config.scriptreviewer_on else 'Disabled'}")
