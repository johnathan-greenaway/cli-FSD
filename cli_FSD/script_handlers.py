import re
import os
import subprocess
import tempfile
import json
import traceback # For detailed error logging
import regex  # For more advanced regex support
from datetime import datetime, date
from typing import Any


def extract_json_from_response(response: str) -> str:
    """
    Extract JSON content from LLM responses that may contain markdown code blocks
    and additional explanatory text.
    
    Args:
        response: The full LLM response text
        
    Returns:
        Extracted JSON string, or empty string if no JSON found
    """
    # Try to find JSON within markdown code blocks
    json_patterns = [
        r'```json\s*\n(.*?)\n```',  # ```json ... ```
        r'```\s*\n(\{.*?\})\s*\n```',  # ``` { ... } ```
        r'(\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\})',  # Direct JSON object
    ]
    
    for pattern in json_patterns:
        matches = re.findall(pattern, response, re.DOTALL | re.MULTILINE)
        if matches:
            # Return the first match that looks like valid JSON
            for match in matches:
                cleaned_match = match.strip()
                if cleaned_match.startswith('{') and cleaned_match.endswith('}'):
                    return cleaned_match
    
    # If no markdown blocks found, try to find JSON-like content
    # Look for lines that start and end with braces
    lines = response.split('\n')
    json_lines = []
    in_json = False
    brace_count = 0
    
    for line in lines:
        stripped = line.strip()
        if stripped.startswith('{'):
            in_json = True
            json_lines = [line]
            brace_count = stripped.count('{') - stripped.count('}')
        elif in_json:
            json_lines.append(line)
            brace_count += stripped.count('{') - stripped.count('}')
            if brace_count <= 0:
                # Found complete JSON object
                return '\n'.join(json_lines)
    
    return ""

def attempt_json_repair(json_str):
    """
    Attempt to repair malformed JSON strings with common errors.
    
    Args:
        json_str: The potentially malformed JSON string
        
    Returns:
        tuple: (fixed_json_str, was_repaired)
    """
    original = json_str
    was_repaired = False
    
    try:
        # First test if it's already valid
        json.loads(json_str)
        return json_str, False
    except json.JSONDecodeError as e:
        # Get the error position
        error_msg = str(e)
        was_repaired = True
        
        # Extract error details
        err_line = None
        err_col = None
        err_char = None
        
        # Parse error location from message
        if "line" in error_msg and "column" in error_msg:
            line_match = regex.search(r"line (\d+)", error_msg)
            col_match = regex.search(r"column (\d+)", error_msg)
            char_match = regex.search(r"char (\d+)", error_msg)
            
            if line_match:
                err_line = int(line_match.group(1))
            if col_match:
                err_col = int(col_match.group(1))
            if char_match:
                err_char = int(char_match.group(1))
        
        # Common JSON syntax errors and fixes
        
        # 1. Missing comma between elements
        if "Expecting ',' delimiter" in error_msg and err_char:
            # Split the string at the error position
            before = json_str[:err_char]
            after = json_str[err_char:]
            
            # Insert a comma
            fixed = before + "," + after
            try:
                json.loads(fixed)
                return fixed, True
            except json.JSONDecodeError:
                pass  # Try next fix

        # 2. Missing quotes around keys
        if "Expecting property name enclosed in double quotes" in error_msg and err_char:
            # Try to identify the unquoted key
            text_after_error = json_str[err_char:err_char+30]
            key_match = regex.search(r'^(\w+)\s*:', text_after_error)
            
            if key_match:
                unquoted_key = key_match.group(1)
                quoted_key = f'"{unquoted_key}"'
                # Replace the unquoted key with a quoted key
                fixed = json_str[:err_char] + quoted_key + text_after_error[len(unquoted_key):]
                try:
                    json.loads(fixed)
                    return fixed, True
                except json.JSONDecodeError:
                    pass  # Try next fix
        
        # 3. Trailing comma in objects or arrays
        if "Expecting '\"', '}', ']'" in error_msg and err_char:
            # Check for trailing comma before closing bracket
            nearby = json_str[max(0, err_char-5):min(len(json_str), err_char+5)]
            if ",}" in nearby or ",]" in nearby:
                fixed = json_str[:err_char-1] + json_str[err_char:]
                try:
                    json.loads(fixed)
                    return fixed, True
                except json.JSONDecodeError:
                    pass  # Try next fix
        
        # 4. Missing closing bracket or brace
        if "Expecting" in error_msg and any(x in error_msg for x in ["'}'", "']'"]):
            # Check for unclosed objects
            if json_str.count('{') > json_str.count('}'):
                fixed = json_str + "}"
                try:
                    json.loads(fixed)
                    return fixed, True
                except json.JSONDecodeError:
                    pass  # Try next fix
                    
            # Check for unclosed arrays
            if json_str.count('[') > json_str.count(']'):
                fixed = json_str + "]"
                try:
                    json.loads(fixed)
                    return fixed, True
                except json.JSONDecodeError:
                    pass  # Try next fix
        
        # 5. Try to fix single quotes - this is a common issue with LLM-generated JSON
        if "'" in json_str:
            # Convert single quotes to double quotes, but only when they're likely to be for keys or string values
            # This regex handles cases where single quotes are used for keys or string values
            fixed = regex.sub(r'(?<=[{,:\s])\s*\'([^\']+)\'\s*(?=[},:\s])', r'"\1"', json_str)
            try:
                json.loads(fixed)
                return fixed, True
            except json.JSONDecodeError:
                pass  # Try next fix
        
        # 6. Try to fix unescaped quotes in strings
        if '"' in json_str and err_char:
            # Find string context around error
            context_start = max(0, err_char - 50)
            context_end = min(len(json_str), err_char + 50)
            context = json_str[context_start:context_end]
            
            # Look for unescaped quotes in strings
            quote_indices = [m.start() for m in regex.finditer(r'(?<!\\)"', context)]
            if len(quote_indices) >= 2:
                for i in range(len(quote_indices) - 1):
                    # Extract content between quotes
                    string_content = context[quote_indices[i]+1:quote_indices[i+1]]
                    # If content has unescaped quotes, escape them
                    if '"' in string_content and not '\\"' in string_content:
                        escaped_content = string_content.replace('"', '\\"')
                        # Replace in original
                        fixed = json_str.replace(string_content, escaped_content)
                        try:
                            json.loads(fixed)
                            return fixed, True
                        except json.JSONDecodeError:
                            pass  # Try next fix
        
        # If all specific fixes failed, try a more aggressive approach
        # For LLM-generated content, sometimes the structure is correct but details are wrong
        
        # 7. Strip out all control characters and non-JSON whitespace
        fixed = regex.sub(r'[\x00-\x1F\x7F-\x9F]', '', json_str)
        try:
            json.loads(fixed)
            return fixed, True
        except json.JSONDecodeError:
            pass  # Try next fix
        
        # 8. Last resort: try to extract valid JSON objects/arrays using regex pattern matching
        json_pattern = regex.compile(r'({[^{}]*(?:{[^{}]*}[^{}]*)*}|\[[^\[\]]*(?:\[[^\[\]]*\][^\[\]]*)*\])')
        matches = json_pattern.findall(json_str)
        if matches:
            for match in matches:
                try:
                    json.loads(match)
                    return match, True
                except json.JSONDecodeError:
                    continue
            
    # If we got here, all repair attempts failed        
    return original, False
from .utils import print_streamed_message, get_system_info, animated_loading, save_script, use_mcp_tool
from .chat_models import chat_with_model
from .resources.assembler import AssemblyAssist
import threading
import importlib.util

# Check if requests is available and import it
requests = None
if importlib.util.find_spec("requests"):
    import requests
else:
    print("Warning: requests package not installed. Some features may be limited.")

from .configuration import Config
from .linting.code_checker import CodeChecker
from .agents.context_agent import ContextAgent
from .agents.web_content_agent import WebContentAgent

# Global response context cache to store information from previous responses
_response_context = {
    'previous_responses': [],  # List of previous responses
    'browser_attempts': 0,     # Number of browser attempts made
    'collected_info': {},      # Information collected from various tools
    'tolerance_level': 'medium'  # Default tolerance level: 'strict', 'medium', 'lenient'
}

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

