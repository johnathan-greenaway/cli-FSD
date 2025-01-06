# script_handlers.py

import re
import os
import subprocess
import tempfile
import json
from datetime import datetime
from .utils import print_streamed_message, get_system_info, animated_loading, save_script, use_mcp_tool
from .chat_models import chat_with_model
from .resources.assembler import AssemblyAssist
import threading
import requests
from .configuration import Config
from .linting.code_checker import CodeChecker

from .agents.context_agent import ContextAgent

# Cache for storing content from MCP tools
_content_cache = {
    'raw_content': None,  # Raw JSON response
    'formatted_content': None,  # Formatted text for summaries
    'headlines': [],  # List of headlines for easy reference
    'paragraphs': []  # List of paragraphs for easy reference
}

def _find_matching_content(query):
    """Find content matching a natural language query."""
    if not _content_cache['raw_content']:
        return None
        
    # Use LLM to help parse the query and find relevant content
    try:
        content = _content_cache['raw_content']
        if content.get("type") == "webpage":
            # Format content for matching
            stories = []
            for item in content.get("content", []):
                if item.get("type") == "story":
                    story_text = [
                        f"Title: {item['title']}",
                        f"URL: {item['url']}"
                    ]
                    for key, value in item.get("metadata", {}).items():
                        story_text.append(f"{key}: {value}")
                    stories.append({
                        "title": item["title"],
                        "content": "\n".join(story_text)
                    })
                elif item.get("type") == "section":
                    for block in item.get("blocks", []):
                        if block.get("text"):
                            text = block["text"]
                            if block.get("links"):
                                text += "\nLinks:\n" + "\n".join(
                                    f"- {link['text']}: {link['url']}"
                                    for link in block["links"]
                                )
                            stories.append({
                                "title": text.split("\n")[0],
                                "content": text
                            })
            
            if stories:
                # Ask LLM to analyze and match content
                analysis = chat_with_model(
                    message=(
                        "Given these content sections:\n\n" +
                        "\n---\n".join(f"Section {i}:\n{s['content']}" for i, s in enumerate(stories)) +
                        f"\n\nAnd this user request: '{query}'\n\n"
                        "Analyze the content and the request to:\n"
                        "1. Find the most relevant section(s)\n"
                        "2. Extract specific details or quotes that answer the request\n"
                        "3. Include any relevant links or references\n\n"
                        "Format your response as JSON:\n"
                        "{\n"
                        "  \"sections\": [section_numbers],\n"
                        "  \"details\": \"extracted details and quotes\",\n"
                        "  \"links\": [\"relevant links\"]\n"
                        "}"
                    ),
                    config=Config(),
                    chat_models=None,
                    system_prompt="You are a content analysis expert. Respond only with a JSON object containing the requested information."
                )
                
                try:
                    result = json.loads(analysis.strip())
                    if result.get("sections"):
                        matched_content = []
                        for section_num in result["sections"]:
                            if 0 <= section_num < len(stories):
                                matched_content.append(stories[section_num]["content"])
                        
                        return {
                            'headline': stories[result["sections"][0]]["title"],
                            'content': "\n\n".join(matched_content),
                            'details': result.get("details", ""),
                            'links': result.get("links", [])
                        }
                except (ValueError, json.JSONDecodeError):
                    pass
            
    except Exception:
        pass
    
    return None

# Ensure query is not empty before processing
def _validate_query(query: str) -> bool:
    """Validate that the query is not empty and contains actual content."""
    return bool(query and query.strip())

