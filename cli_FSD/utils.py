import sys
import time
import platform
import requests
from datetime import datetime, date
import glob
import os
import re
import json

# Color constants
CYAN = "\033[96m"
YELLOW = "\033[93m"
BOLD = "\033[1m"
RESET = "\033[0m"
RED = "\033[31m"
GREEN = "\033[32m"


def animated_loading(stop_event, use_emojis=True, message="Loading", interval=0.2, frames=None):
    """
    Display an animated loading indicator while waiting for a process to complete.
    
    Args:
        stop_event: A threading.Event that signals when to stop the animation
        use_emojis: Whether to use emoji frames (True) or text frames (False)
        message: The message to display before the animation
        interval: Time between frame updates in seconds
        frames: Optional custom animation frames to use instead of defaults
    """
    # Default frames based on use_emojis setting, or use custom frames if provided
    if frames is None:
        if use_emojis:
            frames = ["🌑 ", "🌒 ", "🌓 ", "🌔 ", "🌕 ", "🌖 ", "🌗 ", "🌘 "]
        else:
            frames = ["- ", "\\ ", "| ", "/ "]
    
    # Begin animation loop
    while not stop_event.is_set():
        for frame in frames:
            if stop_event.is_set():
                break
            sys.stdout.write(f"\r{message} {frame}")
            sys.stdout.flush()
            time.sleep(interval)
    
    # Clear the line when animation stops
    sys.stdout.write("\r" + " " * (len(message) + 4) + "\r")  # Clear the line
    sys.stdout.flush()


def get_system_info():
    info = {
        'OS': platform.system(),
        'Version': platform.version(),
        'Machine': platform.machine(),
        'Processor': platform.processor(),
    }
    return ", ".join([f"{key}: {value}" for key, value in info.items()])


def print_instructions():
    from . import configuration
    config = configuration.Config()
    print(f"{GREEN}{BOLD}Terminal Companion with Full Self Drive Mode {config.SMALL_FONT}(v{config.VERSION}){RESET}")
    print(f"{GREEN}{BOLD}FSD is ON. {RESET}")
    print("Type 'CMD' to enter command mode and enter 'script' to save and run a script.")
    print("Type 'autopilot' in command mode to toggle autopilot mode on/off.")
    print(f"{YELLOW}--------------------------------------------------{RESET}")
    print(f"{RED}{BOLD}WARNING: Giving LLMs access to run shell commands is dangerous.{RESET}")
    print(f"{RED}{BOLD}Only use autopilot in sandbox environments.{RESET}")
    print(f"{YELLOW}--------------------------------------------------{RESET}")


def print_instructions_once_per_day():
    instructions_file = ".last_instructions_display.txt"
    current_date = datetime.now().date()

    try:
        if os.path.exists(instructions_file):
            with open(instructions_file, "r") as file:
                last_display_date_str = file.read().strip()
                try:
                    last_display_date = datetime.strptime(last_display_date_str, "%Y-%m-%d").date()
                    if last_display_date < current_date:
                        raise FileNotFoundError
                except ValueError:
                    raise FileNotFoundError
        else:
            raise FileNotFoundError
    except FileNotFoundError:
        with open(instructions_file, "w") as file:
            file.write(current_date.strftime("%Y-%m-%d"))
        print_instructions()


def print_streamed_message(message, color=CYAN, config=None):
    for char in message:
        print(f"{color}{char}{RESET}", end='', flush=True)
        time.sleep(0.03)
    print()
    
    # Mark that this response was streamed so we don't double-print it
    if config:
        config._response_was_streamed = True


def get_weather():
    """Get weather information for the user's location."""
    try:
        # First try to get location from IP
        location_response = requests.get('http://ip-api.com/json/', timeout=5)
        if location_response.status_code == 200:
            location_data = location_response.json()
            if location_data.get('status') == 'success':
                city = location_data.get('city', '')
                country = location_data.get('country', '')
                is_us = country == 'United States'
                
                # Get weather with more details
                weather_url = f'http://wttr.in/{city}?format=%l:+%c+%t+%w+%h'
                weather_response = requests.get(weather_url, timeout=5)
                
                if weather_response.status_code == 200:
                    weather_text = weather_response.text.strip()
                    
                    # If in US, add Fahrenheit
                    if is_us and '°C' in weather_text:
                        temp_c = float(weather_text.split('°C')[0].split()[-1])
                        temp_f = (temp_c * 9/5) + 32
                        weather_text = weather_text.replace('°C', f'°C ({temp_f:.1f}°F)')
                    
                    return weather_text
                
        # Fallback to simple format if detailed fetch fails
        response = requests.get('http://wttr.in/?format=3', timeout=5)
        if response.status_code == 200:
            return response.text
        else:
            return "Weather information is currently unavailable."
    except Exception as e:
        return "Failed to fetch weather information."


