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
        chat_models['model'] = initialize_ollama_client(config)
    elif config.session_model == 'groq':
        chat_models['model'] = initialize_groq_client()
    # Claude doesn't need initialization, handled in chat_with_claude
    
    return chat_models

def initialize_ollama_client(config):
    host = 'http://localhost:11434'
    try:
        client = OllamaClient(host=host)
        # Get running models
        response = requests.get(f"{host}/api/tags")
        if response.status_code == 200:
            models = response.json().get("models", [])
            if models:
                # Filter out known non-chat models
                chat_models = [m for m in models if not any(non_chat in m["name"].lower() for non_chat in 
                    ["embed", "nomic", "all-minilm", "bge", "e5"])]
                
                if chat_models:
                    running_model = chat_models[0]["name"]
                    print(f"Connected to Ollama at {host}. Using chat model: {running_model}")
                    # Store the running model on the client object
                    client.running_model = running_model
                    # Update last used model in config
                    config.last_ollama_model = running_model
                    config.save_preferences()
                    return client
                else:
                    print(f"Connected to Ollama at {host}, but no chat-capable models found. Will use last model: {config.last_ollama_model}")
                    # No chat model found, use the last known model from preferences
                    client.running_model = config.last_ollama_model
            else:
                print(f"Connected to Ollama at {host}, but no models found. Will use last model: {config.last_ollama_model}")
                client.running_model = config.last_ollama_model
        else:
            print(f"Connected to Ollama at {host}, but couldn't get models. Will use last model: {config.last_ollama_model}")
            client.running_model = config.last_ollama_model
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
    import threading
    from .utils import animated_loading
    
    # Check for routing information and apply enhanced prompts
    route_info = getattr(config, 'route_info', None)
    if route_info and system_prompt is None:
        # Use enhanced prompt based on routing decision
        from .query_router import QueryRouter
        router = QueryRouter()
        enhanced_prompt = router.get_enhanced_prompt(message, route_info)
        system_prompt = f"{enhanced_prompt}\n\nSystem info: {get_system_info()}"
    
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
    
    # Set up loading animation
    stop_event = threading.Event()
    
    # Choose different loading animations based on context
    if "browse_web" in message or "search" in message.lower():
        loading_message = "Browsing web"
        animation_frames = ["🌐 ", "🔍 ", "📡 ", "📊 ", "📰 "]
    elif "code" in message.lower() or "program" in message.lower():
        loading_message = "Generating code"
        animation_frames = ["⌨️ ", "💻 ", "🖥️ ", "📝 ", "🔧 "]
    elif "command" in message.lower() or "bash" in message.lower():
        loading_message = "Creating command"
        animation_frames = ["$ ", "# ", "> ", "│ ", "└─ "]
    else:
        loading_message = "Thinking"
        animation_frames = ["✨ ", "🧠 ", "💭 ", "🔮 ", "💫 "]
    
    # Start loading animation in a separate thread if not testing
    if not hasattr(config, 'testing') or not config.testing:
        loading_thread = threading.Thread(
            target=animated_loading,
            args=(stop_event, True, loading_message, 0.1),
            kwargs={"frames": animation_frames}
        )
        loading_thread.daemon = True
        loading_thread.start()
    
    result = None
    try:
        # Use model based on session preference
        if config.session_model:
            try:
                if config.session_model == 'ollama' and 'model' in chat_models:
                    result = chat_with_ollama(message, chat_models['model'], system_prompt, config)
                elif config.session_model == 'groq' and 'model' in chat_models:
                    result = chat_with_groq(message, chat_models['model'], system_prompt)
                elif config.session_model == 'claude':
                    result = chat_with_claude(message, config, system_prompt)
            except Exception as e:
                print(f"Error using {config.session_model}: {e}")
        
        # Fallback to default model handlers if no session preference or if session preference failed
        if result is None:
            model_handlers = [
                ('ollama', lambda: config.use_ollama and 'model' in chat_models,
                 lambda: chat_with_ollama(message, chat_models['model'], system_prompt, config)),
                ('groq', lambda: config.use_groq and 'model' in chat_models,
                 lambda: chat_with_groq(message, chat_models['model'], system_prompt)),
                ('claude', lambda: config.use_claude,
                 lambda: chat_with_claude(message, config, system_prompt))
            ]
            
            for model_name, check_enabled, handler in model_handlers:
                if check_enabled():
                    try:
                        result = handler()
                        break
                    except Exception as e:
                        print(f"Error using {model_name}: {e}")
                        continue
            
            # Only fall back to OpenAI if no specific model is configured
            if result is None and not any([config.use_ollama, config.use_groq, config.use_claude]):
                result = chat_with_openai(message, config, system_prompt)
            elif result is None:
                # If we have a specific model configured but it failed, return an error
                return f"Error: Failed to get response from configured model. Please check your configuration and try again."
        
        return result
    finally:
        # Stop the loading animation
        stop_event.set()
        if not hasattr(config, 'testing') or not config.testing:
            if loading_thread.is_alive():
                loading_thread.join(timeout=0.5)

