import os
from dotenv import load_dotenv, set_key
from pathlib import Path

class Config:
    def __init__(self):
        self.CYAN = "\033[96m"
        self.YELLOW = "\033[93m"
        self.BOLD = "\033[1m"
        self.RESET = "\033[0m"
        self.RED = "\033[31m"
        self.GREEN = "\033[32m"

        self.current_model = os.getenv("DEFAULT_MODEL", "gpt-4o")
        self.api_key = os.getenv("OPENAI_API_KEY")
        self.server_port = int(os.getenv("SERVER_PORT", 5000))
        
        # Add these new attributes
        self.safe_mode = False
        self.autopilot_mode = False
        self.use_claude = False
        self.use_ollama = False
        self.use_groq = False
        self.scriptreviewer_on = False
        self.llm_suggestions = None
        self.last_response = None

        # Your models dictionary
        self.models = {
            "gpt-4o": "gpt-4o",
            "gpt4": "gpt-4",
            "gpt40613": "gpt-4-0613",
            "gpt432k0613": "gpt-4-32k-0613",
            "35turbo": "gpt-3.5-turbo",
            "gpt-3.5-turbo-0125": "gpt-3.5-turbo-0125",
            "gpt-4-32k-0613": "gpt-4-32k-0613",
            "gpt-4-turbo-preview": "gpt-4-turbo-preview",
            "gpt-4-vision-preview": "gpt-4-vision-preview",
            "dall-e-3": "dall-e-3",
            "o1-preview": "o1-preview"
        }

def initialize_config(args):
    config = Config()
    config.safe_mode = args.safe
    config.autopilot_mode = args.autopilot  # Corrected line
    config.use_claude = args.claude
    config.scriptreviewer_on = args.assistantsAPI
    config.use_ollama = args.ollama
    config.use_groq = args.groq
    return config