def display_greeting():
    from . import configuration
    config = configuration.Config()
    
    # Always show the full greeting
    weather = get_weather()
    system_info = get_system_info()
    print(f"{BOLD}Terminal Companion with Full Self Drive Mode {config.SMALL_FONT}(v{config.VERSION}){RESET}")
    print(f"{weather}")
    print(f"{system_info}")
    
    # Add decorated box for session commands
    box_width = 60
    print(f"\n{CYAN}╭─{'─' * box_width}╮{RESET}")
    print(f"{CYAN}│ {BOLD}{YELLOW}SESSION MANAGEMENT COMMANDS{' ' * (box_width - 27)}│{RESET}")
    print(f"{CYAN}├─{'─' * box_width}┤{RESET}")
    print(f"{CYAN}│ {GREEN}• history{RESET}{' ' * (box_width - 10)}│{RESET}")
    print(f"{CYAN}│   View list of past interactions{' ' * (box_width - 32)}│{RESET}")
    print(f"{CYAN}│ {GREEN}• recall N{RESET}{' ' * (box_width - 11)}│{RESET}")
    print(f"{CYAN}│   Display full content of history item N{' ' * (box_width - 40)}│{RESET}")
    print(f"{CYAN}│ {GREEN}• session status{RESET}{' ' * (box_width - 17)}│{RESET}")
    print(f"{CYAN}│   Show current session information{' ' * (box_width - 35)}│{RESET}")
    print(f"{CYAN}│ {GREEN}• set tolerance [strict|medium|lenient]{RESET}{' ' * (box_width - 39)}│{RESET}")
    print(f"{CYAN}│   Adjust how strictly responses are evaluated{' ' * (box_width - 46)}│{RESET}")
    print(f"{CYAN}╰─{'─' * box_width}╯{RESET}")
    print("\nWhat would you like to do today?")

    sys.stdout.flush()


def cleanup_previous_assembled_scripts():
    for filename in glob.glob(".assembled_script_*.sh"):
        try:
            os.remove(filename)
            print(f"Deleted previous assembled script: {filename}")
        except OSError as e:
            print(f"Error deleting file {filename}: {e}")


def clear_line():
    sys.stdout.write("\033[K")  # ANSI escape code to clear the line
    sys.stdout.flush()


def ask_user_to_retry():
    user_input = input("Do you want to retry the original command? (yes/no): ").lower()
    return user_input == "yes"


def print_message(sender, message):
    color = YELLOW if sender == "user" else CYAN
    prefix = f"{color}You:{RESET} " if sender == "user" else f"{color}Bot:{RESET} "
    print(f"{prefix}{message}")


def direct_scrape_hacker_news(url):
    """Direct HTML scraping specifically for Hacker News with simple text output."""
    try:
        import requests
        from bs4 import BeautifulSoup
        import json
        
        # Fetch the page
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5'
        }
        page = requests.get(url, headers=headers, timeout=10)
        page.raise_for_status()
        soup = BeautifulSoup(page.content, 'html.parser')
        
        # Extract stories
        stories = []
        story_elements = soup.select('tr.athing')
        
        for i, story in enumerate(story_elements[:15]):
            if i >= 15:  # Safety limit
                break
                
            # Get the title and link
            title_element = story.select_one('td.title > span.titleline > a')
            if not title_element:
                continue
                
            title = title_element.text.strip()
            link = title_element.get('href', '')
            
            # Skip empty titles
            if not title:
                continue
            
            # Make link absolute if it's relative
            if link and not link.startswith(('http://', 'https://')):
                if link.startswith('/'):
                    link = f"https://news.ycombinator.com{link}"
                else:
                    link = f"https://news.ycombinator.com/{link}"
                
            # Get the source/domain (if available)
            source = ''
            source_element = story.select_one('span.sitestr')
            if source_element:
                source = source_element.text.strip()
                
            # Find the next sibling row with score and comment info
            score = "Unknown score"
            comments = "0 comments"
            
            score_row = story.find_next_sibling('tr')
            if score_row:
                score_element = score_row.select_one('span.score')
                if score_element:
                    score = score_element.text.strip()
                    
                comments_element = score_row.select('a')
                for a in comments_element:
                    if 'comment' in a.text:
                        comments = a.text.strip()
                        break
            
            # Add to stories list
            stories.append({
                "type": "story",
                "title": title,
                "url": link,
                "metadata": {
                    "source": source,
                    "score": score,
                    "comments": comments
                }
            })
        
        # Build a structured response
        response = {
            "type": "webpage",
            "url": url,
            "title": "Hacker News - Current Top Stories",
            "content": [
                {
                    "type": "section",
                    "title": "About Hacker News",
                    "blocks": [
                        {
                            "type": "text",
                            "text": "Hacker News is a social news website focusing on computer science and entrepreneurship, run by Y Combinator. The site features discussions and links to stories about technology, startups, and programming."
                        }
                    ]
                }
            ]
        }
        
        # Add stories as sections
        for story in stories:
            response["content"].append({
                "type": "section",
                "title": story["title"],
                "blocks": [
                    {
                        "type": "text",
                        "text": f"Source: {story['metadata']['source']}\nScore: {story['metadata']['score']}\nComments: {story['metadata']['comments']}"
                    },
                    {
                        "type": "link",
                        "text": "Read more",
                        "url": story["url"]
                    }
                ]
            })
        
        return json.dumps(response)
    except Exception as e:
        print(f"Direct HTML scrape for Hacker News failed: {str(e)}")
        return None

