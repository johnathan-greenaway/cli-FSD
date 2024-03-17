import requests
import os
import time

class AssemblyAssist:
    def __init__(self, instructions="You are a helpful assistant.", name="Helpful Assistant"):
        self.api_key = os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            raise ValueError("OPENAI_API_KEY environment variable not set.")
        self.instructions = instructions
        self.name = name
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "OpenAI-Beta": "assistants=v1"
        }
        self.base_url = "https://api.openai.com/v1"
        self.assistant_id = None
        self.thread_id = None
        self.last_message_id = ""


    def api_request(self, method, endpoint, data=None):
        url = f"{self.base_url}/{endpoint}"
        response = requests.request(method, url, headers=self.headers, json=data)
        if response.status_code not in range(200, 300):
            print(f"API request failed with status code {response.status_code}: {response.text}")
            return None
        return response.json()

    def create_assistant(self):
        data = {
            "instructions": self.instructions,
            "name": self.name,
            "tools": [{"type": "code_interpreter"}],
            "model": "gpt-4"
        }
        response = self.api_request("POST", "assistants", data)
        self.assistant_id = response.get('id') if response else None
        return self.assistant_id


    def create_thread(self):
        response = self.api_request("POST", "threads")
        self.thread_id = response.get("id") if response else None
        return self.thread_id

    def add_message_to_thread(self, content):
        data = {"role": "user", "content": content}
        endpoint = f"threads/{self.thread_id}/messages"
        response = self.api_request("POST", endpoint, data)
        if not response:
            print("Failed to add message to thread.")
            return False
        return True

    def run_assistant(self):
        data = {"assistant_id": self.assistant_id}
        return self.api_request("POST", f"threads/{self.thread_id}/runs", data)

    def get_run_status(self, run_id):
        return self.api_request("GET", f"threads/{self.thread_id}/runs/{run_id}")

    def get_messages(self):
        response = self.api_request("GET", f"threads/{self.thread_id}/messages")
        if response:
            messages = response.get('data', [])
            new_messages = [m for m in messages if (not self.last_message_id or m['id'] > self.last_message_id) and m['role'] == 'assistant']
            return new_messages
        return []

    def delete_assistant(self):
        return self.api_request("DELETE", f"assistants/{self.assistant_id}")

    def wait_for_response(self, run_id):
        run_status = None
        while run_status != "completed":
            status_response = self.get_run_status(run_id)
            if not status_response:
                print("Failed to get run status.")
                return None
            run_status = status_response.get("status")
            if run_status in ["failed", "cancelled", "expired"]:
                print(f"Run ended with status: {run_status}")
                return None
            time.sleep(1)  # Polling interval
        
        print("Run completed. Waiting for the assistant's response...")
        while True:
            new_messages = self.get_messages()
            if new_messages:
                self.last_message_id = new_messages[-1]['id']
                for msg in new_messages:
                    if 'text' in msg['content'][0]:
                        return msg['content'][0]['text']['value']
                time.sleep(1)  # If no new text messages, wait and then check again
            else:
                print("Still waiting for the assistant's response...")
                time.sleep(1)

    def send_message(self, message):
        print(f"Debug: Sending this message to the assistant: '{message}'")  # Debugging line
        if not self.add_message_to_thread(message):
            raise Exception("Failed to add message to thread.")
        run_response = self.run_assistant()
        if not run_response:
            raise Exception("Failed to initiate run.")
        run_id = run_response.get("id")
        return self.wait_for_response(run_id)

    
    def end_conversation(self):
        if self.assistant_id:
            response = self.api_request("DELETE", f"assistants/{self.assistant_id}")
            if response and response.get("deleted"):
                print("Assistant deleted successfully.")
            else:
                print("Failed to delete the assistant.")
        else:
            print("No assistant to delete.")    
    
    def start_conversation(self):
        self.assistant_id = self.create_assistant()
        if not self.assistant_id:
            print("Failed to create assistant.") 
            return False
        self.thread_id = self.create_thread()
        if not self.thread_id:
            print("Failed to create thread.")
            return False
        print("Assistant created and thread initiated.")
        return True
    
# Testing block
if __name__ == "__main__":
#    api_key = *YOUR OPENAI_API_KEY*
    instructions = "You are a code debugging assistant. Provide debugging advice."  # Example instructions
    chatbot = AssemblyAssist(instructions)

    try:
        chatbot.start_conversation()
        while True:
            user_input = input("You: ")
            if user_input.lower() == "exit":
                break
            response = chatbot.send_message(user_input)
            print("Assistant:", response)
    finally:
        chatbot.end_conversation()