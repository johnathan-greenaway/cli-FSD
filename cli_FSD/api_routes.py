from flask import Flask, request, jsonify
from flask_cors import CORS
from .chat_models import chat_with_model
from .configuration import Config

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

if __name__ == "__main__":
    app.run(port=config.server_port)