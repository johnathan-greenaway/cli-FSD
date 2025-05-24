"""Context Agent for tool selection and command parsing.

This module provides an agent that analyzes user requests and determines
which tools to use for processing them.
"""

import json
import logging
from typing import Dict, Any, Optional, List
import platform
import os
from datetime import datetime

# Configure logging
logging.basicConfig(level=logging.INFO,
                   format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class ContextAgent:
    """Agent for analyzing requests and selecting appropriate tools."""
    
    def __init__(self):
        """Initialize the context agent."""
        self.system_info = self._get_system_info()
        self.tools = {
            'web_content': ['fetch', 'browse', 'search'],
            'file_operation': ['read', 'write', 'append', 'delete'],
            'command': ['shell', 'python', 'bash'],
            'memory': ['create_entities', 'add_observations', 'search_nodes', 'read_graph']
        }
        self.context = {
            'last_web_content': None,
            'last_operation': None,
            'last_url': None,
            'last_query': None,
            'session_history': []
        }
    
    def _get_system_info(self) -> Dict[str, str]:
        """Get system information for context.
        
        Returns:
            Dictionary containing system information
        """
        return {
            'os': platform.system(),
            'os_version': platform.version(),
            'architecture': platform.machine(),
            'python_version': platform.python_version(),
            'cpu': platform.processor(),
            'cwd': os.getcwd()
        }
    
    def update_context(self, operation: str, result: Dict[str, Any]) -> None:
        """Update the context with the latest operation result.
        
        Args:
            operation: The operation that was performed
            result: The result of the operation
        """
        self.context['last_operation'] = operation
        if operation in self.tools['web_content']:
            self.context['last_web_content'] = result
            if 'url' in result:
                self.context['last_url'] = result['url']
        elif operation in self.tools['file_operation']:
            self.context['last_file_operation'] = result
            if 'filepath' in result:
                self.context['last_filepath'] = result['filepath']
        
        # Add to session history
        self.context['session_history'].append({
            'timestamp': datetime.now().isoformat(),
            'operation': operation,
            'result': result
        })
    
    def analyze_request(self, query: str, routing_metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Analyze a user request to determine which tool to use.
        
        Args:
            query: User's request to analyze
            routing_metadata: Optional metadata from query router
            
        Returns:
            Dictionary containing analysis results and prompt for LLM
        """
        # Check for follow-up queries
        is_follow_up = self._is_follow_up_query(query)
        
        # For file operations like creating directories, return a direct response
        if "make a folder" in query.lower() or "create a directory" in query.lower():
            folder_name = query.lower().replace("make a folder", "").replace("create a directory", "").replace("called", "").strip()
            return {
                "tool": "command",
                "operation": "shell",
                "command": f"mkdir {folder_name}",
                "requires_llm_processing": False,
                "description": f"Create a directory named '{folder_name}'"
            }
        
        # For file creation requests, provide a more structured prompt
        # But exclude queries that are about using tools
        query_lower = query.lower()
        is_file_creation = any(word in query_lower for word in ['create', 'make', 'write']) and \
                          'file' in query_lower and \
                          'tool' not in query_lower
        
        if is_file_creation:
            prompt = f"""Analyze the following request and determine how to create the requested file.
System Information:
{json.dumps(self.system_info, indent=2)}

Available Tools:
{json.dumps(self.tools, indent=2)}

{self._get_context_prompt() if is_follow_up else ''}

User Request: {query}

Please respond with a JSON object containing:
1. "tool": "file_operation"
2. "operation": "write"
3. "filepath": The full path where the file should be created
4. "content": The complete content of the file to be created
5. "description": A brief description of what the file will do

Example response for creating a Python script:
{{
    "tool": "file_operation",
    "operation": "write",
    "filepath": "scripts/example.py",
    "content": "def main():\\n    print('Hello, World!')\\n\\nif __name__ == '__main__':\\n    main()",
    "description": "Create a Python script that prints 'Hello, World!'"
}}

IMPORTANT: 
- Ensure the filepath is valid for the current system ({self.system_info['os']})
- Include all necessary imports and code structure
- Make sure the content is properly escaped for JSON
- The content should be a complete, working file"""

            return {
                "prompt": prompt,
                "requires_llm_processing": True
            }
        
        # Build routing hints if metadata is provided
        routing_hints = ""
        if routing_metadata:
            if routing_metadata.get('metadata', {}).get('requested_tool'):
                tool = routing_metadata['metadata']['requested_tool']
                routing_hints = f"\nROUTING HINT: The user explicitly requested to use the '{tool}' tool.\n"
                if tool == 'browse_web' and 'news' in query.lower():
                    routing_hints += "For news browsing, select an appropriate news website URL based on the type of news requested.\n"
            elif routing_metadata.get('metadata', {}).get('suggested_tool'):
                tool = routing_metadata['metadata']['suggested_tool']
                score = routing_metadata['metadata'].get('browse_score', 0)
                routing_hints = f"\nROUTING HINT: Query analysis suggests using the '{tool}' tool (confidence score: {score}).\n"
        
        # For other requests, use the default prompt
        prompt = f"""Analyze the following request and determine which tool to use.
System Information:
{json.dumps(self.system_info, indent=2)}

Available Tools:
{json.dumps(self.tools, indent=2)}
{routing_hints}
{self._get_context_prompt() if is_follow_up else ''}

User Request: {query}

Please respond with a JSON object containing:
1. "tool": The type of tool to use (web_content, file_operation, or command)
2. "operation": The specific operation to perform
3. Additional fields based on the tool type:
   - For web_content: "url_or_query" and optional "mode"
   - For file_operation: "filepath" and optional "content"
   - For command: "command" (the shell command to execute)

Example responses:
{{
    "tool": "browse_web",
    "url": "https://news.ycombinator.com",
    "description": "Browse Hacker News for latest tech stories"
}}

For news requests without a specific site, use one of these popular news sources:
- Tech news: https://news.ycombinator.com or https://techcrunch.com
- General news: https://www.reddit.com/r/news or https://news.google.com
- World news: https://www.bbc.com/news or https://www.reuters.com

{{
    "tool": "web_content",
    "operation": "browse",
    "url_or_query": "latest news stories",
    "mode": "basic"
}}

{{
    "tool": "file_operation",
    "operation": "write",
    "filepath": "output.txt",
    "content": "Hello, World!"
}}

{{
    "tool": "command",
    "operation": "shell",
    "command": "ls -la"
}}

{{
    "tool": "memory",
    "operation": "create_entities",
    "entities": [{{"name": "user_preferences", "type": "configuration"}}]
}}

{{
    "tool": "memory",
    "operation": "add_observations",
    "observations": [{{"entity": "user_preferences", "content": "Prefers dark mode"}}]
}}

IMPORTANT: 
- For browse requests, prefer "tool": "browse_web" with a specific URL when the user wants to browse content
- For memory operations, use the memory tool to store and retrieve information across sessions
- For command operations, ensure the command is compatible with the current system ({self.system_info['os']})
- Only output valid shell commands that can be executed on this system"""

        return {
            "prompt": prompt,
            "requires_llm_processing": True
        }
    
    def _is_follow_up_query(self, query: str) -> bool:
        """Check if the query is a follow-up to a previous operation.
        
        Args:
            query: The query to check
            
        Returns:
            True if the query appears to be a follow-up
        """
        follow_up_indicators = [
            'it', 'that', 'this', 'those', 'these', 'them',
            'the story', 'the article', 'the page', 'the file',
            'read', 'show', 'tell me more', 'what about',
            'how about', 'and', 'but', 'also'
        ]
        
        query_lower = query.lower()
        return any(indicator in query_lower for indicator in follow_up_indicators)
    
    def _get_context_prompt(self) -> str:
        """Get a prompt describing the current context.
        
        Returns:
            A string describing the current context
        """
        context_parts = []
        
        if self.context.get('last_web_content'):
            context_parts.append(f"Last web content: {self.context['last_web_content'].get('title', 'Unknown')}")
            if self.context.get('last_url'):
                context_parts.append(f"Last URL: {self.context['last_url']}")
        
        if self.context.get('last_operation'):
            context_parts.append(f"Last operation: {self.context['last_operation']}")
            if self.context.get('last_filepath'):
                context_parts.append(f"Last filepath: {self.context['last_filepath']}")
        
        if context_parts:
            return "Current Context:\n" + "\n".join(context_parts) + "\n"
        return ""
    
    def parse_command(self, command: str) -> Dict[str, Any]:
        """Parse a command string into its components.
        
        Args:
            command: Command string to parse
            
        Returns:
            Dictionary containing parsed command details
        """
        # Check for natural language commands first
        if self._is_natural_language_command(command):
            return self._parse_natural_language_command(command)
        
        # Basic command parsing
        parts = command.strip().split()
        if not parts:
            return {'error': 'Empty command'}
        
        operation = parts[0].lower()
        
        # Check if operation matches any known tool
        for tool_type, operations in self.tools.items():
            if operation in operations:
                return {
                    'tool': tool_type,
                    'operation': operation,
                    'args': parts[1:] if len(parts) > 1 else []
                }
        
        # If no matching operation found, treat as a shell command
        return {
            'tool': 'command',
            'operation': 'shell',
            'command': command
        }
    
    def _is_natural_language_command(self, command: str) -> bool:
        """Check if the command is in natural language format.
        
        Args:
            command: The command to check
            
        Returns:
            True if the command appears to be in natural language
        """
        # Check for common natural language patterns
        patterns = [
            'browse', 'read', 'show', 'tell me about', 'what is',
            'find', 'search', 'look up', 'get', 'fetch',
            'organize', 'sort', 'arrange', 'manage',
            'create', 'make', 'write', 'save'
        ]
        
        command_lower = command.lower()
        return any(pattern in command_lower for pattern in patterns)
    
    def _parse_natural_language_command(self, command: str) -> Dict[str, Any]:
        """Parse a natural language command into a structured command.
        
        Args:
            command: The natural language command to parse
            
        Returns:
            Dictionary containing parsed command details
        """
        command_lower = command.lower()
        
        # Handle web content requests
        if any(word in command_lower for word in ['browse', 'read', 'show', 'tell me about']):
            if 'hacker news' in command_lower or 'hn' in command_lower:
                return {
                    'tool': 'web_content',
                    'operation': 'browse',
                    'url_or_query': 'https://news.ycombinator.com/',
                    'mode': 'basic'
                }
            elif 'reddit' in command_lower:
                return {
                    'tool': 'web_content',
                    'operation': 'browse',
                    'url_or_query': 'https://www.reddit.com/',
                    'mode': 'basic'
                }
            else:
                # Extract the search query
                query = command_lower.replace('browse', '').replace('read', '').replace('show', '').replace('tell me about', '').strip()
                return {
                    'tool': 'web_content',
                    'operation': 'search',
                    'url_or_query': query,
                    'mode': 'basic'
                }
        
        # Handle file operations
        elif any(word in command_lower for word in ['organize', 'sort', 'arrange', 'manage']):
            return {
                'tool': 'file_operation',
                'operation': 'organize',
                'filepath': '.',  # Current directory
                'content': None
            }
        
        # Default to web search for unknown commands
        return {
            'tool': 'web_content',
            'operation': 'search',
            'url_or_query': command,
            'mode': 'basic'
        }
    
    def validate_command(self, command: Dict[str, Any]) -> bool:
        """Validate a parsed command for the current system.
        
        Args:
            command: Parsed command to validate
            
        Returns:
            True if command is valid, False otherwise
        """
        if command.get('tool') == 'command':
            cmd = command.get('command', '')
            
            # Basic validation for shell commands
            if self.system_info['os'] == 'Windows':
                # Windows-specific validation
                if cmd.startswith('./') or cmd.startswith('bash '):
                    return False
            else:
                # Unix-like system validation
                if cmd.startswith('cmd ') or cmd.startswith('powershell '):
                    return False
            
            # Check for potentially dangerous commands
            dangerous_commands = ['rm -rf', 'format', 'dd', 'mkfs']
            if any(dc in cmd.lower() for dc in dangerous_commands):
                return False
        
        return True
    
    def format_command(self, command: Dict[str, Any]) -> str:
        """Format a parsed command for execution.
        
        Args:
            command: Parsed command to format
            
        Returns:
            Formatted command string
        """
        if command.get('tool') == 'command':
            return command.get('command', '')
        
        if command.get('tool') == 'file_operation':
            operation = command.get('operation', '')
            filepath = command.get('filepath', '')
            content = command.get('content', '')
            
            if operation in ['write', 'append']:
                return f"{operation} {filepath} {content}"
            return f"{operation} {filepath}"
        
        if command.get('tool') == 'web_content':
            operation = command.get('operation', '')
            url_or_query = command.get('url_or_query', '')
            mode = command.get('mode', 'basic')
            return f"{operation} {url_or_query} {mode}"
        
        return ''

    def execute_tool_selection(self, analysis: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a tool selection based on the analysis.
        
        Args:
            analysis: Dictionary containing tool selection analysis
            
        Returns:
            Dictionary containing the tool execution details
        """
        selected_tool = analysis.get("selected_tool", "default")
        parameters = analysis.get("parameters", {})
        
        # Handle small context tool
        if selected_tool == "small_context":
            context_config = analysis.get("context_management", {})
            if not context_config.get("required", False):
                return {"error": "Context management not required"}
                
            return {
                "tool": "use_mcp_tool",
                "server": "small-context",
                "operation": parameters.get("operation", "create_context"),
                "arguments": {
                    "contextId": parameters.get("context_id", ""),
                    "content": parameters.get("content", ""),
                    "priority": context_config.get("priority_level", "important"),
                    "entities": context_config.get("entities", []),
                    "relationships": context_config.get("relationships", [])
                }
            }
            
        # Handle fetch tool
        elif selected_tool == "fetch":
            return {
                "tool": "use_mcp_tool",
                "server": "fetch-server",
                "operation": "fetch",
                "arguments": {
                    "url": parameters.get("url", ""),
                    "selector": parameters.get("selector", "")
                }
            }
            
        # Handle sequential thinking tool
        elif selected_tool == "sequential_thinking":
            return {
                "tool": "use_mcp_tool",
                "server": "sequential-thinking",
                "operation": "think",
                "arguments": {
                    "steps": parameters.get("steps", []),
                    "problem": parameters.get("problem", "")
                }
            }
            
        # Handle web content tools
        elif selected_tool in self.tools['web_content']:
            url = parameters.get("url", "")
            return {
                "tool": "use_mcp_tool",
                "server": "small-context",
                "operation": selected_tool,
                "arguments": {
                    "url": url,
                    "mode": parameters.get("mode", "basic")
                }
            }
            
        # Default to command execution
        return {
            "tool": "execute_command",
            "arguments": {
                "command": parameters.get("command", ""),
                "operation": parameters.get("operation", "process_command"),
                "content": parameters.get("content", "")
            }
        }
