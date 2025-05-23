#!/usr/bin/env python3
"""Test script for the Memory MCP tool."""

import asyncio
import json
import sys
import os

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cli_FSD.memory.server import MemoryMCPServer, MemoryGraph
from pathlib import Path

async def test_memory_server():
    """Test the memory server functionality."""
    # Use a test memory file
    test_memory_file = Path("/tmp/test_memory.json")
    server = MemoryMCPServer(test_memory_file)
    
    print("Testing Memory MCP Server")
    print("=" * 50)
    
    # Test 1: List tools
    print("\n1. Testing list tools...")
    tools_response = await server._handle_list_tools({})
    print(f"Available tools: {len(tools_response['tools'])}")
    for tool in tools_response['tools']:
        print(f"  - {tool['name']}: {tool['description']}")
    
    # Test 2: Create entities
    print("\n2. Testing create entities...")
    create_response = await server._handle_tool_call({
        "name": "create_entities",
        "arguments": {
            "entities": [
                {"name": "cli_fsd_user", "type": "user"},
                {"name": "project_notes", "type": "directory"},
                {"name": "browse_tool", "type": "feature"}
            ]
        }
    })
    print(f"Response: {create_response['content'][0]['text']}")
    
    # Test 3: Add observations
    print("\n3. Testing add observations...")
    obs_response = await server._handle_tool_call({
        "name": "add_observations",
        "arguments": {
            "observations": [
                {"entity": "cli_fsd_user", "content": "Prefers using memory tools for persistence"},
                {"entity": "cli_fsd_user", "content": "Working on browse tool improvements"},
                {"entity": "browse_tool", "content": "Successfully routes explicit browse requests"},
                {"entity": "project_notes", "content": "Contains test scripts and documentation"}
            ]
        }
    })
    print(f"Response: {obs_response['content'][0]['text']}")
    
    # Test 4: Create relations
    print("\n4. Testing create relations...")
    rel_response = await server._handle_tool_call({
        "name": "create_relations",
        "arguments": {
            "relations": [
                {"from": "cli_fsd_user", "to": "browse_tool", "type": "implemented"},
                {"from": "browse_tool", "to": "project_notes", "type": "documented_in"},
                {"from": "cli_fsd_user", "to": "project_notes", "type": "created"}
            ]
        }
    })
    print(f"Response: {rel_response['content'][0]['text']}")
    
    # Test 5: Search nodes
    print("\n5. Testing search nodes...")
    search_response = await server._handle_tool_call({
        "name": "search_nodes",
        "arguments": {"query": "browse"}
    })
    print(f"Search results:\n{search_response['content'][0]['text']}")
    
    # Test 6: Open specific nodes
    print("\n6. Testing open nodes...")
    open_response = await server._handle_tool_call({
        "name": "open_nodes",
        "arguments": {"names": ["cli_fsd_user", "browse_tool"]}
    })
    print(f"Node details:\n{open_response['content'][0]['text']}")
    
    # Test 7: Read entire graph
    print("\n7. Testing read graph...")
    graph_response = await server._handle_tool_call({
        "name": "read_graph",
        "arguments": {}
    })
    graph_data = json.loads(graph_response['content'][0]['text'])
    print(f"Graph summary:")
    print(f"  - Entities: {graph_data['metadata']['entity_count']}")
    print(f"  - Relations: {graph_data['metadata']['relation_count']}")
    
    # Clean up test file
    if test_memory_file.exists():
        test_memory_file.unlink()
        print(f"\nCleaned up test file: {test_memory_file}")

def test_memory_graph():
    """Test the MemoryGraph class directly."""
    print("\n\nTesting MemoryGraph Class")
    print("=" * 50)
    
    # Create a test graph
    test_file = Path("/tmp/test_graph.json")
    graph = MemoryGraph(test_file)
    
    # Test entity creation
    user = graph.create_entity("test_user", "user")
    project = graph.create_entity("test_project", "project")
    print(f"Created entities: {user.name}, {project.name}")
    
    # Test observations
    obs1 = graph.add_observation("test_user", "Likes Python programming")
    obs2 = graph.add_observation("test_project", "Uses MCP tools")
    print(f"Added observations: {obs1.content}, {obs2.content}")
    
    # Test relations
    rel = graph.create_relation("test_user", "test_project", "works_on")
    print(f"Created relation: {rel.from_entity} -> {rel.to_entity} ({rel.relation_type})")
    
    # Test search
    results = graph.search_nodes("Python")
    print(f"Search results for 'Python': {[e.name for e in results]}")
    
    # Test connected entities
    connected = graph.get_connected_entities("test_user")
    print(f"Entities connected to test_user: {connected}")
    
    # Clean up
    if test_file.exists():
        test_file.unlink()
        print(f"Cleaned up test file: {test_file}")

if __name__ == "__main__":
    print("Running Memory Tool Tests\n")
    
    # Test the graph functionality
    test_memory_graph()
    
    # Test the MCP server
    asyncio.run(test_memory_server())
    
    print("\n\nAll tests completed successfully!")