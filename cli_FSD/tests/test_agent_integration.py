"""Integration tests for agent interactions with user queries."""

import pytest
from unittest.mock import Mock, patch
from ..agents.context_agent import ContextAgent
from ..script_handlers import process_input_based_on_mode
from ..configuration import Config

@pytest.fixture
def mock_config():
    """Create a mock config with test settings."""
    config = Config()
    config.session_model = "test-model"
    config.safe_mode = False
    config.autopilot_mode = False
    config.CYAN = ""  # Mock color codes
    config.YELLOW = ""
    config.RED = ""
    config.GREEN = ""
    config.RESET = ""
    return config

@pytest.fixture
def mock_chat_models():
    """Create mock chat models for testing."""
    return {"model": Mock()}

def test_simple_command_query(mock_config, mock_chat_models):
    """Test agent handling of a simple command query."""
    query = "What time is it?"
    
    # Mock LLM response for tool selection
    tool_selection_response = '''{
        "selected_tool": "default",
        "reasoning": "Simple command execution request",
        "parameters": {
            "operation": "process_command",
            "content": "date"
        }
    }'''
    
    # Mock LLM responses
    mock_chat_models["model"].chat.side_effect = [
        {"message": {"content": tool_selection_response}},  # Tool selection
        {"message": {"content": "```bash\ndate\n```"}}  # Command generation
    ]
    
    # Process the query
    result = process_input_based_on_mode(query, mock_config, mock_chat_models)
    assert result is not None
    assert "date" in result.lower()

def test_context_management_query(mock_config, mock_chat_models):
    """Test agent handling of a context-aware query."""
    query = "Remember that my favorite color is blue"
    
    # Mock LLM response for tool selection
    tool_selection_response = '''{
        "selected_tool": "small_context",
        "reasoning": "Need to store user preference",
        "parameters": {
            "operation": "create_context",
            "context_id": "user_prefs",
            "content": "favorite_color: blue"
        },
        "context_management": {
            "required": true,
            "priority_level": "important",
            "entities": ["favorite_color"],
            "relationships": []
        }
    }'''
    
    # Mock LLM responses
    mock_chat_models["model"].chat.side_effect = [
        {"message": {"content": tool_selection_response}},  # Tool selection
        {"message": {"content": "I'll remember that your favorite color is blue."}}  # Response
    ]
    
    # Process the query
    result = process_input_based_on_mode(query, mock_config, mock_chat_models)
    assert result is not None
    assert "remember" in result.lower()
    assert "blue" in result.lower()

def test_fetch_tool_query(mock_config, mock_chat_models):
    """Test agent handling of an external data query."""
    query = "Get the weather in London"
    
    # Mock LLM response for tool selection
    tool_selection_response = '''{
        "selected_tool": "fetch",
        "reasoning": "Need to retrieve external weather data",
        "parameters": {
            "url": "https://api.weather.com/london",
            "operation": "fetch_weather"
        }
    }'''
    
    # Mock LLM responses
    mock_chat_models["model"].chat.side_effect = [
        {"message": {"content": tool_selection_response}},  # Tool selection
        {"message": {"content": "The weather in London is cloudy, 15°C"}}  # Response
    ]
    
    # Process the query
    result = process_input_based_on_mode(query, mock_config, mock_chat_models)
    assert result is not None
    assert "weather" in result.lower()
    assert "london" in result.lower()

def test_sequential_thinking_query(mock_config, mock_chat_models):
    """Test agent handling of a complex problem-solving query."""
    query = "Help me debug why my Node.js server isn't starting"
    
    # Mock LLM response for tool selection
    tool_selection_response = '''{
        "selected_tool": "sequential_thinking",
        "reasoning": "Complex debugging requires step-by-step analysis",
        "parameters": {
            "operation": "think",
            "steps": [
                "Check port availability",
                "Verify Node.js installation",
                "Check package.json",
                "Review error logs"
            ]
        }
    }'''
    
    # Mock LLM responses
    mock_chat_models["model"].chat.side_effect = [
        {"message": {"content": tool_selection_response}},  # Tool selection
        {"message": {"content": "Let's debug this step by step:\n1. First, let's check..."}}  # Response
    ]
    
    # Process the query
    result = process_input_based_on_mode(query, mock_config, mock_chat_models)
    assert result is not None
    assert "debug" in result.lower()
    assert "step" in result.lower()

def test_mode_switching(mock_config, mock_chat_models):
    """Test agent behavior with different modes."""
    # Test safe mode
    mock_config.safe_mode = True
    query = "Run git status"
    
    # Mock LLM response
    mock_chat_models["model"].chat.return_value = {
        "message": {"content": "```bash\ngit status\n```"}
    }
    
    # Process in safe mode
    result = process_input_based_on_mode(query, mock_config, mock_chat_models)
    assert result is not None
    
    # Test autopilot mode
    mock_config.safe_mode = False
    mock_config.autopilot_mode = True
    
    # Process in autopilot mode
    result = process_input_based_on_mode(query, mock_config, mock_chat_models)
    assert result is not None

def test_error_handling(mock_config, mock_chat_models):
    """Test agent's error handling capabilities."""
    query = "Execute invalid command"
    
    # Mock LLM to raise an exception
    mock_chat_models["model"].chat.side_effect = Exception("Test error")
    
    # Process query with error
    result = process_input_based_on_mode(query, mock_config, mock_chat_models)
    assert result is not None  # Should handle error gracefully