def handle_simple_command_execution(llm_response: str, original_query: str, config) -> str:
    """
    Extract and execute simple commands from LLM response.
    
    Args:
        llm_response: Response from LLM containing command(s)
        original_query: Original user query
        config: Configuration object
        
    Returns:
        String containing command output or error message
    """
    import subprocess
    import re
    
    # Extract commands from the LLM response
    # Look for bash code blocks first
    bash_pattern = r'```(?:bash|sh)?\n(.*?)\n```'
    matches = re.findall(bash_pattern, llm_response, re.DOTALL)
    
    if matches:
        command = matches[0].strip()
    else:
        # Look for standalone commands (no code blocks)
        lines = llm_response.strip().split('\n')
        # Find lines that look like commands
        command_lines = []
        for line in lines:
            line = line.strip()
            if line and not line.startswith('#') and any(cmd in line for cmd in ['ls', 'cat', 'find', 'head', 'tail', 'grep', 'cp', 'mv']):
                command_lines.append(line)
        
        if command_lines:
            command = command_lines[0]  # Use first command found
        else:
            # Fallback: use the whole response as command if it's short and looks like a command
            if len(llm_response.strip()) < 100 and any(cmd in llm_response for cmd in ['ls', 'cat', 'find', 'head', 'tail', 'grep']):
                command = llm_response.strip()
            else:
                return f"Could not extract a simple command from the response. LLM suggested: {llm_response}"
    
    print(f"{config.YELLOW}Executing command: {command}{config.RESET}")
    
    # Execute the command
    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=30  # 30 second timeout for simple commands
        )
        
        output = ""
        if result.stdout:
            output += result.stdout
        
        if result.stderr:
            output += f"\n{config.YELLOW}Warnings/Errors:{config.RESET}\n{result.stderr}"
        
        if result.returncode != 0:
            output += f"\n{config.RED}Command failed with exit code: {result.returncode}{config.RESET}"
        
        if not output.strip():
            output = f"{config.GREEN}Command executed successfully (no output){config.RESET}"
        
        return f"Command: `{command}`\n\nOutput:\n{output}"
        
    except subprocess.TimeoutExpired:
        return f"Command `{command}` timed out after 30 seconds"
    except Exception as e:
        return f"Error executing command `{command}`: {str(e)}"

def set_evaluation_tolerance(level: str):
    """
    Set the tolerance level for response evaluation.
    
    Args:
        level: 'strict', 'medium', or 'lenient'
    """
    if level in ['strict', 'medium', 'lenient']:
        _response_context['tolerance_level'] = level
        print(f"Response evaluation tolerance set to: {level}")
    else:
        print(f"Invalid tolerance level: {level}. Using default: 'medium'")
        _response_context['tolerance_level'] = 'medium'

def is_raw_mcp_response(response: str) -> bool:
    """
    Check if a response appears to be a raw MCP/browser response.
    
    Args:
        response: The response to check
        
    Returns:
        bool: True if it appears to be a raw MCP response
    """
    # Check for common patterns in raw MCP responses
    if len(response) > 1000:  # Raw responses tend to be long
        # Check for JSON-like structure
        if (response.startswith('{') and response.endswith('}')) or (response.startswith('[') and response.endswith(']')):
            return True
        
        # Check for HTML-like content
        if '<html' in response.lower() or '<body' in response.lower():
            return True
            
        # Check for common web content patterns
        if 'http://' in response or 'https://' in response:
            return True
    
    return False

def evaluate_response(query: str, response: str, config, chat_models, response_type="general") -> bool:
    """
    Use LLM to evaluate if a response adequately answers the user's query.
    Returns True if the response is adequate, False otherwise.
    
    The evaluation strictness depends on the current tolerance level.
    """
    # For raw MCP/browser responses, we should always process them first
    if response_type in ["browser", "mcp"] or is_raw_mcp_response(response):
        print(f"{config.CYAN}Detected raw browser/MCP response, skipping evaluation...{config.RESET}")
        return True
    
    # Store response in context for potential future use
    _response_context['previous_responses'].append({
        'query': query,
        'response': response[:500] if len(response) > 500 else response,  # Store truncated version
        'timestamp': datetime.now().isoformat()
    })
    
    # Adjust evaluation criteria based on tolerance level
    tolerance = _response_context['tolerance_level']
    
    if tolerance == 'lenient':
        strictness = "Be lenient in your evaluation. Accept responses that provide some useful information, even if not complete."
        threshold = 0.6  # Lower threshold for acceptance
    elif tolerance == 'strict':
        strictness = "Be very strict in your evaluation. Only accept responses that fully and accurately answer the question."
        threshold = 0.9  # Higher threshold for acceptance
    else:  # medium (default)
        strictness = "Use balanced judgment in your evaluation. For programming and technical questions, strongly prefer to accept built-in knowledge responses rather than forcing web searches. Accept responses that adequately address the main points."
        threshold = 0.85  # Higher threshold for direct knowledge answers to reduce browser fallback
    
    evaluation = chat_with_model(
        message=(
            f"User Query: {query}\n\n"
            f"Response: {response}\n\n"
            "Rate how well this response answers the user's question on a scale of 0.0 to 1.0, where:\n"
            "- 0.0 means completely inadequate/irrelevant\n"
            "- 1.0 means perfect and complete answer\n\n"
            "Consider:\n"
            "1. Does it directly address what was asked?\n"
            "2. Does it provide actionable information?\n"
            "3. Is it specific enough to be useful?\n"
            "4. For CLI commands, does it provide the correct command?\n"
            "5. For search results, does it provide relevant information?\n"
            "Respond with ONLY a number between 0.0 and 1.0."
        ),
        config=config,
        chat_models=chat_models,
        system_prompt=(
            f"You are a response quality evaluator. {strictness} "
            "For CLI commands, ensure they are correct and complete. "
            "For search results, ensure they provide relevant information."
        )
    )
    
    try:
        # Extract numeric score from response
        score = float(evaluation.strip())
        print(f"Response quality score: {score:.2f} (threshold: {threshold:.2f})")
        return score >= threshold
    except ValueError:
        # Fallback to simple yes/no if numeric parsing fails
        return evaluation.strip().lower() == 'yes'

def get_fallback_response(query: str, original_response: str, config, chat_models) -> str:
    """
    Get a more helpful response from the fallback LLM, using previous responses as context.
    """
    # Gather context from previous responses
    context = ""
    if _response_context['previous_responses']:
        # Get up to 3 most recent previous responses as context
        recent_responses = _response_context['previous_responses'][-3:]
        context = "Information from previous responses:\n"
        for i, resp in enumerate(recent_responses):
            if resp['query'] != query:  # Skip duplicates of current query
                context += f"Response {i+1}: {resp['response'][:300]}...\n\n"
    
    # Add any collected information from tools
    tool_info = ""
    if _response_context['collected_info']:
        tool_info = "Information collected from tools:\n"
        for tool, info in _response_context['collected_info'].items():
            tool_info += f"- {tool}: {str(info)[:300]}...\n"
    
    return chat_with_model(
        message=(
            f"Original query: {query}\n\n"
            f"Previous response: {original_response}\n\n"
            f"{context}\n"
            f"{tool_info}\n"
            "This response was deemed inadequate. Please provide a more helpful response that:\n"
            "1. Directly addresses the user's question\n"
            "2. Provides specific, actionable information\n"
            "3. Draws from your knowledge and the context provided\n"
            "4. For CLI commands, provides the exact command needed\n"
            "5. For general queries, provides comprehensive information\n"
            "6. Incorporates any useful information from previous responses"
        ),
        config=config,
        chat_models=chat_models,
        system_prompt=(
            "You are a helpful expert assistant. Provide detailed, accurate responses "
            "that directly address the user's needs. If the query is about software or "
            "system operations, include specific steps or commands when appropriate. "
            "Use any relevant information from previous responses to improve your answer."
        )
    )

def format_browser_response(query: str, response, config, chat_models) -> str:
    """Format a raw browser/MCP response into a more readable format.

    Args:
        query: The original user query
        response: The raw browser/MCP response (can be string or dict)
        config: Configuration object
        chat_models: Chat models to use
    """
    try:
        # First handle different input types
        if isinstance(response, str):
            # If response is already a simple text/markdown string, just return it
            if not response.strip().startswith('{') and not response.strip().startswith('['):
                print(f"{config.GREEN}Response is already formatted text/markdown{config.RESET}")
                return response

            print(f"{config.YELLOW}Response is a string, attempting to parse as JSON{config.RESET}")
            try:
                result = json.loads(response)
                print(f"{config.GREEN}Successfully parsed response as JSON{config.RESET}")
            except json.JSONDecodeError:
                print(f"{config.RED}Failed to parse response as JSON, returning as plain text{config.RESET}")
                return f"Content from web:\n\n{response[:3000]}" if len(response) > 3000 else response
        elif isinstance(response, dict):
            print(f"{config.GREEN}Response is already a dictionary{config.RESET}")
            result = response
        else:
            print(f"{config.RED}Unknown response type: {type(response).__name__}{config.RESET}")
            return f"Error: Unknown response type {type(response).__name__}"

        # Simplified format - just return as markdown
        formatted = []

        # Add title as heading
        if title := result.get("title"):
            formatted.append(f"# {title}\n")
        else:
            formatted.append("# Web Content\n")

        # Add URL
        if url := result.get("url"):
            formatted.append(f"Source: {url}\n")

        # Handle simple text content first (simpler approach)
        if text_content := result.get("text_content"):
            formatted.append(text_content)

        # Handle structured content next
        elif content := result.get("content"):
            # Handle content based on type
            if isinstance(content, str):
                # If it's just a string, add it directly
                formatted.append(content)
            elif isinstance(content, list):
                for item in content:
                    if isinstance(item, dict):
                        # Handle sections and stories
                        if item.get("type") == "section" and item.get("title"):
                            formatted.append(f"\n## {item['title']}\n")

                            # Add blocks
                            if "blocks" in item and isinstance(item["blocks"], list):
                                for block in item["blocks"]:
                                    if isinstance(block, dict):
                                        if block.get("type") == "text" and block.get("text"):
                                            formatted.append(block["text"])
                                        elif block.get("type") == "link" and block.get("url"):
                                            formatted.append(f"[{block.get('text', block['url'])}]({block['url']})")

                        # Handle story type (common in Hacker News)
                        elif item.get("type") == "story":
                            formatted.append(f"\n## {item.get('title', 'Story')}\n")

                            # Add metadata
                            if metadata := item.get("metadata"):
                                for key, value in metadata.items():
                                    formatted.append(f"**{key.capitalize()}**: {value}")

                            # Add URL
                            if url := item.get("url"):
                                formatted.append(f"\n[Read more]({url})")

                        # Default case - just use whatever we find
                        else:
                            for key, value in item.items():
                                if key != "type" and isinstance(value, str):
                                    formatted.append(value)
                    elif isinstance(item, str):
                        # Add strings directly
                        formatted.append(item)
            else:
                # Just add it as a string
                formatted.append(str(content))

        # If still no content, return a simple message
        if len(formatted) <= 2:  # Only title and URL
            print(f"{config.RED}No content found in the response{config.RESET}")
            return "No content found. The page might be empty or require authentication."

        final_text = "\n\n".join(formatted)
        print(f"{config.GREEN}Successfully formatted response with {len(final_text)} characters{config.RESET}")
        return final_text
    except Exception as e:
        print(f"{config.RED}Error in format_browser_response: {str(e)}{config.RESET}")
        # Try to return something useful even if formatting fails
        if isinstance(response, str):
            return response[:3000] + "..." if len(response) > 3000 else response
        elif isinstance(response, dict):
            if "text_content" in response:
                return response["text_content"]
            return str(response)
        else:
            return f"Error formatting response: {str(e)}. Unknown response type."

