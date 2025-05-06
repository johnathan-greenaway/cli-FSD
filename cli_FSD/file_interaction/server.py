"""File Interaction MCP Server Implementation.

This server provides tools for interacting with files in the active directory
and all subdirectories, with user permission.
"""

import json
import sys
import os
import glob
import re
import asyncio
import shutil
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple, Union
from dataclasses import dataclass

class FileInteractionServer:
    """MCP Server implementation for File Interaction."""
    
    def __init__(self):
        self.working_dir = os.getcwd()
        
    async def start(self):
        """Start the server and initialize services."""
        await self._process_stdin()
    
    async def stop(self):
        """Stop the server and cleanup resources."""
        pass
    
    async def _process_stdin(self):
        """Process MCP protocol messages from stdin."""
        while True:
            try:
                line = await asyncio.get_event_loop().run_in_executor(None, sys.stdin.readline)
                if not line:
                    break
                    
                request = json.loads(line)
                response = await self._handle_request(request)
                
                print(json.dumps(response))
                sys.stdout.flush()
                
            except Exception as e:
                print(json.dumps({
                    "jsonrpc": "2.0",
                    "error": {
                        "code": -32603,
                        "message": f"Internal error: {str(e)}"
                    },
                    "id": None
                }), flush=True)
    
    async def _handle_request(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """Handle incoming MCP requests."""
        method = request.get("method")
        request_id = request.get("id")
        
        if method == "list_tools":
            return {
                "jsonrpc": "2.0",
                "result": self._list_tools(),
                "id": request_id
            }
        elif method == "call_tool":
            result = await self._call_tool(request.get("params", {}))
            return {
                "jsonrpc": "2.0",
                "result": result,
                "id": request_id
            }
        else:
            return {
                "jsonrpc": "2.0",
                "error": {
                    "code": -32601,
                    "message": f"Method not found: {method}"
                },
                "id": request_id
            }
    
    def _list_tools(self) -> Dict[str, Any]:
        """List available tools and their schemas."""
        return {
            "tools": [
                {
                    "name": "list_files",
                    "description": "List files in a directory",
                    "input_schema": {
                        "type": "object",
                        "properties": {
                            "path": {
                                "type": "string",
                                "description": "Directory path (relative to working directory)"
                            },
                            "recursive": {
                                "type": "boolean",
                                "description": "Whether to list files recursively",
                                "default": False
                            },
                            "pattern": {
                                "type": "string",
                                "description": "Optional glob pattern to filter files",
                                "default": "*"
                            }
                        },
                        "required": ["path"]
                    }
                },
                {
                    "name": "read_file",
                    "description": "Read the contents of a file",
                    "input_schema": {
                        "type": "object",
                        "properties": {
                            "path": {
                                "type": "string",
                                "description": "File path (relative to working directory)"
                            }
                        },
                        "required": ["path"]
                    }
                },
                {
                    "name": "write_file",
                    "description": "Write content to a file (requires user permission)",
                    "input_schema": {
                        "type": "object",
                        "properties": {
                            "path": {
                                "type": "string",
                                "description": "File path (relative to working directory)"
                            },
                            "content": {
                                "type": "string",
                                "description": "Content to write to the file"
                            },
                            "requires_approval": {
                                "type": "boolean",
                                "description": "Whether this operation requires explicit user approval",
                                "default": True
                            }
                        },
                        "required": ["path", "content"]
                    }
                },
                {
                    "name": "modify_file",
                    "description": "Modify specific parts of a file (requires user permission)",
                    "input_schema": {
                        "type": "object",
                        "properties": {
                            "path": {
                                "type": "string",
                                "description": "File path (relative to working directory)"
                            },
                            "operations": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "type": {
                                            "type": "string",
                                            "enum": ["replace", "insert", "delete"],
                                            "description": "Type of modification operation"
                                        },
                                        "search": {
                                            "type": "string",
                                            "description": "Text to search for (for replace and delete operations)"
                                        },
                                        "replace": {
                                            "type": "string",
                                            "description": "Text to replace with (for replace operations)"
                                        },
                                        "position": {
                                            "type": "string",
                                            "enum": ["start", "end", "line"],
                                            "description": "Position to insert text (for insert operations)"
                                        },
                                        "line_number": {
                                            "type": "integer",
                                            "description": "Line number for insertion (when position is 'line')"
                                        },
                                        "content": {
                                            "type": "string",
                                            "description": "Content to insert (for insert operations)"
                                        }
                                    },
                                    "required": ["type"]
                                }
                            },
                            "requires_approval": {
                                "type": "boolean",
                                "description": "Whether this operation requires explicit user approval",
                                "default": True
                            }
                        },
                        "required": ["path", "operations"]
                    }
                },
                {
                    "name": "delete_file",
                    "description": "Delete a file (requires user permission)",
                    "input_schema": {
                        "type": "object",
                        "properties": {
                            "path": {
                                "type": "string",
                                "description": "File path (relative to working directory)"
                            },
                            "requires_approval": {
                                "type": "boolean",
                                "description": "Whether this operation requires explicit user approval",
                                "default": True
                            }
                        },
                        "required": ["path"]
                    }
                },
                {
                    "name": "search_files",
                    "description": "Search for text in files",
                    "input_schema": {
                        "type": "object",
                        "properties": {
                            "path": {
                                "type": "string",
                                "description": "Directory path (relative to working directory)"
                            },
                            "pattern": {
                                "type": "string",
                                "description": "Regular expression pattern to search for"
                            },
                            "file_pattern": {
                                "type": "string",
                                "description": "Optional glob pattern to filter files",
                                "default": "*"
                            },
                            "recursive": {
                                "type": "boolean",
                                "description": "Whether to search recursively",
                                "default": True
                            },
                            "context_lines": {
                                "type": "integer",
                                "description": "Number of context lines to include before and after matches",
                                "default": 2
                            }
                        },
                        "required": ["path", "pattern"]
                    }
                },
                {
                    "name": "create_directory",
                    "description": "Create a directory",
                    "input_schema": {
                        "type": "object",
                        "properties": {
                            "path": {
                                "type": "string",
                                "description": "Directory path (relative to working directory)"
                            },
                            "parents": {
                                "type": "boolean",
                                "description": "Whether to create parent directories if they don't exist",
                                "default": True
                            },
                            "requires_approval": {
                                "type": "boolean",
                                "description": "Whether this operation requires explicit user approval",
                                "default": False
                            }
                        },
                        "required": ["path"]
                    }
                }
            ]
        }
    
    async def _call_tool(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle tool execution requests."""
        tool_name = params.get("name")
        args = params.get("arguments", {})
        
        handlers = {
            "list_files": self._handle_list_files,
            "read_file": self._handle_read_file,
            "write_file": self._handle_write_file,
            "modify_file": self._handle_modify_file,
            "delete_file": self._handle_delete_file,
            "search_files": self._handle_search_files,
            "create_directory": self._handle_create_directory
        }
        
        handler = handlers.get(tool_name)
        if not handler:
            return {
                "error": {
                    "code": "tool_not_found",
                    "message": f"Unknown tool: {tool_name}"
                }
            }
        
        try:
            if asyncio.iscoroutinefunction(handler):
                result = await handler(args)
            else:
                result = handler(args)
                
            return {
                "content": result
            }
        except Exception as e:
            return {
                "error": {
                    "code": "tool_execution_error",
                    "message": str(e)
                }
            }
    
    def _handle_list_files(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """List files in a directory."""
        path = args.get("path", ".")
        recursive = args.get("recursive", False)
        pattern = args.get("pattern", "*")
        
        # Ensure path is relative to working directory
        full_path = os.path.normpath(os.path.join(self.working_dir, path))
        
        # Security check: ensure path is within working directory
        if not full_path.startswith(self.working_dir):
            return {
                "error": f"Path must be within the working directory: {self.working_dir}"
            }
        
        if not os.path.exists(full_path):
            return {
                "error": f"Path does not exist: {path}"
            }
        
        if not os.path.isdir(full_path):
            return {
                "error": f"Path is not a directory: {path}"
            }
        
        try:
            files = []
            if recursive:
                for root, dirs, filenames in os.walk(full_path):
                    rel_root = os.path.relpath(root, self.working_dir)
                    for filename in filenames:
                        if glob.fnmatch.fnmatch(filename, pattern):
                            file_path = os.path.join(rel_root, filename)
                            files.append({
                                "path": file_path,
                                "type": "file",
                                "size": os.path.getsize(os.path.join(root, filename))
                            })
                    for dirname in dirs:
                        dir_path = os.path.join(rel_root, dirname)
                        files.append({
                            "path": dir_path,
                            "type": "directory"
                        })
            else:
                rel_path = os.path.relpath(full_path, self.working_dir)
                for entry in os.scandir(full_path):
                    entry_path = os.path.join(rel_path, entry.name)
                    if entry.is_file() and glob.fnmatch.fnmatch(entry.name, pattern):
                        files.append({
                            "path": entry_path,
                            "type": "file",
                            "size": entry.stat().st_size
                        })
                    elif entry.is_dir():
                        files.append({
                            "path": entry_path,
                            "type": "directory"
                        })
            
            return {
                "files": files,
                "path": path,
                "recursive": recursive,
                "pattern": pattern
            }
        except Exception as e:
            return {
                "error": f"Error listing files: {str(e)}"
            }
    
    def _handle_read_file(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Read the contents of a file."""
        path = args.get("path")
        if not path:
            return {
                "error": "Path is required"
            }
        
        # Ensure path is relative to working directory
        full_path = os.path.normpath(os.path.join(self.working_dir, path))
        
        # Security check: ensure path is within working directory
        if not full_path.startswith(self.working_dir):
            return {
                "error": f"Path must be within the working directory: {self.working_dir}"
            }
        
        if not os.path.exists(full_path):
            return {
                "error": f"File does not exist: {path}"
            }
        
        if not os.path.isfile(full_path):
            return {
                "error": f"Path is not a file: {path}"
            }
        
        try:
            with open(full_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            return {
                "path": path,
                "content": content,
                "size": os.path.getsize(full_path)
            }
        except UnicodeDecodeError:
            # Try to read as binary and return a message
            return {
                "path": path,
                "content": "[Binary file content not displayed]",
                "size": os.path.getsize(full_path),
                "is_binary": True
            }
        except Exception as e:
            return {
                "error": f"Error reading file: {str(e)}"
            }
    
    def _handle_write_file(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Write content to a file."""
        path = args.get("path")
        content = args.get("content")
        requires_approval = args.get("requires_approval", True)
        
        if not path:
            return {
                "error": "Path is required"
            }
        
        if content is None:
            return {
                "error": "Content is required"
            }
        
        # Ensure path is relative to working directory
        full_path = os.path.normpath(os.path.join(self.working_dir, path))
        
        # Security check: ensure path is within working directory
        if not full_path.startswith(self.working_dir):
            return {
                "error": f"Path must be within the working directory: {self.working_dir}"
            }
        
        # Create parent directories if they don't exist
        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        
        # Check if file exists for reporting
        file_existed = os.path.exists(full_path)
        
        try:
            # If requires_approval is True, we'll create a temporary file and ask for confirmation
            if requires_approval:
                # Create a temporary file with the content
                temp_path = f"{full_path}.tmp"
                with open(temp_path, 'w', encoding='utf-8') as f:
                    f.write(content)
                
                return {
                    "path": path,
                    "temp_path": os.path.relpath(temp_path, self.working_dir),
                    "requires_approval": True,
                    "operation": "write",
                    "file_existed": file_existed,
                    "message": f"Content ready to be written to {path}. Requires user approval."
                }
            else:
                # Write directly to the file
                with open(full_path, 'w', encoding='utf-8') as f:
                    f.write(content)
                
                return {
                    "path": path,
                    "operation": "write",
                    "file_existed": file_existed,
                    "message": f"Content written to {path}"
                }
        except Exception as e:
            return {
                "error": f"Error writing file: {str(e)}"
            }
    
    def _handle_modify_file(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Modify specific parts of a file."""
        path = args.get("path")
        operations = args.get("operations", [])
        requires_approval = args.get("requires_approval", True)
        
        if not path:
            return {
                "error": "Path is required"
            }
        
        if not operations:
            return {
                "error": "Operations are required"
            }
        
        # Ensure path is relative to working directory
        full_path = os.path.normpath(os.path.join(self.working_dir, path))
        
        # Security check: ensure path is within working directory
        if not full_path.startswith(self.working_dir):
            return {
                "error": f"Path must be within the working directory: {self.working_dir}"
            }
        
        if not os.path.exists(full_path):
            return {
                "error": f"File does not exist: {path}"
            }
        
        if not os.path.isfile(full_path):
            return {
                "error": f"Path is not a file: {path}"
            }
        
        try:
            # Read the original content
            with open(full_path, 'r', encoding='utf-8') as f:
                original_content = f.read()
            
            # Apply operations to create modified content
            modified_content = original_content
            operation_results = []
            
            for op in operations:
                op_type = op.get("type")
                
                if op_type == "replace":
                    search = op.get("search")
                    replace = op.get("replace", "")
                    
                    if not search:
                        operation_results.append({
                            "type": "replace",
                            "success": False,
                            "error": "Search text is required for replace operations"
                        })
                        continue
                    
                    if search not in modified_content:
                        operation_results.append({
                            "type": "replace",
                            "success": False,
                            "error": f"Search text not found: {search}"
                        })
                        continue
                    
                    modified_content = modified_content.replace(search, replace)
                    operation_results.append({
                        "type": "replace",
                        "success": True,
                        "search": search,
                        "replace": replace
                    })
                
                elif op_type == "insert":
                    position = op.get("position")
                    content = op.get("content", "")
                    
                    if not position:
                        operation_results.append({
                            "type": "insert",
                            "success": False,
                            "error": "Position is required for insert operations"
                        })
                        continue
                    
                    if not content:
                        operation_results.append({
                            "type": "insert",
                            "success": False,
                            "error": "Content is required for insert operations"
                        })
                        continue
                    
                    if position == "start":
                        modified_content = content + modified_content
                        operation_results.append({
                            "type": "insert",
                            "success": True,
                            "position": "start",
                            "content": content
                        })
                    elif position == "end":
                        modified_content = modified_content + content
                        operation_results.append({
                            "type": "insert",
                            "success": True,
                            "position": "end",
                            "content": content
                        })
                    elif position == "line":
                        line_number = op.get("line_number")
                        
                        if line_number is None:
                            operation_results.append({
                                "type": "insert",
                                "success": False,
                                "error": "Line number is required for line position"
                            })
                            continue
                        
                        lines = modified_content.splitlines(True)
                        
                        if line_number < 0 or line_number > len(lines):
                            operation_results.append({
                                "type": "insert",
                                "success": False,
                                "error": f"Invalid line number: {line_number}"
                            })
                            continue
                        
                        lines.insert(line_number, content + '\n')
                        modified_content = ''.join(lines)
                        operation_results.append({
                            "type": "insert",
                            "success": True,
                            "position": "line",
                            "line_number": line_number,
                            "content": content
                        })
                    else:
                        operation_results.append({
                            "type": "insert",
                            "success": False,
                            "error": f"Invalid position: {position}"
                        })
                
                elif op_type == "delete":
                    search = op.get("search")
                    
                    if not search:
                        operation_results.append({
                            "type": "delete",
                            "success": False,
                            "error": "Search text is required for delete operations"
                        })
                        continue
                    
                    if search not in modified_content:
                        operation_results.append({
                            "type": "delete",
                            "success": False,
                            "error": f"Search text not found: {search}"
                        })
                        continue
                    
                    modified_content = modified_content.replace(search, "")
                    operation_results.append({
                        "type": "delete",
                        "success": True,
                        "search": search
                    })
                
                else:
                    operation_results.append({
                        "type": op_type,
                        "success": False,
                        "error": f"Invalid operation type: {op_type}"
                    })
            
            # If requires_approval is True, we'll create a temporary file and ask for confirmation
            if requires_approval:
                # Create a temporary file with the modified content
                temp_path = f"{full_path}.tmp"
                with open(temp_path, 'w', encoding='utf-8') as f:
                    f.write(modified_content)
                
                return {
                    "path": path,
                    "temp_path": os.path.relpath(temp_path, self.working_dir),
                    "requires_approval": True,
                    "operation": "modify",
                    "operations": operation_results,
                    "message": f"Modifications ready to be applied to {path}. Requires user approval."
                }
            else:
                # Write directly to the file
                with open(full_path, 'w', encoding='utf-8') as f:
                    f.write(modified_content)
                
                return {
                    "path": path,
                    "operation": "modify",
                    "operations": operation_results,
                    "message": f"Modifications applied to {path}"
                }
        except UnicodeDecodeError:
            return {
                "error": f"Cannot modify binary file: {path}"
            }
        except Exception as e:
            return {
                "error": f"Error modifying file: {str(e)}"
            }
    
    def _handle_delete_file(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Delete a file."""
        path = args.get("path")
        requires_approval = args.get("requires_approval", True)
        
        if not path:
            return {
                "error": "Path is required"
            }
        
        # Ensure path is relative to working directory
        full_path = os.path.normpath(os.path.join(self.working_dir, path))
        
        # Security check: ensure path is within working directory
        if not full_path.startswith(self.working_dir):
            return {
                "error": f"Path must be within the working directory: {self.working_dir}"
            }
        
        if not os.path.exists(full_path):
            return {
                "error": f"File does not exist: {path}"
            }
        
        try:
            # If requires_approval is True, we'll just return information about the file
            if requires_approval:
                file_info = {
                    "path": path,
                    "type": "directory" if os.path.isdir(full_path) else "file",
                    "size": os.path.getsize(full_path) if os.path.isfile(full_path) else None,
                    "requires_approval": True,
                    "operation": "delete",
                    "message": f"File ready to be deleted: {path}. Requires user approval."
                }
                
                return file_info
            else:
                # Delete the file directly
                if os.path.isdir(full_path):
                    shutil.rmtree(full_path)
                    return {
                        "path": path,
                        "operation": "delete",
                        "type": "directory",
                        "message": f"Directory deleted: {path}"
                    }
                else:
                    os.remove(full_path)
                    return {
                        "path": path,
                        "operation": "delete",
                        "type": "file",
                        "message": f"File deleted: {path}"
                    }
        except Exception as e:
            return {
                "error": f"Error deleting file: {str(e)}"
            }
    
    def _handle_search_files(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Search for text in files."""
        path = args.get("path", ".")
        pattern = args.get("pattern")
        file_pattern = args.get("file_pattern", "*")
        recursive = args.get("recursive", True)
        context_lines = args.get("context_lines", 2)
        
        if not pattern:
            return {
                "error": "Search pattern is required"
            }
        
        # Ensure path is relative to working directory
        full_path = os.path.normpath(os.path.join(self.working_dir, path))
        
        # Security check: ensure path is within working directory
        if not full_path.startswith(self.working_dir):
            return {
                "error": f"Path must be within the working directory: {self.working_dir}"
            }
        
        if not os.path.exists(full_path):
            return {
                "error": f"Path does not exist: {path}"
            }
        
        if not os.path.isdir(full_path):
            return {
                "error": f"Path is not a directory: {path}"
            }
        
        try:
            # Compile the regex pattern
            regex = re.compile(pattern)
            
            matches = []
            
            # Walk through the directory
            if recursive:
                for root, dirs, filenames in os.walk(full_path):
                    for filename in filenames:
                        if glob.fnmatch.fnmatch(filename, file_pattern):
                            file_path = os.path.join(root, filename)
                            file_matches = self._search_file(file_path, regex, context_lines)
                            if file_matches:
                                rel_path = os.path.relpath(file_path, self.working_dir)
                                matches.append({
                                    "path": rel_path,
                                    "matches": file_matches
                                })
            else:
                for entry in os.scandir(full_path):
                    if entry.is_file() and glob.fnmatch.fnmatch(entry.name, file_pattern):
                        file_path = entry.path
                        file_matches = self._search_file(file_path, regex, context_lines)
                        if file_matches:
                            rel_path = os.path.relpath(file_path, self.working_dir)
                            matches.append({
                                "path": rel_path,
                                "matches": file_matches
                            })
            
            return {
                "path": path,
                "pattern": pattern,
                "file_pattern": file_pattern,
                "recursive": recursive,
                "context_lines": context_lines,
                "matches": matches
            }
        except re.error as e:
            return {
                "error": f"Invalid regex pattern: {str(e)}"
            }
        except Exception as e:
            return {
                "error": f"Error searching files: {str(e)}"
            }
    
    def _search_file(self, file_path: str, regex: re.Pattern, context_lines: int) -> List[Dict[str, Any]]:
        """Search for regex pattern in a file and return matches with context."""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            
            matches = []
            
            for i, line in enumerate(lines):
                for match in regex.finditer(line):
                    # Get context lines
                    start = max(0, i - context_lines)
                    end = min(len(lines), i + context_lines + 1)
                    
                    context = []
                    for j in range(start, end):
                        context.append({
                            "line_number": j + 1,
                            "content": lines[j].rstrip('\n'),
                            "is_match": j == i
                        })
                    
                    matches.append({
                        "line_number": i + 1,
                        "match": match.group(0),
                        "context": context
                    })
            
            return matches
        except UnicodeDecodeError:
            # Skip binary files
            return []
        except Exception:
            # Skip files with errors
            return []
    
    def _handle_create_directory(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Create a directory."""
        path = args.get("path")
        parents = args.get("parents", True)
        requires_approval = args.get("requires_approval", False)
        
        if not path:
            return {
                "error": "Path is required"
            }
        
        # Ensure path is relative to working directory
        full_path = os.path.normpath(os.path.join(self.working_dir, path))
        
        # Security check: ensure path is within working directory
        if not full_path.startswith(self.working_dir):
            return {
                "error": f"Path must be within the working directory: {self.working_dir}"
            }
        
        # Check if directory already exists
        if os.path.exists(full_path):
            if os.path.isdir(full_path):
                return {
                    "path": path,
                    "operation": "create_directory",
                    "message": f"Directory already exists: {path}"
                }
            else:
                return {
                    "error": f"Path exists but is not a directory: {path}"
                }
        
        try:
            # If requires_approval is True, we'll just return information about the directory
            if requires_approval:
                return {
                    "path": path,
                    "operation": "create_directory",
                    "requires_approval": True,
                    "message": f"Directory ready to be created: {path}. Requires user approval."
                }
            else:
                # Create the directory directly
                if parents:
                    os.makedirs(full_path, exist_ok=True)
                else:
                    os.mkdir(full_path)
                
                return {
                    "path": path,
                    "operation": "create_directory",
                    "message": f"Directory created: {path}"
                }
        except Exception as e:
            return {
                "error": f"Error creating directory: {str(e)}"
            }


if __name__ == "__main__":
    server = FileInteractionServer()
    try:
        asyncio.run(server.start())
    except KeyboardInterrupt:
        asyncio.run(server.stop())
