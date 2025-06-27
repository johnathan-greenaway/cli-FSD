from flask import Flask, request, jsonify
from flask_cors import CORS
import os
import requests
from .chat_models import chat_with_model, initialize_chat_models
from .configuration import Config
from .web_fetcher import fetcher

app = Flask(__name__)
CORS(app, origins='*', 
     allow_headers=['Content-Type', 'Authorization'],
     methods=['GET', 'POST', 'OPTIONS'])

# Initialize config (you might want to pass this from your main application)
config = Config()
chat_models = initialize_chat_models(config)

def extract_keywords(query):
    """Extract meaningful keywords from natural language query"""
    import re
    
    # Remove common question words and phrases
    stop_words = {
        'what', 'do', 'you', 'know', 'about', 'tell', 'me', 'explain', 
        'describe', 'how', 'why', 'when', 'where', 'can', 'could', 
        'would', 'should', 'is', 'are', 'was', 'were', 'the', 'a', 
        'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for',
        'of', 'with', 'by', 'from', 'up', 'about', 'into', 'through',
        'during', 'before', 'after', 'above', 'below', 'between',
        'some', 'any', 'have', 'had', 'has', 'been', 'will', 'would'
    }
    
    # Special handling for reading-related queries
    reading_patterns = [
        (r"stories.*(?:i'?ve\s+)?read", ["stories", "read", "articles", "content"]),
        (r"reference\s+text", ["reference", "text", "content", "articles"]),
        (r"things.*(?:i'?ve\s+)?(?:read|seen|viewed)", ["content", "articles", "read"]),
        (r"content.*(?:i'?ve\s+)?(?:browsed|viewed|seen)", ["content", "articles", "browsed"]),
        (r"articles.*(?:i'?ve\s+)?read", ["articles", "read", "content"]),
        (r"what.*(?:i'?ve\s+)?(?:read|seen|viewed)", ["content", "articles", "read"])
    ]
    
    # Check for reading-related patterns first
    query_lower = query.lower()
    for pattern, fallback_terms in reading_patterns:
        if re.search(pattern, query_lower):
            print(f"DEBUG: Found reading pattern '{pattern}', using fallback terms: {fallback_terms}")
            # Try each fallback term individually for better matching
            return fallback_terms[0]  # Return the first/most specific term
    
    # Clean and tokenize
    cleaned_query = re.sub(r'[^\w\s]', '', query_lower)
    words = cleaned_query.split()
    
    # Filter out stop words and short words
    keywords = [word for word in words if word not in stop_words and len(word) > 2]
    
    # If we filtered out too much, fall back to original query
    if not keywords:
        return query
    
    # Join keywords with spaces for better matching
    return ' '.join(keywords)

def fetch_relevant_embeddings(query, max_results=5):
    """Fetch relevant embedded content from mem-aux service"""
    try:
        # Try original query first
        print(f"DEBUG: Searching embeddings for original query: '{query}'")
        response = requests.post('http://localhost:8000/search', 
                               json={
                                   'query': query,
                                   'top_k': max_results
                               }, 
                               timeout=5)
        
        results = []
        if response.ok:
            results = response.json().get('results', [])
            print(f"DEBUG: Found {len(results)} results for original query")
        
        # If no results, try with extracted keywords
        if not results:
            keywords = extract_keywords(query)
            if keywords != query:
                print(f"DEBUG: No results for original query, trying keywords: '{keywords}'")
                response = requests.post('http://localhost:8000/search', 
                                       json={
                                           'query': keywords,
                                           'top_k': max_results
                                       }, 
                                       timeout=5)
                if response.ok:
                    results = response.json().get('results', [])
                    print(f"DEBUG: Found {len(results)} results for keywords")
                
                # If still no results and it was a reading-related query, try broader terms
                if not results and any(pattern in query.lower() for pattern in ["reference", "stories", "read", "content"]):
                    broader_terms = ["content", "articles", "text", "read"]
                    for term in broader_terms:
                        print(f"DEBUG: Trying broader term: '{term}'")
                        response = requests.post('http://localhost:8000/search', 
                                               json={
                                                   'query': term,
                                                   'top_k': max_results
                                               }, 
                                               timeout=5)
                        if response.ok:
                            results = response.json().get('results', [])
                            if results:
                                print(f"DEBUG: Found {len(results)} results for broader term '{term}'")
                                break
        
        if results:
            context_text = "\n--- RELEVANT CONTEXT FROM YOUR READING HISTORY ---\n"
            for i, result in enumerate(results, 1):
                # Use more text for better context (1000 chars instead of 200)
                text = result.get('text', '')
                if len(text) > 1000:
                    text = text[:1000] + "..."
                context_text += f"{i}. {text}\n\n"
            context_text += "--- END CONTEXT ---\n\n"
            print(f"DEBUG: Returning {len(context_text)} chars of context")
            return context_text
        else:
            print("DEBUG: No results found in embeddings")
            return ""
            
    except Exception as e:
        print(f"DEBUG: Failed to fetch embeddings: {e}")
        return ""