def process_response(query: str, response: str, config, chat_models, allow_browser_fallback=True, response_type="general") -> str:
    """
    Process a response through evaluation and fallback if needed.
    Returns the final response to use.
    
    Args:
        query: The original user query
        response: The response to evaluate
        config: Configuration object
        chat_models: Chat models to use
        allow_browser_fallback: Whether to allow browser fallback if response is inadequate
        response_type: Type of response - "general", "cli", "browser", or "mcp"
    """
    # For raw browser/MCP responses, format them first
    if response_type in ["browser", "mcp"] or is_raw_mcp_response(response):
        try:
            return format_browser_response(query, response, config, chat_models)
        except Exception as e:
            print(f"{config.YELLOW}Error formatting browser response: {str(e)}. Using raw response.{config.RESET}")
            # Return at least something if formatting fails
            if isinstance(response, str) and len(response) > 500:
                return f"Error formatting response: {str(e)}. Raw data (truncated):\n\n{response[:500]}..."
            return f"Error formatting response: {str(e)}. Please try a different query."
    
    # For general and CLI responses, evaluate and use fallbacks if needed
    try:
        if not evaluate_response(query, response, config, chat_models, response_type):
            print(f"{config.YELLOW}Initial response was inadequate. Getting better response...{config.RESET}")
            
            # Try fallback LLM first
            try:
                improved_response = get_fallback_response(query, response, config, chat_models)
            except Exception as e:
                print(f"{config.YELLOW}Error getting fallback response: {str(e)}. Using original response.{config.RESET}")
                improved_response = response
            
            # If fallback still inadequate and browser fallback is allowed, try browser
            # But be more conservative with programming/technical requests
            if (allow_browser_fallback and 
                not evaluate_response(query, improved_response, config, chat_models, response_type) and
                not any(term in query.lower() for term in ['create', 'build', 'make', 'code', 'program', 'python', 'javascript', 'java', 'typescript', 'next.js', 'react'])):
                if _response_context['browser_attempts'] < 2:  # Limit browser attempts
                    print(f"{config.YELLOW}Fallback response still inadequate. Trying browser search...{config.RESET}")
                    _response_context['browser_attempts'] += 1
                    
                    # Try browser search
                    try:
                        browser_response = try_browser_search(query, config, chat_models)
                        if browser_response:
                            # Store browser result in context
                            _response_context['collected_info']['browser_search'] = browser_response[:500]  # Store truncated version
                            
                            try:
                                # Format the browser response
                                formatted_browser = format_browser_response(query, browser_response, config, chat_models)
                                
                                # Determine if we're using a local model like Ollama
                                is_local_model = config.session_model == 'ollama' if hasattr(config, 'session_model') else False
                                
                                if is_local_model:
                                    # Simpler prompt structure for local models
                                    message = (
                                        f"Question: {query}\n\n"
                                        f"Web content: {formatted_browser}\n\n"
                                        "Provide a direct answer based on this information using bullet points. Be concise."
                                    )
                                    system_prompt = (
                                        "You are summarizing web content. Present information as a clear, concise list. "
                                        "Use bullet points for key information. If the content doesn't answer the question well, "
                                        "state that clearly and use your built-in knowledge instead."
                                    )
                                else:
                                    # Standard prompt for cloud models
                                    message = (
                                        f"Original query: {query}\n\n"
                                        f"Previous responses: {improved_response}\n\n"
                                        f"Browser search results: {formatted_browser}\n\n"
                                        "Combine all this information to provide the most accurate and complete response."
                                    )
                                    system_prompt = (
                                        "You are a helpful expert assistant. Synthesize information from multiple sources "
                                        "to provide the most accurate and complete response to the user's query."
                                    )
                                
                                # Combine browser results with previous knowledge
                                final_response = chat_with_model(
                                    message=message,
                                    config=config,
                                    chat_models=chat_models,
                                    system_prompt=system_prompt
                                )
                                return final_response
                            except Exception as e:
                                print(f"{config.YELLOW}Error combining responses: {str(e)}. Using browser response.{config.RESET}")
                                # If combination fails, return the browser response directly
                                return f"Information from web search:\n\n{browser_response[:1000]}..."
                    except Exception as e:
                        print(f"{config.YELLOW}Browser search failed: {str(e)}. Using fallback response.{config.RESET}")
                else:
                    print(f"{config.YELLOW}Maximum browser attempts reached. Using best available response.{config.RESET}")
            
            return improved_response
        return response
    except Exception as e:
        print(f"{config.RED}Error processing response: {str(e)}{config.RESET}")
        # Return original response if processing fails
        return f"Error processing response: {str(e)}. Original response: {response[:500]}..."