def process_input_based_on_mode(query, config, chat_models):
    global _content_cache
    
    # Validate query
    if not _validate_query(query):
        print(f"{config.YELLOW}Please provide a command or question.{config.RESET}")
        return None
        
    # Print current configuration for debugging
    if config.session_model:
        print(f"{config.CYAN}Using model: {config.session_model}{config.RESET}")
    
    # Check if this is a request to view specific cached content
    if _content_cache['raw_content'] and any(word in query.lower() for word in ['show', 'view', 'read', 'tell', 'about']):
        matching_content = _find_matching_content(query)
        if matching_content:
            print(f"\n{config.CYAN}Found relevant content:{config.RESET}")
            print(f"\nHeadline: {matching_content['headline']}")
            if matching_content['content']:
                print(f"\nContent: {matching_content['content']}")
            if matching_content.get('details'):
                print(f"\nDetails: {matching_content['details']}")
            if matching_content.get('links'):
                print("\nRelevant links:")
                for link in matching_content['links']:
                    print(f"- {link}")
            return None
    
    # Check if this is a follow-up question about cached content
    if _content_cache['formatted_content'] and not query.lower().startswith(("get", "fetch", "find")):
        # Process as a question about the cached content
        llm_response = chat_with_model(
            message=(
                f"Based on this content:\n\n{_content_cache['formatted_content']}\n\n"
                f"User question: {query}\n\n"
                "Provide a clear and focused answer. If the question is about a specific topic or article, "
                "include relevant quotes and links from the content. After your answer, suggest 2-3 relevant "
                "follow-up questions the user might want to ask about this topic."
            ),
            config=config,
            chat_models=chat_models
        )
        print_streamed_message(llm_response, config.CYAN)
        return None
    
    llm_response = None
    
    try:
        agent = ContextAgent()
        analysis = agent.analyze_request(query)
        
        # Validate analysis object
        if not analysis or not isinstance(analysis, dict) or "prompt" not in analysis:
            # Fall back to direct LLM processing if analysis fails
            print(f"{config.YELLOW}Failed to generate valid analysis from ContextAgent.{config.RESET}")
            llm_response = chat_with_model(query, config, chat_models)
            return llm_response
        
        # Get LLM's tool selection decision with the analysis prompt
        llm_analysis = chat_with_model(
            message=analysis["prompt"],
            config=config,
            chat_models=chat_models,
            system_prompt=(
                "You are a tool selection expert. Analyze the user's request and determine "
                "which tool would be most effective. For web browsing requests, always select "
                "the small_context tool with browse_web operation. When using browse_web, "
                "ensure the response excludes technical details about servers, responses, or parsing. "
                "Focus only on the actual content. Respond with a JSON object containing your "
                "analysis and selection. Be precise and follow the specified format."
            )
        )
        
        if not llm_analysis:
            print(f"{config.YELLOW}No response received from tool selection LLM analysis.{config.RESET}")
            llm_response = chat_with_model(query, config, chat_models)
            return llm_response
        
        try:
            # Extract JSON from the LLM analysis response
            json_start = llm_analysis.find('{')
            json_end = llm_analysis.rfind('}') + 1
            if json_start >= 0 and json_end > json_start:
                json_str = llm_analysis[json_start:json_end]
                tool_selection = json.loads(json_str)
                
                # Get response using selected tool
                selected_tool = tool_selection.get("selected_tool", "").lower()
                if selected_tool == "small_context":
                    # Rest of the small_context handling code...
                    # [Ensure that existing small_context handling code is placed here]
                    
                    # Example placeholder for small_context handling:
                    parameters = tool_selection.get("parameters", {})
                    url = parameters.get("url")
                    if not url or url == "[URL will be determined based on request]":
                        print(f"{config.RED}No valid URL provided in tool selection.{config.RESET}")
                        return None

                    # Update the request with the LLM-selected URL
                    result = agent.execute_tool_selection(tool_selection)
                    if result.get("tool") == "use_mcp_tool":
                        from .utils import use_mcp_tool
                        # Execute MCP tool with debug output
                        print(f"{config.CYAN}Executing MCP tool: {result['operation']}{config.RESET}")
                        print(f"{config.CYAN}Using URL: {url}{config.RESET}")
                        
                        # Create arguments with the URL
                        arguments = {
                            **result["arguments"],
                            "url": url  # Ensure URL is included in arguments
                        }
                        
                        response = use_mcp_tool(
                            server_name=result["server"],
                            tool_name=result["operation"],
                            arguments=arguments
                        )
                        print(f"{config.CYAN}MCP tool response received.{config.RESET}")
                        
                        try:
                            # Handle both string and list responses
                            if isinstance(response, str):
                                content = json.loads(response)
                            elif isinstance(response, (list, dict)):
                                content = response
                            else:
                                raise ValueError(f"Unexpected response type: {type(response)}")
                            
                            # Format content for processing
                            if isinstance(content, dict):
                                if content.get("type") == "webpage":
                                    # Process structured content
                                    _content_cache['raw_content'] = content
                                    
                                    # Format content for LLM processing
                                    formatted_content = []
                                    
                                    # Process each content block
                                    for item in content.get("content", []):
                                        if item.get("type") == "story":
                                            # Format story with metadata
                                            story_text = [
                                                f"Title: {item['title']}",
                                                f"URL: {item['url']}"
                                            ]
                                            # Add metadata if present
                                            for key, value in item.get("metadata", {}).items():
                                                story_text.append(f"{key}: {value}")
                                            formatted_content.append("\n".join(story_text))
                                        elif item.get("type") == "section":
                                            # Process section blocks
                                            for block in item.get("blocks", []):
                                                if block.get("text"):
                                                    text = block["text"]
                                                    # Add links if present
                                                    if block.get("links"):
                                                        text += "\nLinks:\n" + "\n".join(
                                                            f"- {link['text']}: {link['url']}"
                                                            for link in block["links"]
                                                        )
                                                    formatted_content.append(text)
                                    
                                    # Cache formatted content
                                    _content_cache['formatted_content'] = "\n\n".join(formatted_content)
                                    
                                    # Let LLM analyze and present the content
                                    llm_response = chat_with_model(
                                        message=(
                                            "You are a content analyzer. Given this content:\n\n"
                                            f"{_content_cache['formatted_content']}\n\n"
                                            "1. Provide a clear overview of the main points\n"
                                            "2. Format each point as a bullet\n"
                                            "3. Include relevant links when available\n"
                                            "4. Focus on the actual content\n"
                                            "5. If there are multiple stories/sections, organize them clearly\n"
                                            "6. Highlight any particularly interesting or important information\n\n"
                                            "After your summary, provide a list of suggested interactions like:\n"
                                            "- 'Tell me more about [topic]'\n"
                                            "- 'Show me the full article about [headline]'\n"
                                            "- 'What are the key points about [subject]'\n"
                                            "Choose topics/headlines/subjects from the actual content."
                                        ),
                                        config=config,
                                        chat_models=chat_models
                                    )
                                    print_streamed_message(llm_response, config.CYAN)
                                    
                                    # Print interaction hint
                                    print(f"\n{config.CYAN}You can interact with the content by asking questions or requesting more details about specific topics.{config.RESET}")
                                else:
                                    formatted_response = json.dumps(content, indent=2)
                                    llm_response = chat_with_model(
                                        message=f"Please summarize this content:\n\n{formatted_response}",
                                        config=config,
                                        chat_models=chat_models
                                    )
                                    print_streamed_message(llm_response, config.CYAN)
                            else:
                                formatted_response = str(content)
                                llm_response = chat_with_model(
                                    message=f"Please summarize this content:\n\n{formatted_response}",
                                    config=config,
                                    chat_models=chat_models
                                )
                                print_streamed_message(llm_response, config.CYAN)
                            
                        except json.JSONDecodeError:
                            # Handle raw response directly
                            llm_response = chat_with_model(
                                message=f"Please summarize this content in a clear and concise way:\n\n{response}",
                                config=config,
                                chat_models=chat_models
                            )
                            print_streamed_message(llm_response, config.CYAN)
                        return None
                    else:
                        llm_response = f"Error: {result.get('error', 'Unknown error')}"
                elif selected_tool == "default":
                    # Handle default tool case - generate a shell script for simple commands
                    parameters = tool_selection.get("parameters", {})
                    operation = parameters.get("operation", "")
                    
                    # For simple command requests, wrap in a shell script
                    if operation == "process_command":
                        # Format as a shell script
                        llm_response = chat_with_model(
                            message=query,
                            config=config,
                            chat_models=chat_models,
                            system_prompt=(
                                "You are a shell script expert. Your task is to generate shell commands for the given request. "
                                "Always wrap your commands in ```bash\n[command]\n``` markers. "
                                "For simple queries like time, date, or weather, use the appropriate Unix commands. "
                                "For example:\n"
                                "- Time queries: date command with appropriate format\n"
                                "- Weather queries: curl wttr.in with location\n"
                                "- File operations: ls, cp, mv, etc.\n"
                                "Never explain the commands, just provide them in the code block."
                            )
                        )
                    else:
                        # Default to standard LLM processing with shell command generation
                        llm_response = chat_with_model(
                            message=query,
                            config=config,
                            chat_models=chat_models,
                            system_prompt=(
                                "You are a shell command generator. "
                                "Always provide a shell command to answer the query, wrapped in "
                                "```bash\n[command]\n``` markers. "
                                "If in doubt, generate a command rather than a text response."
                            )
                        )
            else:
                # Fallback if JSON extraction fails
                llm_response = chat_with_model(
                    query, 
                    config, 
                    chat_models
                )
        except (json.JSONDecodeError, KeyError, AttributeError) as e:
            print(
                f"{config.YELLOW}Failed to process tool selection: {str(e)}"
                f"{config.RESET}"
            )
            llm_response = chat_with_model(query, config, chat_models)
    except Exception as e:
        print(
            f"{config.YELLOW}Using standard processing due to error: {str(e)}"
            f"{config.RESET}"
        )
        llm_response = chat_with_model(query, config, chat_models)

    if config.safe_mode:
        print_streamed_message(llm_response, config.CYAN)
        scripts = extract_script_from_response(llm_response)
        if scripts:
            code_checker = CodeChecker()
            for script, file_extension, script_type in scripts:
                # Lint code and show results
                lint_results = code_checker.lint_code(script, file_extension, is_autopilot=config.autopilot_mode)
                code_checker.display_results(lint_results, script, file_extension)
                
                print(f"\nFound a {script_type} script:")
                print(script)
                
                # Determine if there are critical errors that should block execution
                critical_errors = [
                    err for err in lint_results.get('errors', [])
                    if any(critical in err.lower() for critical in [
                        'syntax error', 'undefined variable', 'command not found'
                    ])
                ]
                
                if critical_errors:
                    print(f"{config.RED}Critical errors found that may prevent successful execution:{config.RESET}")
                    for error in critical_errors:
                        print(f"{config.RED}❌ {error}{config.RESET}")
                    
                    if not get_user_confirmation("Proceed despite critical errors?", config):
                        print("Script execution aborted due to critical errors.")
                        continue
                
                # Save and execute script if user confirms
                full_filename = save_script(
                    query, script,
                    file_extension=file_extension,
                    auto_save=False,
                    config=config
                )
                
                if full_filename:
                    print(f"Script saved as {full_filename}")
                    if get_user_confirmation(f"Execute saved script {full_filename}?", config):
                        if script_type == "python":
                            execute_script(full_filename, "py", config)
                        else:
                            execute_shell_command(f"bash {full_filename}", config)
                else:
                    print("Failed to save script. Attempting direct execution...")
                    if get_user_confirmation("Execute script directly?", config):
                        execute_script_directly(script, file_extension, config)
        else:
            print("No executable script found in the LLM response.")

    elif config.autopilot_mode:
        print_streamed_message(llm_response, config.CYAN)
        scripts = extract_script_from_response(llm_response)
        if scripts:
            # In autopilot mode, execute each script directly without saving
            for script, file_extension, script_type in scripts:
                # Perform basic linting to catch critical errors
                code_checker = CodeChecker()
                lint_results = code_checker.lint_code(script, file_extension, is_autopilot=True)
                
                # Only check for syntax errors in autopilot mode
                critical_errors = [
                    err for err in lint_results.get('errors', [])
                    if 'syntax error' in err.lower()
                ]
                
                if critical_errors:
                    print(f"{config.RED}Syntax errors found in {script_type} script:{config.RESET}")
                    for error in critical_errors:
                        print(f"{config.RED}❌ {error}{config.RESET}")
                    continue
                
                # Execute the script directly without saving
                execute_script_directly(script, file_extension, config)
        else:
            print("No executable script found in the LLM response.")

    else:
        print_streamed_message(llm_response, config.CYAN)
        scripts = extract_script_from_response(llm_response)
        if scripts:
            code_checker = CodeChecker()
            for script, file_extension, _ in scripts:
                # Perform linting and show results
                lint_results = code_checker.lint_code(script, file_extension, is_autopilot=config.autopilot_mode)
                code_checker.display_results(lint_results, script, file_extension)
                
                if lint_results['errors'] and not config.autopilot_mode:
                    proceed = input(f"{config.YELLOW}Code contains errors. Would you like to proceed? (yes/no):{config.RESET} ").lower()
                    if proceed != 'yes':
                        print("Skipping this script due to errors.")
                        continue
                
                user_decide_and_act(query, script, file_extension, config)
        else:
            print("No executable script found in the LLM response.")

