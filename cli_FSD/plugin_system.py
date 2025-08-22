"""Plugin-based tool architecture for CLI-FSD.

This module provides a framework for creating and managing tool plugins,
allowing for easy extension and customization of the system's capabilities.
"""

import importlib
import inspect
import logging
from abc import ABC, abstractmethod
from typing import Dict, List, Any, Optional, Type, Callable
from dataclasses import dataclass
from pathlib import Path
import json

logger = logging.getLogger(__name__)


@dataclass
class ToolMetadata:
    """Metadata for a tool plugin."""
    name: str
    version: str
    description: str
    author: str
    category: str
    priority: int = 0
    dependencies: List[str] = None
    supports_autopilot: bool = True
    requires_confirmation: bool = False
    
    def __post_init__(self):
        if self.dependencies is None:
            self.dependencies = []


class BaseTool(ABC):
    """Base class for all tool plugins."""
    
    @property
    @abstractmethod
    def metadata(self) -> ToolMetadata:
        """Return metadata for this tool."""
        pass
    
    @abstractmethod
    def can_handle(self, operation: str, **kwargs) -> bool:
        """Check if this tool can handle the given operation."""
        pass
    
    @abstractmethod
    def execute(self, operation: str, **kwargs) -> Dict[str, Any]:
        """Execute the tool operation."""
        pass
    
    def validate_dependencies(self) -> bool:
        """Validate that all dependencies are available."""
        for dep in self.metadata.dependencies:
            try:
                importlib.import_module(dep)
            except ImportError:
                logger.warning(f"Tool {self.metadata.name} missing dependency: {dep}")
                return False
        return True
    
    def on_install(self):
        """Called when the tool is installed/registered."""
        pass
    
    def on_uninstall(self):
        """Called when the tool is uninstalled/unregistered."""
        pass


class CommandTool(BaseTool):
    """Base class for command execution tools."""
    
    @abstractmethod
    def execute_command(self, command: str, config: Any, **kwargs) -> str:
        """Execute a shell command."""
        pass
    
    def execute(self, operation: str, **kwargs) -> Dict[str, Any]:
        """Execute wrapper for command tools."""
        if operation == "execute_command":
            result = self.execute_command(kwargs.get('command'), kwargs.get('config'), **kwargs)
            return {'success': True, 'result': result}
        return {'success': False, 'error': f"Unsupported operation: {operation}"}


class WebTool(BaseTool):
    """Base class for web content tools."""
    
    @abstractmethod
    def fetch_content(self, url: str, **kwargs) -> Dict[str, Any]:
        """Fetch content from a URL."""
        pass
    
    def execute(self, operation: str, **kwargs) -> Dict[str, Any]:
        """Execute wrapper for web tools."""
        if operation == "fetch_content":
            return self.fetch_content(kwargs.get('url'), **kwargs)
        return {'success': False, 'error': f"Unsupported operation: {operation}"}


class FileTool(BaseTool):
    """Base class for file operation tools."""
    
    @abstractmethod
    def read_file(self, filepath: str, **kwargs) -> str:
        """Read file contents."""
        pass
    
    @abstractmethod
    def write_file(self, filepath: str, content: str, **kwargs) -> bool:
        """Write content to file."""
        pass
    
    def execute(self, operation: str, **kwargs) -> Dict[str, Any]:
        """Execute wrapper for file tools."""
        if operation == "read":
            result = self.read_file(kwargs.get('filepath'), **kwargs)
            return {'success': True, 'result': result}
        elif operation == "write":
            result = self.write_file(kwargs.get('filepath'), kwargs.get('content', ''), **kwargs)
            return {'success': result, 'result': 'File written' if result else 'Write failed'}
        return {'success': False, 'error': f"Unsupported operation: {operation}"}


