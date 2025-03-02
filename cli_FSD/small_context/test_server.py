"""Tests for Small Context Protocol Server."""

import pytest
import asyncio
from .server import SmallContextServer

@pytest.mark.asyncio
async def test_browse_web():
    """Test web browsing functionality."""
    server = SmallContextServer()
    
    # Test with a simple static page first
    result = await server._handle_browse_web({
        "url": "https://example.com",
        "priority": "important"
    })
    
    # Verify we got content back
    assert "content" in result, "Should return content"
    assert isinstance(result["content"], str), "Content should be a string"
    assert len(result["content"]) > 0, "Content should not be empty"
    
    # Verify context was created
    assert "context_id" in result, "Should create a context"
    assert result["context_id"].startswith("web_"), "Context ID should start with web_"
    
    # Test error handling with invalid URL
    error_result = await server._handle_browse_web({
        "url": "not-a-url",
        "priority": "important"
    })
    
    assert "error" in error_result, "Should return error for invalid URL"
    assert "Invalid URL format" in error_result["error"], "Should explain URL format error"

@pytest.mark.asyncio
async def test_context_management():
    """Test context state management."""
    server = SmallContextServer()
    
    # Create a context
    create_result = server._handle_create_context({
        "context_id": "test_context",
        "max_tokens": 1000
    })
    
    assert "message" in create_result, "Should return success message"
    assert create_result["context_id"] == "test_context", "Should use provided context ID"
    
    # Add a message
    add_result = server._handle_add_message({
        "context_id": "test_context",
        "content": "Test message",
        "priority": "important"
    })
    
    assert "message" in add_result, "Should return success message"
    assert add_result["current_tokens"] > 0, "Should track token count"
    
    # Get context state
    get_result = server._handle_get_context({
        "context_id": "test_context"
    })
    
    assert len(get_result["messages"]) == 1, "Should have one message"
    assert get_result["messages"][0]["content"] == "Test message", "Should preserve message content"
    
    # Clear context
    clear_result = server._handle_clear_context({
        "context_id": "test_context"
    })
    
    assert "message" in clear_result, "Should return success message"
    
    # Verify context is empty
    empty_result = server._handle_get_context({
        "context_id": "test_context"
    })
    
    assert len(empty_result["messages"]) == 0, "Should have no messages after clear"

if __name__ == '__main__':
    pytest.main([__file__])