def process_input_in_safe_mode(query, config, chat_models):
    llm_response = chat_with_model(query, config, chat_models)
    print_streamed_message(llm_response, config.CYAN)

    scripts = extract_script_from_response(llm_response)
    if scripts:
        for script, file_extension, _ in scripts:
            print(f"Found a {file_extension} script:")
            print(script)
            
            # Pass the correct parameters: query, script, file_extension, auto_save=False
            full_filename = save_script(query, script, file_extension=file_extension, auto_save=False, config=config)
            if full_filename:
                print(f"Script extracted and saved as {full_filename}.")
                
                if config.safe_mode:
                    user_confirmation = input(f"Do you want to execute the saved script {full_filename}? (yes/no): ").strip().lower()
                    if user_confirmation == "yes":
                        execute_shell_command(f"bash {full_filename}", config)
                    else:
                        print("Script execution aborted by the user.")
            else:
                print("Failed to save the script.")
    else:
        print("No executable script found in the LLM response.")

def process_input_in_autopilot_mode(query, config, chat_models):
    """Process input in autopilot mode with dynamic code display."""
    from contextlib import contextmanager
    
    @contextmanager
    def loading_animation():
        stop_event = threading.Event()
        loading_thread = threading.Thread(
            target=animated_loading,
            args=(stop_event,),
            daemon=True  # Ensure thread cleanup on program exit
        )
        try:
            loading_thread.start()
            yield
        finally:
            stop_event.set()
            loading_thread.join(timeout=1.0)  # Prevent hanging
    
    with loading_animation():
        print(f"{config.CYAN}Sending command to LLM...{config.RESET}")
        llm_response = chat_with_model(query, config, chat_models)
        print_streamed_message(llm_response, config.CYAN)
        
        scripts = extract_script_from_response(llm_response)
        if not scripts:
            print("No executable script found in the LLM response.")
            return
        
        code_checker = CodeChecker()
        for script, file_extension, script_type in scripts:
            # Display code with syntax highlighting and linting
            lint_results = code_checker.lint_code(script, file_extension)
            code_checker.display_results(lint_results, script, file_extension)
            
            # Execute script directly without blocking on errors
            if script_type == "python":
                execute_script_directly(script, "py", config)
            else:
                execute_script_directly(script, "sh", config)