class PluginRegistry:
    """Registry for managing tool plugins."""
    
    def __init__(self):
        self.tools: Dict[str, BaseTool] = {}
        self.categories: Dict[str, List[str]] = {}
        self.tool_metadata: Dict[str, ToolMetadata] = {}
        
    def register_tool(self, tool: BaseTool) -> bool:
        """Register a tool plugin.
        
        Args:
            tool: Tool instance to register
            
        Returns:
            True if registration successful, False otherwise
        """
        try:
            # Validate dependencies
            if not tool.validate_dependencies():
                logger.error(f"Failed to register {tool.metadata.name}: missing dependencies")
                return False
            
            # Check for name conflicts
            if tool.metadata.name in self.tools:
                logger.warning(f"Tool {tool.metadata.name} already registered, replacing...")
            
            # Register the tool
            self.tools[tool.metadata.name] = tool
            self.tool_metadata[tool.metadata.name] = tool.metadata
            
            # Add to category
            category = tool.metadata.category
            if category not in self.categories:
                self.categories[category] = []
            if tool.metadata.name not in self.categories[category]:
                self.categories[category].append(tool.metadata.name)
            
            # Call installation hook
            tool.on_install()
            
            logger.info(f"Registered tool: {tool.metadata.name} (category: {category})")
            return True
            
        except Exception as e:
            logger.error(f"Failed to register tool {tool.metadata.name}: {str(e)}")
            return False
    
    def unregister_tool(self, tool_name: str) -> bool:
        """Unregister a tool plugin."""
        try:
            if tool_name not in self.tools:
                logger.warning(f"Tool {tool_name} not found for unregistration")
                return False
            
            tool = self.tools[tool_name]
            category = tool.metadata.category
            
            # Call uninstallation hook
            tool.on_uninstall()
            
            # Remove from registry
            del self.tools[tool_name]
            del self.tool_metadata[tool_name]
            
            # Remove from category
            if category in self.categories and tool_name in self.categories[category]:
                self.categories[category].remove(tool_name)
                if not self.categories[category]:
                    del self.categories[category]
            
            logger.info(f"Unregistered tool: {tool_name}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to unregister tool {tool_name}: {str(e)}")
            return False
    
    def get_tool(self, tool_name: str) -> Optional[BaseTool]:
        """Get a tool by name."""
        return self.tools.get(tool_name)
    
    def get_tools_by_category(self, category: str) -> List[BaseTool]:
        """Get all tools in a category."""
        if category not in self.categories:
            return []
        return [self.tools[name] for name in self.categories[category]]
    
    def find_tools_for_operation(self, operation: str, **kwargs) -> List[BaseTool]:
        """Find tools that can handle a specific operation."""
        capable_tools = []
        for tool in self.tools.values():
            try:
                if tool.can_handle(operation, **kwargs):
                    capable_tools.append(tool)
            except Exception as e:
                logger.warning(f"Error checking if tool {tool.metadata.name} can handle operation: {e}")
        
        # Sort by priority (higher first)
        capable_tools.sort(key=lambda t: t.metadata.priority, reverse=True)
        return capable_tools
    
    def list_tools(self) -> List[ToolMetadata]:
        """List all registered tools."""
        return list(self.tool_metadata.values())
    
    def get_tool_info(self, tool_name: str) -> Optional[Dict[str, Any]]:
        """Get detailed information about a tool."""
        if tool_name not in self.tools:
            return None
        
        tool = self.tools[tool_name]
        metadata = self.tool_metadata[tool_name]
        
        return {
            'metadata': metadata,
            'methods': [method for method in dir(tool) if not method.startswith('_')],
            'dependencies_valid': tool.validate_dependencies(),
            'class_name': tool.__class__.__name__,
            'module': tool.__class__.__module__
        }


class PluginLoader:
    """Loader for discovering and loading tool plugins."""
    
    def __init__(self, registry: PluginRegistry):
        self.registry = registry
        
    def load_from_directory(self, plugin_dir: str) -> int:
        """Load all plugins from a directory.
        
        Args:
            plugin_dir: Directory containing plugin files
            
        Returns:
            Number of plugins successfully loaded
        """
        plugin_path = Path(plugin_dir)
        if not plugin_path.exists():
            logger.warning(f"Plugin directory {plugin_dir} does not exist")
            return 0
        
        loaded_count = 0
        
        # Look for Python files
        for py_file in plugin_path.glob("*.py"):
            if py_file.name.startswith("__"):
                continue
                
            try:
                loaded_count += self._load_plugin_file(py_file)
            except Exception as e:
                logger.error(f"Failed to load plugin from {py_file}: {str(e)}")
        
        logger.info(f"Loaded {loaded_count} plugins from {plugin_dir}")
        return loaded_count
    
    def _load_plugin_file(self, plugin_file: Path) -> int:
        """Load plugins from a single file."""
        module_name = f"plugin_{plugin_file.stem}"
        
        # Load the module
        spec = importlib.util.spec_from_file_location(module_name, plugin_file)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        
        loaded_count = 0
        
        # Find tool classes in the module
        for name, obj in inspect.getmembers(module, inspect.isclass):
            if (issubclass(obj, BaseTool) and 
                obj != BaseTool and 
                obj not in [CommandTool, WebTool, FileTool]):
                
                try:
                    # Instantiate and register the tool
                    tool_instance = obj()
                    if self.registry.register_tool(tool_instance):
                        loaded_count += 1
                except Exception as e:
                    logger.error(f"Failed to instantiate tool {name}: {str(e)}")
        
        return loaded_count
    
    def load_builtin_tools(self) -> int:
        """Load built-in tools."""
        loaded_count = 0
        
        # Register built-in tools here
        builtin_tools = [
            ExecutionManagerTool(),
            MCPWebTool(),
            StandardFileTool()
        ]
        
        for tool in builtin_tools:
            if self.registry.register_tool(tool):
                loaded_count += 1
        
        return loaded_count


