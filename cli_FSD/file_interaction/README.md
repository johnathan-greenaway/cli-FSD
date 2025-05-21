# File Interaction Tool

The File Interaction Tool is an MCP server that allows the agent to modify files in the active directory and all subdirectories with user permission.

## Features

- **List Files**: List files in a directory with optional recursive listing
- **Read Files**: Read the contents of files
- **Write Files**: Write content to files (with user permission)
- **Modify Files**: Make targeted modifications to specific parts of files (with user permission)
- **Delete Files**: Delete files or directories (with user permission)
- **Search Files**: Search for text patterns in files with context
- **Create Directories**: Create new directories

## Security Features

- All file operations are restricted to the working directory and its subdirectories
- Write, modify, and delete operations require explicit user approval by default
- Temporary files are created for operations requiring approval
- User can review changes before applying them

## Usage

### Command Line Interface

The tool can be accessed through the CLI by entering command mode and using the `fileint` command:

```
CMD> fileint
```

This opens the File Interaction Mode with the following commands:
- `list`: List files in a directory
- `read`: Read a file
- `write`: Write to a file
- `modify`: Modify parts of a file
- `search`: Search for text in files
- `delete`: Delete a file
- `mkdir`: Create a directory
- `exit`: Exit file interaction mode

### Using as an MCP Tool

The file interaction tool can also be used programmatically through the MCP protocol. Here are examples of how to use each tool:

#### List Files

```python
result = use_mcp_tool(
    server_name="file-interaction",
    tool_name="list_files",
    arguments={
        "path": "path/to/directory",
        "recursive": True,  # Optional, default is False
        "pattern": "*.py"   # Optional, default is "*"
    }
)
```

#### Read File

```python
result = use_mcp_tool(
    server_name="file-interaction",
    tool_name="read_file",
    arguments={
        "path": "path/to/file.txt"
    }
)
```

#### Write File

```python
result = use_mcp_tool(
    server_name="file-interaction",
    tool_name="write_file",
    arguments={
        "path": "path/to/file.txt",
        "content": "Content to write to the file",
        "requires_approval": True  # Optional, default is True
    }
)
```

#### Modify File

```python
result = use_mcp_tool(
    server_name="file-interaction",
    tool_name="modify_file",
    arguments={
        "path": "path/to/file.txt",
        "operations": [
            {
                "type": "replace",
                "search": "text to find",
                "replace": "replacement text"
            },
            {
                "type": "insert",
                "position": "start",  # or "end" or "line"
                "content": "content to insert"
                # "line_number": 5  # Required if position is "line"
            },
            {
                "type": "delete",
                "search": "text to delete"
            }
        ],
        "requires_approval": True  # Optional, default is True
    }
)
```

#### Delete File

```python
result = use_mcp_tool(
    server_name="file-interaction",
    tool_name="delete_file",
    arguments={
        "path": "path/to/file.txt",
        "requires_approval": True  # Optional, default is True
    }
)
```

#### Search Files

```python
result = use_mcp_tool(
    server_name="file-interaction",
    tool_name="search_files",
    arguments={
        "path": "path/to/directory",
        "pattern": "regex pattern",
        "file_pattern": "*.py",     # Optional, default is "*"
        "recursive": True,          # Optional, default is True
        "context_lines": 2          # Optional, default is 2
    }
)
```

#### Create Directory

```python
result = use_mcp_tool(
    server_name="file-interaction",
    tool_name="create_directory",
    arguments={
        "path": "path/to/new/directory",
        "parents": True,            # Optional, default is True
        "requires_approval": False  # Optional, default is False
    }
)
```

## Response Format

All tools return a JSON response with the following structure:

```json
{
  "content": {
    // Tool-specific response data
    // May include "error" field if an error occurred
  }
}
```

For operations that require approval, the response will include:

```json
{
  "content": {
    "requires_approval": true,
    "temp_path": "path/to/temporary/file",
    "message": "Operation requires approval",
    // Other operation-specific fields
  }
}
```

## Error Handling

If an error occurs, the response will include an "error" field with a description of the error:

```json
{
  "content": {
    "error": "Error message"
  }
}
```

## Security Considerations

- All file paths are validated to ensure they are within the working directory
- Operations that modify or delete files require explicit user approval by default
- Temporary files are created for operations requiring approval, allowing the user to review changes before applying them
- The tool respects file permissions enforced by the operating system