# Pre-compile regex patterns at module level for better performance
SCRIPT_PATTERN = re.compile(r"```(?:(bash|sh|python))?\n(.*?)```", re.DOTALL)

def extract_script_from_response(response):
    """Extract scripts from LLM response with improved language detection."""
    if not isinstance(response, str):
        print("Error: 'response' expected to be a string, received:", type(response))
        return []
    
    scripts = []
    matches = SCRIPT_PATTERN.finditer(response)
    
    for match in matches:
        lang = match.group(1)
        content = match.group(2).strip()
        
        if not content:
            continue
            
        # Determine script type based on content and language tag
        if lang == "python":
            ext = "py"
            script_type = "python"
        else:
            # Default to shell script
            ext = "sh"
            script_type = "bash"
            
            # Check for shebang line
            if content.startswith("#!"):
                first_line = content.split("\n")[0]
                if "python" in first_line.lower():
                    ext = "py"
                    script_type = "python"
        
        scripts.append((content, ext, script_type))
    
    return scripts

def assemble_final_script(scripts, api_key):
    # Use cached system info
    info_details = get_cached_system_info()
    
    # Optimize script joining
    final_script_prompt = "\n\n".join(
        script.strip() for script, _, _ in scripts if script.strip()
    )
    
    # Prepare API request
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}"
    }
    
    messages = [
        {
            "role": "system",
            "content": "You are a shell script expert. Combine scripts into a single executable, ensuring Unix compatibility and portability. Return only code, no comments or explanations."
        },
        {
            "role": "user",
            "content": f"System Info: {info_details}\n\nCombine these scripts:\n\n{final_script_prompt}"
        }
    ]
    
    try:
        response = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers=headers,
            json={
                "model": "gpt-4-turbo-preview",
                "messages": messages,
                "temperature": 0.3,  # Lower temperature for more consistent output
                "max_tokens": 2000   # Limit response size
            },
            timeout=30  # Add timeout
        )
        response.raise_for_status()
        
        if content := response.json().get('choices', [{}])[0].get('message', {}).get('content', ''):
            return clean_up_llm_response(content)
            
        print("No assembled script was returned by the model.")
        return None
    except requests.exceptions.RequestException as e:
        print(f"API request error: {e}")
        return None
    except Exception as e:
        print(f"Unexpected error during script assembly: {e}")
        return None