@app.route("/chat", methods=["POST"])
def chat():
    
    message = request.json.get("message")
    use_embeddings = request.json.get("use_embeddings", True)
    requested_model = request.json.get("model")  # Get model from request
    
    if not message:
        return jsonify({"error": "No message provided"}), 400

    try:
        # Debug: Print current configuration
        print(f"DEBUG: session_model = {config.session_model}")
        print(f"DEBUG: use_ollama = {config.use_ollama}")
        print(f"DEBUG: use_claude = {config.use_claude}")
        print(f"DEBUG: use_groq = {config.use_groq}")
        print(f"DEBUG: current_model = {config.current_model}")
        print(f"DEBUG: requested_model = {requested_model}")
        print(f"DEBUG: chat_models keys = {list(chat_models.keys()) if chat_models else 'None'}")
        
        # If a specific model is requested and we're using Ollama, update the model
        if requested_model and config.session_model == 'ollama' and 'model' in chat_models:
            ollama_client = chat_models['model']
            if hasattr(ollama_client, 'running_model'):
                print(f"DEBUG: Updating Ollama model from {ollama_client.running_model} to {requested_model}")
                ollama_client.running_model = requested_model
                config.last_ollama_model = requested_model
        
        # Enhance message with relevant embeddings if available
        enhanced_message = message
        if use_embeddings:
            relevant_context = fetch_relevant_embeddings(message)
            if relevant_context:
                enhanced_message = f"{relevant_context}User Question: {message}"
                print(f"DEBUG: Enhanced message with {len(relevant_context)} chars of context")
        
        # Use properly initialized chat_models with enhanced message
        response = chat_with_model(enhanced_message, config, chat_models)
        
        # Include the actual model used in response
        actual_model = config.current_model
        if config.session_model == 'ollama' and 'model' in chat_models:
            ollama_client = chat_models['model']
            actual_model = getattr(ollama_client, 'running_model', config.last_ollama_model)
        
        return jsonify({
            "response": response,
            "model": actual_model,
            "used_embeddings": bool(use_embeddings and relevant_context)
        })
    except Exception as e:
        print(f"DEBUG: Chat error: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route("/save_file", methods=["POST"])
def save_file():
    file_path = request.json.get("file_path")
    content = request.json.get("content")
    
    if not file_path or not content:
        return jsonify({"error": "File path and content are required"}), 400

    try:
        with open(file_path, "w") as file:
            file.write(content)
        return jsonify({"status": "success", "message": f"File saved to {file_path}"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

# Additional route for getting system information
@app.route("/system_info", methods=["GET"])
def get_system_info():
    from .utils import get_system_info
    return jsonify(get_system_info())

@app.route("/weather", methods=["GET"])
def get_weather():
    try:
        import requests
        # Fetch weather from wttr.in
        response = requests.get('http://wttr.in/?format=j1', timeout=10)
        if response.status_code == 200:
            weather_data = response.json()
            current = weather_data['current_condition'][0]
            location = weather_data['nearest_area'][0]
            
            return jsonify({
                'location': f"{location['areaName'][0]['value']}, {location['country'][0]['value']}",
                'temperature': f"{current['temp_C']}°C",
                'condition': current['weatherDesc'][0]['value'],
                'wind': f"{current['windspeedKmph']} km/h {current['winddir16Point']}",
                'huammidity': f"{current['humidity']}%",
                'timestamp': current['observation_time']
            })
        else:
            return jsonify({'error': 'Weather service unavailable'}), 503
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# Additional route for toggling autopilot mode
@app.route("/toggle_autopilot", methods=["POST"])
def toggle_autopilot():
    config.autopilot_mode = not config.autopilot_mode
    return jsonify({"autopilot_mode": config.autopilot_mode})

# Additional route for changing the current model
@app.route("/change_model", methods=["POST"])
def change_model():
    new_model = request.json.get("model")
    if new_model in config.models:
        config.current_model = new_model
        return jsonify({"status": "success", "current_model": config.current_model})
    else:
        return jsonify({"status": "error", "message": "Invalid model"}), 400

# New route for configuring LLM provider
@app.route("/ollama_status", methods=["GET"])
def ollama_status():
    """Get current Ollama endpoint and model information"""
    
    try:
        if config.session_model == 'ollama' and 'model' in chat_models:
            ollama_client = chat_models['model']
            endpoint = getattr(config, 'ollama_endpoint', 'Unknown')
            model = getattr(ollama_client, 'running_model', 'Unknown')
            description = getattr(ollama_client, 'endpoint_description', 'Unknown')
            
            return jsonify({
                "status": "connected",
                "endpoint": endpoint,
                "model": model,
                "description": description,
                "session_model": config.session_model
            })
        else:
            return jsonify({
                "status": "not_configured",
                "session_model": config.session_model
            })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/configure_llm", methods=["POST"])
def configure_llm():
    """Configure the LLM provider and model for the session"""
    global chat_models
    
    provider = request.json.get("provider")
    model = request.json.get("model")
    api_key = request.json.get("api_key")
    endpoint = request.json.get("endpoint")
    
    if not provider:
        return jsonify({"status": "error", "message": "Provider is required"}), 400
    
    try:
        print(f"DEBUG: Configuring LLM - provider: {provider}, model: {model}")
        
        # Update session model based on provider
        if provider == "ollama":
            config.session_model = "ollama"
            config.use_ollama = True
            config.use_claude = False
            config.use_groq = False
            if model:
                config.last_ollama_model = model
                # If Ollama client exists, update its running model
                if 'model' in chat_models and hasattr(chat_models['model'], 'running_model'):
                    chat_models['model'].running_model = model
                    print(f"DEBUG: Updated Ollama client running_model to: {model}")
            print(f"DEBUG: Set Ollama config - session_model: {config.session_model}, use_ollama: {config.use_ollama}, model: {model}")
        elif provider == "openai":
            config.session_model = None  # Use OpenAI as default
            config.use_ollama = False
            config.use_claude = False
            config.use_groq = False
            if model and model in config.models:
                config.current_model = model
            # Note: API key handling should be done securely
            if api_key:
                os.environ["OPENAI_API_KEY"] = api_key
                config.api_key = api_key
        elif provider == "anthropic":
            config.session_model = "claude"
            config.use_claude = True
            config.use_ollama = False
            config.use_groq = False
            # Note: API key handling should be done securely
            if api_key:
                os.environ["ANTHROPIC_API_KEY"] = api_key
        elif provider == "groq":
            config.session_model = "groq"
            config.use_groq = True
            config.use_ollama = False
            config.use_claude = False
            if api_key:
                os.environ["GROQ_API_KEY"] = api_key
        else:
            return jsonify({"status": "error", "message": f"Unsupported provider: {provider}"}), 400
        
        # Save preferences
        config.save_preferences()
        
        # Reinitialize chat models with new configuration
        print(f"DEBUG: Reinitializing chat models with config: session_model={config.session_model}")
        chat_models = initialize_chat_models(config)
        print(f"DEBUG: Chat models after reinit: {list(chat_models.keys()) if chat_models else 'None'}")
        
        return jsonify({
            "status": "success", 
            "provider": provider,
            "session_model": config.session_model,
            "current_model": config.current_model if provider == "openai" else model
        })
        
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/models", methods=["GET"])
def get_models():
    """Get available models based on the current provider"""
    try:
        # If using Ollama, get models from Ollama
        if config.session_model == 'ollama':
            import requests
            
            # Try multiple Ollama endpoints
            ollama_endpoints = [
                'http://localhost:11434',
                'http://127.0.0.1:11434',
                'http://10.255.255.254:11434',
                'http://172.18.0.1:11434'
            ]
            
            for endpoint in ollama_endpoints:
                try:
                    response = requests.get(f"{endpoint}/api/tags", timeout=3)
                    if response.ok:
                        data = response.json()
                        models = []
                        for model in data.get('models', []):
                            if 'name' in model:
                                models.append(model['name'])
                        
                        return jsonify({
                            "models": models,
                            "current_model": config.last_ollama_model,
                            "session_model": config.session_model,
                            "provider": "ollama"
                        })
                except Exception as e:
                    continue
            
            # If all endpoints failed, return empty list
            return jsonify({
                "models": [],
                "current_model": config.last_ollama_model,
                "session_model": config.session_model,
                "provider": "ollama",
                "error": "Could not connect to Ollama"
            })
        else:
            # Return configured models for other providers
            models_list = list(config.models.keys())
            return jsonify({
                "models": models_list,
                "current_model": config.current_model,
                "session_model": config.session_model,
                "provider": config.session_model or "openai"
            })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/ollama/models", methods=["GET"])
def get_ollama_models():
    """Get available Ollama models directly from Ollama API"""
    try:
        import requests
        
        # Try multiple Ollama endpoints
        ollama_endpoints = [
            ('http://localhost:11434', 'Windows/Host Ollama'),
            ('http://127.0.0.1:11434', 'Local WSL Ollama'),
            ('http://10.255.255.254:11434', 'Windows via WSL bridge'),
            ('http://172.18.0.1:11434', 'Docker bridge')
        ]
        
        for endpoint, description in ollama_endpoints:
            try:
                response = requests.get(f"{endpoint}/api/tags", timeout=3)
                if response.ok:
                    data = response.json()
                    models = []
                    
                    for model in data.get('models', []):
                        if 'name' in model:
                            # Filter out non-chat models
                            model_name = model['name']
                            if not any(non_chat in model_name.lower() for non_chat in 
                                     ["embed", "nomic", "all-minilm", "bge", "e5"]):
                                models.append({
                                    "name": model_name,
                                    "size": model.get("size", 0),
                                    "modified": model.get("modified_at", ""),
                                    "digest": model.get("digest", "")
                                })
                    
                    return jsonify({
                        "models": models,
                        "endpoint": endpoint,
                        "description": description,
                        "current_model": config.last_ollama_model
                    })
            except Exception as e:
                print(f"Failed to connect to {description}: {e}")
                continue
        
        # If all endpoints failed
        return jsonify({
            "models": [],
            "error": "Could not connect to any Ollama endpoint"
        }), 503
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/fetch_web_content", methods=["POST"])
def fetch_web_content():
    """Fetch and process web content based on provided parameters.
    
    Expected JSON payload:
    {
        "url": "https://example.com",
        "mode": "basic|detailed|summary",
        "use_cache": true|false
    }
    """
    url = request.json.get("url")
    mode = request.json.get("mode", "basic")
    use_cache = request.json.get("use_cache", True)
    
    if not url:
        return jsonify({"error": "URL is required"}), 400
        
    if mode not in ["basic", "detailed", "summary"]:
        return jsonify({"error": "Invalid mode - must be one of: basic, detailed, summary"}), 400
    
    try:
        result = fetcher.fetch_and_process(url, mode, use_cache)
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e), "url": url}), 500

if __name__ == "__main__":
    app.run(port=config.server_port)