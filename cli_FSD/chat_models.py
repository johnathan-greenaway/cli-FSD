import os
import json
import asyncio
import aiohttp
from ollama import Client as OllamaClient
from groq import Groq as GroqClient
from .utils import get_system_info, print_immediate
import sys

async def initialize_chat_models_async(config):
    """Initialize chat models asynchronously."""
    chat_models = {}
    
    if config.session_model == 'ollama':
        chat_models['model'] = await initialize_ollama_client_async()
    elif config.session_model == 'groq':
        chat_models['model'] = await initialize_groq_client_async()
    # Claude doesn't need initialization, handled in chat_with_claude
    
    return chat_models

def initialize_chat_models(config):
    """Synchronous wrapper for async initialization."""
    loop = asyncio.get_event_loop()
    return loop.run_until_complete(initialize_chat_models_async(config))

async def initialize_ollama_client_async():
    """Initialize Ollama client asynchronously."""
    host = 'http://localhost:11434'
    try:
        client = OllamaClient(host=host)
        # Get running models using aiohttp
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{host}/api/ps") as response:
                if response.status == 200:
                    data = await response.json()
                    models = data.get("models", [])
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

async def initialize_groq_client_async():
    """Initialize Groq client asynchronously."""
    groq_api_key = os.getenv("GROQ_API_KEY")
    if groq_api_key:
        try:
            groq_client = GroqClient(api_key=groq_api_key)
            # Test connection asynchronously
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    "https://api.groq.com/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {groq_api_key}",
                        "Content-Type": "application/json"
                    },
                    json={
                        "messages": [{"role": "system", "content": "Test connection"}],
                        "model": "mixtral-8x7b-32768",
                        "max_tokens": 1
                    }
                ) as response:
                    if response.status == 200:
                        print("Groq client initialized successfully.")
                        return groq_client
                    else:
                        print(f"Failed to initialize Groq client: {await response.text()}")
        except Exception as e:
            print(f"Failed to initialize Groq client: {e}")
    else:
        print("Groq API key not found.")
    return None

async def chat_with_model(message, config, chat_models, system_prompt=None):
    """Chat with the selected model.
    
    Args:
        message: The user's message
        config: Configuration object
        chat_models: Dictionary of initialized model clients
        system_prompt: Optional system prompt to override default
    """
    from .utils import print_immediate, print_streamed_message
    
    print_immediate(f"\nProcessing request: {message}", config.CYAN)
    
    # Use provided system prompt or default
    if system_prompt is None:
        system_prompt = (
            "You are a helpful assistant that can either generate bash commands for tasks "
            "or provide direct responses. For web browsing or information requests, provide "
            "a direct response. For system operations, generate runnable bash commands. "
            f"System info: {get_system_info()}"
        )
    
    response = None
    # Use model based on session preference
    if config.session_model:
        try:
            if config.session_model == 'ollama' and 'model' in chat_models:
                response = await chat_with_ollama(message, chat_models['model'], system_prompt)
            elif config.session_model == 'groq' and 'model' in chat_models:
                response = await chat_with_groq(message, chat_models['model'], system_prompt)
            elif config.session_model == 'claude':
                response = await chat_with_claude(message, config, system_prompt)
            
            if response:
                # For command responses, print immediately
                if '```' in response:
                    print_immediate("\nGenerated command:", config.CYAN)
                    print_immediate(response, config.RESET)
                else:
                    # For regular responses, use streaming
                    print_immediate("\nReceived response:", config.CYAN)
                    await print_streamed_message(response, config.RESET)
                return response
                
        except Exception as e:
            print_immediate(f"\nError using {config.session_model}: {e}", config.RED)
    
    # Try each model handler in sequence
    for model_name, check_enabled, handler in [
        ('ollama', lambda: config.use_ollama and 'model' in chat_models,
         lambda: chat_with_ollama(message, chat_models['model'], system_prompt)),
        ('groq', lambda: config.use_groq and 'model' in chat_models,
         lambda: chat_with_groq(message, chat_models['model'], system_prompt)),
        ('claude', lambda: config.use_claude,
         lambda: chat_with_claude(message, config, system_prompt))
    ]:
        if check_enabled():
            try:
                print_immediate(f"\nTrying {model_name}...", config.CYAN)
                response = await handler()
                if response:
                    # For command responses, print immediately
                    if '```' in response:
                        print_immediate("\nGenerated command:", config.CYAN)
                        print_immediate(response, config.RESET)
                    else:
                        # For regular responses, use streaming
                        print_immediate(f"\nReceived response from {model_name}:", config.CYAN)
                        await print_streamed_message(response, config.RESET)
                    return response
            except Exception as e:
                print_immediate(f"\nError using {model_name}: {e}", config.RED)
                continue
    
    # Final fallback to OpenAI
    print_immediate("\nFalling back to OpenAI...", config.CYAN)
    try:
        response = await chat_with_openai(message, config, system_prompt)
        if response:
            # For command responses, print immediately
            if '```' in response:
                print_immediate("\nGenerated command:", config.CYAN)
                print_immediate(response, config.RESET)
            else:
                # For regular responses, use streaming
                print_immediate("\nReceived response from OpenAI:", config.CYAN)
                await print_streamed_message(response, config.RESET)
            return response
        else:
            print_immediate("\nNo response received from any model", config.RED)
            return None
    except Exception as e:
        print_immediate(f"\nError using OpenAI: {e}", config.RED)
        return None
    