# Track assembled scripts for cleanup
_assembled_scripts = set()

def handle_script_cleanup(config):
    """Handle cleanup of assembled scripts with option to save."""
    global _assembled_scripts
    
    if not _assembled_scripts:
        return
        
    print(f"\n{config.CYAN}Found {len(_assembled_scripts)} unnamed script(s) from this session.{config.RESET}")
    save_all = input("Would you like to review and save any scripts before cleanup? (yes/no): ").strip().lower()
    
    if save_all == 'yes':
        for script_path in _assembled_scripts.copy():
            try:
                if os.path.exists(script_path):
                    with open(script_path, 'r') as f:
                        content = f.read()
                    
                    print(f"\n{config.CYAN}Script content:{config.RESET}\n{content}")
                    save = input(f"Save this script? (yes/no): ").strip().lower()
                    
                    if save == 'yes':
                        name = input("Enter name for the script (without extension): ").strip()
                        if name:
                            new_path = f"{name}.sh"
                            os.rename(script_path, new_path)
                            print(f"Script saved as {new_path}")
                            _assembled_scripts.remove(script_path)
                            continue
                    
                    # If not saving or no name provided, delete the script
                    os.unlink(script_path)
                    _assembled_scripts.remove(script_path)
                    
            except OSError as e:
                print(f"{config.RED}Warning: Failed to handle script {script_path}: {e}{config.RESET}")
    else:
        # Clean up all scripts without saving
        for script in _assembled_scripts.copy():
            try:
                if os.path.exists(script):
                    os.unlink(script)
                    _assembled_scripts.remove(script)
            except OSError as e:
                print(f"{config.RED}Warning: Failed to clean up script {script}: {e}{config.RESET}")

