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

def chat_with_model(message, config, chat_models, system_prompt=None):
    """Chat with the selected model.
    
    Args:
        message: The user's message
        config: Configuration object
        chat_models: Dictionary of initialized model clients
        system_prompt: Optional system prompt to override default
    """
    # Use provided system prompt or default
    if system_prompt is None:
        system_prompt = (
            "You are a helpful assistant with extensive programming knowledge that can either generate bash commands for tasks "
            "or provide direct responses. You have strong understanding of programming languages, frameworks, "
            "development practices, and system administration. For web browsing or information requests, provide "
            "a direct response. For system operations, generate runnable bash commands. For programming requests, "
            "provide complete, working solutions from your built-in knowledge. If web browser results are incomplete "
            "or unhelpful, rely on your built-in knowledge to solve the problem instead of getting stuck. "
            f"System info: {get_system_info()}"
        )
    
    # Use model based on session preference
    if config.session_model:
        try:
            if config.session_model == 'ollama' and 'model' in chat_models:
                return chat_with_ollama(message, chat_models['model'], system_prompt)
            elif config.session_model == 'groq' and 'model' in chat_models:
                return chat_with_groq(message, chat_models['model'], system_prompt)
            elif config.session_model == 'claude':
                return chat_with_claude(message, config, system_prompt)
        except Exception as e:
            print(f"Error using {config.session_model}: {e}")
    
    # Fallback to default model handlers if no session preference
    model_handlers = [
        ('ollama', lambda: config.use_ollama and 'model' in chat_models,
         lambda: chat_with_ollama(message, chat_models['model'], system_prompt)),
        ('groq', lambda: config.use_groq and 'model' in chat_models,
         lambda: chat_with_groq(message, chat_models['model'], system_prompt)),
        ('claude', lambda: config.use_claude,
         lambda: chat_with_claude(message, config, system_prompt))
    ]
    
    for model_name, check_enabled, handler in model_handlers:
        if check_enabled():
            try:
                return handler()
            except Exception as e:
                print(f"Error using {model_name}: {e}")
                continue
    
    # Final fallback to OpenAI
    return chat_with_openai(message, config, system_prompt)

def chat_with_ollama(message, ollama_client, system_prompt):
    try:
        # Use the running model if available, otherwise fallback to a default
        model = getattr(ollama_client, 'running_model', 'llama3.1:8b')
        
        # Check if the message contains JSON data from web browsing
        is_json_data = False
        json_prompt = ""
        
        if "browse_web" in message and any(domain in message for domain in ["news.ycombinator.com", "reddit.com", "github.com", "stackoverflow.com"]):
            # For web browsing with structured data, add special prompt instructions
            json_prompt = (
                "You are analyzing structured web content. "
                "The data provided is in JSON format and may be incomplete. "
                "Format your response as a clear summary of the key information. "
                "For news aggregators like Hacker News, list the important stories with their details. "
                "Always present information in a readable format, even if the JSON is truncated. "
                "IMPORTANT: If the web content isn't helpful or is incomplete, don't get stuck - " 
                "use your built-in knowledge to answer the original question instead. "
                "You have extensive programming knowledge and can solve most technical questions "
                "without relying on incomplete web data. The web content should SUPPLEMENT your knowledge, not REPLACE it."
            )
        
        # Combine system prompts if needed
        full_system_prompt = json_prompt + "\n\n" + system_prompt if json_prompt else system_prompt
        
        response = ollama_client.chat(
            model=model,
            messages=[
                {"role": "system", "content": full_system_prompt},
                {"role": "user", "content": message},
            ]
        )
        if 'message' in response and 'content' in response['message']:
            return response['message']['content']
        else:
            return "Unexpected response format."
    except Exception as e:
        return f"Error while chatting with Ollama: {e}"

def chat_with_groq(message, groq_client, system_prompt):
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

