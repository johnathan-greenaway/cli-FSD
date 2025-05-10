"""CLI-FSD: A Full Self Drive Command Line Interface

This package provides a modular command-line interface with AI-powered capabilities.
It can be used as a standalone CLI or imported as a module in other applications.
"""

from .main import main
from .version import __version__
from .configuration import initialize_config
from .chat_models import initialize_chat_models, chat_with_model
from .agents.context_agent import ContextAgent
from .agents.web_content_agent import WebContentAgent
from .command_handlers import execute_shell_command
from .script_handlers import process_input_based_on_mode

# Package metadata
__name__ = "cli-FSD"
__author__ = "JG"

# Export core functionality for use as a module
__all__ = [
    'main',
    '__version__',
    'initialize_config',
    'initialize_chat_models',
    'chat_with_model',
    'ContextAgent',
    'WebContentAgent',
    'execute_shell_command',
    'process_input_based_on_mode'
]

# Example usage as a module:
"""
from cli_FSD import (
    initialize_config,
    initialize_chat_models,
    chat_with_model,
    ContextAgent,
    WebContentAgent,
    execute_shell_command,
    process_input_based_on_mode
)

# Initialize components
config = initialize_config()
chat_models = initialize_chat_models(config)
context_agent = ContextAgent()
web_agent = WebContentAgent()

# Process a command
response = process_input_based_on_mode("create a new file called test.txt", config, chat_models)

# Execute a shell command
result = execute_shell_command("ls -la", config.api_key, stream_output=True, safe_mode=True)

# Chat with the model
chat_response = chat_with_model("What is the weather like?", config, chat_models)
"""