"""Tests for the Context Agent module."""

import json
import pytest
from ..agents.context_agent import ContextAgent

def test_analyze_request_structure():
    """Test that analyze_request returns the expected structure."""
    agent = ContextAgent()
    result = agent.analyze_request("What time is it?")
    
    assert isinstance(result, dict)
    assert "prompt" in result
    assert "requires_llm_processing" in result
    assert result["requires_llm_processing"] is True

def test_execute_tool_selection_default():
    """Test default tool selection handling."""
    agent = ContextAgent()
    analysis = {
        "selected_tool": "default",
        "parameters": {
            "operation": "process_command",
            "content": "What time is it?"
        }
    }
    
    result = agent.execute_tool_selection(analysis)
    assert result["tool"] == "execute_command"
    assert "arguments" in result

def test_execute_tool_selection_small_context():
    """Test small context tool selection with context management."""
    agent = ContextAgent()
    analysis = {
        "selected_tool": "small_context",
        "parameters": {
            "operation": "create_context",
            "context_id": "test-123",
            "content": "Remember this information"
        },
        "context_management": {
            "required": True,
            "priority_level": "important",
            "entities": ["test"],
            "relationships": []
        }
    }
    
    result = agent.execute_tool_selection(analysis)
    assert result["tool"] == "use_mcp_tool"
    assert result["server"] == "small-context"
    assert result["operation"] == "create_context"
    assert "arguments" in result
    assert result["arguments"]["contextId"] == "test-123"

def test_execute_tool_selection_fetch():
    """Test fetch tool selection."""
    agent = ContextAgent()
    analysis = {
        "selected_tool": "fetch",
        "parameters": {
            "url": "https://example.com",
            "selector": ".content"
        }
    }
    
    result = agent.execute_tool_selection(analysis)
    assert result["tool"] == "use_mcp_tool"
    assert result["server"] == "fetch-server"
    assert result["operation"] == "fetch"
    assert "arguments" in result

def test_execute_tool_selection_sequential():
    """Test sequential thinking tool selection."""
    agent = ContextAgent()
    analysis = {
        "selected_tool": "sequential_thinking",
        "parameters": {
            "steps": ["analyze", "plan", "execute"],
            "problem": "Complex task"
        }
    }
    
    result = agent.execute_tool_selection(analysis)
    assert result["tool"] == "use_mcp_tool"
    assert result["server"] == "sequential-thinking"
    assert result["operation"] == "think"
    assert "arguments" in result

def test_analysis_prompt_format():
    """Test that the analysis prompt contains all required sections."""
    agent = ContextAgent()
    prompt = agent._generate_analysis_prompt("Test request")
    
    # Check for key sections
    assert "User Request: Test request" in prompt
    assert "Available Tools:" in prompt
    assert "Analysis Instructions:" in prompt
    assert "Provide your analysis in JSON format:" in prompt
    
    # Extract the JSON template from the prompt
    # Find the template after the "JSON format:" marker
    marker = "Provide your analysis in JSON format:"
    template_start = prompt.find(marker) + len(marker)
    json_template = prompt[template_start:].strip()
    
    try:
        print("\nJSON Template:", repr(json_template))  # Show raw string with escapes
        print("\nTemplate length:", len(json_template))
        print("\nLast few characters:", repr(json_template[-10:]))  # Show last 10 chars
        
        # Try to find any extra data
        try:
            parsed = json.loads(json_template)
        except json.JSONDecodeError as e:
            print(f"\nError position: {e.pos}")
            print(f"Error message: {e.msg}")
            print(f"Document excerpt: {json_template[max(0, e.pos-20):e.pos+20]}")
            raise
        
        # Verify required fields
        assert isinstance(parsed, dict), "Template should be a JSON object"
        assert "selected_tool" in parsed, "Missing 'selected_tool' field"
        assert "parameters" in parsed, "Missing 'parameters' field"
        assert isinstance(parsed["parameters"], dict), "'parameters' should be an object"
        assert "context_management" in parsed, "Missing 'context_management' field"
        assert isinstance(parsed["context_management"], dict), "'context_management' should be an object"
        
        # Verify parameters structure
        params = parsed["parameters"]
        assert isinstance(params, dict), "'parameters' should be an object"
        assert "operation" in params, "Missing 'operation' in parameters"
        assert params["operation"] == "process_command", "Unexpected operation value"
        assert "content" in params, "Missing 'content' in parameters"
        assert params["content"] == "user_request", "Unexpected content value"
        
        # Verify context_management structure
        ctx_mgmt = parsed["context_management"]
        assert isinstance(ctx_mgmt, dict), "'context_management' should be an object"
        assert "required" in ctx_mgmt, "Missing 'required' in context_management"
        assert isinstance(ctx_mgmt["required"], bool), "'required' should be a boolean"
        assert "priority_level" in ctx_mgmt, "Missing 'priority_level' in context_management"
        assert ctx_mgmt["priority_level"] == "normal", "Unexpected priority_level value"
        assert "entities" in ctx_mgmt, "Missing 'entities' in context_management"
        assert isinstance(ctx_mgmt["entities"], list), "'entities' should be an array"
        assert "relationships" in ctx_mgmt, "Missing 'relationships' in context_management"
        assert isinstance(ctx_mgmt["relationships"], list), "'relationships' should be an array"
        
    except json.JSONDecodeError as e:
        pytest.fail(f"Invalid JSON template: {e}")

def test_handle_small_context_without_requirement():
    """Test small context handling when context management is not required."""
    agent = ContextAgent()
    result = agent._handle_small_context(
        parameters={},
        context_config={"required": False}
    )
    assert "error" in result
    assert result["error"] == "Context management not required"

def test_handle_default_tools_custom_tool():
    """Test default tools handler with custom tool specification."""
    agent = ContextAgent()
    result = agent._handle_default_tools({
        "tool": "custom_command",
        "args": ["--flag", "value"]
    })
    assert result["tool"] == "custom_command"
    assert "arguments" in result

def test_invalid_tool_selection():
    """Test handling of invalid tool selection."""
    agent = ContextAgent()
    analysis = {
        "selected_tool": "invalid_tool",
        "parameters": {}
    }
    
    # Should fall back to default tools
    result = agent.execute_tool_selection(analysis)
    assert result["tool"] == "execute_command"
    assert "arguments" in result
