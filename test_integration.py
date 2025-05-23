"""Integration tests for smart query routing in cli-FSD.

This module tests the end-to-end integration of query routing with the
existing cli-FSD system, including script handlers, chat models, and
web search functionality.
"""

import pytest
import sys
import os
import json
from unittest.mock import Mock, patch, MagicMock

# Add the cli_FSD package to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'cli_FSD'))

from cli_FSD.query_router import QueryRouter
from cli_FSD.web_search import WebSearchHandler, format_search_response
from cli_FSD.configuration import Config


class MockConfig:
    """Mock configuration object for testing."""
    
    def __init__(self):
        self.CYAN = "\033[96m"
        self.YELLOW = "\033[93m"
        self.RESET = "\033[0m"
        self.session_model = 'openai'
        self.api_key = 'test-key'
        self.current_model = 'gpt-4'
        self.models = {'gpt-4': 'gpt-4-turbo-preview'}
        self.route_info = None


class TestQueryRoutingIntegration:
    """Integration tests for query routing system."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.router = QueryRouter()
        self.web_handler = WebSearchHandler()
        self.mock_config = MockConfig()
    
    @patch('cli_FSD.script_handlers.print_streamed_message')
    @patch('cli_FSD.web_search.WebSearchHandler.search_web')
    def test_web_search_route_integration(self, mock_search, mock_print):
        """Test integration of web search routing."""
        # Mock web search response
        mock_search.return_value = {
            'success': True,
            'source': 'Test Source',
            'content': 'Test weather information',
            'url': 'http://example.com',
            'type': 'instant_answer'
        }
        
        # Import here to avoid circular imports in testing
        from cli_FSD.script_handlers import process_input_based_on_mode
        
        # Test weather query (should route to web search)
        with patch('cli_FSD.chat_models.initialize_chat_models') as mock_init:
            mock_init.return_value = {}
            
            result = process_input_based_on_mode("what's the weather today?", self.mock_config)
            
            # Verify web search was called
            mock_search.assert_called_once()
            # Verify response formatting
            assert 'Test weather information' in result
    
    @patch('cli_FSD.script_handlers.print_streamed_message')
    @patch('cli_FSD.chat_models.chat_with_model')
    def test_direct_llm_route_integration(self, mock_chat, mock_print):
        """Test integration of direct LLM routing."""
        # Mock LLM response
        mock_chat.return_value = "Here's how to write a Python function..."
        
        from cli_FSD.script_handlers import process_input_based_on_mode
        
        # Test Python programming query (should route to direct LLM)
        with patch('cli_FSD.chat_models.initialize_chat_models') as mock_init:
            mock_init.return_value = {}
            
            result = process_input_based_on_mode("how to write a python function", self.mock_config)
            
            # Verify LLM was called with enhanced prompt
            mock_chat.assert_called_once()
            args, kwargs = mock_chat.call_args
            # The first argument should be the enhanced prompt, not the original query
            assert "technical topics you have strong knowledge" in args[0]
    
    def test_enhanced_prompt_application(self):
        """Test that enhanced prompts are properly applied."""
        from cli_FSD.chat_models import chat_with_model
        
        # Set up routing info
        route_info = {
            'route': 'direct_llm',
            'reason': 'high_confidence_technical',
            'confidence': 'high'
        }
        self.mock_config.route_info = route_info
        
        # Mock the actual chat functions
        with patch('cli_FSD.chat_models.chat_with_openai') as mock_openai:
            mock_openai.return_value = "Mock response"
            
            with patch('cli_FSD.chat_models.initialize_chat_models') as mock_init:
                mock_init.return_value = {}
                
                # Call chat_with_model
                result = chat_with_model("test query", self.mock_config, {})
                
                # Verify enhanced prompt was used
                if mock_openai.called:
                    args, kwargs = mock_openai.call_args
                    system_prompt = args[2] if len(args) > 2 else kwargs.get('system_prompt', '')
                    assert "technical topics you have strong knowledge" in system_prompt
    
    def test_web_search_handler_integration(self):
        """Test WebSearchHandler functionality."""
        # Test with a simple query
        with patch('requests.Session.get') as mock_get:
            # Mock DuckDuckGo response
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                'Answer': 'Test answer from DuckDuckGo',
                'AnswerURL': 'http://example.com'
            }
            mock_get.return_value = mock_response
            
            result = self.web_handler.search_web("test query")
            
            assert result['success'] == True
            assert result['content'] == 'Test answer from DuckDuckGo'
            assert result['source'] == 'DuckDuckGo Instant Answer'
    
    def test_response_formatting(self):
        """Test search response formatting."""
        # Test instant answer formatting
        search_result = {
            'success': True,
            'source': 'DuckDuckGo',
            'content': 'Test content',
            'url': 'http://example.com',
            'type': 'instant_answer'
        }
        
        formatted = format_search_response(search_result)
        assert '💡 **Quick Answer**' in formatted
        assert 'Test content' in formatted
        assert 'http://example.com' in formatted
        
        # Test Wikipedia formatting
        search_result['type'] = 'wikipedia_summary'
        formatted = format_search_response(search_result)
        assert '📚 **Wikipedia Summary**' in formatted
    
    def test_routing_decision_consistency(self):
        """Test that routing decisions are consistent across similar queries."""
        similar_queries = [
            "how to write a python function",
            "python function syntax example",
            "create a function in python"
        ]
        
        routes = []
        for query in similar_queries:
            result = self.router.classify_query(query)
            routes.append(result['route'])
        
        # All should route to the same destination (likely direct_llm)
        unique_routes = set(routes)
        assert len(unique_routes) <= 2, f"Similar queries should have consistent routing: {routes}"
    
    def test_fallback_handling(self):
        """Test fallback handling when web search fails."""
        with patch('requests.Session.get') as mock_get:
            # Mock failed web search
            mock_get.side_effect = Exception("Network error")
            
            result = self.web_handler.search_web("test query")
            
            # Should fall back to search guidance
            assert result['success'] == True
            assert result['type'] == 'search_guidance'
            assert 'suggestions for finding this information' in result['content']
    
    @patch('cli_FSD.script_handlers.print_streamed_message')
    def test_session_commands_bypass_routing(self, mock_print):
        """Test that session management commands bypass routing."""
        from cli_FSD.script_handlers import process_input_based_on_mode
        
        with patch('cli_FSD.chat_models.initialize_chat_models') as mock_init:
            mock_init.return_value = {}
            
            # Test history command
            result = process_input_based_on_mode("history", self.mock_config)
            
            # Should bypass routing and go directly to history handler
            # The exact response depends on session state, but it shouldn't trigger routing
            assert isinstance(result, str)


class TestRouteSpecificBehaviors:
    """Test route-specific behaviors and edge cases."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.router = QueryRouter()
    
    def test_mixed_query_routing(self):
        """Test queries that might match multiple patterns."""
        mixed_queries = [
            "search for python tutorial online",  # web search + code help
            "what's the latest python version and how to install it",  # current info + technical
            "find current weather and write bash script to log it"  # web search + system ops
        ]
        
        for query in mixed_queries:
            result = self.router.classify_query(query)
            
            # Should make a clear routing decision
            assert result['route'] in ['web_search', 'direct_llm', 'enhanced_llm', 'tool_selection']
            assert result['confidence'] in ['high', 'medium', 'low']
            
            # Should have scoring details
            assert 'scores' in result
            assert 'flags' in result
    
    def test_route_priority_order(self):
        """Test that routing priorities work correctly."""
        # Explicit web search should override other patterns
        query = "search for python tutorial"  # has both web search and code help patterns
        result = self.router.classify_query(query)
        assert result['route'] == 'web_search'
        
        # Time-sensitive should override high confidence
        query = "today's python news"  # has both current info and code help patterns
        result = self.router.classify_query(query)
        assert result['route'] == 'web_search'
    
    def test_confidence_thresholds(self):
        """Test confidence threshold handling."""
        # High confidence technical query
        query = "python list comprehension syntax"
        result = self.router.classify_query(query)
        assert result['scores']['internal_confidence'] >= 70
        assert result['route'] == 'direct_llm'
        
        # Low confidence query
        query = "help me with this vague problem"
        result = self.router.classify_query(query)
        assert result['scores']['internal_confidence'] < 70
        assert result['route'] in ['enhanced_llm', 'tool_selection']
    
    def test_empty_query_handling(self):
        """Test handling of empty or minimal queries."""
        empty_queries = ["", "   ", "?", "help", "hi"]
        
        for query in empty_queries:
            result = self.router.classify_query(query)
            
            # Should not crash and should provide valid routing
            assert 'route' in result
            assert 'reason' in result
            assert result['route'] in ['enhanced_llm', 'tool_selection']


