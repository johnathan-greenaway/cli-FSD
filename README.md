# cli-FSD
Use natural language to interface with your command line. 

A lightweight and portable autopilot utility for your command line. Takes natural language as input and uses the OpenAI API to take the appropriate actions on your command line. Use safe mode to run Companion mode and creates .sh scripts incrementally to accomplish the users request.

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
    Flask==2.1.2
    flask-cors==3.0.10
    python-dotenv==0.20.0
    requests==2.27.1
    ```

5. **Environment Variables: (optional)**

    Create a `.env` file in the project root directory and add your OpenAI API key and the server port (optional):

    ```
    OPENAI_API_KEY=your_openai_api_key_here
    SERVER_PORT=5000 # Optional: default is 5000
    ```

### Usage

- To start the chatbot in Terminal:

    ```bash
    python <script-name>.py
    ```

- To enable Autopilot mode from the start, use the `-autopilot on` argument:

    ```bash
    python <script-name>.py -autopilot on
    ```

- To process a specific query at startup without entering the interactive mode:

    ```bash
    python <script-name>.py "Your query here"
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