# Built-in tool implementations

class ExecutionManagerTool(CommandTool):
    """Built-in tool that uses the execution manager."""
    
    @property
    def metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="execution_manager",
            version="1.0.0",
            description="Command execution using the centralized execution manager",
            author="CLI-FSD",
            category="command",
            priority=100
        )
    
    def can_handle(self, operation: str, **kwargs) -> bool:
        return operation in ["execute_command", "execute_script"]
    
    def execute_command(self, command: str, config: Any, **kwargs) -> str:
        from .execution_manager import get_execution_manager
        exec_manager = get_execution_manager()
        return exec_manager.execute_with_mode(command, config, **kwargs)


class MCPWebTool(WebTool):
    """Built-in tool for MCP web content fetching."""
    
    @property
    def metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="mcp_web",
            version="1.0.0",
            description="Web content fetching using MCP tools",
            author="CLI-FSD",
            category="web",
            priority=90,
            dependencies=["cli_FSD.utils"]
        )
    
    def can_handle(self, operation: str, **kwargs) -> bool:
        return operation == "fetch_content"
    
    def fetch_content(self, url: str, **kwargs) -> Dict[str, Any]:
        try:
            from .utils import use_mcp_tool
            result = use_mcp_tool(
                server_name="small-context",
                tool_name="browse_web",
                arguments={"url": url}
            )
            return {'success': True, 'content': result}
        except Exception as e:
            return {'success': False, 'error': str(e)}


class StandardFileTool(FileTool):
    """Built-in tool for standard file operations."""
    
    @property
    def metadata(self) -> ToolMetadata:
        return ToolMetadata(
            name="standard_file",
            version="1.0.0",
            description="Standard file operations using Python I/O",
            author="CLI-FSD",
            category="file",
            priority=80
        )
    
    def can_handle(self, operation: str, **kwargs) -> bool:
        return operation in ["read", "write", "delete"]
    
    def read_file(self, filepath: str, **kwargs) -> str:
        with open(filepath, 'r') as f:
            return f.read()
    
    def write_file(self, filepath: str, content: str, **kwargs) -> bool:
        try:
            with open(filepath, 'w') as f:
                f.write(content)
            return True
        except:
            return False


# Global plugin system instance
_plugin_registry = None
_plugin_loader = None


def get_plugin_registry() -> PluginRegistry:
    """Get or create the global plugin registry."""
    global _plugin_registry
    if _plugin_registry is None:
        _plugin_registry = PluginRegistry()
    return _plugin_registry


def get_plugin_loader() -> PluginLoader:
    """Get or create the global plugin loader."""
    global _plugin_loader
    if _plugin_loader is None:
        _plugin_loader = PluginLoader(get_plugin_registry())
    return _plugin_loader


def initialize_plugin_system() -> None:
    """Initialize the plugin system with built-in tools."""
    loader = get_plugin_loader()
    loaded = loader.load_builtin_tools()
    logger.info(f"Plugin system initialized with {loaded} built-in tools")
    
    # Try to load additional plugins from plugins directory
    try:
        plugin_dir = Path(__file__).parent / "plugins"
        if plugin_dir.exists():
            additional = loader.load_from_directory(str(plugin_dir))
            logger.info(f"Loaded {additional} additional plugins")
    except Exception as e:
        logger.warning(f"Failed to load additional plugins: {e}")


def execute_with_plugins(operation: str, **kwargs) -> Dict[str, Any]:
    """Execute an operation using the plugin system."""
    registry = get_plugin_registry()
    tools = registry.find_tools_for_operation(operation, **kwargs)
    
    if not tools:
        return {
            'success': False,
            'error': f"No tools available for operation: {operation}"
        }
    
    # Try each tool until one succeeds
    for tool in tools:
        try:
            result = tool.execute(operation, **kwargs)
            if result.get('success'):
                result['tool_used'] = tool.metadata.name
                return result
        except Exception as e:
            logger.warning(f"Tool {tool.metadata.name} failed: {str(e)}")
            continue
    
    return {
        'success': False,
        'error': f"All tools failed for operation: {operation}"
    }