def try_browser_search(query: str, config, chat_models) -> str:
    """Attempt to use browser search to find an answer or final answer."""
    search_query = query
    # Clean up query for search
    for term in ['search', 'find', 'lookup', 'what is', 'how to', 'browse']:
        search_query = search_query.replace(term, '').strip()

    # Check for direct site visits
    if "hacker news" in search_query.lower() or "hackernews" in search_query.lower() or "hn" in search_query.lower():
        url = "https://news.ycombinator.com/"
        print(f"{config.CYAN}Detected Hacker News request. Will prioritize accordingly.{config.RESET}")
    elif "reddit" in search_query.lower():
        url = f"https://www.reddit.com/search/?q={search_query.replace('reddit', '').replace(' ', '+')}"
    elif "github" in search_query.lower():
        url = f"https://github.com/search?q={search_query.replace('github', '').replace(' ', '+')}"
    else:
        # Default to Google search
        url = f"https://www.google.com/search?q={search_query.replace(' ', '+')}"

    print(f"{config.CYAN}Trying browser search for: {search_query}{config.RESET}")
    print(f"{config.CYAN}Using URL: {url}{config.RESET}")

    # Priority 1: Special direct scraper for Hacker News
    if "news.ycombinator.com" in url:
        try:
            print(f"{config.GREEN}Priority 1: Using direct Hacker News scraper...{config.RESET}")
            from .utils import direct_scrape_hacker_news
            result = direct_scrape_hacker_news(url)
            if result:
                print(f"{config.GREEN}Direct Hacker News scraper returned content successfully!{config.RESET}")
                # Return a simpler format when possible
                try:
                    if isinstance(result, str) and result.strip().startswith('{'):
                        parsed = json.loads(result)
                        # Check if we can simplify further
                        if parsed.get("content") and parsed.get("title"):
                            simplified = f"# {parsed.get('title')}\n\n"
                            for section in parsed.get("content", []):
                                if section.get("type") == "section" and section.get("title"):
                                    simplified += f"## {section['title']}\n\n"
                                    for block in section.get("blocks", []):
                                        if block.get("type") == "text":
                                            simplified += f"{block.get('text', '')}\n\n"
                            return simplified
                except:
                    pass
                return result
        except Exception as e:
            print(f"{config.YELLOW}Direct Hacker News scraper failed: {str(e)}. Trying web fetcher...{config.RESET}")

    # Priority 2: General web fetcher
    try:
        print(f"{config.GREEN}Priority 2: Using web fetcher for {url}...{config.RESET}")
        from .web_fetcher import fetcher
        result = fetcher.fetch_and_process(url, mode="detailed", use_cache=True)
        if result:
            print(f"{config.GREEN}Web fetcher returned content successfully!{config.RESET}")
            # Try to return a simple text format when possible
            if isinstance(result, dict):
                if result.get("text_content"):
                    # For simpler models, just return text
                    if hasattr(config, 'session_model') and config.session_model == 'ollama':
                        return f"# {result.get('title', 'Web Content')}\n\n{result.get('text_content')}"

                # Otherwise create a more structured response
                formatted_result = {
                    "type": "webpage",
                    "url": url,
                    "title": result.get("title", "No title"),
                    "content": result.get("text_content", "")
                }

                # Add some simple markdown formatting
                formatted_text = f"# {formatted_result['title']}\n\n"
                formatted_text += f"Source: {url}\n\n"

                # Add main content
                formatted_text += formatted_result['content']

                # Return the simple text format
                return formatted_text
            return result
    except Exception as e:
        print(f"{config.YELLOW}Web fetcher failed: {str(e)}. Trying MCP browser tool...{config.RESET}")

    # Priority 3: MCP browser tool as final fallback
    try:
        print(f"{config.GREEN}Priority 3: Using MCP browser tool for {url}...{config.RESET}")
        response = use_mcp_tool(
            server_name="small-context",
            tool_name="browse_web",
            arguments={"url": url}
        )
        if response:
            print(f"{config.GREEN}MCP browser tool returned content successfully!{config.RESET}")
            # Try to simplify the format
            if isinstance(response, str):
                # If it's already a string that's not JSON, just return it
                if not (response.strip().startswith('{') and response.strip().endswith('}')):
                    return response

                # Try to parse as JSON and simplify
                try:
                    parsed = json.loads(response)
                    # Check if we can extract a simpler format
                    if isinstance(parsed, dict):
                        if parsed.get("content"):
                            # Extract simple text
                            simple_text = f"# {parsed.get('title', 'Web Content')}\n\n"
                            simple_text += f"Source: {parsed.get('url', url)}\n\n"

                            # Extract content
                            if isinstance(parsed["content"], str):
                                simple_text += parsed["content"]
                            elif isinstance(parsed["content"], list):
                                for item in parsed["content"]:
                                    if isinstance(item, dict) and item.get("text"):
                                        simple_text += f"{item['text']}\n\n"

                            return simple_text
                except:
                    # If parsing fails, just return the original
                    pass

            return response
    except Exception as e:
        print(f"{config.YELLOW}MCP browser tool failed: {str(e)}.{config.RESET}")

    # All methods failed, return error
    return f"Failed to retrieve content from {url}. This could be due to network issues, site restrictions, or the site requiring authentication."

def handle_cli_command(query: str, config, chat_models) -> str:
    """Handle CLI command generation and evaluation."""
    response = chat_with_model(
        query,
        config=config,
        chat_models=chat_models,
        system_prompt=(
            "You are a CLI expert. If this request can be handled with CLI commands, "
            "provide the appropriate command wrapped in ```bash\n[command]\n``` markers. "
            "If no CLI command is suitable, respond with 'NO_CLI_COMMAND'."
        )
    )
    
    if "NO_CLI_COMMAND" not in response:
        print(f"{config.CYAN}Generated CLI command, evaluating...{config.RESET}")
        processed_response = process_response(query, response, config, chat_models, response_type="cli")
        # Ensure CLI commands are returned properly
        return processed_response
    return response

def handle_web_search(query: str, response: str, config, chat_models) -> str:
    """Handle web search result evaluation."""
    print(f"{config.CYAN}Processing search result...{config.RESET}")
    return process_response(query, response, config, chat_models, allow_browser_fallback=False, response_type="browser")

def get_search_url(query):
    """Generate a search URL from a query."""
    search_terms = ['search', 'find', 'lookup', 'what is', 'how to']
    if any(term in query.lower() for term in search_terms):
        search_query = query
        for term in search_terms:
            search_query = search_query.replace(term, '').strip()
        return f"https://www.google.com/search?q={search_query}"
    return None

def _validate_query(query: str) -> bool:
    """Validate that the query is not empty and contains actual content."""
    return bool(query and query.strip())