def chat_with_claude(message, config, system_prompt):
    anthropic_api_key = os.getenv("ANTHROPIC_API_KEY")
    if not anthropic_api_key:
        return "Anthropic API key missing."
    
    # Get the current model from config, default to opus if not specified
    model = config.models.get(config.current_model, "claude-3-opus-20240229")
    if not model.startswith("claude-"):  # If not a Claude model, use default
        model = "claude-3-opus-20240229"
    
    # Set headers based on model
    headers = {
        "x-api-key": anthropic_api_key,
        "content-type": "application/json",
        "anthropic-version": "2023-06-01"
    }
    
    # Check message size - Claude has a limit on input size
    if len(message) > 100000:
        # Truncate long messages to prevent API errors
        message = message[:100000] + "... [content truncated due to length]"
        print(f"Warning: Message truncated to 100K characters for Claude API.")
    
    # Check if message is JSON and handle specially
    if message.strip().startswith('{') or message.strip().startswith('['):
        try:
            # Try to parse and simplify JSON to reduce token usage
            json_data = json.loads(message)
            # Keep track of original message for fallback
            original_message = message
            
            # If it's a large JSON object, simplify it
            if isinstance(json_data, dict):
                # For browser content, extract the most relevant parts
                if "url" in json_data and "text_content" in json_data:
                    # It's likely a web page result
                    simplified_message = (
                        f"Web content from {json_data.get('url', 'unknown URL')}:\n\n"
                        f"Title: {json_data.get('title', 'No title')}\n\n"
                        f"Content: {json_data.get('text_content', '')[:50000]}"
                    )
                    message = simplified_message
            
            # If simplification failed or wasn't applicable, use the original but warn
            if message == original_message:
                print("Warning: Large JSON being sent to Claude API. This may cause token limit issues.")
        except json.JSONDecodeError:
            # Not valid JSON, leave as is
            pass
    
    # Claude API expects system in the top level, not as a message
    data = {
        "model": model,
        "max_tokens": 1024,
        "system": system_prompt,  # System prompt at the top level
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
    except requests.exceptions.HTTPError as e:
        error_msg = f"Error while chatting with Claude: {e}"
        
        # Check for specific error responses to provide better feedback
        if e.response is not None:
            try:
                error_json = e.response.json()
                if "error" in error_json:
                    error_type = error_json.get("error", {}).get("type", "")
                    error_message = error_json.get("error", {}).get("message", "")
                    
                    if "token" in error_message.lower() or "context_length" in error_type.lower():
                        return "The message is too long for Claude to process. Please try with a shorter query or different content."
                    elif "rate" in error_type.lower():
                        return "Rate limit exceeded for Claude API. Please try again in a few moments."
                    elif "credit" in error_message.lower():
                        return "Claude API credit balance is too low. Please check your Anthropic account."
                    # Handle specific formatting errors
                    elif "unexpected role" in error_message.lower():
                        # Try with an older API format as fallback
                        try:
                            fallback_data = {
                                "model": model,
                                "max_tokens": 1024,
                                "messages": [
                                    {"role": "user", "content": f"System instruction: {system_prompt}\n\nUser query: {message}"}
                                ]
                            }
                            fallback_response = requests.post(endpoint, headers=headers, data=json.dumps(fallback_data))
                            fallback_response.raise_for_status()
                            content_blocks = fallback_response.json().get('content', [])
                            return ' '.join(block['text'] for block in content_blocks if block['type'] == 'text')
                        except Exception as fallback_error:
                            return f"Claude API format error and fallback failed: {error_message}"
                    else:
                        return f"Claude API error: {error_message}"
            except (ValueError, AttributeError):
                pass  # Use the default error message if we can't parse the response
                
        return error_msg
    except requests.exceptions.RequestException as e:
        return f"Connection error while chatting with Claude: {e}"
    except Exception as e:
        return f"Unexpected error while chatting with Claude: {e}"

def chat_with_openai(message, config, system_prompt=None):
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
            "You are a helpful assistant with extensive programming knowledge that can either generate bash commands for tasks "
            "or provide direct responses. You have strong understanding of programming languages, frameworks, "
            "development practices, and system administration. For web browsing or information requests, provide "
            "a direct response. For system operations, generate runnable bash commands. For programming requests, "
            "provide complete, working solutions from your built-in knowledge. If web browser results are incomplete "
            "or unhelpful, rely on your built-in knowledge to solve the problem instead of getting stuck. "
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
        return chat_with_claude(message, config, system_prompt)

    endpoint = "https://api.openai.com/v1/chat/completions"

    try:
        response = requests.post(endpoint, headers=headers, data=json.dumps(data))
        response.raise_for_status()
        return response.json().get('choices', [{}])[0].get('message', {}).get('content', 'No response')
    except requests.exceptions.RequestException as e:
        return f"Error while chatting with OpenAI: {e}"
