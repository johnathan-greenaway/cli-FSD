"""Tool Fallback Manager for handling tool failures with graceful degradation.

This module provides a system for falling back to alternative tools when primary tools fail,
implementing a chain of fallback strategies for robustness.
"""

import logging
from typing import Dict, List, Any, Optional, Callable
from datetime import datetime
import time

logger = logging.getLogger(__name__)


class ToolFallbackChain:
    """Manages a chain of fallback tools for a specific operation."""
    
    def __init__(self, operation_name: str):
        self.operation_name = operation_name
        self.tools = []  # List of (tool_name, tool_function, priority)
        self.attempts = {}  # Track attempts for each tool
        self.last_errors = {}  # Store last error for each tool
        
    def add_tool(self, tool_name: str, tool_function: Callable, priority: int = 0):
        """Add a tool to the fallback chain.
        
        Args:
            tool_name: Name of the tool
            tool_function: Callable that executes the tool
            priority: Priority (higher = tried first)
        """
        self.tools.append((tool_name, tool_function, priority))
        # Sort by priority (descending)
        self.tools.sort(key=lambda x: x[2], reverse=True)
        
    def execute(self, *args, **kwargs) -> Dict[str, Any]:
        """Execute the tool chain, trying each tool until one succeeds.
        
        Returns:
            Dict with 'success', 'result', 'tool_used', and 'errors' keys
        """
        errors = []
        
        for tool_name, tool_function, priority in self.tools:
            try:
                logger.info(f"Attempting {self.operation_name} with {tool_name}")
                
                # Track attempt
                self.attempts[tool_name] = self.attempts.get(tool_name, 0) + 1
                
                # Execute tool
                result = tool_function(*args, **kwargs)
                
                # Check if result indicates success
                if self._is_successful_result(result):
                    logger.info(f"Successfully executed {self.operation_name} with {tool_name}")
                    return {
                        'success': True,
                        'result': result,
                        'tool_used': tool_name,
                        'errors': errors
                    }
                else:
                    error_msg = f"{tool_name} returned unsuccessful result"
                    errors.append({'tool': tool_name, 'error': error_msg})
                    self.last_errors[tool_name] = error_msg
                    
            except Exception as e:
                error_msg = f"{tool_name} failed: {str(e)}"
                logger.warning(error_msg)
                errors.append({'tool': tool_name, 'error': str(e)})
                self.last_errors[tool_name] = str(e)
                
                # Small delay before trying next tool
                time.sleep(0.5)
        
        # All tools failed
        logger.error(f"All tools failed for {self.operation_name}")
        return {
            'success': False,
            'result': None,
            'tool_used': None,
            'errors': errors
        }
    
    def _is_successful_result(self, result) -> bool:
        """Check if a result indicates success."""
        if result is None:
            return False
        
        # Check for error indicators
        if isinstance(result, str):
            error_indicators = ['error', 'failed', 'exception', 'timeout']
            if any(indicator in result.lower() for indicator in error_indicators):
                return False
                
        # Check for dict with error key
        if isinstance(result, dict):
            if result.get('error') or not result.get('success', True):
                return False
                
        return True
    
    def reset_attempts(self):
        """Reset attempt counters."""
        self.attempts = {}
        self.last_errors = {}


