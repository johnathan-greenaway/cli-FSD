"""Context Management Agent for determining optimal tool selection.

This agent analyzes user requests and determines whether to use the Small Context Protocol
or other tools like fetch, sequential thinking, etc. based on the nature of the task.
"""

from typing import Dict, List, Optional, Union
import json

class ContextAgent:
    """Agent for context-aware tool selection."""
    
    def analyze_request(self, request: str) -> Dict[str, any]:
        """Analyze user request to determine optimal tool selection.
        
        This method generates a prompt for the LLM to analyze the request and
        determine which tools/approaches would be most effective.
        
        Args:
            request: The user's natural language request
            
        Returns:
            Dict containing:
            - tool_selection: Selected tool/approach
            - context_id: Context ID if using small context protocol
            - reasoning: Explanation of the selection
            - parameters: Tool-specific parameters
        """
        prompt = self._generate_analysis_prompt(request)
        
        # This will be processed by the LLM to determine:
        # 1. If the task benefits from context management (e.g. multi-step reasoning,
        #    information synthesis, maintaining conversation state)
        # 2. If other tools like fetch or sequential thinking are more appropriate
        # 3. What parameters/approach to use
        return {
            "prompt": prompt,
            "requires_llm_processing": True
        }
    
    def _generate_analysis_prompt(self, request: str) -> str:
        """Generate prompt for LLM analysis of the request."""
        return f"""Analyze the following user request and determine the optimal tool selection:

User Request: {request}

Available Tools:
1. Small Context Protocol
   - Best for: Managing conversation context, multi-step reasoning, information synthesis
   - Features: Priority-based context management, token optimization, entity tracking

2. Fetch Tool
   - Best for: Retrieving external information, web scraping, API calls
   - Features: Clean data extraction, content processing

3. Sequential Thinking
   - Best for: Breaking down complex problems, step-by-step reasoning
   - Features: Structured problem decomposition, dependency tracking

4. Default Tools
   - Best for: Simple file operations, command execution, basic tasks
   - Features: File reading/writing, command execution, basic operations

Analysis Instructions:
1. Evaluate if the request involves:
   - Managing conversation context
   - Multi-step reasoning
   - Information synthesis
   - External data retrieval
   - Complex problem solving
   
2. Consider:
   - Token efficiency requirements
   - Need for context preservation
   - Information dependencies
   - External resource needs

3. Determine:
   - Primary tool selection
   - Required parameters
   - Context management needs
   - Integration requirements

Provide your analysis in JSON format:
{
    "selected_tool": "tool_name",
    "reasoning": "Detailed explanation of selection",
    "parameters": {
        "param1": "value1",
        ...
    },
    "context_management": {
        "required": boolean,
        "priority_level": "critical|important|supplementary",
        "entities": [],
        "relationships": []
    }
}"""

    def execute_tool_selection(self, analysis: Dict[str, any]) -> Dict[str, any]:
        """Execute the selected tool based on LLM analysis.
        
        Args:
            analysis: The LLM's analysis of the request
            
        Returns:
            Dict containing execution results
        """
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
    
    def _handle_small_context(
        self,
        parameters: Dict[str, any],
        context_config: Dict[str, any]
    ) -> Dict[str, any]:
        """Handle Small Context Protocol execution."""
        if context_config.get("required", False):
            # Use MCP tool for context management
            return {
                "tool": "use_mcp_tool",
                "server": "small-context",
                "operation": parameters.get("operation", "create_context"),
                "arguments": {
                    "contextId": parameters.get("context_id"),
                    "content": parameters.get("content"),
                    "priority": context_config.get("priority_level", "important"),
                    "entities": context_config.get("entities", []),
                    "relationships": context_config.get("relationships", [])
                }
            }
        return {"error": "Context management not required"}
    
    def _handle_fetch(self, parameters: Dict[str, any]) -> Dict[str, any]:
        """Handle fetch tool execution."""
        return {
            "tool": "use_mcp_tool",
            "server": "fetch-server",
            "operation": "fetch",
            "arguments": parameters
        }
    
    def _handle_sequential_thinking(
        self,
        parameters: Dict[str, any]
    ) -> Dict[str, any]:
        """Handle sequential thinking execution."""
        return {
            "tool": "use_mcp_tool",
            "server": "sequential-thinking",
            "operation": "think",
            "arguments": parameters
        }
    
    def _handle_default_tools(self, parameters: Dict[str, any]) -> Dict[str, any]:
        """Handle default tool execution."""
        return {
            "tool": parameters.get("tool", "execute_command"),
            "arguments": parameters
        }
