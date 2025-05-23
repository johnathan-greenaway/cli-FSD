#!/usr/bin/env python3
"""Test script to verify browse tool routing improvements."""

from cli_FSD.query_router import QueryRouter
from cli_FSD.agents.context_agent import ContextAgent

def test_routing():
    """Test various browse tool queries."""
    router = QueryRouter()
    
    test_queries = [
        "use the browse tool to find cool news stories from today",
        "browse to hacker news",
        "using the browse tool, show me tech news",
        "find news about AI",  # Should not trigger browse tool
        "search for python tutorials",  # Should not trigger browse tool
        "browse tool for reddit news"
    ]
    
    print("Testing Query Router\n" + "="*50)
    
    for query in test_queries:
        route_info = router.classify_query(query)
        print(f"\nQuery: {query}")
        print(f"Route: {route_info['route']}")
        print(f"Reason: {route_info['reason']}")
        if route_info.get('metadata'):
            print(f"Metadata: {route_info['metadata']}")
        print(f"Browse tool score: {route_info['scores']['browse_tool']}")

def test_context_agent():
    """Test ContextAgent with routing metadata."""
    agent = ContextAgent()
    
    print("\n\nTesting Context Agent\n" + "="*50)
    
    # Test with explicit tool request metadata
    routing_metadata = {
        'route': 'tool_selection',
        'reason': 'explicit_tool_request',
        'confidence': 'high',
        'metadata': {
            'requested_tool': 'browse_web',
            'user_explicit_request': True
        }
    }
    
    query = "use the browse tool to find cool news stories from today"
    analysis = agent.analyze_request(query, routing_metadata=routing_metadata)
    
    print(f"\nQuery: {query}")
    print(f"Has LLM prompt: {'prompt' in analysis}")
    
    if 'prompt' in analysis:
        # Check if routing hints are included
        prompt = analysis['prompt']
        if 'ROUTING HINT' in prompt:
            print("✓ Routing hints included in prompt")
            # Extract just the routing hint line
            for line in prompt.split('\n'):
                if 'ROUTING HINT' in line:
                    print(f"  {line.strip()}")
        else:
            print("✗ Routing hints NOT included in prompt")

if __name__ == "__main__":
    test_routing()
    test_context_agent()
    print("\n\nTests completed!")