def chat_with_ollama(message, ollama_client, system_prompt, config):
    try:
        # Use the running model if available, otherwise fallback to the last used model
        model = getattr(ollama_client, 'running_model', config.last_ollama_model)
        
        # Check if the message contains JSON data from web browsing
        is_json_data = False
        json_prompt = ""
        is_browse_request = False
        
        # Check if this is a browse request (we need to guide Ollama to use URLs)
        if any(term in message.lower() for term in ['browse', 'search', 'find', 'lookup', 'check website', 'go to website', 'go to site', 'check out']):
            is_browse_request = True
            
            # Extract any URLs from the message
            import re
            urls = re.findall(r'https?://(?:[-\w.]|(?:%[\da-fA-F]{2}))+', message)
            
            # If we found a URL, add instructions to use the browse_web tool
            if urls:
                browse_url_prompt = (
                    "The user wants you to browse the web for information. "
                    f"Use the browse_web tool with the URL: {urls[0]}. "
                    "Do not try to process the URL yourself. Instead, remember to pass the URL to the tool. "
                    "When showing the results, highlight the most important information clearly and concisely."
                )
                json_prompt += browse_url_prompt
            # If the user is asking to browse but didn't include a URL
            else:
                # Check for site names
                site_names = []
                if 'hacker news' in message.lower() or 'hackernews' in message.lower() or 'hn' in message.lower():
                    site_names.append("https://news.ycombinator.com/")
                if 'reddit' in message.lower():
                    site_names.append("https://www.reddit.com/")
                if 'github' in message.lower():
                    site_names.append("https://github.com/")
                
                if site_names:
                    browse_site_prompt = (
                        "The user wants you to browse a specific website. "
                        f"Use the browse_web tool with the URL: {site_names[0]}. "
                        "Do not try to process the URL yourself. Pass the URL to the tool."
                    )
                    json_prompt += browse_site_prompt
                else:
                    # General search request
                    browse_query = message.lower()
                    for term in ['browse', 'search', 'find', 'lookup', 'what is', 'how to']:
                        browse_query = browse_query.replace(term, '').strip()
                    
                    if browse_query:
                        search_prompt = (
                            "The user wants you to search for information. "
                            f"Use the browse_web tool with an appropriate search engine URL like: https://www.google.com/search?q={browse_query.replace(' ', '+')}. "
                            "Remember to pass the URL to the tool, do not try to process it yourself."
                        )
                        json_prompt += search_prompt
        
        # Check if the message contains JSON data from web browsing specific sites
        if "browse_web" in message and any(domain in message for domain in ["reddit.com", "github.com", "stackoverflow.com", "news.ycombinator.com"]):
            # For web browsing with structured data, add special prompt instructions
            web_handling_prompt = (
                "You are analyzing structured web content. "
                "The data provided is in JSON format. Focus on extracting and presenting the key information clearly. "
                "For news aggregators like Hacker News, list the important stories with their titles, points, and links. "
                "For Reddit, extract the main posts and their scores. "
                "For Stack Overflow, focus on the questions and answers. "
                "For GitHub, summarize repository information or search results. "
                "\n\nSteps to process this web content:\n"
                "1. Identify the type of content (news site, forum, documentation, etc.)\n"
                "2. Extract the most relevant sections and ignore boilerplate text\n"
                "3. Present information in a clear list format with headings and bullet points\n"
                "4. Include direct quotes when useful\n"
                "5. Always mention the source of information\n\n"
                "IMPORTANT: If you see JSON with an empty array '[]' or if the content seems incomplete, "
                "say 'The website content could not be properly retrieved' and try to answer from your knowledge instead."
            )
            json_prompt += web_handling_prompt
        
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
