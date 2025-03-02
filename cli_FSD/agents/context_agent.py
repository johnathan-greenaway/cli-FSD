"""Context Management Agent for determining optimal tool selection.

This agent analyzes user requests and determines whether to use the Small Context Protocol
or other tools like fetch, sequential thinking, etc. based on the nature of the task.
"""

from typing import Any, Dict, List, Optional, Union
import json
import time


class ContextAgent:
    """Agent for context-aware tool selection."""
    
    def analyze_request(self, request: str) -> Dict[str, Any]:
        """Analyze user request to determine optimal tool selection.
        
        This method generates a prompt for the LLM to analyze the request and
        determine which tools/approaches would be most effective.
        
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
    "selected_tool": "tool_name",
    "reasoning": "Explanation of why this tool was selected",
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
4. IMPORTANT: For specific commands:
   - Queries that mention weather: Use 'curl wttr.in/[location]' command instead of web browsing
   - Time queries: Use appropriate system commands
   - File operations: Use standard Unix commands""",
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
            selected_tool = analysis.get("selected_tool")
            parameters = analysis.get("parameters", {})
            
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