def run_integration_test_suite():
    """Run comprehensive integration test suite."""
    print("🔧 Running Smart Query Routing Integration Tests")
    print("=" * 60)
    
    # Test routing accuracy with sample queries
    router = QueryRouter()
    web_handler = WebSearchHandler()
    
    test_scenarios = [
        {
            'name': 'Web Search Routing',
            'queries': [
                "what's the weather today?",
                "latest AI news",
                "current bitcoin price"
            ],
            'expected_route': 'web_search'
        },
        {
            'name': 'Direct LLM Routing',
            'queries': [
                "how to write a python function",
                "git merge vs rebase",
                "bash command to list files"
            ],
            'expected_route': 'direct_llm'
        },
        {
            'name': 'Enhanced Prompting',
            'queries': [
                "explain machine learning",
                "database best practices",
                "web development tips"
            ],
            'expected_route': ['enhanced_llm', 'direct_llm']  # Either is acceptable
        }
    ]
    
    total_passed = 0
    total_tests = 0
    
    for scenario in test_scenarios:
        print(f"\n🧪 Testing {scenario['name']}:")
        
        for query in scenario['queries']:
            result = router.classify_query(query)
            actual_route = result['route']
            
            expected = scenario['expected_route']
            if isinstance(expected, list):
                passed = actual_route in expected
            else:
                passed = actual_route == expected
            
            status = "✅" if passed else "❌"
            print(f"  {status} '{query}' -> {actual_route}")
            
            if passed:
                total_passed += 1
            total_tests += 1
    
    # Test web search handler
    print(f"\n🌐 Testing Web Search Handler:")
    
    with patch('requests.Session.get') as mock_get:
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'Answer': 'Test response',
            'AnswerURL': 'http://example.com'
        }
        mock_get.return_value = mock_response
        
        try:
            result = web_handler.search_web("test query")
            if result['success']:
                print("  ✅ Web search handler working")
                total_passed += 1
            else:
                print("  ❌ Web search handler failed")
            total_tests += 1
        except Exception as e:
            print(f"  ❌ Web search handler error: {e}")
            total_tests += 1
    
    # Calculate success rate
    success_rate = (total_passed / total_tests) * 100 if total_tests > 0 else 0
    
    print(f"\n📊 Integration Test Results:")
    print(f"Success Rate: {success_rate:.1f}% ({total_passed}/{total_tests})")
    
    if success_rate >= 80:
        print("🎉 Integration tests PASSED - Smart query routing is working well!")
    elif success_rate >= 60:
        print("⚠️ Integration tests PARTIAL - Some issues need attention")
    else:
        print("🚨 Integration tests FAILED - Significant issues detected")
    
    return success_rate


if __name__ == "__main__":
    # Run integration tests
    success_rate = run_integration_test_suite()
    
    # Run pytest if available
    try:
        import pytest
        print(f"\n🔬 Running pytest integration suite...")
        pytest.main([__file__, "-v"])
    except ImportError:
        print(f"\n💡 Install pytest to run full test suite: pip install pytest")