#!/usr/bin/env python3
"""
Example script demonstrating how to use the file interaction tool programmatically.
"""

import json
import os
import sys

# Add parent directory to path to import from cli_FSD
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from cli_FSD.utils import use_mcp_tool

def print_result(result, title=None):
    """Print the result of an MCP tool call in a formatted way."""
    if title:
        print(f"\n=== {title} ===")
    
    try:
        # Parse the result as JSON
        data = json.loads(result)
        # Pretty print the JSON
        print(json.dumps(data, indent=2))
    except json.JSONDecodeError:
        # If it's not valid JSON, print as is
        print(result)
    
    print()

def example_list_files():
    """Example of listing files in a directory."""
    result = use_mcp_tool(
        server_name="file-interaction",
        tool_name="list_files",
        arguments={
            "path": ".",
            "recursive": False,
            "pattern": "*"
        }
    )
    
    print_result(result, "List Files Example")

def example_read_file():
    """Example of reading a file."""
    # First, let's read our own source code
    result = use_mcp_tool(
        server_name="file-interaction",
        tool_name="read_file",
        arguments={
            "path": __file__
        }
    )
    
    print_result(result, "Read File Example")

def example_write_file():
    """Example of writing to a file."""
    # Create a temporary file for demonstration
    temp_file = "example_output.txt"
    
    result = use_mcp_tool(
        server_name="file-interaction",
        tool_name="write_file",
        arguments={
            "path": temp_file,
            "content": "This is an example file created by the file interaction tool.\n"
                      "It demonstrates how to write content to a file.",
            "requires_approval": False  # Set to False for this example
        }
    )
    
    print_result(result, "Write File Example")
    
    # Clean up the temporary file
    try:
        os.remove(temp_file)
        print(f"Cleaned up temporary file: {temp_file}")
    except OSError:
        pass

def example_modify_file():
    """Example of modifying a file."""
    # Create a temporary file for demonstration
    temp_file = "example_modify.txt"
    
    # First, create the file
    use_mcp_tool(
        server_name="file-interaction",
        tool_name="write_file",
        arguments={
            "path": temp_file,
            "content": "Line 1: This is the first line.\nLine 2: This is the second line.\nLine 3: This is the third line.",
            "requires_approval": False
        }
    )
    
    # Now, modify the file
    result = use_mcp_tool(
        server_name="file-interaction",
        tool_name="modify_file",
        arguments={
            "path": temp_file,
            "operations": [
                {
                    "type": "replace",
                    "search": "first",
                    "replace": "modified first"
                },
                {
                    "type": "insert",
                    "position": "end",
                    "content": "\nLine 4: This is a new line added at the end."
                },
                {
                    "type": "delete",
                    "search": "Line 2: This is the second line.\n"
                }
            ],
            "requires_approval": False
        }
    )
    
    print_result(result, "Modify File Example")
    
    # Read the modified file
    read_result = use_mcp_tool(
        server_name="file-interaction",
        tool_name="read_file",
        arguments={
            "path": temp_file
        }
    )
    
    print_result(read_result, "Modified File Content")
    
    # Clean up the temporary file
    try:
        os.remove(temp_file)
        print(f"Cleaned up temporary file: {temp_file}")
    except OSError:
        pass

def example_search_files():
    """Example of searching for text in files."""
    result = use_mcp_tool(
        server_name="file-interaction",
        tool_name="search_files",
        arguments={
            "path": ".",
            "pattern": "example",
            "file_pattern": "*.py",
            "recursive": False,
            "context_lines": 2
        }
    )
    
    print_result(result, "Search Files Example")

def example_create_directory():
    """Example of creating a directory."""
    # Create a temporary directory for demonstration
    temp_dir = "example_dir"
    
    result = use_mcp_tool(
        server_name="file-interaction",
        tool_name="create_directory",
        arguments={
            "path": temp_dir,
            "parents": True,
            "requires_approval": False
        }
    )
    
    print_result(result, "Create Directory Example")
    
    # Clean up the temporary directory
    try:
        os.rmdir(temp_dir)
        print(f"Cleaned up temporary directory: {temp_dir}")
    except OSError:
        pass

def example_delete_file():
    """Example of deleting a file."""
    # Create a temporary file for demonstration
    temp_file = "example_delete.txt"
    
    # First, create the file
    use_mcp_tool(
        server_name="file-interaction",
        tool_name="write_file",
        arguments={
            "path": temp_file,
            "content": "This file will be deleted.",
            "requires_approval": False
        }
    )
    
    # Now, delete the file
    result = use_mcp_tool(
        server_name="file-interaction",
        tool_name="delete_file",
        arguments={
            "path": temp_file,
            "requires_approval": False
        }
    )
    
    print_result(result, "Delete File Example")

def main():
    """Run all examples."""
    print("File Interaction Tool Examples")
    print("==============================")
    
    example_list_files()
    example_read_file()
    example_write_file()
    example_modify_file()
    example_search_files()
    example_create_directory()
    example_delete_file()
    
    print("All examples completed successfully!")

if __name__ == "__main__":
    main()