def process_input_based_on_mode(user_input: str, config: Any) -> str:
    """Process user input based on the current mode."""
    # Initialize chat models
    from .chat_models import initialize_chat_models, chat_with_model
    chat_models = initialize_chat_models(config)
    
    # Reset browser attempts counter for new queries
    browser_attempts = 0
    
    # Smart Query Routing - Classify query before processing
    from .query_router import QueryRouter
    from .llm_query_router import LLMQueryRouter
    from .web_search import WebSearchHandler, format_search_response
    
    # Try LLM-based routing first if we have a chat model
    route_info = None
    if chat_models and 'model' in chat_models:
        try:
            llm_router = LLMQueryRouter(chat_models['model'], config.session_model)
            route_info = llm_router.classify_query(user_input)
            print(f"{config.GREEN}LLM routing decision: {route_info['route']} ({route_info.get('reason', 'no reason')}){config.RESET}")
        except Exception as e:
            print(f"{config.YELLOW}LLM routing failed: {e}. Falling back to pattern matching.{config.RESET}")
    
    # Fallback to pattern-based routing if LLM routing fails
    if not route_info:
        router = QueryRouter()
        route_info = router.classify_query(user_input)
        print(f"{config.YELLOW}Pattern routing decision: {route_info['route']} ({route_info.get('reason', 'no reason')}){config.RESET}")
    
    config.route_info = route_info  # Store for use by chat models
    
    # Check for session management commands
    if user_input.lower() == 'history':
        return display_session_history(config)
    elif user_input.lower().startswith('recall '):
        try:
            index = int(user_input.lower().replace('recall ', '').strip())
            return recall_history_item(config, index)
        except ValueError:
            print(f"{config.YELLOW}Please provide a valid index number.{config.RESET}")
            return "Invalid recall index. Use 'history' to see available items."
    elif user_input.lower() == 'session status':
        return display_session_status(config)
    
    # Route-specific processing based on query classification
    if route_info['route'] == 'web_search':
        print(f"{config.CYAN}🔍 Web search route detected: {route_info['reason']}{config.RESET}")
        web_handler = WebSearchHandler()
        search_result = web_handler.search_web(user_input)
        formatted_response = format_search_response(search_result)
        print_streamed_message(formatted_response, config.CYAN)
        return formatted_response
    
    elif route_info['route'] == 'simple_command':
        print(f"{config.CYAN}⚡ Simple command route detected: {route_info['reason']}{config.RESET}")
        # Use enhanced prompt for simple command processing
        enhanced_prompt = router.get_enhanced_prompt(user_input, route_info)
        from .chat_models import chat_with_model
        llm_response = chat_with_model(enhanced_prompt, config, chat_models)
        
        # Extract and execute the command directly
        command_response = handle_simple_command_execution(llm_response, user_input, config)
        print_streamed_message(command_response, config.CYAN)
        return command_response
    
    elif route_info['route'] == 'direct_llm':
        print(f"{config.CYAN}💡 Direct LLM route detected: {route_info['reason']}{config.RESET}")
        # Use enhanced prompt for direct LLM processing
        enhanced_prompt = router.get_enhanced_prompt(user_input, route_info)
        from .chat_models import chat_with_model
        llm_response = chat_with_model(enhanced_prompt, config, chat_models)
        print_streamed_message(llm_response, config.CYAN)
        return llm_response
    
    elif route_info['route'] == 'tool_selection':
        print(f"{config.CYAN}🔧 Tool selection route detected: {route_info['reason']}{config.RESET}")
        # Fall through to ContextAgent processing with routing metadata
        pass
    
    # Continue with existing processing for other routes
    # Direct command to browse a site (special handler for local models)
    elif user_input.lower().startswith(('browse ', '@browse ', '@ browse ')):
        # Extract the site name - handle "using the browse tool" and similar phrases
        site_query = user_input.lower()
        for phrase in ['browse', '@', 'using the', 'with the', 'tool', 'browse tool']:
            site_query = site_query.replace(phrase, '').strip()

        print(f"{config.CYAN}Direct browse command detected for: {site_query}{config.RESET}")

        # Check for specific sites
        if "hacker news" in site_query or "hackernews" in site_query or "hn" in site_query:
            url = "https://news.ycombinator.com/"
            clean_query = "hacker news"
        elif "reddit" in site_query:
            search_terms = site_query.replace('reddit', '').strip()
            url = f"https://www.reddit.com/search/?q={search_terms}" if search_terms else "https://www.reddit.com/"
            clean_query = f"reddit {search_terms}" if search_terms else "reddit"
        elif "github" in site_query:
            search_terms = site_query.replace('github', '').strip()
            url = f"https://github.com/search?q={search_terms}" if search_terms else "https://github.com/"
            clean_query = f"github {search_terms}" if search_terms else "github"
        elif "." in site_query and " " not in site_query:
            # If it looks like a domain, add https://
            url = f"https://{site_query}"
            clean_query = site_query
        else:
            # For any other site, treat as a search
            url = f"https://www.google.com/search?q={site_query}"
            clean_query = site_query

        # Directly use the browser search function
        print(f"{config.CYAN}Direct browsing: {url}{config.RESET}")

        # Priority 1: Try MCP tool first
        try:
            from .utils import use_mcp_tool

            print(f"{config.CYAN}Using MCP browse_web tool for {url}...{config.RESET}")
            mcp_result = use_mcp_tool(
                server_name="small-context",
                tool_name="browse_web",
                arguments={"url": url}
            )

            if mcp_result:
                try:
                    # Format and return the result
                    formatted_response = format_browser_response(clean_query, mcp_result, config, chat_models)

                    # Print the response
                    print_streamed_message(formatted_response, config.CYAN, config)
                    return formatted_response
                except Exception as format_error:
                    print(f"{config.YELLOW}Error formatting MCP browser response: {str(format_error)}. Trying fallback methods...{config.RESET}")
            else:
                print(f"{config.YELLOW}MCP tool returned no result. Trying fallback methods...{config.RESET}")
        except Exception as mcp_error:
            print(f"{config.YELLOW}MCP browse_web tool failed: {str(mcp_error)}. Trying fallback methods...{config.RESET}")

        # Priority 2: Special direct HTML scrape for Hacker News as fallback
        if "news.ycombinator.com" in url:
            from .utils import direct_scrape_hacker_news

            print(f"{config.CYAN}Using direct Hacker News scraper...{config.RESET}")

            try:
                # Import required libraries
                import requests
                from bs4 import BeautifulSoup
                # json is imported at function scope

                # Fetch the page directly
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

                    title_element = story.select_one('td.title > span.titleline > a')
                    if not title_element:
                        continue

                    title = title_element.text.strip()
                    link = title_element.get('href', '')

                    # Skip empty stories
                    if not title:
                        continue

                    # Format each story
                    stories.append(f"• {title}")

                # Build a simple, direct response
                response = "# Top Stories from Hacker News\n\n"
                response += "\n".join(stories)
                response += "\n\nSource: https://news.ycombinator.com/"

                print(f"{config.GREEN}Successfully scraped Hacker News directly.{config.RESET}")

                # In autopilot mode, ensure we print the response directly to console
                if hasattr(config, 'autopilot_mode') and config.autopilot_mode:
                    print("\n" + response + "\n")

                # Also stream the message to ensure it's visible
                print_streamed_message(response, config.CYAN, config)

                return response

            except Exception as e:
                print(f"{config.YELLOW}Direct HN scraper failed: {str(e)}. Trying final fallback method...{config.RESET}")

        # Priority 3: For all other cases or if above methods failed, use the browser search function
        try:
            browser_response = try_browser_search(clean_query, config, chat_models)

            if browser_response:
                # Process the browser response
                if isinstance(browser_response, str) and len(browser_response) > 100000:
                    # Truncate extremely long responses to avoid timeouts
                    print(f"{config.YELLOW}Response too large ({len(browser_response)} chars), truncating...{config.RESET}")
                    browser_response = browser_response[:100000] + "... [content truncated]"
                
                try:
                    # Check if it's JSON and simplify if needed
                    # Rely on top-level import json
                    if browser_response.strip().startswith('{') and browser_response.strip().endswith('}'):
                        data = json.loads(browser_response)
                        
                        # For Ollama and other local models, create a simpler response
                        if config.session_model == 'ollama':
                            # Create a simplified text response
                            simple_response = f"# Content from {url}\n\n"
                            
                            # Add title if available
                            if "title" in data:
                                simple_response += f"## {data['title']}\n\n"
                            
                            # Add main content
                            if "content" in data and isinstance(data["content"], list):
                                for section in data["content"][:5]:  # Limit sections
                                    if isinstance(section, dict):
                                        if "title" in section:
                                            simple_response += f"### {section['title']}\n\n"
                                        if "blocks" in section and isinstance(section["blocks"], list):
                                            for block in section["blocks"]:
                                                if isinstance(block, dict) and "text" in block:
                                                    simple_response += f"{block['text'][:500]}...\n\n"
                            elif "text_content" in data and data["text_content"]:
                                # Truncate and add the text content
                                content = data["text_content"]
                                simple_response += content[:1000] + "...\n\n" if len(content) > 1000 else content
                            
                            return simple_response
                except Exception as e:
                    print(f"{config.YELLOW}Error simplifying response: {str(e)}{config.RESET}")

                # Try formatting directly without timeout
                try:
                    formatted_response = format_browser_response(clean_query, browser_response, config, chat_models)
                    return formatted_response
                except Exception as e:
                    print(f"{config.RED}Error formatting response: {str(e)}{config.RESET}")
                    # Fallback if formatting fails
                    safe_response = browser_response if isinstance(browser_response, str) else str(browser_response)
                    return f"Error formatting the browser response. Raw data first 1000 chars:\n\n{safe_response[:1000]}..."
            else:
                return f"Failed to browse {clean_query}. Please try a different search term."
        except Exception as e:
            print(f"{config.RED}Error in direct browse handler: {str(e)}{config.RESET}")
            return f"Error browsing {site_query}: {str(e)}"

    # Check for tolerance level commands
    elif user_input.lower().startswith("set tolerance "):
        level = user_input.lower().replace("set tolerance ", "").strip()
        set_evaluation_tolerance(level)
        print(f"{config.GREEN}Tolerance level set to: {level}{config.RESET}")
        return f"Tolerance level set to: {level}"

    # Validate query
    if not _validate_query(user_input):
        print(f"{config.YELLOW}Please provide a command or question.{config.RESET}")
        return "Please provide a command or question."

    # Check if this is a request to view specific cached content
    if _content_cache['raw_content'] and any(word in user_input.lower() for word in ['show', 'view', 'read', 'tell', 'about']):
        matching_content = _find_matching_content(user_input)
        if matching_content:
            # Box dimensions - adjust based on content
            box_width = min(100, max(60, len(matching_content.split('\n')[0]) + 4))
            box_height = min(20, len(matching_content.split('\n')) + 2)
            
            # Create a boxed display
            boxed_content = "\n" + "═" * box_width + "\n"
            boxed_content += "║ " + matching_content.replace("\n", "\n║ ") + "\n"
            boxed_content += "═" * box_width + "\n"
            
            return boxed_content

    # Check if this is a follow-up question about cached content
    if _content_cache['formatted_content'] and not user_input.lower().startswith(("get", "fetch", "find")):
        # Process as a question about the cached content
        llm_response = chat_with_model(
            message=(
                f"Based on this content:\n\n{_content_cache['formatted_content']}\n\n"
                f"User question: {user_input}\n\n"
                "Provide a clear and focused answer. If the question is about a specific topic or article, "
                "include relevant quotes and links from the content. After your answer, suggest 2-3 relevant "
                "follow-up questions the user might want to ask."
            ),
            config=config,
            chat_models=chat_models
        )
        return llm_response

    # Check if this is explicitly a browser request
    is_browser_request = any(term in user_input.lower() for term in ['browse', 'open website', 'go to', 'visit'])

    # First try CLI commands for system operations (unless it's a browser request)
    if not is_browser_request and any(word in user_input.lower() for word in ['install', 'setup', 'configure', 'run', 'start', 'stop', 'restart']):
        response = handle_cli_command(user_input, config, chat_models)
        if "NO_CLI_COMMAND" not in response:
            return response

    try:
        agent = ContextAgent()
        # Pass routing metadata if available
        routing_metadata = route_info if route_info.get('route') == 'tool_selection' else None
        analysis = agent.analyze_request(user_input, routing_metadata=routing_metadata)
        
        # Validate analysis object
        if not analysis or not isinstance(analysis, dict) or "prompt" not in analysis:
            # Fall back to direct LLM processing if analysis fails
            print(f"{config.YELLOW}Failed to generate valid analysis from ContextAgent.{config.RESET}")
            llm_response = chat_with_model(message=user_input, config=config, chat_models=chat_models)
            final_response = process_response(user_input, llm_response, config, chat_models, allow_browser_fallback=True)
            print_streamed_message(final_response, config.CYAN)
            return final_response

        # Extract the prompt from the analysis
        llm_analysis = analysis.get("prompt", "")
        
        # Debug output for tool selection route
        if route_info.get('route') == 'tool_selection':
            print(f"{config.CYAN}ContextAgent routing metadata: {routing_metadata}{config.RESET}")
        
        if not llm_analysis:
            print(f"{config.YELLOW}No response received from tool selection LLM analysis.{config.RESET}")
            llm_response = chat_with_model(message=user_input, config=config, chat_models=chat_models)
            final_response = process_response(user_input, llm_response, config, chat_models, allow_browser_fallback=True)
            print_streamed_message(final_response, config.CYAN)
            return final_response

        # Send the prompt to the LLM for tool selection
        print(f"{config.CYAN}Sending to LLM for tool selection...{config.RESET}")
        tool_selection_response = chat_with_model(
            message=llm_analysis,
            config=config,
            chat_models=chat_models
        )
        
        # Debug: show what the LLM returned
        if route_info.get('route') == 'tool_selection':
            print(f"{config.CYAN}LLM raw response: {tool_selection_response[:200]}...{config.RESET}")
        
        # Try to extract JSON from the LLM response
        try:
            # First try direct JSON parsing
            try:
                tool_selection = json.loads(tool_selection_response)
            except json.JSONDecodeError:
                # Try to extract JSON from markdown code blocks
                json_content = extract_json_from_response(tool_selection_response)
                if json_content:
                    try:
                        tool_selection = json.loads(json_content)
                    except json.JSONDecodeError:
                        # If that fails, try to repair the JSON
                        repaired_json, was_repaired = attempt_json_repair(json_content)
                        if was_repaired:
                            tool_selection = json.loads(repaired_json)
                        else:
                            raise ValueError("Could not parse tool selection JSON")
                else:
                    # If that fails, try to repair the original JSON
                    repaired_json, was_repaired = attempt_json_repair(tool_selection_response)
                    if was_repaired:
                        tool_selection = json.loads(repaired_json)
                    else:
                        raise ValueError("Could not parse tool selection JSON")

            # Debug output for tool selection
            if route_info.get('route') == 'tool_selection':
                print(f"{config.CYAN}LLM tool selection JSON: {json.dumps(tool_selection, indent=2)}{config.RESET}")
            
            # Validate the tool selection
            if not isinstance(tool_selection, dict):
                raise ValueError("Tool selection is not a dictionary")

            # Extract tool information
            tool_name = tool_selection.get("tool", "")
            url = tool_selection.get("url", "")
            arguments = tool_selection.get("arguments", {})

            # Validate required fields
            if not tool_name:
                raise ValueError("No tool name provided in selection")

            # Handle different tool types
            if tool_name == "browse_web":
                if not url or url == "[URL will be determined based on request]":
                    print(f"{config.RED}No valid URL provided in tool selection.{config.RESET}")
                    llm_response = chat_with_model(message=user_input, config=config, chat_models=chat_models)
                    final_response = process_response(user_input, llm_response, config, chat_models, allow_browser_fallback=True)
                    print_streamed_message(final_response, config.CYAN)
                    return final_response

                # Use the MCP tool for web browsing
                try:
                    from .utils import use_mcp_tool
                    mcp_result = use_mcp_tool(
                        server_name="small-context",
                        tool_name="browse_web",
                        arguments={"url": url}
                    )

                    if mcp_result:
                        try:
                            # Format and return the result
                            formatted_response = format_browser_response(user_input, mcp_result, config, chat_models)
                            print_streamed_message(formatted_response, config.CYAN)
                            return formatted_response
                        except Exception as format_error:
                            print(f"{config.YELLOW}Error formatting MCP browser response: {str(format_error)}. Trying fallback methods...{config.RESET}")
                    else:
                        print(f"{config.YELLOW}MCP tool returned no result. Trying fallback methods...{config.RESET}")
                except Exception as mcp_error:
                    print(f"{config.YELLOW}MCP browse_web tool failed: {str(mcp_error)}. Trying fallback methods...{config.RESET}")

                # Fallback to direct browser search
                try:
                    browser_response = try_browser_search(user_input, config, chat_models)
                    if browser_response:
                        formatted_response = format_browser_response(user_input, browser_response, config, chat_models)
                        print_streamed_message(formatted_response, config.CYAN)
                        return formatted_response
                except Exception as browser_error:
                    print(f"{config.YELLOW}Browser search failed: {str(browser_error)}. Falling back to LLM...{config.RESET}")

            elif tool_name == "memory":
                # Handle memory operations
                operation = tool_selection.get("operation", "")
                
                if not operation:
                    print(f"{config.RED}No memory operation specified.{config.RESET}")
                    return "Please specify a memory operation (create_entities, add_observations, search_nodes, read_graph)"
                
                try:
                    from .utils import use_mcp_tool
                    
                    # Build arguments based on operation
                    mcp_arguments = {}
                    if operation == "create_entities":
                        mcp_arguments["entities"] = tool_selection.get("entities", [])
                    elif operation == "add_observations":
                        mcp_arguments["observations"] = tool_selection.get("observations", [])
                    elif operation == "search_nodes":
                        mcp_arguments["query"] = tool_selection.get("query", "")
                    elif operation == "read_graph":
                        pass  # No arguments needed
                    elif operation == "open_nodes":
                        mcp_arguments["names"] = tool_selection.get("names", [])
                    elif operation == "create_relations":
                        mcp_arguments["relations"] = tool_selection.get("relations", [])
                    elif operation == "delete_entities":
                        mcp_arguments["names"] = tool_selection.get("names", [])
                    elif operation == "delete_observations":
                        mcp_arguments["deletions"] = tool_selection.get("deletions", [])
                    elif operation == "delete_relations":
                        mcp_arguments["relation_ids"] = tool_selection.get("relation_ids", [])
                    
                    mcp_result = use_mcp_tool(
                        server_name="memory",
                        tool_name=operation,
                        arguments=mcp_arguments
                    )
                    
                    if mcp_result:
                        print_streamed_message(mcp_result, config.CYAN)
                        return mcp_result
                    else:
                        return f"Memory operation '{operation}' completed but returned no result"
                        
                except Exception as memory_error:
                    print(f"{config.RED}Memory operation failed: {str(memory_error)}{config.RESET}")
                    return f"Error executing memory operation: {str(memory_error)}"
            
            elif tool_name == "generate_script":
                # Format as a shell script
                llm_response = chat_with_model(
                    message=user_input,
                    config=config,
                    chat_models=chat_models,
                    system_prompt=(
                        "You are a helpful assistant that generates shell scripts. "
                        "Provide only the script content, no explanations. "
                        "Make sure the script is executable and follows best practices."
                    )
                )
                return llm_response

            elif tool_name == "execute_command":
                # Default to standard LLM processing with shell command generation
                llm_response = chat_with_model(
                    message=user_input,
                    config=config,
                    chat_models=chat_models,
                    system_prompt=(
                        "You are a helpful assistant that generates shell commands. "
                        "Provide only the command, no explanations. "
                        "Make sure the command is safe and follows best practices."
                    )
                )
                return llm_response

            else:
                # Default to standard LLM processing
                llm_response = chat_with_model(message=user_input, config=config, chat_models=chat_models)
                final_response = process_response(user_input, llm_response, config, chat_models, allow_browser_fallback=True)
                print_streamed_message(final_response, config.CYAN)
                return final_response

        except Exception as e:
            # Fallback if JSON extraction fails
            llm_response = chat_with_model(message=user_input, config=config, chat_models=chat_models)
            final_response = process_response(user_input, llm_response, config, chat_models, allow_browser_fallback=True)
            print_streamed_message(final_response, config.CYAN)
            return final_response

    except Exception as e:
        print(f"{config.RED}Error in main processing: {str(e)}{config.RESET}")
        traceback.print_exc()
        # Fallback logic remains the same
        llm_response = chat_with_model(message=user_input, config=config, chat_models=chat_models)
        final_response = process_response(user_input, llm_response, config, chat_models, allow_browser_fallback=True)
        print_streamed_message(final_response, config.CYAN)
        return final_response

    # If we get here, try browser search as a last resort
    try:
        # Check if this appears to be a web browsing or search request
        is_likely_browse_request = any(term in user_input.lower() for term in 
            ['browse', 'search', 'find', 'look up', 'lookup', 'concert', 'dates', 'news', 
             'website', 'page', 'web', 'info about', 'information on', 'latest'])
        
        if is_likely_browse_request:
            # Extract the search query - remove command words
            search_query = user_input
            for term in ['browse', 'search', 'find', 'lookup', 'look up', 'using the browse tool', 'with the browse tool']:
                search_query = search_query.replace(term, '').strip()
            
            # Try browser search
            browser_response = try_browser_search(search_query, config, chat_models)
            if browser_response:
                try:
                    formatted_response = format_browser_response(search_query, browser_response, config, chat_models)
                    print_streamed_message(formatted_response, config.CYAN)
                    return formatted_response
                except Exception as e:
                    print(f"{config.YELLOW}Error formatting browser response: {str(e)}. Falling back to LLM...{config.RESET}")
        
        # Default fallback if not a browse request or if browser search fails
        llm_response = chat_with_model(message=user_input, config=config, chat_models=chat_models)
        final_response = process_response(user_input, llm_response, config, chat_models, allow_browser_fallback=True)
        print_streamed_message(final_response, config.CYAN)
        return final_response
    except Exception as e:
        print(f"{config.RED}Error in fallback processing: {str(e)}{config.RESET}")
        traceback.print_exc()
        # Final fallback to direct LLM
        llm_response = chat_with_model(message=user_input, config=config, chat_models=chat_models)
        final_response = process_response(user_input, llm_response, config, chat_models, allow_browser_fallback=True)
        print_streamed_message(final_response, config.CYAN)
        return final_response

