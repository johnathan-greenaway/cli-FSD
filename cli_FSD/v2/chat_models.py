import os
import requests
import json
from ollama import Client as OllamaClient
from groq import Groq as GroqClient
from utils import get_system_info

def initialize_chat_models(config):
    chat_models = {}
    if config.use_ollama:
        chat_models['ollama'] = initialize_ollama_client()
    if config.use_groq:
        chat_models['groq'] = initialize_groq_client()
    return chat_models

def initialize_ollama_client():
    host = 'http://localhost:11434'
    try:
        client = OllamaClient(host=host)
        response = client.list()
        if response:
            print(f"Connected to Ollama at {host}.")
        else:
            print(f"Connected to Ollama at {host}, but no models found.")
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
    
    if config.use_ollama and 'ollama' in chat_models:
        return chat_with_ollama(message, chat_models['ollama'], system_info)
    elif config.use_groq and 'groq' in chat_models:
        return chat_with_groq(message, chat_models['groq'], system_info)
    elif config.use_claude:
        return chat_with_claude(message, config)
    else:
        return chat_with_openai(message, config)

def chat_with_ollama(message, ollama_client, system_info):
    system_prompt = (f"Generate bash commands for tasks. "
                     "Comment minimally, you are expected to produce code that is runnable. "
                     f"You are part of a chain. System info: {system_info}")
    try:
        response = ollama_client.chat(
            model='llama3',
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
        "x-api-key": f"{anthropic_api_key}",
        "Content-Type": "application/json",
        "Anthropic-Version": "2023-06-01"
    }
    data = {
        "model": "claude-3-opus-20240229",
        "system": "Generate bash commands for tasks. Comment minimally, you are expected to produce code that is runnable. You are part of a chain.",
        "messages": [
            {"role": "user", "content": message},
        ],
        "max_tokens": 4096,
        "temperature": 0.7
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
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {config.api_key}"
    }
    data = {
        "model": config.models[config.current_model],
        "messages": [
            {"role": "system", "content": "Generate bash commands for tasks. Comment minimally, you are expected to produce code that is runnable. You are part of a chain."},
            {"role": "user", "content": message}
        ]
    }
    endpoint = "https://api.openai.com/v1/chat/completions"

    try:
        response = requests.post(endpoint, headers=headers, data=json.dumps(data))
        response.raise_for_status()
        return response.json().get('choices', [{}])[0].get('message', {}).get('content', 'No response')
    except requests.exceptions.RequestException as e:
        return f"Error while chatting with OpenAI: {e}"