def use_mcp_tool(server_name: str, tool_name: str, arguments: dict) -> str:
    """Use an MCP tool with the specified parameters.

    Args:
        server_name: Name of the MCP server
        tool_name: Name of the tool to use
        arguments: Tool arguments as a dictionary

    Returns:
        Tool execution result as a string
    """
    # Import necessary modules
    import json
    import os
    import sys
    import subprocess
    from pathlib import Path

    # For browse_web operation, use different fetching strategies
    if tool_name == "browse_web" and "url" in arguments:
        url = arguments["url"]
        from urllib.parse import urljoin  # For resolving relative URLs

        # Priority 1: Special handling for Hacker News
        if "news.ycombinator.com" in url:
            try:
                # Direct HTML scrape approach for Hacker News
                import requests
                from bs4 import BeautifulSoup

                print(f"{CYAN}Priority 1: Using direct HTML scrape for Hacker News...{RESET}")

                # Fetch the page
                headers = {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                }
                page = requests.get(url, headers=headers, timeout=10)
                soup = BeautifulSoup(page.content, 'html.parser')

                # Extract stories
                stories = []
                story_elements = soup.select('tr.athing')

                for story in story_elements[:20]:  # Get top 20 stories
                    # Get the title and link
                    title_element = story.select_one('td.title > span.titleline > a')
                    if not title_element:
                        continue

                    title = title_element.text.strip()
                    link = title_element.get('href', '')

                    # Make link absolute if it's relative
                    if link and not link.startswith(('http://', 'https://')):
                        if link.startswith('/'):
                            link = f"https://news.ycombinator.com{link}"
                        else:
                            link = f"https://news.ycombinator.com/{link}"

                    # Get the source/domain (if available)
                    source = ''
                    source_element = story.select_one('span.sitestr')
                    if source_element:
                        source = source_element.text.strip()

                    # Find the next sibling row with score and comment info
                    score = "Unknown score"
                    comments = "0 comments"

                    score_row = story.find_next_sibling('tr')
                    if score_row:
                        score_element = score_row.select_one('span.score')
                        if score_element:
                            score = score_element.text.strip()

                        comments_element = score_row.select('a')
                        for a in comments_element:
                            if 'comment' in a.text:
                                comments = a.text.strip()
                                break

                    # Add to our stories list as a simple markdown format
                    stories.append(f"## {title}")
                    stories.append(f"Source: {source}")
                    stories.append(f"Score: {score}")
                    stories.append(f"Comments: {comments}")
                    stories.append(f"[Read more]({link})")
                    stories.append("\n")

                # Build a simple text response instead of complex JSON
                response = "# Hacker News - Current Top Stories\n\n"
                response += "Hacker News is a social news website focusing on computer science and entrepreneurship, run by Y Combinator.\n\n"
                response += "\n".join(stories)

                print(f"{GREEN}Successfully scraped Hacker News directly.{RESET}")
                return response
            except Exception as e:
                print(f"{YELLOW}Direct HTML scrape for Hacker News failed: {str(e)}{RESET}")
                # Fall through to other methods

        # Priority 2: WebContentFetcher
        try:
            from .web_fetcher import fetcher
            print(f"{CYAN}Priority 2: Using WebContentFetcher for {url}...{RESET}")

            # Try to use our efficient fetcher with simplified output
            result = fetcher.fetch_and_process(url, mode="detailed", use_cache=True)

            if result:
                # Check if fetcher returned a dictionary
                if isinstance(result, dict):
                    # Create a simple markdown text response
                    title = result.get("title", "Web Content")
                    text_content = result.get("text_content", "")

                    # Format as markdown
                    simple_response = f"# {title}\n\nSource: {url}\n\n"

                    # Add main content
                    if text_content:
                        simple_response += text_content

                    # If there are structured elements, add them too
                    if structured_content := result.get("structured_content"):
                        for item in structured_content[:10]:  # Limit to first 10 items
                            if item.get("type") == "heading":
                                simple_response += f"\n\n## {item.get('text', '')}"
                            elif item.get("type") == "paragraph":
                                simple_response += f"\n\n{item.get('text', '')}"

                    # If there are links, add them
                    if links := result.get("links"):
                        simple_response += "\n\n## Related Links\n"
                        for link in links[:5]:  # Limit to first 5 links
                            if isinstance(link, dict) and "url" in link and "text" in link:
                                simple_response += f"- [{link['text']}]({link['url']})\n"

                    print(f"{GREEN}WebContentFetcher returned content for {url}{RESET}")
                    return simple_response

                # If not a dict, convert to string and return
                return str(result)
            else:
                print(f"{YELLOW}WebContentFetcher returned empty content for {url}{RESET}")
        except Exception as e:
            print(f"{YELLOW}WebContentFetcher failed: {str(e)}. Trying MCP tool...{RESET}")

        # Priority 3: MCP browser tool
        try:
            print(f"{CYAN}Priority 3: Using MCP browser tool for {url}...{RESET}")
            # Get MCP settings from config directory
            try:
                config_dir = Path(__file__).parent / "config_files"
                mcp_settings_file = config_dir / "mcp_settings.json"

                with open(mcp_settings_file) as f:
                    mcp_settings = json.load(f)
            except Exception as e:
                print(f"{RED}Error loading MCP settings: {str(e)}{RESET}")
                raise

            # Get server config
            server_config = mcp_settings["mcpServers"].get(server_name)
            if not server_config:
                print(f"{RED}Error: MCP server '{server_name}' not found in settings{RESET}")
                raise ValueError(f"MCP server '{server_name}' not found")

            # Format the MCP command
            mcp_command = {
                "jsonrpc": "2.0",
                "method": "call_tool",
                "params": {
                    "name": tool_name,
                    "arguments": arguments
                },
                "id": 1
            }

            # Build command with args from config
            cmd = [server_config["command"]] + server_config["args"]

            # Get the current working directory
            cwd = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

            # Set up environment for subprocess
            env = os.environ.copy()  # Copy current environment

            # Add any additional env settings from server_config
            if server_config.get("env"):
                env.update(server_config["env"])

            # Ensure PYTHONPATH includes site-packages
            python_path = env.get('PYTHONPATH', '').split(os.pathsep)
            site_packages = os.path.join(os.path.dirname(os.__file__), 'site-packages')
            if site_packages not in python_path:
                python_path.append(site_packages)
            env['PYTHONPATH'] = os.pathsep.join(filter(None, python_path))

            # Write command to stdin and read response from stdout
            process = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=env,  # Use our modified environment
                cwd=cwd  # Set the working directory
            )

            # Send command and get response
            stdout, stderr = process.communicate(input=json.dumps(mcp_command) + "\n")

            if stderr:
                print(f"{YELLOW}MCP server warning: {stderr}{RESET}", file=sys.stderr)

            try:
                response = json.loads(stdout)
                if "error" in response:
                    print(f"{RED}MCP server error: {response['error']['message']}{RESET}")
                    raise ValueError(response['error']['message'])
                if "result" in response:
                    content = response["result"].get("content")
                    if content:
                        print(f"{GREEN}MCP browser tool returned content for {url}{RESET}")

                        # If content is already a string, return it directly
                        if isinstance(content, str):
                            return content

                        # If content is a list, convert to a simple text format
                        if isinstance(content, list):
                            text_content = "\n\n".join([
                                block.get("text", "")
                                for block in content
                                if isinstance(block, dict) and block.get("type") == "text"
                            ])
                            if text_content:
                                return text_content

                        # If content is a dict, extract title and text
                        if isinstance(content, dict):
                            title = content.get("title", "Web Content")
                            text = content.get("text_content", "")
                            if not text and "content" in content:
                                if isinstance(content["content"], str):
                                    text = content["content"]

                            # Format as markdown
                            return f"# {title}\n\nSource: {url}\n\n{text}"

                        # For other types, just convert to string
                        return str(content)

                    print(f"{YELLOW}MCP browser tool returned empty content for {url}{RESET}")
                    return f"No content found for {url}"
                print(f"{YELLOW}MCP browser tool returned unexpected response format{RESET}")
                return f"Unexpected response format from {url}"
            except json.JSONDecodeError:
                print(f"{RED}MCP browser tool returned invalid JSON response{RESET}")
                return stdout  # Return the raw stdout if we can't parse it as JSON
        except Exception as e:
            print(f"{YELLOW}MCP browser tool failed: {str(e)}.{RESET}")
            return f"Unable to retrieve content from {url}: {str(e)}"

    # For all other tools (non-browse_web), use standard MCP approach
    try:
        # Get MCP settings from config directory
        try:
            config_dir = Path(__file__).parent / "config_files"
            mcp_settings_file = config_dir / "mcp_settings.json"

            with open(mcp_settings_file) as f:
                mcp_settings = json.load(f)
        except Exception as e:
            return f"Error loading MCP settings: {str(e)}"

        # Get server config
        server_config = mcp_settings["mcpServers"].get(server_name)
        if not server_config:
            return f"Error: MCP server '{server_name}' not found in settings"

        # Format the MCP command
        mcp_command = {
            "jsonrpc": "2.0",
            "method": "call_tool",
            "params": {
                "name": tool_name,
                "arguments": arguments
            },
            "id": 1
        }

        # Build command with args from config
        cmd = [server_config["command"]] + server_config["args"]

        # Get the current working directory
        cwd = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

        # Set up environment for subprocess
        env = os.environ.copy()  # Copy current environment

        # Add any additional env settings from server_config
        if server_config.get("env"):
            env.update(server_config["env"])

        # Ensure PYTHONPATH includes site-packages
        python_path = env.get('PYTHONPATH', '').split(os.pathsep)
        site_packages = os.path.join(os.path.dirname(os.__file__), 'site-packages')
        if site_packages not in python_path:
            python_path.append(site_packages)
        env['PYTHONPATH'] = os.pathsep.join(filter(None, python_path))

        # Write command to stdin and read response from stdout
        process = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=env,  # Use our modified environment
            cwd=cwd  # Set the working directory
        )

        # Send command and get response
        stdout, stderr = process.communicate(input=json.dumps(mcp_command) + "\n")

        if stderr:
            print(f"MCP server error: {stderr}", file=sys.stderr)
            return f"Error: {stderr}"

        try:
            response = json.loads(stdout)
            if "error" in response:
                return f"Error: {response['error']['message']}"
            if "result" in response:
                content = response["result"].get("content")
                if isinstance(content, list):
                    return "\n".join(
                        block["text"] for block in content
                        if block["type"] == "text"
                    )
                elif isinstance(content, str):
                    return content
                else:
                    return str(content)
            return "Error: No result in response"
        except json.JSONDecodeError:
            return stdout  # Return raw stdout if we can't parse as JSON

    except Exception as e:
        return f"Error using MCP tool: {str(e)}"
    