def process_input_in_safe_mode(query, config, chat_models):
    """Process input in safe mode with additional checks and confirmations."""
    llm_response = chat_with_model(query, config, chat_models)
    final_response = process_response(query, llm_response, config, chat_models)
    print_streamed_message(final_response, config.CYAN)

def process_input_in_autopilot_mode(query, config, chat_models):
    """Process input in autopilot mode with automatic execution."""
    llm_response = chat_with_model(query, config, chat_models)
    final_response = process_response(query, llm_response, config, chat_models)
    print_streamed_message(final_response, config.CYAN)

# Track assembled scripts for cleanup
_assembled_scripts = set()
# Pre-compile regex patterns for better performance
SCRIPT_PATTERN = re.compile(r"```(?:(bash|sh|python))?\n(.*?)```", re.DOTALL)
CLEANUP_PATTERN = re.compile(r"```(?:bash|sh)\n(.*?)\n```", re.DOTALL)

def assemble_final_script(scripts: list) -> str:
    """
    Assemble multiple script blocks into a final executable script.
    
    Args:
        scripts: List of tuples containing (content, extension, script_type)
    
    Returns:
        str: The assembled script ready for execution
    """
    if not scripts:
        return ""
        
    # If there's only one script, return it directly
    if len(scripts) == 1:
        return scripts[0][0]
        
    # For multiple scripts, combine them with proper separators
    final_script = "#!/bin/bash\n\n"
    
    for content, ext, script_type in scripts:
        if script_type == "python":
            # For Python scripts, wrap in python -c
            escaped_content = content.replace('"', '\\"')
            final_script += f'python3 -c "{escaped_content}"\n\n'
        else:
            # For bash scripts, include directly
            final_script += f"{content}\n\n"
            
    return final_script.strip()


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
            
        # Add shebang line if not present
        if not content.startswith("#!"):
            if lang == "python":
                content = "#!/usr/bin/env python3\n" + content
                ext = "py"
                script_type = "python"
            else:
                content = "#!/bin/bash\n" + content
                ext = "sh"
                script_type = "bash"
        else:
            # Check for shebang line
            first_line = content.split("\n")[0]
            if "python" in first_line.lower():
                ext = "py"
                script_type = "python"
            else:
                ext = "sh"
                script_type = "bash"
        
        scripts.append((content, ext, script_type))
    
    return scripts