async def chat_with_ollama(message, ollama_client, system_prompt):
    try:
        # Use the running model if available, otherwise fallback to a default
        model = getattr(ollama_client, 'running_model', 'llama3.1:8b')
        
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{ollama_client.base_url}/api/chat",
                json={
                    "model": model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": message},
                    ]
                },
                timeout=aiohttp.ClientTimeout(total=30)
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    if 'message' in data and 'content' in data['message']:
                        return data['message']['content']
                return "Unexpected response format."
    except Exception as e:
        return f"Error while chatting with Ollama: {e}"

async def chat_with_groq(message, groq_client, system_prompt):
    try:
        # Using aiohttp instead of the sync groq client
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "https://api.groq.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {groq_client.api_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": message}
                    ],
                    "model": "mixtral-8x7b-32768"
                },
                timeout=aiohttp.ClientTimeout(total=30)
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    return data['choices'][0]['message']['content']
                return f"Error: {response.status} - {await response.text()}"
    except Exception as e:
        return f"Error while chatting with Groq: {e}"

async def chat_with_claude(message, config, system_prompt):
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
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": message}
        ]
    }
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "https://api.anthropic.com/v1/messages",
                headers=headers,
                json=data,
                timeout=aiohttp.ClientTimeout(total=30)
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    content_blocks = data.get('content', [])
                    return ' '.join(block['text'] for block in content_blocks if block['type'] == 'text')
                return f"Error: {response.status} - {await response.text()}"
    except Exception as e:
        return f"Error while chatting with Claude: {e}"

async def chat_with_openai(message, config, system_prompt=None):
    if not config.api_key:
        return "OpenAI API key missing."

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {config.api_key}"
    }

    # Get model from config's models dictionary, fallback to gpt-4-turbo-preview
    model = config.models.get(config.current_model, "gpt-4-turbo-preview")
    
    # Use provided system prompt or default
    if system_prompt is None:
        system_prompt = (
            "You are a helpful assistant that can either generate bash commands for tasks "
            "or provide direct responses. For web browsing or information requests, provide "
            "a direct response. For system operations, generate runnable bash commands. "
            f"System info: {get_system_info()}"
        )
    
    data = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": message}
        ],
        "temperature": 0.7,
        "max_tokens": 4096  # Default token limit
    }

    # Add model-specific configurations
    if model.startswith("gpt-4"):
        data["max_tokens"] = 8192  # Higher token limit for GPT-4 models
    elif model.startswith("claude-"):
        # Claude models are handled by chat_with_claude
        return await chat_with_claude(message, config, system_prompt)

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "https://api.openai.com/v1/chat/completions",
                headers=headers,
                json=data,
                timeout=aiohttp.ClientTimeout(total=30)
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    return data.get('choices', [{}])[0].get('message', {}).get('content', 'No response')
                return f"Error: {response.status} - {await response.text()}"
    except Exception as e:
        return f"Error while chatting with OpenAI: {e}"
