from flask import Flask, request, jsonify
from flask_cors import CORS
import os
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

@app.route("/chat", methods=["POST"])
def chat():
    message = request.json.get("message")
    if not message:
        return jsonify({"error": "No message provided"}), 400

    try:
        # Use properly initialized chat_models
        response = chat_with_model(message, config, chat_models)
        return jsonify({"response": response})
    except Exception as e:
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
                'humidity': f"{current['humidity']}%",
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
@app.route("/configure_llm", methods=["POST"])
def configure_llm():
    """Configure the LLM provider and model for the session"""
    provider = request.json.get("provider")
    model = request.json.get("model")
    api_key = request.json.get("api_key")
    endpoint = request.json.get("endpoint")
    
    if not provider:
        return jsonify({"status": "error", "message": "Provider is required"}), 400
    
    try:
        # Update session model based on provider
        if provider == "ollama":
            config.session_model = "ollama"
            config.use_ollama = True
            config.use_claude = False
            config.use_groq = False
            if model:
                config.last_ollama_model = model
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
        global chat_models
        chat_models = initialize_chat_models(config)
        
        return jsonify({
            "status": "success", 
            "provider": provider,
            "session_model": config.session_model,
            "current_model": config.current_model if provider == "openai" else model
        })
        
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

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