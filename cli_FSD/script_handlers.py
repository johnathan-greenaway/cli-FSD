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
        strictness = "Use balanced judgment in your evaluation. Accept responses that adequately address the main points."
        threshold = 0.75  # Moderate threshold
    
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
    
    # Truncate very long responses for processing
    truncated_response = response[:5000] if len(response) > 5000 else response
    
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
        return format_browser_response(query, response, config, chat_models)
    
    # For general and CLI responses, evaluate and use fallbacks if needed
    if not evaluate_response(query, response, config, chat_models, response_type):
        print(f"{config.YELLOW}Initial response was inadequate. Getting better response...{config.RESET}")
        
        # Try fallback LLM first
        improved_response = get_fallback_response(query, response, config, chat_models)
        
        # If fallback still inadequate and browser fallback is allowed, try browser
        if allow_browser_fallback and not evaluate_response(query, improved_response, config, chat_models, response_type):
            if _response_context['browser_attempts'] < 2:  # Limit browser attempts
                print(f"{config.YELLOW}Fallback response still inadequate. Trying browser search...{config.RESET}")
                _response_context['browser_attempts'] += 1
                
                # Try browser search
                browser_response = try_browser_search(query, config, chat_models)
                if browser_response:
                    # Store browser result in context
                    _response_context['collected_info']['browser_search'] = browser_response[:500]  # Store truncated version
                    
                    # Format the browser response
                    formatted_browser = format_browser_response(query, browser_response, config, chat_models)
                    
                    # Combine browser results with previous knowledge
                    final_response = chat_with_model(
                        message=(
                            f"Original query: {query}\n\n"
                            f"Previous responses: {improved_response}\n\n"
                            f"Browser search results: {formatted_browser}\n\n"
                            "Combine all this information to provide the most accurate and complete response."
                        ),
                        config=config,
                        chat_models=chat_models,
                        system_prompt=(
                            "You are a helpful expert assistant. Synthesize information from multiple sources "
                            "to provide the most accurate and complete response to the user's query."
                        )
                    )
                    return final_response
            else:
                print(f"{config.YELLOW}Maximum browser attempts reached. Using best available response.{config.RESET}")
        
        return improved_response
    return response

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
    
    url = f"https://www.google.com/search?q={search_query}"
    print(f"{config.CYAN}Trying browser search for: {search_query}{config.RESET}")
    
    try:
        # Try MCP browser tool first
        try:
            response = use_mcp_tool(
                server_name="small-context",
                tool_name="browse_web",
                arguments={"url": url}
            )
            if response:
                return response
        except Exception as e:
            print(f"{config.YELLOW}MCP browser failed: {str(e)}. Trying alternative search...{config.RESET}")
        
        # Fallback to using WebBrowser class directly
        from .small_context.protocol import WebBrowser
        browser = WebBrowser()
        result = browser.browse(url)
        return json.dumps(result)
    except Exception as e:
        print(f"{config.YELLOW}Browser search failed: {str(e)}{config.RESET}")
        return ""

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
        return process_response(query, response, config, chat_models, response_type="cli")
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
    global _response_context
    global _content_cache
    
    # Reset browser attempts counter for new queries
    _response_context['browser_attempts'] = 0
    
    # Check for tolerance level commands
    if query.lower().startswith("set tolerance "):
        level = query.lower().replace("set tolerance ", "").strip()
        set_evaluation_tolerance(level)
        print(f"{config.GREEN}Tolerance level set to: {level}{config.RESET}")
        return None
    
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
        return llm_response
    
    llm_response = None
    
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
                "You are a tool selection expert. Analyze the user's request and determine "
                "which tool would be most effective. For web browsing requests, always select "
                "the small_context tool with browse_web operation. When using browse_web, "
                "ensure the response excludes technical details about servers, responses, or parsing. "
                "Focus only on the actual content. Respond with a JSON object containing your "
                "analysis and selection. Be precise and follow the specified format.\n\n"
                "IMPORTANT: For each request, decide if you should:\n"
                "1. Answer with your latent knowledge (direct_knowledge)\n"
                "2. Use a tool to get information (tool_based)\n"
                "3. Provide a hybrid response with both latent knowledge and tool-based information (hybrid)\n\n"
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
                tool_selection = json.loads(json_str)
                
                # Get response using selected approach
                response_type = tool_selection.get("response_type", "tool_based").lower()
                selected_tool = tool_selection.get("selected_tool", "").lower()
                confidence = tool_selection.get("confidence", 0.0)
                
                # Handle direct knowledge response
                if response_type == "direct_knowledge":
                    print(f"{config.CYAN}Using direct knowledge to answer (confidence: {confidence:.2f}){config.RESET}")
                    llm_response = chat_with_model(
                        message=query,
                        config=config,
                        chat_models=chat_models,
                        system_prompt=(
                            "You are a knowledgeable assistant. Answer this question using your built-in knowledge. "
                            "Provide a comprehensive and accurate response without using external tools. "
                            "Format your answer clearly with appropriate headings, bullet points, and paragraphs as needed."
                        )
                    )
                    print_streamed_message(llm_response, config.CYAN)
                    return llm_response
                    
                # Handle hybrid response
                elif response_type == "hybrid":
                    print(f"{config.CYAN}Using hybrid approach (confidence: {confidence:.2f}){config.RESET}")
                    
                    # Execute tool selection to prepare the tool response
                    result = agent.execute_tool_selection(tool_selection)
                    
                    if result.get("type") == "hybrid" and result.get("response_id"):
                        response_id = result.get("response_id")
                        
                        # Get latent knowledge preview
                        print(f"{config.CYAN}Generating knowledge preview while preparing tool response...{config.RESET}")
                        preview = chat_with_model(
                            message=(
                                f"User query: {query}\n\n"
                                "Provide a brief, accurate answer using only your built-in knowledge. "
                                "This is a preview response, so keep it concise (3-5 sentences) but informative. "
                                "Acknowledge any limitations in your answer."
                            ),
                            config=config,
                            chat_models=chat_models
                        )
                        
                        # Display the preview
                        print(f"\n{config.CYAN}Knowledge Preview:{config.RESET}")
                        print_streamed_message(preview, config.CYAN)
                        
                        # Get the cached tool response
                        tool_response = agent.get_cached_tool_response(response_id)
                        
                        # Ask user if they want to continue with the tool response
                        print(f"\n{config.YELLOW}I can provide more complete information using {selected_tool}.{config.RESET}")
                        user_choice = input(f"{config.YELLOW}Would you like to see the complete answer? (yes/no): {config.RESET}").strip().lower()
                        
                        if user_choice in ["yes", "y"]:
                            print(f"{config.CYAN}Retrieving complete information...{config.RESET}")
                            
                            # Process the tool response
                            if tool_response:
                                # Handle different tool responses
                                if tool_response.get("tool") == "use_mcp_tool":
                                    try:
                                        from .utils import use_mcp_tool
                                        response = use_mcp_tool(
                                            server_name=tool_response.get("server"),
                                            tool_name=tool_response.get("operation"),
                                            arguments=tool_response.get("arguments", {})
                                        )
                                        
                                        # Format the complete response
                                        complete_response = chat_with_model(
                                            message=(
                                                f"User query: {query}\n\n"
                                                f"Knowledge preview: {preview}\n\n"
                                                f"Additional information from {selected_tool}: {response}\n\n"
                                                "Combine the knowledge preview with this additional information to provide "
                                                "a comprehensive answer. Format your response clearly and ensure it fully "
                                                "addresses the user's query."
                                            ),
                                            config=config,
                                            chat_models=chat_models
                                        )
                                        
                                        print_streamed_message(complete_response, config.CYAN)
                                        return complete_response
                                    except Exception as e:
                                        print(f"{config.RED}Error executing MCP tool: {e}{config.RESET}")
                                        return preview
                                else:
                                    # For other tool types
                                    print(f"{config.CYAN}Using {selected_tool} to complete the response...{config.RESET}")
                                    complete_response = chat_with_model(
                                        message=(
                                            f"User query: {query}\n\n"
                                            f"Knowledge preview: {preview}\n\n"
                                            "Expand on this preview with more detailed information. "
                                            "Provide a comprehensive answer that fully addresses the user's query."
                                        ),
                                        config=config,
                                        chat_models=chat_models
                                    )
                                    
                                    print_streamed_message(complete_response, config.CYAN)
                                    return complete_response
                            else:
                                print(f"{config.RED}Tool response not available.{config.RESET}")
                                return preview
                        else:
                            print(f"{config.CYAN}Using knowledge preview as final response.{config.RESET}")
                            return preview
                    else:
                        print(f"{config.RED}Error preparing hybrid response: {result.get('error', 'Unknown error')}{config.RESET}")
                        llm_response = chat_with_model(query, config, chat_models)
                        print_streamed_message(llm_response, config.CYAN)
                        return llm_response
                
                # Handle tool-based response (default)
                elif selected_tool == "small_context":
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
                                    print_streamed_message(llm_response, config.CYAN)
                                    
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
                                    print_streamed_message(llm_response, config.CYAN)
                                    return llm_response
                            else:
                                formatted_response = str(content)
                                llm_response = chat_with_model(
                                    message=f"Please summarize this content:\n\n{formatted_response}",
                                    config=config,
                                    chat_models=chat_models
                                )
                                print_streamed_message(llm_response, config.CYAN)
                                return llm_response
                        except json.JSONDecodeError:
                            # Handle raw response directly
                            llm_response = chat_with_model(
                                message=f"Please summarize this content in a clear and concise way:\n\n{response}",
                                config=config,
                                chat_models=chat_models
                            )
                            print_streamed_message(llm_response, config.CYAN)
                            return llm_response
                    else:
                        llm_response = f"Error: {result.get('error', 'Unknown error')}"
                        print_streamed_message(llm_response, config.CYAN)
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
                    
                    print_streamed_message(llm_response, config.CYAN)
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
            llm_response = chat_with_model(query, config, chat_models)
            final_response = process_response(query, llm_response, config, chat_models, allow_browser_fallback=True)
            print_streamed_message(final_response, config.CYAN)
            return final_response
    except Exception as e:
        print(f"{config.YELLOW}Using standard processing due to error: {str(e)}{config.RESET}")
        llm_response = chat_with_model(query, config, chat_models)
        final_response = process_response(query, llm_response, config, chat_models, allow_browser_fallback=True)
        print_streamed_message(final_response, config.CYAN)
        return final_response
    
    # After all processing, handle safe_mode and autopilot_mode
    if config.safe_mode:
        scripts = extract_script_from_response(llm_response)
        if scripts:
            code_checker = CodeChecker()
            for script, file_extension, script_type in scripts:
                # Lint code and show results
                lint_results = code_checker.lint_code(script, file_extension)
                code_checker.display_results(lint_results, script, file_extension)

                # Determine if there are critical errors that should block execution
                critical_errors = [
                    err for err in lint_results.get('errors', [])
                    if any(critical in err.lower() for critical in [
                        'syntax error', 'undefined variable', 'command not found'
                    ])
                ]

                if critical_errors:
                    print(f"{config.RED}Critical errors found that may affect execution:{config.RESET}")
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
                            execute_script(full_filename, "sh", config)
                else:
                    print("Failed to save script. Attempting direct execution...")
                    if get_user_confirmation("Execute script directly?", config):
                        execute_script_directly(script, file_extension, config)
        else:
            print("No executable script found in the LLM response.")
        return llm_response

    elif config.autopilot_mode:
        scripts = extract_script_from_response(llm_response)
        if scripts:
            # In autopilot mode, execute each script directly without confirmation
            for script, file_extension, script_type in scripts:
                # Perform basic linting to catch critical errors
                code_checker = CodeChecker()
                lint_results = code_checker.lint_code(script, file_extension)

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
        return llm_response

    return llm_response
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
        strictness = "Use balanced judgment in your evaluation. Accept responses that adequately address the main points."
        threshold = 0.75  # Moderate threshold
    
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
    
    # Truncate very long responses for processing
    truncated_response = response[:5000] if len(response) > 5000 else response
    
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
        return format_browser_response(query, response, config, chat_models)
    
    # For general and CLI responses, evaluate and use fallbacks if needed
    if not evaluate_response(query, response, config, chat_models, response_type):
        print(f"{config.YELLOW}Initial response was inadequate. Getting better response...{config.RESET}")
        
        # Try fallback LLM first
        improved_response = get_fallback_response(query, response, config, chat_models)
        
        # If fallback still inadequate and browser fallback is allowed, try browser
        if allow_browser_fallback and not evaluate_response(query, improved_response, config, chat_models, response_type):
            if _response_context['browser_attempts'] < 2:  # Limit browser attempts
                print(f"{config.YELLOW}Fallback response still inadequate. Trying browser search...{config.RESET}")
                _response_context['browser_attempts'] += 1
                
                # Try browser search
                browser_response = try_browser_search(query, config, chat_models)
                if browser_response:
                    # Store browser result in context
                    _response_context['collected_info']['browser_search'] = browser_response[:500]  # Store truncated version
                    
                    # Format the browser response
                    formatted_browser = format_browser_response(query, browser_response, config, chat_models)
                    
                    # Combine browser results with previous knowledge
                    final_response = chat_with_model(
                        message=(
                            f"Original query: {query}\n\n"
                            f"Previous responses: {improved_response}\n\n"
                            f"Browser search results: {formatted_browser}\n\n"
                            "Combine all this information to provide the most accurate and complete response."
                        ),
                        config=config,
                        chat_models=chat_models,
                        system_prompt=(
                            "You are a helpful expert assistant. Synthesize information from multiple sources "
                            "to provide the most accurate and complete response to the user's query."
                        )
                    )
                    return final_response
            else:
                print(f"{config.YELLOW}Maximum browser attempts reached. Using best available response.{config.RESET}")
        
        return improved_response
    return response

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
    
    url = f"https://www.google.com/search?q={search_query}"
    print(f"{config.CYAN}Trying browser search for: {search_query}{config.RESET}")
    
    try:
        # Try MCP browser tool first
        try:
            response = use_mcp_tool(
                server_name="small-context",
                tool_name="browse_web",
                arguments={"url": url}
            )
            if response:
                return response
        except Exception as e:
            print(f"{config.YELLOW}MCP browser failed: {str(e)}. Trying alternative search...{config.RESET}")
        
        # Fallback to using WebBrowser class directly
        from .small_context.protocol import WebBrowser
        browser = WebBrowser()
        result = browser.browse(url)
        return json.dumps(result)
    except Exception as e:
        print(f"{config.YELLOW}Browser search failed: {str(e)}{config.RESET}")
        return ""

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
        return process_response(query, response, config, chat_models, response_type="cli")
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
    global _response_context
    global _content_cache
    
    # Reset browser attempts counter for new queries
    _response_context['browser_attempts'] = 0
    
    # Check for tolerance level commands
    if query.lower().startswith("set tolerance "):
        level = query.lower().replace("set tolerance ", "").strip()
        set_evaluation_tolerance(level)
        print(f"{config.GREEN}Tolerance level set to: {level}{config.RESET}")
        return None
    
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
            return None
        
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
                "analysis and selection. Be precise and follow the specified format.\n\n"
                "IMPORTANT: For each request, decide if you should:\n"
                "1. Answer with your latent knowledge (direct_knowledge)\n"
                "2. Use a tool to get information (tool_based)\n"
                "3. Provide a hybrid response with both latent knowledge and tool-based information (hybrid)\n\n"
                "For hybrid responses, set confidence between 0.5-0.8 to indicate partial confidence."
            )
        )
        
        if not llm_analysis:
            print(f"{config.YELLOW}No response received from tool selection LLM analysis.{config.RESET}")
            llm_response = chat_with_model(query, config, chat_models)
            final_response = process_response(query, llm_response, config, chat_models, allow_browser_fallback=True)
            print_streamed_message(final_response, config.CYAN)
            return None
        
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
                    # Handle small_context tool
                    parameters = tool_selection.get("parameters", {})
                    url = parameters.get("url")
                    if not url or url == "[URL will be determined based on request]":
                        print(f"{config.RED}No valid URL provided in tool selection.{config.RESET}")
                        llm_response = chat_with_model(query, config, chat_models)
                        final_response = process_response(query, llm_response, config, chat_models, allow_browser_fallback=True)
                        print_streamed_message(final_response, config.CYAN)
                        return None

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
                                    print_streamed_message(llm_response, config.CYAN)
                                    
                                    # Print interaction hint
                                    print(f"\n{config.CYAN}You can interact with the content by asking questions or requesting more details about specific topics.{config.RESET}")
                                    return None
                                else:
                                    formatted_response = json.dumps(content, indent=2)
                                    llm_response = chat_with_model(
                                        message=f"Please summarize this content:\n\n{formatted_response}",
                                        config=config,
                                        chat_models=chat_models
                                    )
                                    print_streamed_message(llm_response, config.CYAN)
                                    return None
                            else:
                                formatted_response = str(content)
                                llm_response = chat_with_model(
                                    message=f"Please summarize this content:\n\n{formatted_response}",
                                    config=config,
                                    chat_models=chat_models
                                )
                                print_streamed_message(llm_response, config.CYAN)
                                return None
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
                        print_streamed_message(llm_response, config.CYAN)
                        return None
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
                    
                    print_streamed_message(llm_response, config.CYAN)
                    return None
                else:
                    # Default to standard LLM processing
                    llm_response = chat_with_model(query, config, chat_models)
                    final_response = process_response(query, llm_response, config, chat_models, allow_browser_fallback=True)
                    print_streamed_message(final_response, config.CYAN)
                    return None
            else:
                # Fallback if JSON extraction fails
                llm_response = chat_with_model(query, config, chat_models)
                final_response = process_response(query, llm_response, config, chat_models, allow_browser_fallback=True)
                print_streamed_message(final_response, config.CYAN)
                return None
        except (json.JSONDecodeError, KeyError, AttributeError) as e:
            print(f"{config.YELLOW}Failed to process tool selection: {str(e)}{config.RESET}")
            llm_response = chat_with_model(query, config, chat_models)
            final_response = process_response(query, llm_response, config, chat_models, allow_browser_fallback=True)
            print_streamed_message(final_response, config.CYAN)
            return None
    except Exception as e:
        print(f"{config.YELLOW}Using standard processing due to error: {str(e)}{config.RESET}")
        llm_response = chat_with_model(query, config, chat_models)
        final_response = process_response(query, llm_response, config, chat_models, allow_browser_fallback=True)
        print_streamed_message(final_response, config.CYAN)
        return None

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
                
                if not config.autopilot_mode and not get_user_confirmation(f"Execute script:\n{script}"):
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
    global _assembled_scripts
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
