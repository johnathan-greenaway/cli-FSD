"""Context Management Agent for determining optimal tool selection.

This agent analyzes user requests and determines whether to use the Small Context Protocol
or other tools like fetch, sequential thinking, etc. based on the nature of the task.
It can also provide hybrid responses that combine latent knowledge with tool-based answers.
"""

from typing import Any, Dict, List, Optional, Union
import json
import time
import threading


class ContextAgent:
    """Agent for context-aware tool selection with hybrid response capabilities."""
    
    def __init__(self):
        """Initialize the context agent."""
        self._tool_response_cache = {}
        self._background_tasks = {}
    
    def analyze_request(self, request: str) -> Dict[str, Any]:
        """Analyze user request to determine optimal tool selection.
        
        This method generates a prompt for the LLM to analyze the request and
        determine which tools/approaches would be most effective, including
        the possibility of a hybrid response.
        
        Args:
            request: The user's natural language request
            
        Returns:
            Dict containing:
            - prompt: The generated prompt for LLM analysis
            - requires_llm_processing: Whether LLM processing is needed
        """
        return {
            "prompt": f"""Analyze this request: "{request}"

You are an expert in tool selection and content analysis. Your task is to determine the best way to handle this request.

Respond with a JSON object in this format:
{{
    "response_type": "direct_knowledge|tool_based|hybrid",
    "confidence": 0.0-1.0,
    "selected_tool": "tool_name",
    "reasoning": "Explanation of why this approach was selected",
    "parameters": {{
        "operation": "operation_name",
        "url": "url_if_needed",
        "content": "{request}"
    }},
    "context_management": {{
        "required": true,
        "priority_level": "important",
        "entities": [],
        "relationships": []
    }}
}}

Response types:
1. direct_knowledge: Use when you can confidently answer with your latent knowledge
2. tool_based: Use when a tool is clearly needed to provide an accurate response
3. hybrid: Use when you can provide a partial answer from latent knowledge but a tool would provide more complete information

Available tools and operations:
1. small_context
   - browse_web: For web browsing and content extraction
   - create_context: For managing conversation context
2. fetch: For data retrieval
3. sequential_thinking: For complex reasoning
4. default: For simple commands. USE THIS FOR WEATHER REQUESTS.

Guidelines:
1. For web browsing:
   - Always include complete URLs with https://
   - Choose authoritative sources
   - Consider the type of content needed
2. For context management:
   - Set appropriate priority level
   - Identify relevant entities
   - Track relationships between concepts
3. For tool selection:
   - Consider the complexity of the request
   - Evaluate need for context preservation
   - Assess if external data is needed
   - Set confidence level based on how certain you are that the selected approach is optimal
4. IMPORTANT: For specific commands:
   - Queries that mention weather: Use 'curl wttr.in/[location]' command instead of web browsing
   - Time queries: Use appropriate system commands
   - File operations: Use standard Unix commands
5. For hybrid responses:
   - Provide a confidence score between 0.5-0.8 (indicating partial confidence)
   - Select the tool that would provide the most complete information
   - The system will provide a preview of latent knowledge while preparing the tool response""",
            "requires_llm_processing": True
        }
    
    def execute_tool_selection(self, analysis: Dict[str, Any]) -> Dict[str, Any]:
        """Execute the selected tool based on LLM analysis.
        
        Args:
            analysis: The LLM's analysis of the request
            
        Returns:
            Dict containing execution results
        """
        try:
            response_type = analysis.get("response_type", "tool_based")
            selected_tool = analysis.get("selected_tool")
            parameters = analysis.get("parameters", {})
            confidence = analysis.get("confidence", 0.0)
            
            # Handle different response types
            if response_type == "direct_knowledge":
                return {
                    "type": "direct_knowledge",
                    "confidence": confidence,
                    "requires_tools": False,
                    "message": "Use latent knowledge to answer directly"
                }
            elif response_type == "hybrid":
                return self._handle_hybrid_response(
                    selected_tool,
                    parameters,
                    analysis.get("context_management", {}),
                    confidence
                )
            else:  # tool_based (default)
                if selected_tool == "small_context":
                    return self._handle_small_context(
                        parameters,
                        analysis.get("context_management", {})
                    )
                elif selected_tool == "fetch":
                    return self._handle_fetch(parameters)
                elif selected_tool == "sequential_thinking":
                    return self._handle_sequential_thinking(parameters)
                else:
                    return self._handle_default_tools(parameters)
        except Exception as e:
            return {
                "type": "error",
                "error": f"Tool execution failed: {str(e)}"
            }
    
    def _handle_hybrid_response(
        self,
        selected_tool: str,
        parameters: Dict[str, Any],
        context_config: Dict[str, Any],
        confidence: float
    ) -> Dict[str, Any]:
        """Handle hybrid response that combines latent knowledge with tool-based answers.
        
        Args:
            selected_tool: The tool selected for the complete answer
            parameters: Parameters for tool execution
            context_config: Configuration for context management
            confidence: Confidence level in the latent knowledge portion
            
        Returns:
            Dict containing hybrid response configuration
        """
        # Create a unique ID for this hybrid response
        response_id = f"hybrid_{int(time.time())}"
        
        # Prepare the tool response in the background
        tool_response = None
        if selected_tool == "small_context":
            tool_response = self._handle_small_context(parameters, context_config)
        elif selected_tool == "fetch":
            tool_response = self._handle_fetch(parameters)
        elif selected_tool == "sequential_thinking":
            tool_response = self._handle_sequential_thinking(parameters)
        else:
            tool_response = self._handle_default_tools(parameters)
        
        # Cache the tool response
        self._tool_response_cache[response_id] = tool_response
        
        # Return hybrid response configuration
        return {
            "type": "hybrid",
            "response_id": response_id,
            "confidence": confidence,
            "preview_message": "Provide a brief answer from latent knowledge",
            "tool_info": {
                "tool": selected_tool,
                "parameters": parameters
            },
            "requires_user_choice": True
        }
    
    def get_cached_tool_response(self, response_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve a cached tool response by ID.
        
        Args:
            response_id: The unique ID of the cached response
            
        Returns:
            The cached tool response or None if not found
        """
        return self._tool_response_cache.get(response_id)
    
    def _handle_small_context(
        self,
        parameters: Dict[str, Any],
        context_config: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Handle Small Context Protocol execution."""
        operation = parameters.get("operation", "create_context")
        
        # Handle web browsing operation
        if operation == "browse_web":
            # Create a new context ID for this browsing session
            context_id = f"web_{int(time.time())}"
            
            # Get URL from parameters or use default
            url = parameters.get("url")
            if not url:
                # This shouldn't happen since the LLM should always provide a URL
                url = "https://www.google.com"  # Fallback to Google if somehow no URL was provided
                
            return {
                "tool": "use_mcp_tool",
                "server": "small-context",
                "operation": "browse_web",
                "arguments": {
                    "url": url,
                    "priority": context_config.get("priority_level", "important"),
                    "context_id": context_id
                }
            }
            
        # Handle standard context operations
        if context_config.get("required", False):
            return {
                "tool": "use_mcp_tool",
                "server": "small-context",
                "operation": operation,
                "arguments": {
                    "contextId": parameters.get("context_id"),
                    "content": parameters.get("content"),
                    "priority": context_config.get("priority_level", "important"),
                    "entities": context_config.get("entities", []),
                    "relationships": context_config.get("relationships", [])
                }
            }
        return {"error": "Context management not required"}
    
    def _handle_fetch(self, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """Handle fetch tool execution."""
        return {
            "tool": "use_mcp_tool",
            "server": "fetch-server",
            "operation": "fetch",
            "arguments": parameters
        }
    
    def _handle_sequential_thinking(
        self,
        parameters: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Handle sequential thinking execution."""
        return {
            "tool": "use_mcp_tool",
            "server": "sequential-thinking",
            "operation": "think",
            "arguments": parameters
        }
    
    def _handle_default_tools(self, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """Handle default tool execution."""
        return {
            "tool": parameters.get("tool", "execute_command"),
            "arguments": parameters
        }
