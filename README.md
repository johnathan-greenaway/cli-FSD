# cli-FSD
Natural language driven autopilot for interfacing with your command line. 

A lightweight and portable autopilot utility for your CLI. Takes natural language as input and uses the OpenAI API to take the appropriate actions by generating and parsing shell scripts. Run '''safe mode.py''' to run as a terminal companion that creates, stored and asks permission to execute scripts incrementally to accomplish the user's request.

**Warning**: Giving LLMs shell-level access to your computer is dangerous and should only be done in sandbox or otherwise expendable environments. 

## Getting Started

### Prerequisites

- Python 3.10 (may work with earlier versions)
- Pip for Python package installation
- An OpenAI API key

### Installation

1. **Clone the repository:**

    ```bash
    git clone https://github.com/WazaCraft/cli-FSD
    cd cli-FSD
    ```

2. **Set up a Python virtual environment:**

    ```bash
    python -m venv venv
    ```

3. **Activate the virtual environment:**

    - On Windows:

        ```cmd
        .\venv\Scripts\activate
        ```

    - On Unix or MacOS:

        ```bash
        source venv/bin/activate
        ```

4. **Install the required Python packages:**

    ```bash
    pip install -r requirements.txt
    ```

    The `requirements.txt` file should include the following packages:

    ```
    Flask
    flask-cors
    python-dotenv
    requests
    ```

5. **Environment Variables: (optional)**

    Create a `.env` file in the project root directory and add your OpenAI API key and the server port (optional):

    ```
    OPENAI_API_KEY=your_openai_api_key_here
    SERVER_PORT=5000 # Optional: default is 5000
    ```

### Usage

- To start in companion mode in Terminal:

    ```bash
    python safe-mode.py
    ```

- To enable Autopilot from the start, use the `-autopilot on` argument:

    ```bash
    python safe-mode.py -autopilot on
    ```
    OR:

- To process a specific task using autopilot and bypass companion mode:

    ```bash
    python cli-FSD.py "Your task here"
    ```

- For additional options, you can enter `CMD` mode by typing `CMD` at any prompt.

### Flask Server

- To start the Flask server, enter `CMD` mode and type `server up`. The server listens on the port specified in your `.env` file or defaults to 5000.

### Contributing

Contributions to this project are welcome. Please fork the repository, make your changes, and submit a pull request for review.

## License

This project is licensed under the MIT License - see the [LICENSE.md](LICENSE.md) file for details.

## Acknowledgments

- OpenAI for providing the API used for generating chat responses.
- Flask and Flask-CORS for the web server functionality.
