# main.py

import argparse
import sys
import os
import logging
from datetime import datetime
from . import configuration
from .configuration import initialize_config
import readline
from .command_history import CommandHistory

from cli_FSD.utils import (
    print_instructions_once_per_day,
    display_greeting,
    cleanup_previous_assembled_scripts,
    direct_scrape_hacker_news
)
from cli_FSD.chat_models import initialize_chat_models, chat_with_model
from cli_FSD.command_handlers import (
    handle_command_mode, 
    handle_browse_command,
    execute_shell_command,
    get_user_confirmation
)
from cli_FSD.script_handlers import (
    process_input_based_on_mode,
    process_response,
    print_streamed_message,
    display_session_history,
    recall_history_item,
    display_session_status,
    format_browser_response
)

# Initialize response context
_response_context = {
    'browser_attempts': 0,
    'last_response': None,
    'last_operation': None,
    'last_url': None,
    'previous_responses': [],  # List of previous responses
    'collected_info': {},      # Information collected from various tools
    'tolerance_level': 'medium'  # Default tolerance level: 'strict', 'medium', 'lenient'
}

def main():
    # Configure logging
    logging.basicConfig(
        filename='cli_fsd.log',
        filemode='a',
        format='%(asctime)s - %(levelname)s - %(message)s',
        level=logging.WARNING
    )

    logging.info("cli-FSD started")

    # Initialize web fetcher early
    try:
        from .web_fetcher import fetcher
    except Exception as e:
        logging.error(f"Failed to initialize WebContentFetcher: {e}")
        print(f"Warning: WebContentFetcher initialization failed: {e}")

    args = parse_arguments()
    config = initialize_config(args)
    chat_models = initialize_chat_models(config)

    # Initialize command history
    command_history = CommandHistory()

    # Set up readline for query history
    readline.set_history_length(1000)

    def completer(text, state):
        """Query completer for fuzzy search."""
        if not text:
            return None

        # Get fuzzy matches from command history
        matches = command_history.fuzzy_search(text)
        if state < len(matches):
            return matches[state]
        return None

    # Set up readline completer
    readline.set_completer(completer)
    readline.parse_and_bind('tab: complete')
    readline.parse_and_bind('set show-all-if-ambiguous on')
    readline.parse_and_bind('set completion-ignore-case on')
    
    # Add key bindings for history navigation
    readline.parse_and_bind('"\e[A": history-search-backward')  # Up arrow
    readline.parse_and_bind('"\e[B": history-search-forward')   # Down arrow

    # Process command line arguments if provided
    # This handles direct commands like "@ visit example.com"
    if args.query and len(args.query) > 0:
        # Join the query arguments to form a single command
        direct_command = ' '.join(args.query)
        logging.info(f"Processing direct command: {direct_command}")

        try:
            # Special handling for browse/visit commands
            if direct_command.lower().startswith(('browse ', 'visit ')):
                from .script_handlers import process_input_based_on_mode as process_input_script_handlers
                result = process_input_script_handlers(direct_command, config)
                sys.exit(0)  # Exit after processing the direct command
            else:
                # Process other commands using the updated script_handlers version
                from .script_handlers import process_input_based_on_mode as process_input_script_handlers
                result = process_input_script_handlers(direct_command, config)
                sys.exit(0)  # Exit after processing the direct command
        except Exception as e:
            logging.error(f"Error processing direct command: {str(e)}")
            print(f"Error processing command: {str(e)}")
            sys.exit(1)

    # Display greeting for interactive mode
    display_greeting()

    while True:
        try:
            # Get user input with history navigation
            # Format the prompt with model and version
            model_display = config.current_model if hasattr(config, 'current_model') else 'default'
            prompt = f"{config.GREEN}{model_display}@{config.VERSION}{config.RESET} "
            user_input = multiline_input(prompt).strip()
            
            # Add query to history
            command_history.add_command(user_input)
            
            if not user_input:
                continue
                
            if user_input.upper() == 'CMD':
                handle_command_mode(config, chat_models)
            elif user_input.lower() == 'safe':
                config.safe_mode = True
                config.autopilot_mode = False
                config.save_preferences()
                print("Switched to safe mode. You will be prompted before executing any commands.")
                logging.info("Switched to safe mode.")
            elif user_input.lower() == 'autopilot':
                config.safe_mode = False
                config.autopilot_mode = True
                config.save_preferences()
                print("Switched to autopilot mode.")
                logging.info("Switched to autopilot mode.")
            elif user_input.lower() == 'normal':
                config.safe_mode = False
                config.autopilot_mode = False
                config.save_preferences()
                print("Switched to normal mode.")
                logging.info("Switched to normal mode.")
            else:
                if config.autopilot_mode:
                    from .script_handlers import process_input_based_on_mode as process_input_script_handlers, print_streamed_message
                    result = process_input_script_handlers(user_input, config)
                    print_streamed_message(result, config.CYAN)
                else:
                    from .script_handlers import process_input_based_on_mode as process_input_script_handlers, print_streamed_message
                    result = process_input_script_handlers(user_input, config)
                    print_streamed_message(result, config.CYAN)
                    
        except KeyboardInterrupt:
            print("\nExiting cli-FSD...")
            logging.info("cli-FSD exited by user.")
            
            # Handle cleanup of assembled scripts
            from .script_handlers import handle_script_cleanup
            handle_script_cleanup(config)
            
            print("Goodbye!")
            break
        except Exception as e:
            error_message = f"Error in main loop: {str(e)}"
            print(f"{config.RED}{error_message}{config.RESET}")
            logging.error(error_message)

    print("Operation completed.")
    logging.info("cli-FSD operation completed.")