class ToolFallbackManager:
    """Manages fallback chains for different types of operations."""
    
    def __init__(self):
        self.chains = {}
        self._setup_default_chains()
        
    def _setup_default_chains(self):
        """Set up default fallback chains for common operations."""
        
        # Web content fetching chain
        web_chain = ToolFallbackChain("web_content_fetch")
        web_chain.add_tool("mcp_browser", self._mcp_browser_tool, priority=100)
        web_chain.add_tool("direct_scrape", self._direct_scrape_tool, priority=80)
        web_chain.add_tool("web_api", self._web_api_tool, priority=60)
        web_chain.add_tool("cached_content", self._cached_content_tool, priority=40)
        self.chains["web_content"] = web_chain
        
        # Command execution chain
        cmd_chain = ToolFallbackChain("command_execution")
        cmd_chain.add_tool("subprocess", self._subprocess_tool, priority=100)
        cmd_chain.add_tool("os_system", self._os_system_tool, priority=80)
        cmd_chain.add_tool("shell_script", self._shell_script_tool, priority=60)
        self.chains["command"] = cmd_chain
        
        # File operation chain
        file_chain = ToolFallbackChain("file_operation")
        file_chain.add_tool("file_interaction", self._file_interaction_tool, priority=100)
        file_chain.add_tool("direct_io", self._direct_io_tool, priority=80)
        file_chain.add_tool("shell_command", self._shell_file_tool, priority=60)
        self.chains["file"] = file_chain
        
    def execute_with_fallback(self, operation_type: str, *args, **kwargs) -> Dict[str, Any]:
        """Execute an operation with fallback support.
        
        Args:
            operation_type: Type of operation ('web_content', 'command', 'file')
            *args, **kwargs: Arguments to pass to the tool functions
            
        Returns:
            Dict with execution results
        """
        if operation_type not in self.chains:
            return {
                'success': False,
                'error': f"Unknown operation type: {operation_type}",
                'result': None
            }
            
        chain = self.chains[operation_type]
        return chain.execute(*args, **kwargs)
    
    def add_custom_chain(self, operation_type: str, chain: ToolFallbackChain):
        """Add a custom fallback chain."""
        self.chains[operation_type] = chain
    
    # Tool implementations (these would normally import from actual tool modules)
    
    def _mcp_browser_tool(self, url: str, **kwargs) -> Optional[Dict]:
        """MCP browser tool implementation."""
        try:
            from .utils import use_mcp_tool
            result = use_mcp_tool(
                server_name="small-context",
                tool_name="browse_web",
                arguments={"url": url}
            )
            return result
        except Exception as e:
            raise Exception(f"MCP browser failed: {str(e)}")
    
    def _direct_scrape_tool(self, url: str, **kwargs) -> Optional[str]:
        """Direct web scraping tool."""
        try:
            import requests
            from bs4 import BeautifulSoup
            
            headers = {'User-Agent': 'Mozilla/5.0'}
            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Extract text content
            text = soup.get_text(separator='\n', strip=True)
            return text[:5000]  # Limit response size
            
        except Exception as e:
            raise Exception(f"Direct scrape failed: {str(e)}")
    
    def _web_api_tool(self, url: str, **kwargs) -> Optional[Dict]:
        """Web API tool for structured data."""
        try:
            import requests
            
            # Try to fetch as JSON API
            headers = {'Accept': 'application/json'}
            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()
            
            return response.json()
            
        except Exception as e:
            raise Exception(f"Web API failed: {str(e)}")
    
    def _cached_content_tool(self, url: str, **kwargs) -> Optional[str]:
        """Retrieve cached content if available."""
        try:
            from .web_fetcher import fetcher
            
            # Check if fetcher has cached content
            if hasattr(fetcher, 'get_cached'):
                cached = fetcher.get_cached(url)
                if cached:
                    return cached
                    
            raise Exception("No cached content available")
            
        except Exception as e:
            raise Exception(f"Cache lookup failed: {str(e)}")
    
    def _subprocess_tool(self, command: str, **kwargs) -> str:
        """Execute command using subprocess."""
        import subprocess
        
        try:
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=kwargs.get('timeout', 30)
            )
            
            if result.returncode != 0:
                raise Exception(f"Command failed with code {result.returncode}: {result.stderr}")
                
            return result.stdout
            
        except subprocess.TimeoutExpired:
            raise Exception("Command timed out")
        except Exception as e:
            raise Exception(f"Subprocess execution failed: {str(e)}")
    
    def _os_system_tool(self, command: str, **kwargs) -> str:
        """Execute command using os.system."""
        import os
        import tempfile
        
        try:
            # Create temp file for output
            with tempfile.NamedTemporaryFile(mode='w+', delete=False) as f:
                temp_file = f.name
                
            # Execute command with output redirection
            exit_code = os.system(f"{command} > {temp_file} 2>&1")
            
            # Read output
            with open(temp_file, 'r') as f:
                output = f.read()
                
            # Clean up
            os.unlink(temp_file)
            
            if exit_code != 0:
                raise Exception(f"Command failed with code {exit_code}")
                
            return output
            
        except Exception as e:
            raise Exception(f"OS system execution failed: {str(e)}")
    
    def _shell_script_tool(self, command: str, **kwargs) -> str:
        """Execute command as shell script."""
        import tempfile
        import subprocess
        import os
        
        try:
            # Create temporary shell script
            with tempfile.NamedTemporaryFile(mode='w', suffix='.sh', delete=False) as f:
                f.write("#!/bin/bash\n")
                f.write(command)
                script_path = f.name
                
            # Make executable
            os.chmod(script_path, 0o755)
            
            # Execute script
            result = subprocess.run(
                ['/bin/bash', script_path],
                capture_output=True,
                text=True,
                timeout=kwargs.get('timeout', 30)
            )
            
            # Clean up
            os.unlink(script_path)
            
            if result.returncode != 0:
                raise Exception(f"Script failed with code {result.returncode}")
                
            return result.stdout
            
        except Exception as e:
            raise Exception(f"Shell script execution failed: {str(e)}")
    
    def _file_interaction_tool(self, operation: str, filepath: str, **kwargs) -> Any:
        """File interaction tool."""
        try:
            from .file_interaction import FileInteraction
            
            fi = FileInteraction()
            
            if operation == 'read':
                return fi.read_file(filepath)
            elif operation == 'write':
                return fi.write_file(filepath, kwargs.get('content', ''))
            elif operation == 'delete':
                return fi.delete_file(filepath)
            else:
                raise Exception(f"Unknown file operation: {operation}")
                
        except Exception as e:
            raise Exception(f"File interaction failed: {str(e)}")
    
    def _direct_io_tool(self, operation: str, filepath: str, **kwargs) -> Any:
        """Direct I/O tool."""
        try:
            if operation == 'read':
                with open(filepath, 'r') as f:
                    return f.read()
            elif operation == 'write':
                with open(filepath, 'w') as f:
                    f.write(kwargs.get('content', ''))
                return "File written successfully"
            elif operation == 'delete':
                import os
                os.remove(filepath)
                return "File deleted successfully"
            else:
                raise Exception(f"Unknown operation: {operation}")
                
        except Exception as e:
            raise Exception(f"Direct I/O failed: {str(e)}")
    
    def _shell_file_tool(self, operation: str, filepath: str, **kwargs) -> str:
        """Shell command file tool."""
        import subprocess
        
        try:
            if operation == 'read':
                cmd = f"cat {filepath}"
            elif operation == 'write':
                content = kwargs.get('content', '').replace("'", "'\\''")
                cmd = f"echo '{content}' > {filepath}"
            elif operation == 'delete':
                cmd = f"rm {filepath}"
            else:
                raise Exception(f"Unknown operation: {operation}")
                
            result = subprocess.run(
                cmd,
                shell=True,
                capture_output=True,
                text=True,
                timeout=10
            )
            
            if result.returncode != 0:
                raise Exception(f"Shell command failed: {result.stderr}")
                
            return result.stdout or "Operation completed"
            
        except Exception as e:
            raise Exception(f"Shell file operation failed: {str(e)}")


# Global instance
_fallback_manager = None


def get_fallback_manager() -> ToolFallbackManager:
    """Get or create the global fallback manager instance."""
    global _fallback_manager
    if _fallback_manager is None:
        _fallback_manager = ToolFallbackManager()
    return _fallback_manager