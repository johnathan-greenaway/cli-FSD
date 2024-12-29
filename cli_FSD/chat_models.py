import os
import requests
import json
from ollama import Client as OllamaClient
from groq import Groq as GroqClient
from .utils import get_system_info

def initialize_chat_models(config):
    chat_models = {}
    # Initialize based on session model preference
    if config.session_model == 'ollama':
        chat_models['model'] = initialize_ollama_client()
    elif config.session_model == 'groq':
        chat_models['model'] = initialize_groq_client()
    # Claude doesn't need initialization, handled in chat_with_claude
    
    return chat_models

def initialize_ollama_client():
    host = 'http://localhost:11434'
    try:
        client = OllamaClient(host=host)
        # Get running models
        response = requests.get(f"{host}/api/ps")
        if response.status_code == 200:
            models = response.json().get("models", [])
            if models:
                running_model = models[0]["name"]
                print(f"Connected to Ollama at {host}. Using running model: {running_model}")
                # Store the running model on the client object
                client.running_model = running_model
                return client
            else:
                print(f"Connected to Ollama at {host}, but no running models found.")
        else:
            print(f"Connected to Ollama at {host}, but couldn't get running models.")
        return client
    except Exception as e:
        print(f"Failed to connect to Ollama at {host}: {str(e)}")
    return None

def initialize_groq_client():
    groq_api_key = os.getenv("GROQ_API_KEY")
    if groq_api_key:
        try:
            groq_client = GroqClient(api_key=groq_api_key)
            print("Groq client initialized successfully.")
            return groq_client
        except Exception as e:
            print(f"Failed to initialize Groq client: {e}")
    else:
        print("Groq API key not found.")
    return None

def chat_with_model(message, config, chat_models):
    system_info = get_system_info()
    
    # Use model based on session preference
    if config.session_model:
        try:
            if config.session_model == 'ollama' and 'model' in chat_models:
                return chat_with_ollama(message, chat_models['model'], system_info)
            elif config.session_model == 'groq' and 'model' in chat_models:
                return chat_with_groq(message, chat_models['model'], system_info)
            elif config.session_model == 'claude':
                return chat_with_claude(message, config)
        except Exception as e:
            print(f"Error using {config.session_model}: {e}")
    
    # Fallback to default model handlers if no session preference
    model_handlers = [
        ('ollama', lambda: config.use_ollama and 'model' in chat_models,
         lambda: chat_with_ollama(message, chat_models['model'], system_info)),
        ('groq', lambda: config.use_groq and 'model' in chat_models,
         lambda: chat_with_groq(message, chat_models['model'], system_info)),
        ('claude', lambda: config.use_claude,
         lambda: chat_with_claude(message, config))
    ]
    
    for model_name, check_enabled, handler in model_handlers:
        if check_enabled():
            try:
                return handler()
            except Exception as e:
                print(f"Error using {model_name}: {e}")
                continue
    
    # Final fallback to OpenAI
    return chat_with_openai(message, config)

def chat_with_ollama(message, ollama_client, system_info):
    system_prompt = (f"Generate bash commands for tasks. "
                     "Comment minimally, you are expected to produce code that is runnable. "
                     f"You are part of a chain. System info: {system_info}")
    try:
        # Use the running model if available, otherwise fallback to a default
        model = getattr(ollama_client, 'running_model', 'llama3.1:8b')
        response = ollama_client.chat(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": message},
            ]
        )
        if 'message' in response and 'content' in response['message']:
            return response['message']['content']
        else:
            return "Unexpected response format."
    except Exception as e:
        return f"Error while chatting with Ollama: {e}"

def chat_with_groq(message, groq_client, system_info):
    system_prompt = (f"Generate bash commands for terminal tasks. "
                     "Comment minimally, you are expected to produce code that is runnable. "
                     f"You are part of a chain. System info: {system_info}")
    try:
        chat_completion = groq_client.chat.completions.create(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": message}
            ],
            model="mixtral-8x7b-32768",
        )
        return chat_completion.choices[0].message.content
    except Exception as e:
        return f"Error while chatting with Groq: {e}"

def chat_with_claude(message, config):
    anthropic_api_key = os.getenv("ANTHROPIC_API_KEY")
    if not anthropic_api_key:
        return "Anthropic API key missing."
    
    headers = {
        "x-api-key": anthropic_api_key,
        "content-type": "application/json",
        "anthropic-version": "2023-06-01"
    }
    
    # Get the current model from config, default to opus if not specified
    model = config.models.get(config.current_model, "claude-3-opus-20240229")
    if not model.startswith("claude-"):  # If not a Claude model, use default
        model = "claude-3-opus-20240229"
    
    data = {
        "model": model,
        "max_tokens": 1024,
        "messages": [
            {"role": "user", "content": message}
        ]
    }
    endpoint = "https://api.anthropic.com/v1/messages"
    
    try:
        response = requests.post(endpoint, headers=headers, data=json.dumps(data))
        response.raise_for_status()
        content_blocks = response.json().get('content', [])
        return ' '.join(block['text'] for block in content_blocks if block['type'] == 'text')
    except requests.exceptions.RequestException as e:
        return f"Error while chatting with Claude: {e}"

def chat_with_openai(message, config):
    if not config.api_key:
        return "OpenAI API key missing."

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {config.api_key}"
    }

    model = config.models.get(config.current_model)
    if not model:
        return f"Unknown model: {config.current_model}"

    # Base request data
    data = {
        "model": model,
        "messages": [
            {"role": "system", "content": "Generate bash commands for tasks. Comment minimally, you are expected to produce code that is runnable. You are part of a chain."},
            {"role": "user", "content": message}
        ]
    }

    # Add model-specific configurations
    if model.startswith("gpt-4o"):
        data["max_tokens"] = 16384  # Higher token limit for GPT-4o models
    elif model.startswith("o1"):
        data["max_tokens"] = 32768  # Higher token limit for o1 models
        data["reasoning_steps"] = "auto"  # Enable reasoning for o1 models

    endpoint = "https://api.openai.com/v1/chat/completions"

    try:
        response = requests.post(endpoint, headers=headers, data=json.dumps(data))
        response.raise_for_status()
        return response.json().get('choices', [{}])[0].get('message', {}).get('content', 'No response')
    except requests.exceptions.RequestException as e:
        return f"Error while chatting with OpenAI: {e}"
