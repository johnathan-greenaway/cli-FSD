import re
import os
import subprocess
import tempfile
import json
import traceback # For detailed error logging
import regex  # For more advanced regex support
from datetime import datetime, date

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

def format_browser_response(query: str, response: str, config, chat_models) -> str:
    """
    Format a raw browser/MCP response into a more readable format.
    
    Args:
        query: The original user query
        response: The raw browser/MCP response
        config: Configuration object
        chat_models: Chat models to use
        
    Returns:
        str: Formatted response
    """
    print(f"{config.CYAN}Formatting raw browser/MCP response...{config.RESET}")
    
    # Handle empty or None response
    if not response:
        return "No browser response received. Please try a different query."
    
    # Handle response based on type and size
    try:
        # If response is already a string and seems reasonable in size, use it directly
        if isinstance(response, str):
            # For very long responses, truncate them first
            if len(response) > 5000:
                truncated_response = response[:5000] + "... [content truncated]"
            else:
                truncated_response = response
            
            # Check if it appears to be JSON
            if response.strip().startswith('{') or response.strip().startswith('['):
                try:
                    # Try to parse as JSON to make it more readable
                    parsed_json = json.loads(response)
                    # Format JSON nicely with minimal indentation for token efficiency
                    truncated_response = json.dumps(parsed_json, indent=1)[:5000]
                except (json.JSONDecodeError, TypeError):
                    # Not valid JSON or couldn't be parsed, use as is
                    pass
        else:
            # For non-string responses, convert to string
            try:
                truncated_response = json.dumps(response, indent=1)[:5000]
            except (TypeError, OverflowError):
                truncated_response = str(response)[:5000]
        
        # Only send to LLM for formatting if it seems to be a complex response
        # that would benefit from structuring
        if len(truncated_response) > 200:
            try:
                formatted_response = chat_with_model(
                    message=(
                        f"The following is a raw response from a browser/MCP tool for the query: '{query}'\n\n"
                        f"{truncated_response}\n\n"
                        "Please format this information into a clear, concise, and well-structured response that directly "
                        "answers the user's query. Include all relevant information from the raw response."
                    ),
                    config=config,
                    chat_models=chat_models,
                    system_prompt=(
                        "You are an expert at formatting raw web data into helpful responses. "
                        "Focus on extracting the most relevant information and presenting it clearly."
                    )
                )
                
                # Store the formatted response in context
                _response_context['collected_info']['formatted_browser'] = formatted_response[:500]
                
                return formatted_response
            except Exception as e:
                print(f"{config.YELLOW}Error using LLM for formatting: {str(e)}. Using simplified response.{config.RESET}")
                # If LLM formatting fails, return a simplified version
                return f"Information from web search for '{query}':\n\n{truncated_response}"
        else:
            # For short responses, don't bother with LLM formatting
            return f"Information from web search for '{query}':\n\n{truncated_response}"
    
    except Exception as e:
        print(f"{config.RED}Error formatting browser response: {str(e)}{config.RESET}")
        # Return a helpful error message with whatever we can salvage
        if isinstance(response, str) and response:
            return f"Error formatting browser response: {str(e)}. Raw data:\n\n{response[:1000]}..."
        else:
            return f"Error formatting browser response: {str(e)}. Unable to display raw data."

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
    """
    Attempt to use browser search to find an answer.
    
    Args:
        query: The user query
        config: Configuration object
        chat_models: Chat models to use
        
    Returns:
        str: Browser search results or empty string if failed
    """
    search_query = query
    # Clean up query for search
    for term in ['search', 'find', 'lookup', 'what is', 'how to', 'browse']:
        search_query = search_query.replace(term, '').strip()
    
    # Check for concert/artist-related queries
    concert_keywords = ["concert", "tour", "show", "ticket", "live", "performance", "upcoming", "dates"]
    has_concert_terms = any(keyword in search_query.lower() for keyword in concert_keywords)
    
    # Check for direct site visits - but prioritize concert searches
    if has_concert_terms:
        # For concert/artist queries, always use Google search for best results
        url = f"https://www.google.com/search?q={search_query.replace(' ', '+')}+upcoming+concerts"
        print(f"{config.GREEN}Detected concert/artist search query. Using Google search.{config.RESET}")
    elif "hacker news" in search_query.lower() or "hackernews" in search_query.lower() or "hn" in search_query.lower():
        url = "https://news.ycombinator.com/"
    elif "reddit" in search_query.lower():
        url = f"https://www.reddit.com/search/?q={search_query.replace('reddit', '').replace(' ', '+')}"
    elif "github" in search_query.lower():
        url = f"https://github.com/search?q={search_query.replace('github', '').replace(' ', '+')}"
    else:
        # Default to Google search
        url = f"https://www.google.com/search?q={search_query.replace(' ', '+')}"
    
    print(f"{config.CYAN}Trying browser search for: {search_query}{config.RESET}")
    print(f"{config.CYAN}Using URL: {url}{config.RESET}")
    
    try:
        # Use our efficient web fetcher first (more reliable than MCP)
        try:
            from .web_fetcher import fetcher
            result = fetcher.fetch_and_process(url, mode="detailed", use_cache=True)
            if result:
                # Return standard JSON for all sites
                return json.dumps(result)
        except Exception as e:
            print(f"{config.YELLOW}Efficient web fetcher failed: {str(e)}. Trying WebBrowser fallback...{config.RESET}")
        
        # Use WebBrowser class directly as second choice
        try:
            from .small_context.protocol import WebBrowser
            browser = WebBrowser()
            result = browser.browse(url)
            
            # Format browser result into a structured format
            formatted_result = {
                "type": "webpage",
                "url": url,
                "title": result.get("title", "Web Page"),
                "content": [
                    {
                        "type": "section",
                        "title": "Web Content",
                        "blocks": [
                            {
                                "type": "text",
                                "text": result.get("content", "No content found")
                            }
                        ]
                    }
                ]
            }
            
            # Add entities if available
            if entities := result.get("entities"):
                formatted_result["content"].append({
                    "type": "section",
                    "title": "Key Topics",
                    "blocks": [
                        {
                            "type": "text",
                            "text": "\n".join(f"• {entity}" for entity in entities)
                        }
                    ]
                })
            
            return json.dumps(formatted_result)
        except Exception as e:
            print(f"{config.YELLOW}WebBrowser failed: {str(e)}. Trying MCP browser...{config.RESET}")
        
        # Try MCP browser tool as last resort
        try:
            response = use_mcp_tool(
                server_name="small-context",
                tool_name="browse_web",
                arguments={"url": url}
            )
            # Empty array/object check
            if not response or response.strip() in ["[]", "{}", ""]:
                # Generic fallback for empty responses
                fallback_content = {
                    "type": "webpage",
                    "url": url,
                    "title": f"Content from {url}",
                    "content": [
                        {
                            "type": "section",
                            "title": "Information",
                            "blocks": [
                                {
                                    "type": "text",
                                    "text": f"Successfully connected to {url} but no content was returned. This might be due to site restrictions or content formatting."
                                }
                            ]
                        }
                    ]
                }
                return json.dumps(fallback_content)
            
            # If we have a valid response
            return response
        except Exception as e:
            print(f"{config.YELLOW}MCP browser failed: {str(e)}.{config.RESET}")
        
        # If all methods failed, return a helpful message
        return json.dumps({
            "type": "error",
            "url": url,
            "title": "Browser Search Failed",
            "content": [
                {
                    "type": "section",
                    "title": "Error Information",
                    "blocks": [
                        {
                            "type": "text",
                            "text": f"Failed to retrieve content from {url}. This could be due to network issues, site restrictions, or the site requiring authentication."
                        }
                    ]
                }
            ]
        })
    except Exception as e:
        print(f"{config.YELLOW}All browser search methods failed: {str(e)}{config.RESET}")
        return json.dumps({
            "type": "error",
            "url": url,
            "title": "Browser Search Failed",
            "message": f"Failed to retrieve content. Error: {str(e)}"
        })

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