def parse_arguments():
    parser = argparse.ArgumentParser(
        description="Terminal Companion with Full Self Drive Mode",
        formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("-s", "--safe", action="store_true", help="Run in safe mode")
    parser.add_argument("-a", "--autopilot", action="store_true", help="Enable autopilot mode")
    parser.add_argument("-c", "--claude", action="store_true", help="Use Claude for processing requests")
    parser.add_argument("-ci", "--assistantsAPI", action="store_true", help="Use OpenAI for error resolution")
    parser.add_argument("-o", "--ollama", action="store_true", help="Use Ollama for processing requests")
    parser.add_argument("-g", "--groq", action="store_true", help="Use Groq for processing requests")
    parser.add_argument("-d", "--default", action="store_true", help="Reset to default model settings")
    parser.add_argument("query", nargs=argparse.REMAINDER, help="User query to process directly")
    return parser.parse_args()

def process_input_based_on_mode(query, config, chat_models):
    """Process user input based on the current mode and query type."""
    import json
    from .agents.web_content_agent import WebContentAgent
    from .agents.context_agent import ContextAgent
    
    # Initialize agents
    web_agent = WebContentAgent()
    context_agent = ContextAgent()
    
    # Reset browser attempts counter for new queries
    _response_context['browser_attempts'] = 0
    
    # Check for session management commands
    if query.lower() == 'history':
        return display_session_history(config)
    elif query.lower().startswith('recall '):
        try:
            index = int(query.lower().replace('recall ', '').strip())
            return recall_history_item(config, index)
        except ValueError:
            print(f"{config.YELLOW}Please provide a valid index number.{config.RESET}")
            return "Invalid recall index. Use 'history' to see available items."
    elif query.lower() == 'session status':
        return display_session_status(config)
    
    # Check for browse/visit commands
    if query.lower().startswith(('browse ', 'visit ')):
        # First make sure the format_browser_response function is available
        from .script_handlers import format_browser_response, try_browser_search

        # Extract the target from the command
        target = query[7:].strip() if query.lower().startswith('browse ') else query[6:].strip()

        # Special handling for Hacker News
        if "hacker news" in target.lower() or "hn" in target.lower():
            print(f"{config.CYAN}Detected Hacker News request. Will prioritize accordingly.{config.RESET}")

            # Add more detailed debugging
            print(f"{config.GREEN}Using try_browser_search for Hacker News...{config.RESET}")

            # Skip try_browser_search for Hacker News and go directly to our reliable scraper
            # result = try_browser_search("hacker news", config, chat_models)

            # Just set result to None so we use the fallback
            result = None

            # Debug the result (skip if result is None)
            if result is not None:
                print(f"{config.YELLOW}Result type: {type(result).__name__}{config.RESET}")
                if isinstance(result, str):
                    print(f"{config.YELLOW}Result length: {len(result)} chars{config.RESET}")
                    print(f"{config.YELLOW}Result preview: {result[:100] if len(result) > 100 else result}{config.RESET}")

            # Force a direct Hacker News scrape for reliability
            print(f"{config.GREEN}Trying direct Hacker News scrape as a fallback...{config.RESET}")
            try:
                # Just output simple stories in markdown format for reliability
                stories = []
                stories.append("# Hacker News - Top Stories\n")
                stories.append("Hacker News is a social news website focusing on computer science and entrepreneurship, run by Y Combinator.\n")

                # Use beautiful soup for a very simple scrape
                import requests
                from bs4 import BeautifulSoup

                hn_url = "https://news.ycombinator.com/"
                headers = {'User-Agent': 'Mozilla/5.0'}

                page = requests.get(hn_url, headers=headers, timeout=10)
                soup = BeautifulSoup(page.content, 'html.parser')

                # Extract stories
                story_elements = soup.select('tr.athing')

                for i, story in enumerate(story_elements[:10]):  # Top 10 stories
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

                    # Get source domain if available
                    source = ""
                    source_element = story.select_one('span.sitestr')
                    if source_element:
                        source = f"Source: {source_element.text.strip()}\n"

                    # Try to get score and comments
                    score = "Unknown points"
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

                    # Add story to list
                    stories.append(f"## {title}\n")
                    if source:
                        stories.append(source)
                    stories.append(f"**{score}** | **{comments}**\n")
                    stories.append(f"[Read more]({link})\n")

                simple_result = "\n".join(stories)
                print_streamed_message(simple_result, config.CYAN, config)
                return simple_result

            except Exception as fallback_e:
                print(f"{config.RED}Fallback direct scrape failed: {str(fallback_e)}{config.RESET}")

                # If we have a result from try_browser_search, still try to use it
                if result:
                    try:
                        # If the result is already a string and not JSON, return it directly
                        if isinstance(result, str) and not (result.strip().startswith('{') and result.strip().endswith('}')):
                            print_streamed_message(result, config.CYAN, config)
                            return result

                        # Otherwise format the response
                        formatted_response = format_browser_response(target, result, config, chat_models)
                        print_streamed_message(formatted_response, config.CYAN, config)
                        return formatted_response
                    except Exception as e:
                        print(f"{config.RED}Error formatting Hacker News response: {str(e)}{config.RESET}")
                        # Return the raw result if formatting fails
                        if isinstance(result, str):
                            print_streamed_message(result, config.CYAN, config)
                            return result
                        return f"Error processing Hacker News content: {str(e)}"
                else:
                    return "Failed to fetch Hacker News content after multiple attempts. Please try again."
        
        # Use ContextAgent to analyze and execute other browse requests
        try:
            # Function already imported at the beginning of the function

            # Get the context agent's analysis
            context_analysis = context_agent.analyze_request(target)

            if not context_analysis or not isinstance(context_analysis, dict):
                print(f"{config.YELLOW}Failed to generate valid analysis from ContextAgent.{config.RESET}")
                return "Failed to analyze browse request. Please try again."

            # Create a tool selection for browsing
            tool_selection = {
                "tool_selection": {
                    "tool": "small_context",
                    "operation": "browse_web",
                    "parameters": {
                        "url": target
                    }
                }
            }

            # Execute the tool selection
            result = context_agent.execute_tool_selection(tool_selection)
            
            # Special handling for Hacker News
            if "news.ycombinator.com" in target:
                result = direct_scrape_hacker_news(target)
                if result:
                    try:
                        # Parse the JSON response
                        parsed_result = json.loads(result)
                        # Format the response
                        formatted_response = format_browser_response(target, result, config, chat_models)
                        print_streamed_message(formatted_response, config.CYAN)
                        return formatted_response
                    except Exception as e:
                        print(f"{config.RED}Error formatting Hacker News response: {str(e)}{config.RESET}")
                        return f"Error processing Hacker News content: {str(e)}"
                else:
                    # Fallback to standard processing if HN scraper fails
                    pass

            # Use MCP tool directly for browsing - prioritizing the small-context server
            try:
                from .utils import use_mcp_tool

                # Directly call the MCP browse_web tool
                print(f"{config.CYAN}Using MCP browse_web tool for {target}...{config.RESET}")
                mcp_result = use_mcp_tool(
                    server_name="small-context",
                    tool_name="browse_web",
                    arguments={"url": target}
                )

                if mcp_result:
                    try:
                        # Format and return the result
                        formatted_response = format_browser_response(target, mcp_result, config, chat_models)

                        # Always print the formatted response
                        print(f"{config.GREEN}Successfully formatted MCP browser response{config.RESET}")

                        if formatted_response and len(formatted_response) > 0:
                            print_streamed_message(formatted_response, config.CYAN, config)
                        else:
                            print(f"{config.RED}Empty formatted response{config.RESET}")

                        return formatted_response
                    except Exception as format_error:
                        print(f"{config.YELLOW}Error formatting MCP browser response: {str(format_error)}. Using raw response.{config.RESET}")
                        return mcp_result
                else:
                    # If MCP tool returns nothing, continue with normal execution
                    print(f"{config.YELLOW}MCP tool returned no result. Continuing with normal execution.{config.RESET}")
            except Exception as mcp_error:
                print(f"{config.YELLOW}MCP browse_web tool failed: {str(mcp_error)}. Continuing with normal execution.{config.RESET}")

            # Fall back to the original execution path
            if result and not result.get("error"):
                # Format and return the result
                formatted_response = format_browser_response(target, json.dumps(result), config, chat_models)

                # If the response is a string, print it directly
                if isinstance(formatted_response, str):
                    print_streamed_message(formatted_response, config.CYAN)
                # If it's a dict, format it nicely
                elif isinstance(formatted_response, dict):
                    if "content" in formatted_response:
                        print_streamed_message(formatted_response["content"], config.CYAN)
                    else:
                        print_streamed_message(json.dumps(formatted_response, indent=2), config.CYAN)
                return formatted_response
            else:
                error_msg = result.get("error", "Unknown error occurred") if result else "No result returned"
                print(f"{config.RED}Error executing browse: {error_msg}{config.RESET}")
                return f"Failed to browse {target}. Error: {error_msg}"
                
        except Exception as e:
            print(f"{config.RED}Error in browse command: {str(e)}{config.RESET}")
            return f"Error processing browse command: {str(e)}"
    
    # Use ContextAgent to analyze the request and determine which tool to use
    try:
        analysis = context_agent.analyze_request(query)
        
        # If the analysis is a direct response (no LLM processing needed)
        if not analysis.get("requires_llm_processing", True):
            if analysis.get("tool") == "command":
                command = analysis.get("command")
                description = analysis.get("description", "Execute command")
                if command:
                    # Show the command to the user
                    print(f"\n{description}:")
                    print(f"```bash\n{command}\n```")
                    
                    if config.autopilot_mode:
                        print(f"{config.CYAN}Executing command in autopilot mode...{config.RESET}")
                        result = execute_shell_command(command, config.api_key, stream_output=True, safe_mode=False)
                        if result.startswith("Error"):
                            print(f"{config.RED}{result}{config.RESET}")
                        else:
                            print(f"{config.GREEN}{result}{config.RESET}")
                        return result
                    else:
                        if get_user_confirmation(command, config):
                            result = execute_shell_command(command, config.api_key, stream_output=True, safe_mode=True)
                            if result.startswith("Error"):
                                print(f"{config.RED}{result}{config.RESET}")
                            else:
                                print(f"{config.GREEN}{result}{config.RESET}")
                            return result
                        return "Command execution cancelled by user."
            return "Error: Invalid direct response format."
        
        # Validate analysis object
        if not analysis or not isinstance(analysis, dict) or "prompt" not in analysis:
            # Fall back to direct LLM processing if analysis fails
            print(f"{config.YELLOW}Failed to generate valid analysis from ContextAgent.{config.RESET}")
            llm_response = chat_with_model(query, config, chat_models)
            final_response = process_response(query, llm_response, config, chat_models, allow_browser_fallback=True)
            print_streamed_message(final_response, config.CYAN)
            return final_response
        
        # Get LLM's tool selection decision with the analysis prompt
        llm_analysis = chat_with_model(analysis["prompt"], config, chat_models)
        
        try:
            # Use improved JSON extraction from script_handlers
            from .script_handlers import extract_json_from_response
            json_content = extract_json_from_response(llm_analysis)
            if json_content:
                result = json.loads(json_content)
            else:
                # Fall back to simple cleaning
                cleaned_response = llm_analysis.replace("```json", "").replace("```", "").strip()
                result = json.loads(cleaned_response)
        except json.JSONDecodeError:
            print(f"{config.YELLOW}Failed to parse LLM analysis response.{config.RESET}")
            print(f"\n{config.CYAN}Raw LLM response for debugging:{config.RESET}")
            print(f"```json\n{llm_analysis}\n```")
            
            # Show extracted JSON if available for debugging
            from .script_handlers import extract_json_from_response
            extracted_json = extract_json_from_response(llm_analysis)
            if extracted_json:
                print(f"\n{config.CYAN}Extracted JSON content:{config.RESET}")
                print(f"```json\n{extracted_json}\n```")
            
            return "Error: Could not parse tool selection response."
        
        # Handle different tool types
        if result.get("tool") == "web_content":
            # Use web content agent with our updated prioritization
            if result.get("operation") in ["fetch", "browse", "search"]:
                # For browse/search operations, use our specialized function for better prioritization
                if result.get("operation") in ["browse", "search"]:
                    # Import both needed functions at once
                    from .script_handlers import try_browser_search, format_browser_response

                    # For browse operations, use the URL directly
                    if result.get("operation") == "browse" and "url_or_query" in result:
                        print(f"{config.CYAN}Using specialized browser search for URL: {result['url_or_query']}{config.RESET}")
                        browser_result = try_browser_search(result['url_or_query'], config, chat_models)

                        # Format the response if needed
                        if browser_result:
                            # If already a string, just return it
                            if isinstance(browser_result, str):
                                # If it's a JSON string, try to format it
                                if browser_result.strip().startswith('{') and browser_result.strip().endswith('}'):
                                    try:
                                        formatted_response = format_browser_response(result['url_or_query'], browser_result, config, chat_models)
                                        print_streamed_message(formatted_response, config.CYAN, config)
                                        return formatted_response
                                    except Exception as e:
                                        print(f"{config.RED}Error formatting browser response: {str(e)}{config.RESET}")
                                        return browser_result
                                # Otherwise just print it directly
                                print_streamed_message(browser_result, config.CYAN, config)
                                return browser_result
                        else:
                            error_msg = f"Failed to browse {result['url_or_query']}"
                            print(f"{config.RED}{error_msg}{config.RESET}")
                            return error_msg

                    # For search operations, use the query
                    elif result.get("operation") == "search" and "url_or_query" in result:
                        print(f"{config.CYAN}Using specialized browser search for query: {result['url_or_query']}{config.RESET}")
                        browser_result = try_browser_search(result['url_or_query'], config, chat_models)

                        # Format and return the response
                        if browser_result:
                            try:
                                formatted_response = format_browser_response(result['url_or_query'], browser_result, config, chat_models)
                                print_streamed_message(formatted_response, config.CYAN, config)
                                return formatted_response
                            except Exception as e:
                                print(f"{config.RED}Error formatting browser response: {str(e)}{config.RESET}")
                                print_streamed_message(browser_result, config.CYAN, config)
                                return browser_result
                        else:
                            error_msg = f"Failed to search for {result['url_or_query']}"
                            print(f"{config.RED}{error_msg}{config.RESET}")
                            return error_msg

                # Fall back to standard web_agent for other operations
                response = web_agent.execute_command(f"{result['operation']} {result['url_or_query']} {result.get('mode', 'basic')}")
                if response.get("error"):
                    print(f"{config.RED}Error: {response['error']}{config.RESET}")
                    return f"Error: {response['error']}"

                # Update context with the response
                context_agent.update_context(result['operation'], response)

                # Format the response if needed
                if isinstance(response, dict) and not response.get("error"):
                    formatted_response = format_browser_response(result.get('url_or_query', 'query'), response, config, chat_models)
                    print_streamed_message(formatted_response, config.CYAN, config)
                    return formatted_response
                return response
                
        elif result.get("tool") == "file_operation":
            # Use file operations
            operation = result.get("operation")
            filepath = result.get("filepath")
            content = result.get("content", "")
            description = result.get("description", "Perform file operation")
            
            if not filepath:
                print(f"{config.RED}Error: No filepath specified for file operation{config.RESET}")
                return "Error: No filepath specified"
            
            # Show the operation to the user
            print(f"\n{description}:")
            print(f"File: {filepath}")
            
            if operation == "write":
                # Create directory if it doesn't exist
                os.makedirs(os.path.dirname(filepath), exist_ok=True)
                
                # Write the content to the file
                try:
                    with open(filepath, 'w') as f:
                        f.write(content)
                    print(f"{config.GREEN}Successfully created file: {filepath}{config.RESET}")
                    return f"Created file: {filepath}"
                except Exception as e:
                    error_msg = f"Error writing to file: {str(e)}"
                    print(f"{config.RED}{error_msg}{config.RESET}")
                    return error_msg
            else:
                error_msg = f"Unsupported file operation: {operation}"
                print(f"{config.RED}{error_msg}{config.RESET}")
                return error_msg
            
        elif result.get("tool") == "command":
            # Handle shell commands
            command = result.get("command")
            description = result.get("description", "Execute command")
            requires_confirmation = result.get("requires_confirmation", True)
            
            if command:
                # Show the command to the user
                print(f"\n{description}:")
                print(f"```bash\n{command}\n```")
                
                if config.autopilot_mode or not requires_confirmation:
                    print(f"{config.CYAN}Executing command...{config.RESET}")
                    result = execute_shell_command(command, config.api_key, stream_output=True, safe_mode=not config.autopilot_mode)
                    if result.startswith("Error"):
                        print(f"{config.RED}{result}{config.RESET}")
                    else:
                        print(f"{config.GREEN}{result}{config.RESET}")
                    return result
                else:
                    if get_user_confirmation(command, config):
                        result = execute_shell_command(command, config.api_key, stream_output=True, safe_mode=True)
                        if result.startswith("Error"):
                            print(f"{config.RED}{result}{config.RESET}")
                        else:
                            print(f"{config.GREEN}{result}{config.RESET}")
                        return result
                    return "Command execution cancelled by user."
        
        # If no specific tool was selected or tool execution failed, fall back to direct LLM processing
        llm_response = chat_with_model(query, config, chat_models)
        final_response = process_response(query, llm_response, config, chat_models, allow_browser_fallback=True)
        print_streamed_message(final_response, config.CYAN)
        return final_response
        
    except Exception as e:
        print(f"{config.RED}Error in process_input_based_on_mode: {str(e)}{config.RESET}")
        # Fall back to direct LLM processing
        llm_response = chat_with_model(query, config, chat_models)
        final_response = process_response(query, llm_response, config, chat_models, allow_browser_fallback=True)
        print_streamed_message(final_response, config.CYAN)
        return final_response

def process_input_in_autopilot_mode(query, config, chat_models):
    """Process input in autopilot mode with automatic execution."""
    # Set autopilot mode in config
    config.autopilot_mode = True
    
    # Process the input
    response = process_input_based_on_mode(query, config, chat_models)
    
    # If response contains a command, execute it
    if isinstance(response, dict) and response.get("command"):
        command = response["command"]
        print(f"{config.CYAN}Executing command in autopilot mode: {command}{config.RESET}")
        execute_shell_command(command, config.api_key, stream_output=True, safe_mode=False)
        return f"Executed command: {command}"
    
    return response

def process_input_in_safe_mode(query, config, chat_models):
    """Process input in safe mode with additional checks and confirmations."""
    # Set safe mode in config
    config.safe_mode = True
    config.autopilot_mode = False
    
    # Process the input
    response = process_input_based_on_mode(query, config, chat_models)
    
    # If response contains a command, ask for confirmation
    if isinstance(response, dict) and response.get("command"):
        command = response["command"]
        if get_user_confirmation(command, config):
            execute_shell_command(command, config.api_key, stream_output=True, safe_mode=True)
            return f"Executed command: {command}"
        else:
            return "Command execution aborted by user."
    
    return response

def multiline_input(prompt="> ", show_hint=False):
    """
    Enhanced multiline input with better control.
    - Type 'EOF' on a new line to send multiline input
    - Type ';' at the end of a line to continue to next line
    - Press Enter without ';' to send single line immediately
    """
    # Show hint if requested (for places where users might be confused)
    if show_hint:
        prompt = prompt + "(';' for multiline) "
    
    # First line
    line = input(prompt)
    
    # Check if it ends with ; - if so, start multiline mode
    if line.endswith(';'):
        lines = [line[:-1]]  # Remove the trailing ;
        print("(Multiline mode - enter 'EOF' to finish or ';;' to send)")
        
        while True:
            next_line = input("... ")
            if next_line.strip() == "EOF" or next_line.strip() == ";;":
                break
            lines.append(next_line)
        
        return "\n".join(lines)
    else:
        # Single line mode - return immediately
        return line
