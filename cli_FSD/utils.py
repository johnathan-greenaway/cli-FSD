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


def animated_loading(stop_event, use_emojis=True, message="Loading", interval=0.2):
    frames = ["🌑 ", "🌒 ", "🌓 ", "🌔 ", "🌕 ", "🌖 ", "🌗 ", "🌘 "] if use_emojis else ["- ", "\\ ", "| ", "/ "]
    while not stop_event.is_set():
        for frame in frames:
            if stop_event.is_set():
                break
            sys.stdout.write(f"\r{message} {frame}")
            sys.stdout.flush()
            time.sleep(interval)
    sys.stdout.write("\r" + " " * (len(message) + 4) + "\r")  # Clear the line


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
    try:
        response = requests.get('http://wttr.in/?format=3')
        if response.status_code == 200:
            return response.text
        else:
            return "Weather information is currently unavailable."
    except Exception as e:
        return "Failed to fetch weather information."


def display_greeting():
    today = date.today()
    last_run_file = ".last_run.txt"
    last_run = None

    if os.path.exists(last_run_file):
        with open(last_run_file, "r") as file:
            last_run = file.read().strip()
    
    with open(last_run_file, "w") as file:
        file.write(str(today))

    from . import configuration
    config = configuration.Config()
    
    if str(today) != last_run:
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
    else:
        # For returning users, just show a minimal reminder
        print(f"{GREEN}Tip: Use 'history', 'recall N', or 'session status' to manage your session{RESET}")

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
    # Import json at the function level to ensure it's always available
    import json
    
    try:
        import requests
        from bs4 import BeautifulSoup
        
        print(f"{CYAN}Using direct HTML scrape for Hacker News...{RESET}")
        
        # Fetch the page
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        page = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(page.content, 'html.parser')
        
        # Extract stories
        stories = []
        story_elements = soup.select('tr.athing')
        
        for i, story in enumerate(story_elements[:15]):  # Get top 15 stories
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
            
            # Format as plain text
            story_text = f"{i+1}. {title}"
            if source:
                story_text += f" ({source})"
            stories.append(story_text)
        
        # Build a simple text response
        response = "# Top Stories from Hacker News\n\n"
        response += "\n".join(stories)
        response += "\n\nSource: https://news.ycombinator.com/"
        
        return response
    except Exception as e:
        print(f"{YELLOW}Direct HTML scrape for Hacker News failed: {str(e)}{RESET}")
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
    # Ensure json module is available via top-level import

    # Import json at the very beginning of the function to ensure it's available everywhere
    import json
    
    # For browse_web operation, use different fetching strategies
    if tool_name == "browse_web" and "url" in arguments:
        url = arguments["url"]
        from urllib.parse import urljoin  # For resolving relative URLs
        
        # Special handling for Hacker News
        if "news.ycombinator.com" in url:
            try:
                # Direct HTML scrape approach for Hacker News
                import requests
                from bs4 import BeautifulSoup
                
                print(f"{CYAN}Using direct HTML scrape for Hacker News...{RESET}")
                
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
                    
                    # Add to our stories list
                    stories.append({
                        "type": "story",
                        "title": title,
                        "url": link,
                        "metadata": {
                            "source": source,
                            "score": score,
                            "comments": comments
                        },
                        "content": f"Source: {source}\nScore: {score}\nComments: {comments}"
                    })
                
                # Build a structured response
                hn_content = {
                    "type": "webpage",
                    "url": url,
                    "title": "Hacker News - Current Top Stories",
                    "content": []
                }
                
                # Add an intro section
                hn_content["content"].append({
                    "type": "section",
                    "title": "About Hacker News",
                    "blocks": [
                        {
                            "type": "text",
                            "text": "Hacker News is a social news website focusing on computer science and entrepreneurship, run by Y Combinator. The site features discussions and links to stories about technology, startups, and programming."
                        }
                    ]
                })
                
                # Add the stories
                for story in stories:
                    hn_content["content"].append(story)
                    
                return json.dumps(hn_content)
            except Exception as e:
                print(f"{YELLOW}Direct HTML scrape for Hacker News failed: {str(e)}{RESET}")
                # Fall through to standard methods if scraping fails
        
        # Standard WebContentFetcher for all sites (or as fallback)
        try:
            from .web_fetcher import fetcher
            # Try to use our efficient fetcher
            result = fetcher.fetch_and_process(url, mode="detailed", use_cache=True)
            if result:
                # Check if the result is empty or has minimal content
                if not result.get("text_content") or len(result.get("text_content", "").strip()) < 100:
                    print(f"{YELLOW}JSON result has minimal/empty content. Trying direct HTML scrape...{RESET}")
                    # Try direct HTML scrape for any site that returns empty JSON
                    try:
                        import requests
                        from bs4 import BeautifulSoup
                        
                        print(f"{CYAN}Using generic direct HTML scrape for {url}...{RESET}")
                        
                        # Fetch the page
                        headers = {
                            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
                        }
                        page = requests.get(url, headers=headers, timeout=10)
                        soup = BeautifulSoup(page.content, 'html.parser')
                        
                        # Get the title
                        title = soup.title.string.strip() if soup.title else url
                        
                        # Get main content - paragraphs and headings
                        main_content = []
                        for element in soup.find_all(['h1', 'h2', 'h3', 'p']):
                            text = element.get_text().strip()
                            if text and len(text) > 15:  # Skip very short snippets
                                main_content.append(text)
                        
                        # Extract links
                        links = []
                        for a in soup.find_all('a', href=True)[:10]:  # Limit to 10 links
                            href = a['href']
                            if not href.startswith(('http://', 'https://')):
                                href = urljoin(url, href)
                            
                            link_text = a.get_text().strip()
                            if link_text and href and len(link_text) > 3:
                                links.append({"text": link_text, "url": href})
                        
                        # Build a new result
                        new_result = {
                            "url": url,
                            "title": title,
                            "text_content": "\n\n".join(main_content),
                            "structured_content": [
                                {
                                    "type": "section",
                                    "title": "Page Content",
                                    "blocks": [{"text": content} for content in main_content]
                                }
                            ],
                            "links": links
                        }
                        return json.dumps(new_result)
                    except Exception as e:
                        print(f"{YELLOW}Generic direct HTML scrape failed: {str(e)}. Using original result.{RESET}")
                        
                # Return the standard JSON result if it has content
                return json.dumps(result)
        except Exception as e:
            # Log the exception for debugging
            print(f"WebFetcher error: {str(e)}", file=sys.stderr)
            # If our fetcher fails, continue with MCP tool
            pass
    
    try:
        import json
        import subprocess
        from pathlib import Path
        import os
        
        # Import json explicitly at this level
        import json
        
        # Try direct HTML scrape first for any site - as a general fallback
        try:
            # Check if url is defined - it won't be if we're not in browse_web operation
            if 'url' not in locals() and tool_name == "browse_web" and "url" in arguments:
                url = arguments["url"]
            elif 'url' not in locals():
                # Skip scraping if we don't have a URL
                raise ValueError("No URL available for scraping")
                
            import requests
            from bs4 import BeautifulSoup
            
            print(f"{CYAN}Trying direct HTML scrape for {url} as fallback method...{RESET}")
            
            # Fetch the page
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.5'
            }
            page = requests.get(url, headers=headers, timeout=10)
            soup = BeautifulSoup(page.content, 'html.parser')
            
            # Get the title
            title = soup.title.string.strip() if soup.title else url
            
            # Get main content - paragraphs and headings
            main_content = []
            for element in soup.find_all(['h1', 'h2', 'h3', 'p']):
                text = element.get_text().strip()
                if text and len(text) > 15:  # Skip very short snippets
                    main_content.append(text)
            
            # Build a structured response
            site_content = {
                "type": "webpage",
                "url": url,
                "title": title,
                "content": [
                    {
                        "type": "section",
                        "title": "Page Content",
                        "blocks": [
                            {
                                "type": "text",
                                "text": "\n\n".join(main_content[:15])  # Limit to 15 paragraphs
                            }
                        ]
                    }
                ]
            }
            
            # Special handling for Ollama model - simplify content
            try:
                # Check if we're serving an Ollama model (could add other local models here)
                is_local_model = "ollama" in server_name.lower() if server_name else False
                
                # If using Ollama, simplify the content even further to help parsing
                if is_local_model:
                    simplified_content = {
                        "url": url,
                        "title": title,
                        "content": "\n\n".join([
                            "WEBSITE CONTENT:",
                            f"Title: {title}",
                            "Main content:",
                            "\n".join([f"• {text[:200]}{'...' if len(text) > 200 else ''}" for text in main_content[:10]])
                        ])
                    }
                    return json.dumps(simplified_content)
            except Exception:
                # If any error in simplification, just use normal content
                pass
            
            # Return the directly scraped content
            return json.dumps(site_content)
        except Exception as e:
            print(f"{YELLOW}Final direct HTML scrape fallback failed: {str(e)}. Continuing with MCP tool...{RESET}")
            
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
                    try:
                        # Try to parse as JSON first
                        parsed = json.loads(content)
                        if isinstance(parsed, dict) and "content" in parsed:
                            return parsed["content"]
                        return content
                    except json.JSONDecodeError:
                        return content
                else:
                    return f"Error: Unexpected content format: {content}"
            return "Error: No result in response"
        except json.JSONDecodeError:
            return f"Error: Invalid JSON response from MCP server"
            
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