def clean_up_llm_response(llm_response):
    """Clean up LLM response by extracting and formatting script blocks."""
    script_blocks = CLEANUP_PATTERN.findall(llm_response)
    if script_blocks:
        return "\n".join(block.strip() for block in script_blocks if block.strip())
    print("No executable script blocks found in the response.")
    return llm_response.strip()

def handle_script_cleanup(config):
    """Handle cleanup of assembled scripts with option to save."""
    # Using _assembled_scripts but not reassigning it, so no global needed
    
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

def execute_script(filename, file_extension, config):
    """Execute a saved script with proper error handling."""
    try:
        if file_extension == "py":
            result = subprocess.run(
                ["python", filename],
                capture_output=True,
                text=True,
                check=False
            )
        elif file_extension in ["sh", "bash", ""]:
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
        
        if result.stdout:
            print(result.stdout)
        if result.stderr:
            print(f"{config.RED}{result.stderr}{config.RESET}")
            
        if result.returncode != 0:
            print(f"{config.RED}Script execution failed with return code {result.returncode}{config.RESET}")
            
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
        if file_extension in ["sh", "bash", ""]:
            if not script.startswith("#!"):
                script = "#!/bin/bash\n" + script

        if file_extension == "py":
            with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as temp_file:
                temp_file.write(script)
                temp_file_path = temp_file.name
            
            try:
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
                
        elif file_extension in ["sh", "bash", ""]:
            with tempfile.NamedTemporaryFile(mode='w', suffix='.sh', delete=False) as temp_file:
                temp_file.write(script)
                temp_file_path = temp_file.name
                
            try:
                os.chmod(temp_file_path, 0o755)
                
                if not config.autopilot_mode and not get_user_confirmation(f"Execute script:\n{script}", config):
                    print("Script execution aborted by the user.")
                    return False
                
                result = subprocess.run(
                    ["bash", temp_file_path],
                    capture_output=True,
                    text=True,
                    check=False
                )
                
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
        if temp_file_path and os.path.exists(temp_file_path):
            try:
                os.unlink(temp_file_path)
            except OSError as e:
                print(f"Warning: Failed to clean up temporary file {temp_file_path}: {e}")

def cleanup_assembled_scripts():
    """Clean up any remaining assembled scripts without prompting."""
    # Using _assembled_scripts but not reassigning it, so no global needed
    for script in _assembled_scripts.copy():
        try:
            if os.path.exists(script):
                os.unlink(script)
                _assembled_scripts.remove(script)
        except OSError as e:
            print(f"Warning: Failed to clean up script {script}: {e}")

def execute_resolution_script(resolution, config):
    """Execute a resolution script with proper error handling."""
    print(f"{config.CYAN}Executing resolution:{config.RESET}\n{resolution}")
    try:
        subprocess.run(resolution, shell=True, check=True)
        print(f"{config.GREEN}Resolution executed successfully.{config.RESET}")
    except subprocess.CalledProcessError as e:
        print(f"{config.RED}Resolution execution failed with error: {e}{config.RESET}")
    except Exception as e:
        print(f"An error occurred while executing the resolution: {e}")

def get_user_confirmation(command: str, config=None) -> bool:
    """Get user confirmation before executing a command."""
    if config and config.autopilot_mode:
        return True
    print(f"\nAbout to execute command:\n{command}")
    response = input("Do you want to proceed? (yes/no): ").strip().lower()
    return response in ['yes', 'y']

def auto_handle_script_execution(script: str, config) -> bool:
    """
    Automatically handle script execution with proper error handling.
    
    Args:
        script: The script content to execute
        config: Configuration object containing execution settings
        
    Returns:
        bool: True if execution was successful, False otherwise
    """
    if not script:
        print("No script content provided.")
        return False
        
    # Determine script type based on content
    script_type = "python" if script.startswith("#!/usr/bin/env python") else "bash"
    ext = "py" if script_type == "python" else "sh"
    
    return execute_script_directly(script, ext, config)

def consult_llm_for_error_resolution(error_message, config):
    """Consult LLM for error resolution suggestions."""
    system_info = get_system_info()
    print(f"{config.CYAN}Consulting LLM for error resolution:{config.RESET} {error_message}")
    
    if not requests:
        print(f"{config.YELLOW}Requests package not available. Cannot consult LLM for error resolution.{config.RESET}")
        return None
    
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
                "temperature": 0.3
            }
        )
        response.raise_for_status()
        
        if suggestion := response.json().get('choices', [{}])[0].get('message', {}).get('content', '').strip():
            config.llm_suggestions = suggestion
            return suggestion
            
        print("No advice was returned by the model.")
        return None
    except Exception as e:
        print(f"API request error: {e}")
        return None
        
# Session management functions

def display_session_history(config):
    """Display the session history."""
    if not hasattr(config, 'session_history') or not config.session_history:
        message = "No session history available."
        print(f"{config.YELLOW}{message}{config.RESET}")
        return message
    
    # Print header with border
    print(f"\n{config.CYAN}╭─{'─' * 50}╮{config.RESET}")
    print(f"{config.CYAN}│ {config.BOLD}Session History{' ' * 35}│{config.RESET}")
    print(f"{config.CYAN}├─{'─' * 50}┤{config.RESET}")
    
    # Print history items
    for i, item in enumerate(config.session_history):
        # Format timestamp nicely
        try:
            timestamp = datetime.fromisoformat(item['timestamp'])
            time_str = timestamp.strftime("%H:%M:%S")
        except (ValueError, TypeError):
            time_str = "Unknown time"
            
        # Truncate long queries/responses
        query = item['query']
        if len(query) > 42:  # Adjusted for box width
            query = query[:39] + "..."
        
        # Left-pad index for alignment    
        idx_str = f"{i}".rjust(2)
        
        # Add color coding based on even/odd rows for easier scanning
        if i % 2 == 0:
            print(f"{config.CYAN}│ {config.YELLOW}{idx_str}{config.RESET}: [{time_str}] {query}{' ' * (43 - len(query))}{config.CYAN}│{config.RESET}")
        else:
            print(f"{config.CYAN}│ {config.GREEN}{idx_str}{config.RESET}: [{time_str}] {query}{' ' * (43 - len(query))}{config.CYAN}│{config.RESET}")
    
    # Print footer
    print(f"{config.CYAN}╰─{'─' * 50}╯{config.RESET}")
    print(f"\n{config.YELLOW}Tip: Use 'recall N' to view the full content of an item{config.RESET}\n")
    
    # Return formatted string for history
    result = ["Session History:"]
    for i, item in enumerate(config.session_history):
        try:
            timestamp = datetime.fromisoformat(item['timestamp'])
            time_str = timestamp.strftime("%H:%M:%S")
        except (ValueError, TypeError):
            time_str = "Unknown time"
            
        query = item['query']
        if len(query) > 50:
            query = query[:47] + "..."
            
        result.append(f"{i}: [{time_str}] {query}")
    
    return "\n".join(result)