def process_input_based_on_mode(query, config, chat_models):
    """Process user input based on the current mode and query type."""
    import json # Ensure json is explicitly available in this function's scope
    # Access global variables, but don't declare them global since we're not reassigning them
    # Using them as read-only doesn't require global declaration
    
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
    
    # Direct command to browse a site (special handler for local models)
    elif query.lower().startswith(('browse ', '@browse ', '@ browse ')):
        # Extract the site name - handle "using the browse tool" and similar phrases 
        site_query = query.lower()
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
        else:
            # For any other site, treat as a search
            url = f"https://www.google.com/search?q={site_query}"
            clean_query = site_query
            
        # Directly use the browser search function
        print(f"{config.CYAN}Direct browsing: {url}{config.RESET}")
        
        try:
            # Special direct HTML scrape for Hacker News to ensure reliability
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
                    print(f"{config.YELLOW}Direct HN scraper failed: {str(e)}. Trying standard methods...{config.RESET}")
            
            # For other sites or if HN scraper failed
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
    elif query.lower().startswith("set tolerance "):
        level = query.lower().replace("set tolerance ", "").strip()
        set_evaluation_tolerance(level)
        print(f"{config.GREEN}Tolerance level set to: {level}{config.RESET}")
        return f"Tolerance level set to: {level}"
    
    # Validate query
    if not _validate_query(query):
        print(f"{config.YELLOW}Please provide a command or question.{config.RESET}")
        return "Please provide a command or question."
        
    # Print current configuration for debugging
    if config.session_model:
        print(f"{config.CYAN}Using model: {config.session_model}{config.RESET}")
    
    # Check if this is a request to view specific cached content
    if _content_cache['raw_content'] and any(word in query.lower() for word in ['show', 'view', 'read', 'tell', 'about']):
        matching_content = _find_matching_content(query)
        if matching_content:
            # Box dimensions - adjust based on content
            headline = matching_content['headline']
            box_width = min(80, max(60, len(headline) + 10))
            
            # Print header with border
            print(f"\n{config.CYAN}╭─{'─' * box_width}╮{config.RESET}")
            print(f"{config.CYAN}│ {config.BOLD}{config.YELLOW}MATCHED CONTENT{' ' * (box_width - 16)}│{config.RESET}")
            print(f"{config.CYAN}├─{'─' * box_width}┤{config.RESET}")
            
            # Print headline
            print(f"{config.CYAN}│ {config.BOLD}HEADLINE:{' ' * (box_width - 11)}│{config.RESET}")
            
            # Split headline into multiple lines if needed
            remaining = headline
            while remaining:
                line = remaining[:box_width - 4]
                padding = ' ' * (box_width - len(line) - 2)
                print(f"{config.CYAN}│ {config.GREEN}{line}{config.RESET}{padding}{config.CYAN}│{config.RESET}")
                remaining = remaining[box_width - 4:]
            
            # Main content section
            if matching_content['content']:
                print(f"{config.CYAN}├─{'─' * box_width}┤{config.RESET}")
                print(f"{config.CYAN}│ {config.BOLD}CONTENT:{' ' * (box_width - 10)}│{config.RESET}")
                
                # Format content paragraphs
                paragraphs = matching_content['content'].split('\n\n')
                for i, paragraph in enumerate(paragraphs):
                    if i > 0:
                        # Add paragraph separator
                        print(f"{config.CYAN}│{' ' * (box_width - 1)}│{config.RESET}")
                    
                    # Split paragraph into lines
                    remaining = paragraph
                    while remaining:
                        line = remaining[:box_width - 4]
                        padding = ' ' * (box_width - len(line) - 2)
                        print(f"{config.CYAN}│ {config.RESET}{line}{padding}{config.CYAN}│{config.RESET}")
                        remaining = remaining[box_width - 4:]
            
            # Additional details section
            if matching_content.get('details'):
                print(f"{config.CYAN}├─{'─' * box_width}┤{config.RESET}")
                print(f"{config.CYAN}│ {config.BOLD}DETAILS:{' ' * (box_width - 10)}│{config.RESET}")
                
                # Format details paragraphs
                details = matching_content['details']
                remaining = details
                while remaining:
                    line = remaining[:box_width - 4]
                    padding = ' ' * (box_width - len(line) - 2)
                    print(f"{config.CYAN}│ {config.YELLOW}{line}{config.RESET}{padding}{config.CYAN}│{config.RESET}")
                    remaining = remaining[box_width - 4:]
            
            # Links section
            if matching_content.get('links') and matching_content['links']:
                print(f"{config.CYAN}├─{'─' * box_width}┤{config.RESET}")
                print(f"{config.CYAN}│ {config.BOLD}LINKS:{' ' * (box_width - 8)}│{config.RESET}")
                
                # Display each link
                for link in matching_content['links']:
                    remaining = f"• {link}"
                    while remaining:
                        line = remaining[:box_width - 4]
                        padding = ' ' * (box_width - len(line) - 2)
                        print(f"{config.CYAN}│ {config.RESET}{line}{padding}{config.CYAN}│{config.RESET}")
                        remaining = remaining[box_width - 4:]
            
            # Print footer with tip
            print(f"{config.CYAN}╰─{'─' * box_width}╯{config.RESET}")
            print(f"{config.YELLOW}Tip: Ask follow-up questions about this content for more details{config.RESET}\n")
            
            # Return formatted text for history
            result = []
            result.append(f"Found relevant content:")
            result.append(f"\nHeadline: {matching_content['headline']}")
            if matching_content['content']:
                result.append(f"\nContent: {matching_content['content']}")
            if matching_content.get('details'):
                result.append(f"\nDetails: {matching_content['details']}")
            if matching_content.get('links'):
                result.append("\nRelevant links:")
                for link in matching_content['links']:
                    result.append(f"- {link}")
            
            return "\n".join(result)
    
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
        print_streamed_message(llm_response, config.CYAN, config)
        return llm_response
    
    # Check if this is explicitly a browser request
    is_browser_request = any(term in query.lower() for term in ['browse', 'open website', 'go to', 'visit'])
    
    # First try CLI commands for system operations (unless it's a browser request)
    if not is_browser_request and any(word in query.lower() for word in ['install', 'setup', 'configure', 'run', 'start', 'stop', 'restart']):
        response = handle_cli_command(query, config, chat_models)
        if "NO_CLI_COMMAND" not in response:
            return response
    
    # Use ContextAgent to analyze the request and determine which tool to use
    try:
        agent = ContextAgent()
        analysis = agent.analyze_request(query)
        
        # Validate analysis object
        if not analysis or not isinstance(analysis, dict) or "prompt" not in analysis:
            # Fall back to direct LLM processing if analysis fails
            print(f"{config.YELLOW}Failed to generate valid analysis from ContextAgent.{config.RESET}")
            llm_response = chat_with_model(query, config, chat_models)
            final_response = process_response(query, llm_response, config, chat_models, allow_browser_fallback=True)
            print_streamed_message(final_response, config.CYAN)
            return final_response
        
        # Get LLM's tool selection decision with the analysis prompt
        llm_analysis = chat_with_model(
            message=analysis["prompt"],
            config=config,
            chat_models=chat_models,
            system_prompt=(
                "You are a tool selection expert with excellent programming knowledge. Analyze the user's request and determine "
                "which tool would be most effective. For web browsing requests BE PREPPARED TO PARSE JSON, use the small_context tool with browse_web operation. "
                "When using browse_web, ensure the response ALWAYS INCLUDES A URL AND  excludes technical details about servers, responses, or parsing. "
                "Focus only on the actual content. Respond with a JSON object containing your analysis and selection. "
                "Be precise and follow the specified format.\n\n"
                "IMPORTANT: For each request, decide if you should:\n"
                "1. Answer with your built-in knowledge (direct_knowledge) - STRONGLY PREFERRED FOR PROGRAMMING QUESTIONS\n"
                "2. Use a tool to get information (tool_based) - ONLY USE FOR VERY SPECIFIC CURRENT DATA\n"
                "3. Provide a hybrid response with both built-in knowledge and tool-based information (hybrid)\n\n"
                "For programming tasks like creating projects, writing code, explaining frameworks, or technical concepts, "
                "ALWAYS use direct_knowledge with high confidence (0.85+).\n"
                "For hybrid responses, set confidence between 0.5-0.8 to indicate partial confidence."
            )
        )
        
        if not llm_analysis:
            print(f"{config.YELLOW}No response received from tool selection LLM analysis.{config.RESET}")
            llm_response = chat_with_model(query, config, chat_models)
            final_response = process_response(query, llm_response, config, chat_models, allow_browser_fallback=True)
            print_streamed_message(final_response, config.CYAN)
            return final_response
        
        try:
            # Extract JSON from the LLM analysis response
            json_start = llm_analysis.find('{')
            json_end = llm_analysis.rfind('}') + 1
            if json_start >= 0 and json_end > json_start:
                json_str = llm_analysis[json_start:json_end]
                # Try to parse JSON, attempt repair if it fails
                try:
                    tool_selection = json.loads(json_str)
                except json.JSONDecodeError as e:
                    # Log the error
                    print(f"{config.YELLOW}JSON decode error: {str(e)}{config.RESET}")
                    print(f"{config.CYAN}Attempting to repair malformed JSON...{config.RESET}")
                    
                    # Try to repair the JSON
                    repaired_json, was_repaired = attempt_json_repair(json_str)
                    
                    if was_repaired:
                        try:
                            tool_selection = json.loads(repaired_json)
                            print(f"{config.GREEN}Successfully repaired JSON!{config.RESET}")
                        except json.JSONDecodeError:
                            # If repair also failed, log and continue to fallback
                            print(f"{config.RED}Repair attempt failed, falling back to standard processing.{config.RESET}")
                            raise  # Re-raise to be caught by the outer except
                    else:
                        # If no repair was needed but parsing still failed
                        raise  # Re-raise to be caught by the outer except
                
                # Get response using selected tool
                response_type = tool_selection.get("response_type", "tool_based").lower()
                selected_tool = tool_selection.get("selected_tool", "") 
                if selected_tool is not None:
                    selected_tool = selected_tool.lower()
                else:
                    selected_tool = ""
                if selected_tool == "small_context":
                    # Handle small_context tool
                    parameters = tool_selection.get("parameters", {})
                    url = parameters.get("url")
                    if not url or url == "[URL will be determined based on request]":
                        print(f"{config.RED}No valid URL provided in tool selection.{config.RESET}")
                        llm_response = chat_with_model(query, config, chat_models)
                        final_response = process_response(query, llm_response, config, chat_models, allow_browser_fallback=True)
                        print_streamed_message(final_response, config.CYAN)
                        return final_response

                    # Update the request with the LLM-selected URL
                    result = agent.execute_tool_selection(tool_selection)
                    if result.get("tool") == "use_mcp_tool":
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
                                    print_streamed_message(llm_response, config.CYAN, config)
                                    
                                    # Print interaction hint
                                    print(f"\n{config.CYAN}You can interact with the content by asking questions or requesting more details about specific topics.{config.RESET}")
                                    return llm_response
                                else:
                                    formatted_response = json.dumps(content, indent=2)
                                    llm_response = chat_with_model(
                                        message=f"Please summarize this content:\n\n{formatted_response}",
                                        config=config,
                                        chat_models=chat_models
                                    )
                                    print_streamed_message(llm_response, config.CYAN, config)
                                    return llm_response
                            else:
                                formatted_response = str(content)
                                llm_response = chat_with_model(
                                    message=f"Please summarize this content:\n\n{formatted_response}",
                                    config=config,
                                    chat_models=chat_models
                                )
                                print_streamed_message(llm_response, config.CYAN, config)
                                return llm_response
                        except json.JSONDecodeError:
                            # Handle raw response directly
                            llm_response = chat_with_model(
                                message=f"Please summarize this content in a clear and concise way:\n\n{response}",
                                config=config,
                                chat_models=chat_models
                            )
                            print_streamed_message(llm_response, config.CYAN, config)
                            return llm_response
                    else:
                        llm_response = f"Error: {result.get('error', 'Unknown error')}"
                        print_streamed_message(llm_response, config.CYAN, config)
                        return llm_response
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
                    
                    print_streamed_message(llm_response, config.CYAN, config)
                    return llm_response
                else:
                    # Default to standard LLM processing
                    llm_response = chat_with_model(query, config, chat_models)
                    final_response = process_response(query, llm_response, config, chat_models, allow_browser_fallback=True)
                    print_streamed_message(final_response, config.CYAN)
                    return final_response
            else:
                # Fallback if JSON extraction fails
                llm_response = chat_with_model(query, config, chat_models)
                final_response = process_response(query, llm_response, config, chat_models, allow_browser_fallback=True)
                print_streamed_message(final_response, config.CYAN)
                return final_response
        except (json.JSONDecodeError, KeyError, AttributeError) as e:
            print(f"{config.YELLOW}Failed to process tool selection: {str(e)}{config.RESET}")
            
            # Check if this appears to be a web browsing or search request
            is_likely_browse_request = any(term in query.lower() for term in 
                ['browse', 'search', 'find', 'look up', 'lookup', 'concert', 'dates', 'news', 
                 'website', 'page', 'web', 'info about', 'information on', 'latest'])
            
            if is_likely_browse_request:
                print(f"{config.GREEN}Detected web search request. Bypassing JSON parsing and using browser directly.{config.RESET}")
                
                # Extract the search query - remove command words
                search_query = query
                for term in ['browse', 'search', 'find', 'lookup', 'look up', 'using the browse tool', 'with the browse tool']:
                    search_query = search_query.replace(term, '').strip()
                
                # Make sure we're actually searching for real content, not routing to default sites
                print(f"{config.CYAN}Performing search for: '{search_query}'{config.RESET}")
                browser_response = try_browser_search(search_query, config, chat_models)
                
                if browser_response:
                    formatted_response = format_browser_response(search_query, browser_response, config, chat_models)
                    print_streamed_message(formatted_response, config.CYAN, config)
                    return formatted_response
            
            # Default fallback if not a browse request or if browser search fails
            llm_response = chat_with_model(query, config, chat_models)
            final_response = process_response(query, llm_response, config, chat_models, allow_browser_fallback=True)
            print_streamed_message(final_response, config.CYAN)
            return final_response
    except Exception as e:
        print(f"{config.YELLOW}Using standard processing due to error: {str(e)}{config.RESET}")
        # Print the full traceback for detailed debugging
        print(f"{config.RED}Full traceback:{config.RESET}")
        traceback.print_exc()
        # Fallback logic remains the same
        llm_response = chat_with_model(query, config, chat_models)
        final_response = process_response(query, llm_response, config, chat_models, allow_browser_fallback=True)
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
    """Display current session status."""
    # Box dimensions
    box_width = 60
    
    # Headers for each section
    model_header = "🤖 MODEL"
    cache_header = "💾 CACHE"
    history_header = "📜 HISTORY"
    settings_header = "⚙️ SETTINGS"
    
    # Print title box
    print(f"\n{config.CYAN}╭─{'─' * box_width}╮{config.RESET}")
    print(f"{config.CYAN}│ {config.BOLD}{config.YELLOW}SESSION STATUS DASHBOARD{' ' * (box_width - 24)}│{config.RESET}")
    print(f"{config.CYAN}├─{'─' * box_width}┤{config.RESET}")
    
    # MODEL SECTION
    print(f"{config.CYAN}│ {config.BOLD}{model_header}{' ' * (box_width - len(model_header) - 2)}│{config.RESET}")
    print(f"{config.CYAN}│{config.RESET} • Active Model: {config.GREEN}{config.session_model or 'Default'}{config.RESET}{' ' * (box_width - 16 - len(config.session_model or 'Default'))}{config.CYAN}│{config.RESET}")
    
    model_status = []
    if hasattr(config, 'use_claude') and config.use_claude:
        model_status.append(f"{config.GREEN}Claude{config.RESET}")
    else:
        model_status.append(f"{config.RED}Claude{config.RESET}")
        
    if hasattr(config, 'use_ollama') and config.use_ollama:
        model_status.append(f"{config.GREEN}Ollama{config.RESET}")
    else:
        model_status.append(f"{config.RED}Ollama{config.RESET}")
        
    if hasattr(config, 'use_groq') and config.use_groq:
        model_status.append(f"{config.GREEN}Groq{config.RESET}")
    else:
        model_status.append(f"{config.RED}Groq{config.RESET}")
    
    print(f"{config.CYAN}│{config.RESET} • Available: {' | '.join(model_status)}{' ' * (box_width - 14 - len(' | '.join(['Claude', 'Ollama', 'Groq'])))}{config.CYAN}│{config.RESET}")
    
    # Divider
    print(f"{config.CYAN}├─{'─' * box_width}┤{config.RESET}")
    
    # CACHE SECTION
    print(f"{config.CYAN}│ {config.BOLD}{cache_header}{' ' * (box_width - len(cache_header) - 2)}│{config.RESET}")
    
    # Browser cache status
    has_browser_cache = bool(_content_cache['raw_content'])
    cache_status = f"{config.GREEN}Available{config.RESET}" if has_browser_cache else f"{config.RED}Empty{config.RESET}"
    print(f"{config.CYAN}│{config.RESET} • Browser Cache: {cache_status}{' ' * (box_width - 17 - len('Available' if has_browser_cache else 'Empty'))}{config.CYAN}│{config.RESET}")
    
    # Show formatted content status
    has_formatted = bool(_content_cache['formatted_content'])
    formatted_status = f"{config.GREEN}Yes{config.RESET}" if has_formatted else f"{config.RED}No{config.RESET}"
    print(f"{config.CYAN}│{config.RESET} • Formatted Content: {formatted_status}{' ' * (box_width - 21 - len('Yes' if has_formatted else 'No'))}{config.CYAN}│{config.RESET}")
    
    # Divider
    print(f"{config.CYAN}├─{'─' * box_width}┤{config.RESET}")
    
    # HISTORY SECTION
    print(f"{config.CYAN}│ {config.BOLD}{history_header}{' ' * (box_width - len(history_header) - 2)}│{config.RESET}")
    
    # History count
    history_count = len(config.session_history) if hasattr(config, 'session_history') else 0
    print(f"{config.CYAN}│{config.RESET} • Items: {config.YELLOW}{history_count}{config.RESET}{' ' * (box_width - 9 - len(str(history_count)))}{config.CYAN}│{config.RESET}")
    
    # Context items count
    context_count = len(_response_context['previous_responses'])
    print(f"{config.CYAN}│{config.RESET} • Context Items: {config.YELLOW}{context_count}{config.RESET}{' ' * (box_width - 17 - len(str(context_count)))}{config.CYAN}│{config.RESET}")
    
    # Divider
    print(f"{config.CYAN}├─{'─' * box_width}┤{config.RESET}")
    
    # SETTINGS SECTION
    print(f"{config.CYAN}│ {config.BOLD}{settings_header}{' ' * (box_width - len(settings_header) - 2)}│{config.RESET}")
    
    # Tolerance level with appropriate color
    tolerance = _response_context['tolerance_level']
    if tolerance == 'strict':
        tolerance_display = f"{config.RED}strict{config.RESET}"
    elif tolerance == 'lenient':
        tolerance_display = f"{config.GREEN}lenient{config.RESET}"
    else:
        tolerance_display = f"{config.YELLOW}medium{config.RESET}"
    
    print(f"{config.CYAN}│{config.RESET} • Response Tolerance: {tolerance_display}{' ' * (box_width - 21 - len(tolerance))}{config.CYAN}│{config.RESET}")
    
    # Modes with appropriate colors
    safe_mode = f"{config.GREEN}Enabled{config.RESET}" if config.safe_mode else f"{config.RED}Disabled{config.RESET}"
    print(f"{config.CYAN}│{config.RESET} • Safe Mode: {safe_mode}{' ' * (box_width - 13 - len('Enabled' if config.safe_mode else 'Disabled'))}{config.CYAN}│{config.RESET}")
    
    autopilot_mode = f"{config.GREEN}Enabled{config.RESET}" if config.autopilot_mode else f"{config.RED}Disabled{config.RESET}"
    print(f"{config.CYAN}│{config.RESET} • Autopilot Mode: {autopilot_mode}{' ' * (box_width - 18 - len('Enabled' if config.autopilot_mode else 'Disabled'))}{config.CYAN}│{config.RESET}")
    
    scriptreviewer = f"{config.GREEN}Enabled{config.RESET}" if hasattr(config, 'scriptreviewer_on') and config.scriptreviewer_on else f"{config.RED}Disabled{config.RESET}"
    print(f"{config.CYAN}│{config.RESET} • Script Reviewer: {scriptreviewer}{' ' * (box_width - 19 - len('Enabled' if hasattr(config, 'scriptreviewer_on') and config.scriptreviewer_on else 'Disabled'))}{config.CYAN}│{config.RESET}")
    
    # Print footer
    print(f"{config.CYAN}╰─{'─' * box_width}╯{config.RESET}\n")
    
    # Return formatted string for status
    result = ["Current Session Status:"]
    
    # Model information
    result.append(f"Model: {config.session_model or 'Default'}")
    
    # Browser cache status
    result.append(f"Browser cache: {'Available' if has_browser_cache else 'Empty'}")
    
    # History count
    result.append(f"History items: {history_count}")
    
    # Tolerance level
    result.append(f"Response tolerance: {_response_context['tolerance_level']}")
    
    # Modes
    result.append(f"Safe mode: {'Enabled' if config.safe_mode else 'Disabled'}")
    result.append(f"Autopilot mode: {'Enabled' if config.autopilot_mode else 'Disabled'}")
    
    return "\n".join(result)
