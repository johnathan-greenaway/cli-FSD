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
        # Prevent certain problematic requests that should be handled differently
        if any(pattern in request.lower() for pattern in [
            "browse news", "browse financial news", "browse stock", 
            "open browser", "open a browser", "open web browser", "launch browser"
        ]):
            # Create a special direct knowledge prompt for browser-related requests
            return {
                "prompt": json.dumps({
                    "response_type": "direct_knowledge",
                    "confidence": 0.9,
                    "selected_tool": "none",
                    "reasoning": "User is asking to browse news/financial sites. Using built-in knowledge instead of browser instructions.",
                    "parameters": {
                        "content": request
                    }
                }),
                "requires_llm_processing": False  # Skip further LLM processing
            }
        
        # Check for file interaction requests
        file_interaction_patterns = [
            "list files", "list directory", "list folder", "show files", "show directory", "show folder",
            "read file", "read the file", "read the contents", "show file contents", "display file", "cat file",
            "write file", "write to file", "create file", "make file", "save file", "save to file",
            "modify file", "edit file", "change file", "update file", "replace in file", "replace text in file",
            "delete file", "remove file", "erase file",
            "search file", "search in file", "search files", "search in files", "find in files", "grep",
            "create directory", "create folder", "make directory", "make folder", "mkdir",
            "use file tool", "use the file tool", "with file tool", "with the file tool", 
            "using file tool", "using the file tool", "file interaction tool"
        ]
        
        if any(pattern in request.lower() for pattern in file_interaction_patterns):
            # Determine the specific file operation
            operation = None
            path = None
            
            # Extract potential file path from the request
            # This is a simple extraction and might need refinement
            words = request.split()
            for i, word in enumerate(words):
                if word.endswith(('.txt', '.py', '.js', '.html', '.css', '.md', '.json', '.xml', '.csv')):
                    path = word
                    break
                elif i < len(words) - 1 and words[i] in ["file", "directory", "folder"] and i > 0:
                    path = words[i-1]
                    break
            
            # Determine operation type
            if any(pattern in request.lower() for pattern in ["list files", "list directory", "list folder", "show files", "show directory", "show folder"]) or (
                any(pattern in request.lower() for pattern in ["use file tool", "use the file tool", "with file tool", "with the file tool", "using file tool", "using the file tool", "file interaction tool"]) and 
                any(pattern in request.lower() for pattern in ["list", "show", "display"])
            ):
                operation = "list_files"
                # If no path was specified, default to current directory
                if not path:
                    path = "."
            elif any(pattern in request.lower() for pattern in ["read file", "read the file", "read the contents", "show file contents", "display file", "cat file"]) or (
                any(pattern in request.lower() for pattern in ["use file tool", "use the file tool", "with file tool", "with the file tool", "using file tool", "using the file tool", "file interaction tool"]) and 
                any(pattern in request.lower() for pattern in ["read", "cat", "view", "display contents"])
            ):
                operation = "read_file"
            elif any(pattern in request.lower() for pattern in ["write file", "write to file", "create file", "make file", "save file", "save to file"]) or (
                any(pattern in request.lower() for pattern in ["use file tool", "use the file tool", "with file tool", "with the file tool", "using file tool", "using the file tool", "file interaction tool"]) and 
                any(pattern in request.lower() for pattern in ["write", "create", "make", "save"])
            ):
                operation = "write_file"
            elif any(pattern in request.lower() for pattern in ["modify file", "edit file", "change file", "update file", "replace in file", "replace text in file"]) or (
                any(pattern in request.lower() for pattern in ["use file tool", "use the file tool", "with file tool", "with the file tool", "using file tool", "using the file tool", "file interaction tool"]) and 
                any(pattern in request.lower() for pattern in ["modify", "edit", "change", "update", "replace"])
            ):
                operation = "modify_file"
            elif any(pattern in request.lower() for pattern in ["delete file", "remove file", "erase file"]) or (
                any(pattern in request.lower() for pattern in ["use file tool", "use the file tool", "with file tool", "with the file tool", "using file tool", "using the file tool", "file interaction tool"]) and 
                any(pattern in request.lower() for pattern in ["delete", "remove", "erase"])
            ):
                operation = "delete_file"
            elif any(pattern in request.lower() for pattern in ["search file", "search in file", "search files", "search in files", "find in files", "grep"]) or (
                any(pattern in request.lower() for pattern in ["use file tool", "use the file tool", "with file tool", "with the file tool", "using file tool", "using the file tool", "file interaction tool"]) and 
                any(pattern in request.lower() for pattern in ["search", "find", "grep"])
            ):
                operation = "search_files"
            elif any(pattern in request.lower() for pattern in ["create directory", "create folder", "make directory", "make folder", "mkdir"]) or (
                any(pattern in request.lower() for pattern in ["use file tool", "use the file tool", "with file tool", "with the file tool", "using file tool", "using the file tool", "file interaction tool"]) and 
                any(pattern in request.lower() for pattern in ["create directory", "create folder", "make directory", "make folder", "mkdir"])
            ):
                operation = "create_directory"
            
            if operation:
                return {
                    "prompt": json.dumps({
                        "response_type": "tool_based",
                        "confidence": 0.9,
                        "selected_tool": "file_interaction",
                        "reasoning": f"User is requesting a file operation: {operation}",
                        "parameters": {
                            "operation": operation,
                            "path": path,
                            "content": request
                        }
                    }),
                    "requires_llm_processing": False  # Skip further LLM processing
                }
        return {
            "prompt": f"""Analyze this request: "{request}"

You are an expert in tool selection and content analysis with a strong preference for using your built-in knowledge whenever possible. Your task is to determine the best way to handle this request.

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
1. direct_knowledge: STRONGLY PREFERRED - Use whenever you can reasonably answer with your built-in knowledge
2. tool_based: Use ONLY when a tool is ABSOLUTELY NECESSARY to provide an accurate response
3. hybrid: Use when you can provide a substantial answer from built-in knowledge but specific details require tool support

Available tools and operations:
1. small_context
   - browse_web: For web browsing and content extraction - ONLY use for very specific current information or data that you cannot possibly know
   - create_context: For managing conversation context
2. fetch: For data retrieval
3. sequential_thinking: For complex reasoning
4. file_interaction: For file operations
   - list_files: List files in a directory
   - read_file: Read the contents of a file
   - write_file: Write content to a file
   - modify_file: Modify specific parts of a file
   - delete_file: Delete a file
   - search_files: Search for text in files
   - create_directory: Create a directory
5. default: For simple commands. USE THIS FOR WEATHER REQUESTS.

Guidelines:
1. STRONG PREFERENCE FOR BUILT-IN KNOWLEDGE:
   - For coding tasks like "create a Next.js project", "write a Python script", etc., ALWAYS use direct_knowledge response
   - For general technical questions about frameworks, languages, or common development practices, use direct_knowledge
   - For explanations of concepts, algorithms, or patterns, use direct_knowledge
   - Always set a high confidence (0.8-0.95) when using direct_knowledge for technical/programming questions

2. For web browsing (use SPARINGLY):
   - ONLY use for highly specific current information like "latest React release notes"
   - ONLY use for specific documentation lookups that require exact details from a recent version
   - ONLY use when the user explicitly asks for content from a specific website
   - Always include complete URLs with https://
   - Never use web browsing for general programming knowledge or how-to questions
   - Never use web browsing for tasks you can perform with your built-in knowledge

3. For context management:
   - Set appropriate priority level
   - Identify relevant entities
   - Track relationships between concepts

4. IMPORTANT: For specific commands:
   - Queries that mention weather: Use 'curl wttr.in/[location]' command instead of web browsing
   - Time queries: Use appropriate system commands
   - Simple file operations: Use standard Unix commands
   - Complex file operations: Use the file_interaction tool for operations like listing, reading, writing, modifying, deleting files, searching in files, and creating directories

5. For hybrid responses:
   - Provide a confidence score between 0.5-0.8 (indicating partial confidence)
   - Select the tool that would provide the most complete information
   - The system will provide a preview of built-in knowledge while preparing the tool response
   - Only use hybrid when you are confident your built-in knowledge covers 75% of what's needed""",
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
                elif selected_tool == "file_interaction":
                    return self._handle_file_interaction(parameters)
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
        elif selected_tool == "file_interaction":
            tool_response = self._handle_file_interaction(parameters)
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
    
    def _handle_file_interaction(self, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """Handle file interaction tool execution.
        
        Args:
            parameters: Parameters for the file interaction tool
            
        Returns:
            Dict containing the tool execution configuration
        """
        operation = parameters.get("operation")
        path = parameters.get("path")
        content = parameters.get("content")
        
        # Default arguments for each operation type
        arguments = {"path": path} if path else {}
        
        # Add operation-specific arguments
        if operation == "list_files":
            # Extract additional parameters from the content if needed
            recursive = "recursive" in content.lower()
            arguments.update({
                "recursive": recursive,
                "pattern": "*"  # Default pattern
            })
        elif operation == "read_file":
            # No additional arguments needed for read_file
            pass
        elif operation == "write_file":
            # For write operations, we need content
            # This is a simplified approach - in a real implementation,
            # we would need to extract the content to write from the user's request
            arguments.update({
                "content": "Content to be determined by LLM",
                "requires_approval": True
            })
        elif operation == "modify_file":
            # For modify operations, we need operations list
            # This is a simplified approach - in a real implementation,
            # we would need to extract the operations from the user's request
            arguments.update({
                "operations": [],  # To be filled by LLM
                "requires_approval": True
            })
        elif operation == "delete_file":
            arguments.update({
                "requires_approval": True
            })
        elif operation == "search_files":
            # Extract search pattern from content
            pattern = "pattern to be determined by LLM"
            arguments.update({
                "pattern": pattern,
                "recursive": True,
                "file_pattern": "*",
                "context_lines": 2
            })
        elif operation == "create_directory":
            arguments.update({
                "parents": True,
                "requires_approval": False
            })
        
        return {
            "tool": "use_mcp_tool",
            "server": "file-interaction",
            "operation": operation,
            "arguments": arguments
        }