def recall_history_item(config, index):
    """Recall and display a specific history item."""
    if not hasattr(config, 'session_history') or not config.session_history:
        message = "No session history available."
        print(f"{config.YELLOW}{message}{config.RESET}")
        return message
    
    try:
        item = config.session_history[index]
        
        # Get timestamp in readable format
        try:
            timestamp = datetime.fromisoformat(item['timestamp'])
            time_str = timestamp.strftime("%H:%M:%S")
        except (ValueError, TypeError):
            time_str = "Unknown time"
        
        # Calculate box width based on query length
        query = item['query']
        box_width = min(80, max(50, len(query) + 10))  # Dynamic width based on content
        
        # Print header with border
        print(f"\n{config.CYAN}╭─{'─' * box_width}╮{config.RESET}")
        print(f"{config.CYAN}│ {config.BOLD}History Item #{index} • {time_str}{' ' * (box_width - 19 - len(str(index)) - len(time_str))}│{config.RESET}")
        print(f"{config.CYAN}├─{'─' * box_width}┤{config.RESET}")
        
        # Print query with label
        print(f"{config.CYAN}│ {config.YELLOW}QUERY:{' ' * (box_width - 8)}{config.CYAN}│{config.RESET}")
        
        # Split query into multiple lines if needed
        query_lines = []
        remaining = query
        while remaining:
            # Take up to box_width - 4 chars (accounting for margins)
            line = remaining[:box_width - 4]
            query_lines.append(line)
            remaining = remaining[box_width - 4:]
        
        for line in query_lines:
            padding = ' ' * (box_width - len(line) - 2)
            print(f"{config.CYAN}│ {config.RESET}{line}{padding}{config.CYAN}│{config.RESET}")
        
        # Divider between query and response
        print(f"{config.CYAN}├─{'─' * box_width}┤{config.RESET}")
        
        # Print response with label
        print(f"{config.CYAN}│ {config.GREEN}RESPONSE:{' ' * (box_width - 11)}{config.CYAN}│{config.RESET}")
        
        # Split response into multiple lines
        response = item['response']
        response_lines = []
        remaining = response
        while remaining:
            line = remaining[:box_width - 4]
            response_lines.append(line)
            remaining = remaining[box_width - 4:]
        
        # Display first 15 lines max to avoid flooding terminal
        max_lines = 15
        for i, line in enumerate(response_lines[:max_lines]):
            padding = ' ' * (box_width - len(line) - 2)
            print(f"{config.CYAN}│ {config.RESET}{line}{padding}{config.CYAN}│{config.RESET}")
        
        # If response is truncated, show indicator
        if len(response_lines) > max_lines:
            print(f"{config.CYAN}│ {config.YELLOW}... {len(response_lines) - max_lines} more lines ...{' ' * (box_width - 24 - len(str(len(response_lines) - max_lines)))}{config.CYAN}│{config.RESET}")
        
        # Print footer
        print(f"{config.CYAN}╰─{'─' * box_width}╯{config.RESET}\n")
        
        # Format result for return
        result = [
            f"Query: {item['query']}",
            "",
            f"Response: {item['response']}"
        ]
        return "\n".join(result)
    except IndexError:
        message = f"No history item at index {index}."
        print(f"{config.YELLOW}{message}{config.RESET}")
        return message

def display_session_status(config):
    """Display current session status in a formatted dashboard."""
    print(f"\n{config.CYAN}╭{'─' * 60}╮{config.RESET}")
    print(f"{config.CYAN}│{'SESSION STATUS DASHBOARD':^60}│{config.RESET}")
    print(f"{config.CYAN}├{'─' * 60}┤{config.RESET}")
    
    # Model Status
    print(f"{config.CYAN}│ 🤖 MODEL{' ' * 51}│{config.RESET}")
    print(f"{config.CYAN}│ • Active Model: {config.current_model:<40}│{config.RESET}")
    print(f"{config.CYAN}│ • Available: Claude | Ollama | Groq{' ' * 30}│{config.RESET}")
    
    # Cache Status
    print(f"{config.CYAN}├{'─' * 60}┤{config.RESET}")
    print(f"{config.CYAN}│ 💾 CACHE{' ' * 51}│{config.RESET}")
    from .script_handlers import _content_cache
    cache_status = "Empty" if not _content_cache['raw_content'] else "Loaded"
    formatted_status = "Yes" if _content_cache['formatted_content'] else "No"
    print(f"{config.CYAN}│ • Browser Cache: {cache_status:<40}│{config.RESET}")
    print(f"{config.CYAN}│ • Formatted Content: {formatted_status:<35}│{config.RESET}")
    
    # History Status
    print(f"{config.CYAN}├{'─' * 60}┤{config.RESET}")
    print(f"{config.CYAN}│ 📜 HISTORY{' ' * 50}│{config.RESET}")
    history_count = len(config.session_history) if hasattr(config, 'session_history') else 0
    context_count = len(config.context_history) if hasattr(config, 'context_history') else 0
    print(f"{config.CYAN}│ • Items: {history_count:<45}│{config.RESET}")
    print(f"{config.CYAN}│ • Context Items: {context_count:<40}│{config.RESET}")
    
    # Settings Status
    print(f"{config.CYAN}├{'─' * 60}┤{config.RESET}")
    print(f"{config.CYAN}│ ⚙️ SETTINGS{' ' * 50}│{config.RESET}")
    print(f"{config.CYAN}│ • Response Tolerance: {config.tolerance_level:<35}│{config.RESET}")
    print(f"{config.CYAN}│ • Safe Mode: {'Enabled' if config.safe_mode else 'Disabled':<40}│{config.RESET}")
    print(f"{config.CYAN}│ • Autopilot Mode: {'Enabled' if config.autopilot_mode else 'Disabled':<35}│{config.RESET}")
    print(f"{config.CYAN}│ • Script Reviewer: {'Enabled' if config.scriptreviewer_on else 'Disabled':<35}│{config.RESET}")
    print(f"{config.CYAN}│ • Sequential Thinking: {'Enabled' if config.sequential_thinking_enabled else 'Disabled':<30}│{config.RESET}")
    if config.sequential_thinking_enabled:
        print(f"{config.CYAN}│ • LLM Choice: {'Enabled' if config.sequential_thinking_llm_choice else 'Disabled':<40}│{config.RESET}")
    
    print(f"{config.CYAN}╰{'─' * 60}╯{config.RESET}")

def show_session_status(config):
    """Display current session status and available commands."""
    print(f"\n{config.CYAN}=== Session Status ==={config.RESET}")
    print(f"Model: {config.current_model}")
    print(f"Mode: {'Autopilot' if config.autopilot_mode else 'Safe' if config.safe_mode else 'Normal'}")
    print(f"Script Reviewer: {'Enabled' if config.scriptreviewer_on else 'Disabled'}")
    print(f"Sequential Thinking: {'Enabled' if config.sequential_thinking_enabled else 'Disabled'}")
    if config.sequential_thinking_enabled:
        print(f"LLM Choice: {'Enabled' if config.sequential_thinking_llm_choice else 'Disabled'}")
    
    print(f"\n{config.CYAN}=== Available Commands ==={config.RESET}")
    print(f"{config.YELLOW}Session Management:{config.RESET}")
    print("  history          - Show conversation history")
    print("  recall <index>   - Recall specific history item")
    print("  clear history    - Clear conversation history")
    print("  save            - Save last response to file")
    print("  reset           - Reset conversation")
    
    print(f"\n{config.YELLOW}Model & Mode Control:{config.RESET}")
    print("  model           - Change model")
    print("  list_models     - List available models")
    print("  safe            - Switch to safe mode")
    print("  autopilot       - Switch to autopilot mode")
    print("  normal          - Switch to normal mode")
    
    print(f"\n{config.YELLOW}Sequential Thinking:{config.RESET}")
    print("  sequential thinking on/off           - Enable/disable sequential thinking")
    print("  sequential thinking llm choice on/off - Enable/disable LLM choice")
    print("  sequential thinking history          - Show thought history")
    print("  sequential thinking clear            - Clear thought history")
    
    print(f"\n{config.YELLOW}File Operations:{config.RESET}")
    print("  file            - Browse and view files")
    print("  fileint         - Advanced file operations")
    
    print(f"\n{config.YELLOW}Other Commands:{config.RESET}")
    print("  script          - Handle script execution")
    print("  config          - Show current configuration")
    print("  session         - Show this help message")
    print("  exit            - Exit command mode")
    
    print(f"\n{config.CYAN}=== Current Session ==={config.RESET}")
    if hasattr(config, 'session_history') and config.session_history:
        print(f"History items: {len(config.session_history)}")
        for i, item in enumerate(config.session_history):
            print(f"{i}: {item[:50]}..." if len(item) > 50 else f"{i}: {item}")
    else:
        print("No history items")
