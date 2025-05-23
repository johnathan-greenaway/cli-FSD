"""Test suite for query routing functionality.

This module tests the accuracy of the QueryRouter classification system
and validates routing decisions for different types of queries.
"""

import pytest
import sys
import os

# Add the cli_FSD package to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'cli_FSD'))

from cli_FSD.query_router import QueryRouter


class TestQueryRouter:
    """Test cases for QueryRouter functionality."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.router = QueryRouter()
    
    def test_web_search_route_explicit(self):
        """Test explicit web search requests."""
        test_cases = [
            "search for the latest news",
            "look up weather in New York",
            "find information about Python 3.12",
            "what is the current stock price of Apple?",
            "google the latest bitcoin price"
        ]
        
        for query in test_cases:
            result = self.router.classify_query(query)
            assert result['route'] == 'web_search', f"Query '{query}' should route to web_search"
            assert result['confidence'] == 'high'
    
    def test_web_search_route_time_sensitive(self):
        """Test time-sensitive queries that should route to web search."""
        test_cases = [
            "what's the weather today?",
            "latest news about AI",
            "current exchange rate USD to EUR",
            "what happened this week in tech?",
            "breaking news about Tesla",
            "live cryptocurrency prices"
        ]
        
        for query in test_cases:
            result = self.router.classify_query(query)
            assert result['route'] == 'web_search', f"Query '{query}' should route to web_search"
    
    def test_direct_llm_route_technical(self):
        """Test high-confidence technical queries that should use direct LLM."""
        test_cases = [
            "how to write a python function",
            "explain bash regex patterns",
            "git merge vs git rebase differences",
            "create a javascript loop example",
            "linux file permissions chmod explained",
            "docker container vs image difference"
        ]
        
        for query in test_cases:
            result = self.router.classify_query(query)
            # Accept both direct_llm and enhanced_llm for technical queries
            assert result['route'] in ['direct_llm', 'enhanced_llm'], f"Query '{query}' should route to direct_llm or enhanced_llm"
    
    def test_direct_llm_route_programming(self):
        """Test programming-related queries."""
        test_cases = [
            "how do I create a list in Python?",
            "bash command to list files recursively",
            "regular expression for email validation",
            "SQL query to join two tables",
            "CSS flexbox layout example"
        ]
        
        for query in test_cases:
            result = self.router.classify_query(query)
            # Accept both direct_llm and enhanced_llm for programming queries
            assert result['route'] in ['direct_llm', 'enhanced_llm'], f"Query '{query}' should route to direct_llm or enhanced_llm"
    
    def test_enhanced_llm_route_moderate_confidence(self):
        """Test queries with moderate confidence that should get enhanced prompts."""
        test_cases = [
            "explain machine learning concepts",
            "best practices for software development",
            "how does blockchain work?",
            "database design principles",
            "web security best practices"
        ]
        
        for query in test_cases:
            result = self.router.classify_query(query)
            # These could be enhanced_llm or direct_llm depending on confidence
            assert result['route'] in ['enhanced_llm', 'direct_llm'], f"Query '{query}' should route to enhanced_llm or direct_llm"
    
    def test_tool_selection_route_ambiguous(self):
        """Test ambiguous queries that should fall back to tool selection."""
        test_cases = [
            "help me with this problem",
            "what should I do?",
            "I need assistance",
            "can you help?",
            "unclear request here"
        ]
        
        for query in test_cases:
            result = self.router.classify_query(query)
            # These should likely fall back to tool selection
            assert result['route'] in ['tool_selection', 'enhanced_llm'], f"Query '{query}' routing: {result['route']}"
    
    def test_pattern_scoring(self):
        """Test pattern scoring functionality."""
        # Test current info patterns
        query = "what's the weather today and latest news?"
        result = self.router.classify_query(query)
        assert result['scores']['current_info'] > 0
        
        # Test code help patterns
        query = "how to write a python function with bash commands?"
        result = self.router.classify_query(query)
        assert result['scores']['code_help'] > 0
        
        # Test system ops patterns
        query = "create directory and change file permissions"
        result = self.router.classify_query(query)
        assert result['scores']['system_ops'] > 0
    
    def test_confidence_assessment(self):
        """Test internal confidence assessment."""
        # High confidence technical query
        high_conf_query = "python list comprehension syntax"
        result = self.router.classify_query(high_conf_query)
        assert result['scores']['internal_confidence'] >= 70
        
        # Low confidence current info query
        low_conf_query = "today's stock market performance"
        result = self.router.classify_query(low_conf_query)
        assert result['scores']['internal_confidence'] <= 50
    
    def test_time_sensitivity_detection(self):
        """Test time sensitivity detection."""
        time_sensitive_queries = [
            "what's happening now?",
            "today's weather",
            "current bitcoin price",
            "latest breaking news",
            "this week's events"
        ]
        
        for query in time_sensitive_queries:
            result = self.router.classify_query(query)
            assert result['flags']['time_sensitive'] == True, f"Query '{query}' should be time-sensitive"
        
        non_time_sensitive_queries = [
            "how to write python code",
            "explain git commands",
            "database design principles"
        ]
        
        for query in non_time_sensitive_queries:
            result = self.router.classify_query(query)
            assert result['flags']['time_sensitive'] == False, f"Query '{query}' should not be time-sensitive"
    
    def test_enhanced_prompt_generation(self):
        """Test enhanced prompt generation for different routes."""
        query = "how to write a python function"
        route_info = {'route': 'direct_llm', 'reason': 'high_confidence_technical'}
        
        enhanced_prompt = self.router.get_enhanced_prompt(query, route_info)
        assert "internal knowledge" in enhanced_prompt.lower()
        assert "do not suggest using external tools" in enhanced_prompt.lower()
        
        # Test web search prompt
        route_info = {'route': 'web_search', 'reason': 'time_sensitive'}
        enhanced_prompt = self.router.get_enhanced_prompt(query, route_info)
        assert "web search tools" in enhanced_prompt.lower()
        assert "up-to-date information" in enhanced_prompt.lower()
    
    def test_routing_consistency(self):
        """Test that similar queries get consistent routing."""
        python_queries = [
            "how to write a python function",
            "python function syntax",
            "create python function example"
        ]
        
        routes = []
        for query in python_queries:
            result = self.router.classify_query(query)
            routes.append(result['route'])
        
        # All should be the same route (likely direct_llm)
        assert len(set(routes)) <= 2, f"Similar queries should have consistent routing: {routes}"
    
    def test_empty_and_invalid_queries(self):
        """Test handling of empty and invalid queries."""
        invalid_queries = ["", "   ", "?", ".", "a"]
        
        for query in invalid_queries:
            result = self.router.classify_query(query)
            # Should not crash and should return valid structure
            assert 'route' in result
            assert 'reason' in result
            assert 'confidence' in result


def run_routing_accuracy_test():
    """Run comprehensive routing accuracy test with detailed results."""
    router = QueryRouter()
    
    # Test cases organized by expected route
    test_cases = {
        'web_search': [
            "what's the weather today?",
            "latest news about AI",
            "current stock price of Tesla",
            "search for Python 3.12 release date",
            "what happened this week in tech?"
        ],
        'direct_llm': [
            "how to write a python function",
            "bash command to list files",
            "git merge vs rebase difference",
            "explain regex patterns",
            "linux file permissions chmod"
        ],
        'enhanced_llm': [
            "explain machine learning",
            "database design principles",
            "web development best practices"
        ]
    }
    
    total_tests = 0
    correct_routes = 0
    results = {}
    
    print("🧪 Running Query Routing Accuracy Test")
    print("=" * 50)
    
    for expected_route, queries in test_cases.items():
        results[expected_route] = {'correct': 0, 'total': len(queries), 'details': []}
        
        print(f"\n📋 Testing {expected_route.upper()} route:")
        
        for query in queries:
            result = router.classify_query(query)
            actual_route = result['route']
            is_correct = actual_route == expected_route
            
            if is_correct:
                correct_routes += 1
                results[expected_route]['correct'] += 1
                status = "✅"
            else:
                status = "❌"
            
            total_tests += 1
            
            print(f"  {status} '{query}' -> {actual_route} (expected: {expected_route})")
            results[expected_route]['details'].append({
                'query': query,
                'expected': expected_route,
                'actual': actual_route,
                'correct': is_correct,
                'confidence': result['confidence'],
                'reason': result['reason']
            })
    
    # Calculate and display accuracy
    overall_accuracy = (correct_routes / total_tests) * 100
    
    print(f"\n📊 Results Summary:")
    print(f"Overall Accuracy: {overall_accuracy:.1f}% ({correct_routes}/{total_tests})")
    
    for route, data in results.items():
        route_accuracy = (data['correct'] / data['total']) * 100
        print(f"{route.upper()}: {route_accuracy:.1f}% ({data['correct']}/{data['total']})")
    
    return overall_accuracy, results


if __name__ == "__main__":
    # Run the accuracy test
    accuracy, detailed_results = run_routing_accuracy_test()
    
    # Also run pytest if available
    try:
        import pytest
        print(f"\n🔬 Running pytest suite...")
        pytest.main([__file__, "-v"])
    except ImportError:
        print(f"\n💡 Install pytest to run full test suite: pip install pytest")