def cleanup_assembled_scripts():
    """Clean up any remaining assembled scripts without prompting."""
    global _assembled_scripts
    for script in _assembled_scripts.copy():
        try:
            if os.path.exists(script):
                os.unlink(script)
                _assembled_scripts.remove(script)
        except OSError as e:
            print(f"Warning: Failed to clean up script {script}: {e}")

def auto_handle_script_execution(final_script, config):
    """Handle script assembly and execution with proper cleanup."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f".assembled_script_{timestamp}.sh"
    
    try:
        # Use tempfile for safer file handling
        with tempfile.NamedTemporaryFile(mode='w', suffix='.sh', delete=False) as temp_file:
            temp_file.write(final_script)
            temp_path = temp_file.name
            
        try:
            # Move temp file to final location
            os.rename(temp_path, filename)
            _assembled_scripts.add(filename)  # Track for cleanup
            
            print(f"{config.CYAN}Final script assembled and saved as {filename}.{config.RESET}")
            os.chmod(filename, 0o755)
            
            print(f"{config.CYAN}Executing {filename}...{config.RESET}")
            success = execute_shell_command(f"./{filename}", config)
            
            if success:
                print(f"{config.GREEN}Script execution completed successfully.{config.RESET}")
            else:
                print(f"{config.RED}Script execution failed.{config.RESET}")
                
            return success
            
        except Exception as e:
            # Clean up temp file if move failed
            try:
                os.unlink(temp_path)
            except OSError:
                pass
            raise e
            
    except Exception as e:
        print(f"{config.RED}Failed to handle script execution: {e}{config.RESET}")
        return False

def get_user_confirmation(command: str, config=None) -> bool:
    """Get user confirmation before executing a command."""
    if config and config.autopilot_mode:
        return True
    print(f"\nAbout to execute command:\n{command}")
    response = input("Do you want to proceed? (yes/no): ").strip().lower()
    return response in ['yes', 'y']

def execute_shell_command(command, config, stream_output=True):
    """Execute a shell command with proper error handling and output management."""
    if command.startswith('./'):
        try:
            script_path = command[2:]
            os.chmod(script_path, 0o755)
        except OSError as e:
            print(f"{config.RED}Failed to set executable permissions: {e}{config.RESET}")
            return False

    if not get_user_confirmation(command, config):
        return False

    try:
        # Use context manager with timeout
        with subprocess.Popen(
            command,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            bufsize=1,
            encoding='utf-8',
            errors='replace'  # Handle encoding errors by replacing invalid characters
        ) as process:
            output_lines = []
            
            # Use select for non-blocking reads with timeout
            from select import select
            while True:
                reads, _, _ = select([process.stdout], [], [], 0.1)
                if not reads:
                    # No output available, check if process is still running
                    if process.poll() is not None:
                        break
                    continue
                    
                line = process.stdout.readline()
                if not line:
                    break
                    
                if stream_output:
                    print(line, end='', flush=True)
                output_lines.append(line.strip())
            
            return_code = process.wait(timeout=300)  # 5 minute timeout

            if return_code != 0:
                error_context = "\n".join(output_lines)
                print(f"{config.RED}Error encountered executing command: {error_context}{config.RESET}")
                
                if resolution := consult_llm_for_error_resolution(error_context, config):
                    print(f"{config.CYAN}Suggested resolution:{config.RESET}\n{resolution}")
                    
                    if not config.safe_mode or get_user_confirmation("Apply suggested resolution?", config):
                        return execute_resolution_script(resolution, config)
                return False
                
            return True
            
    except subprocess.TimeoutExpired:
        print(f"{config.RED}Command execution timed out after 5 minutes{config.RESET}")
        return False
    except subprocess.CalledProcessError as e:
        print(f"{config.RED}Command execution failed with error: {e}{config.RESET}")
        return False
    except Exception as e:
        print(f"{config.RED}An error occurred while executing the command: {e}{config.RESET}")
        return False

# Pre-compile additional regex pattern for cleanup
CLEANUP_PATTERN = re.compile(r"```(?:bash|sh)\n(.*?)\n```", re.DOTALL)

def clean_up_llm_response(llm_response):
    script_blocks = CLEANUP_PATTERN.findall(llm_response)
    if script_blocks:
        # Use list comprehension for better performance
        return "\n".join(block.strip() for block in script_blocks if block.strip())
    print("No executable script blocks found in the response.")
    return llm_response.strip()

def execute_script(filename, file_extension, config):
    """Execute a saved script with proper error handling and output capture."""
    try:
        if file_extension == "py":
            result = subprocess.run(
                ["python", filename],
                capture_output=True,
                text=True,
                check=False
            )
        elif file_extension in ["sh", "bash", ""]:
            # Ensure script is executable
            try:
                os.chmod(filename, 0o755)
            except OSError as e:
                print(f"{config.RED}Failed to set executable permissions: {e}{config.RESET}")
                return
            
            result = subprocess.run(
                ["bash", filename],
                capture_output=True,
                text=True,
                check=False
            )
        else:
            print(f"{config.RED}Running scripts with .{file_extension} extension is not supported.{config.RESET}")
            return
        
        # Always show output
        if result.stdout:
            print(result.stdout)
        if result.stderr:
            print(f"{config.RED}{result.stderr}{config.RESET}")
            
        # Handle return code
        if result.returncode != 0:
            print(f"{config.RED}Script execution failed with return code {result.returncode}{config.RESET}")
            
            # Try to get resolution for the error
            if resolution := consult_llm_for_error_resolution(result.stderr or result.stdout, config):
                if get_user_confirmation("Would you like to apply the suggested fix?", config):
                    execute_resolution_script(resolution, config)
        else:
            print(f"{config.GREEN}Script executed successfully.{config.RESET}")
            
    except Exception as e:
        print(f"{config.RED}An error occurred while executing the script: {e}{config.RESET}")

def execute_script_directly(script, file_extension, config):
    """Execute a script directly with proper cleanup and error handling."""
    temp_file_path = None
    try:
        # Add shebang line if missing for shell scripts
        if file_extension in ["sh", "bash", ""]:
            if not script.startswith("#!"):
                script = "#!/bin/bash\n" + script

        if file_extension == "py":
            # Create a temporary file for Python scripts too
            with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as temp_file:
                temp_file.write(script)
                temp_file_path = temp_file.name
            
            try:
                # Execute Python script as a subprocess for better isolation
                result = subprocess.run(
                    ["python", temp_file_path],
                    capture_output=True,
                    text=True,
                    check=False
                )
                if result.returncode != 0:
                    print(f"{config.RED}Python script execution failed:{config.RESET}")
                    if result.stderr:
                        print(result.stderr)
                    return False
                if result.stdout:
                    print(result.stdout)
                return True
            except Exception as e:
                print(f"{config.RED}Error executing Python script: {e}{config.RESET}")
                return False
                
        elif file_extension in ["sh", "bash", ""]:  # Accept empty extension as shell script
            # Create temporary shell script
            with tempfile.NamedTemporaryFile(mode='w', suffix='.sh', delete=False) as temp_file:
                temp_file.write(script)
                temp_file_path = temp_file.name
                
            try:
                # Set executable permissions
                os.chmod(temp_file_path, 0o755)
                
                if not config.autopilot_mode and not get_user_confirmation(f"Execute script:\n{script}"):
                    print("Script execution aborted by the user.")
                    return False
                
                # Execute the shell script
                result = subprocess.run(
                    ["bash", temp_file_path],
                    capture_output=True,
                    text=True,
                    check=False
                )
                
                # Print output regardless of success/failure
                if result.stdout:
                    print(result.stdout)
                if result.stderr:
                    print(f"{config.RED}{result.stderr}{config.RESET}")
                
                return result.returncode == 0
                
            except Exception as e:
                print(f"{config.RED}Error executing shell script: {e}{config.RESET}")
                return False
        else:
            print(f"{config.RED}Running scripts with .{file_extension} extension is not supported.{config.RESET}")
            return False
            
    except Exception as e:
        print(f"{config.RED}Error preparing script for execution: {e}{config.RESET}")
        return False
        
    finally:
        # Clean up temporary file
        if temp_file_path and os.path.exists(temp_file_path):
            try:
                os.unlink(temp_file_path)
            except OSError as e:
                print(f"Warning: Failed to clean up temporary file {temp_file_path}: {e}")

def user_decide_and_act(query, script, file_extension, config):
    """Handle script execution based on user preferences and mode."""
    if config.autopilot_mode:
        # In autopilot mode, execute directly without saving
        execute_script_directly(script, file_extension, config)
    else:
        # Interactive mode
        auto_save = False  # Default to manual save in interactive mode
        full_filename = save_script(query, script, file_extension=file_extension, auto_save=auto_save, config=config)
        
        if full_filename:
            print(f"Script saved to {full_filename}.")
            run = input("Would you like to run this script? (yes/no): ").strip().lower()
            if run == 'yes':
                if file_extension == "py":
                    execute_script(full_filename, file_extension, config)
                else:
                    execute_shell_command(f"bash {full_filename}", config)
        else:
            run = input("Would you like to run this script without saving? (yes/no): ").strip().lower()
            if run == 'yes':
                execute_script_directly(script, file_extension, config)
            else:
                print("Script execution aborted by the user.")

def execute_resolution_script(resolution, config):
    print(f"{config.CYAN}Executing resolution:{config.RESET}\n{resolution}")
    try:
        subprocess.run(resolution, shell=True, check=True)
        print(f"{config.GREEN}Resolution executed successfully.{config.RESET}")
    except subprocess.CalledProcessError as e:
        print(f"{config.RED}Resolution execution failed with error: {e}{config.RESET}")
    except Exception as e:
        print(f"An error occurred while executing the resolution: {e}")

# Initialize system info cache
_system_info_cache = None

def get_cached_system_info():
    global _system_info_cache
    if _system_info_cache is None:
        _system_info_cache = get_system_info()
    return _system_info_cache

def consult_llm_for_error_resolution(error_message, config):
    system_info = get_cached_system_info()
    print(f"{config.CYAN}Consulting LLM for error resolution:{config.RESET} {error_message}")
    
    # Reuse headers and base message structure
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {config.api_key}"
    }
    
    messages = [
        {
            "role": "system",
            "content": "You are an expert in debugging shell scripts and providing fix commands. Respond only with the fix command or script, no explanations."
        },
        {
            "role": "user",
            "content": f"System Info: {system_info}\nError: '{error_message}'.\nProvide a bash command or script to resolve this error. Only respond with the command or script, no explanations."
        }
    ]

    try:
        response = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers=headers,
            json={
                "model": config.current_model,
                "messages": messages,
                "temperature": 0.3  # Lower temperature for more focused responses
            }
        )
        response.raise_for_status()
        
        if suggestion := response.json().get('choices', [{}])[0].get('message', {}).get('content', '').strip():
            config.llm_suggestions = suggestion
            return suggestion
            
        print("No advice was returned by the model.")
        return None
    except requests.exceptions.RequestException as e:
        print(f"API request error: {e}")
        return None

def consult_openai_for_error_resolution(error_message, config):
    """Consult OpenAI for error resolution with improved error handling and caching."""
    try:
        # Use cached system info
        system_info = get_cached_system_info()
        
        instructions = "You are a code debugging assistant specializing in shell scripts and system commands. Provide concise, practical solutions."
        scriptReviewer = AssemblyAssist(instructions)
        
        if not scriptReviewer.start_conversation():
            print(f"{config.RED}Failed to initialize error resolution.{config.RESET}")
            return None
            
        message = f"""
Error: {error_message}
System: {system_info}
Provide a solution command or script.
"""
        response = scriptReviewer.send_message(message)
        
        if response:
            print(f"{config.CYAN}Suggested solution:{config.RESET}\n{response}")
            return response.strip()
            
        return None
        
    except Exception as e:
        print(f"{config.RED}Error resolution failed: {e}{config.RESET}")
        return None
    finally:
        if 'scriptReviewer' in locals():
            scriptReviewer.end_conversation()
