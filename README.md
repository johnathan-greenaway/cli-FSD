# cli-FSD
Natural language interface for your command line. 

A lightweight and portable autopilot utility for CLI tasks that takes natural language as input and uses the LLM of your choice to take the appropriate actions by generating and parsing shell scripts. Find answers to questions and let AI execute commands with your permission in Safe Mode or enable Autopilot to automate tasks or script modules and microservices on the fly. 

**Warning**: Giving LLMs shell-level access to your computer is dangerous and should only be done in sandbox or otherwise expendable environments.

##### I made cli-FSD for experimenting and problem solving in low stakes development environments. If you don't have access to a machine like that you can try it below: 

[![Open in GitHub Codespaces](https://github.com/codespaces/badge.svg)](https://github.com/codespaces/new?repo=wazacraft/cli-FSD&ref=main)

[![Run on Replit](https://replit.com/badge/github/wazacraft/cli-FSD)](https://replit.com/@wazacraft/cli-FSD)
## Getting Started

### Prerequisites

- Python 3.10 or later (may work with earlier versions)
- pip 24.0 or later 
- An OpenAI API key **or** Anthropic API key **or** Ollama running in the same environment as cli-FSD

### Installation

0. **Pre-requisites:**
   
- Upgrade pip

           python3 -m pip install --upgrade pip
    

**One line install using pip:**

    pip install cli-FSD

  (if you are testing the package, follow steps to setup and activate a virtual environment **before** running pip install.).

**Manual Installation**

1. **Clone the repo:**

    ```
    git clone https://github.com/WazaCraft/cli-FSD
    cd cli-FSD
    ```

2. **Set up a Python virtual environment:**

    ```
        python -m venv FSD
    ```

3. **Activate the virtual environment:**

    - On Windows:

        ```cmd
        .\FSD\Scripts\activate
        ```

    - On Unix or MacOS:

        ```bash
        source FSD/bin/activate
        ```

4. **Install the cli-FSD Python package:**

    ```bash
    pip install .
    ```
   
### Usage

- To start in safe-mode in your Terminal:

    ```bash
    @ what time is it -s
    ```

- To run in companion mode and process a specific task using autopilot type '@' from anywhere in your terminal followed by a command:

    ```bash
   @ what time is it
    ```

- For additional options, you can enter `CMD` mode by typing `CMD` at any prompt.

### Low-stakes Demos
Letting an LLM execute code on your computer is objectively dangerous. I've used cli-FSD on every computer I own but think it's important for users to understand the risk associated with this concept. 

If you don't want to run it locally:

[![Open in GitHub Codespaces](https://github.com/codespaces/badge.svg)](https://github.com/codespaces/new?repo=wazacraft/cli-FSD&ref=main)

[![Run on Replit](https://replit.com/badge/github/wazacraft/cli-FSD)](https://replit.com/@wazacraft/cli-FSD)

## Project Progress
v0.94
- [x] - Added support for [Ollama]([url](https://github.com/ollama/ollama)) (use -o to run cli-FSD using any supported local LLM model)
- [x] - support for script custom gpt-4-turbo assistant OpenAI's Assistants API to revie
v0.87
- [x] - finish OpenAI Assistants integration (done but but needs to be made accessible in main.py)
- [x] - integrate other LLM providers with http request APIs similar to /v1/completions (pass -c with your query to use Anthropic API's Claude 3 Opus)
- [x] - improved error handling 

v0.75
- [x] - overhauled and refactored error resolution function to address a bug that sometimes prevented the resolution from executing
- [x] - fixed niche text handling errors and submodule implementation for upcoming OpenAI AssistantsAPI integration
v0.52
- [x] - implement LLM error handling and resolution flows 
- [x] - refactor flags for SafeMode, Autopilot

### To Do
- [ ] - refactor and expand CMD module
- [x] for v0.8 - route requests to a custom gpt-4-turbo assistant with code interpreter access using OpenAI's Assistants API 
- [ ] - build advanced menu and config options

## Considering
- [ ] - passive error detection and resolution for CLI interactions
- [ ] - voice control
   - [ ] - voice notation
- [ ] - automation schedules and background states


### Contributing

Contributions to this project are welcome. Please fork the repository, make your changes, and submit a pull request for review.

Contributions to the main branch should aim to adhere to the project principles: 
- portable (I'm avoiding unnecessary dependencies whenever possible)
- utility focused



## License

This project is licensed under the GNU GPL - see the [LICENSE.md](LICENSE.md) file for details.

## Acknowledgments

- OpenAI for providing the API used for generating chat responses.
- Flask and Flask-CORS for the web server functionality.
