import ollama
from ollama import Client

def test_ollama_connection():
    # Use the "localhost" directly with the port you confirmed works with curl
    host = 'http://localhost:11434'
    try:
        # Create an Ollama client instance with the specified host
        client = Client(host=host)
        # Sending a simple chat request to the Ollama server
        response = client.chat(
            model='llama2',
            messages=[{'role': 'user', 'content': 'Hello, Ollama!'}]
        )
        # Print the response from the server
        print("Response from Ollama:", response['message']['content'])
    except Exception as e:
        print("Failed to connect or send/receive with Ollama:", str(e))

if __name__ == "__main__":
    test_ollama_connection()
