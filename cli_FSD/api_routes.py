from flask import Flask, request, jsonify
from flask_cors import CORS
from .chat_models import chat_with_model
from .configuration import Config
from .web_fetcher import fetcher

app = Flask(__name__)
CORS(app)

# Initialize config (you might want to pass this from your main application)
config = Config()

@app.route("/chat", methods=["POST"])
def chat():
    message = request.json.get("message")
    if not message:
        return jsonify({"error": "No message provided"}), 400

    try:
        # Assuming chat_with_model is accessible and properly configured
        response = chat_with_model(message, config, {})  # Empty dict for chat_models, adjust as needed
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
    from utils import get_system_info
    return jsonify(get_system_info())

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