def save_script(query, script, file_extension="sh", auto_save=False, config=None):
    scripts_dir = "scripts"
    os.makedirs(scripts_dir, exist_ok=True)

    # Create a safe filename by replacing non-alphanumeric characters with underscores
    filename = re.sub(r'[^a-zA-Z0-9_-]', '_', query.lower()) + f".{file_extension}"
    filepath = os.path.join(scripts_dir, filename)

    if auto_save or (config and config.autopilot_mode):
        # Automatically save the script without prompting
        try:
            with open(filepath, 'w') as f:
                f.write(script + "\n")
            print(f"Script saved automatically to {filepath}")
            return filepath
        except Exception as e:
            if config:
                print(f"{config.RED}Failed to save script: {e}{config.RESET}")
            else:
                print(f"Failed to save script: {e}")
            return None
    else:
        # Prompt the user to save the script
        choice = input("Would you like to save this script? (yes/no): ").strip().lower()
        if choice in ['yes', 'y']:
            try:
                with open(filepath, 'w') as f:
                    f.write(script + "\n")
                print(f"Script saved to {filepath}")
                return filepath
            except Exception as e:
                if config:
                    print(f"{config.RED}Failed to save script: {e}{config.RESET}")
                else:
                    print(f"Failed to save script: {e}")
                return None
        else:
            print("Script not saved.")
            return None