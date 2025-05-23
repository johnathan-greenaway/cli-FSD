"""Interactive demo for smart query routing in cli-FSD.

This module provides an interactive demonstration of the query routing system,
allowing users to test different queries and see how they are classified and routed.
"""

import sys
import os
from typing import Dict, Any

# Add the cli_FSD package to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'cli_FSD'))

from cli_FSD.query_router import QueryRouter
from cli_FSD.web_search import WebSearchHandler, format_search_response


class RoutingDemo:
    """Interactive demonstration of query routing functionality."""
    
    def __init__(self):
        """Initialize the demo with router and web handler."""
        self.router = QueryRouter()
        self.web_handler = WebSearchHandler()
        self.colors = {
            'cyan': '\033[96m',
            'yellow': '\033[93m',
            'green': '\033[92m',
            'red': '\033[91m',
            'blue': '\033[94m',
            'magenta': '\033[95m',
            'reset': '\033[0m',
            'bold': '\033[1m'
        }
    
    def print_header(self):
        """Print the demo header."""
        print(f"{self.colors['cyan']}{self.colors['bold']}")
        print("=" * 70)
        print("🚀 CLI-FSD SMART QUERY ROUTING DEMO")
        print("=" * 70)
        print(f"{self.colors['reset']}")
        print("This demo shows how queries are intelligently routed to:")
        print(f"  🔍 {self.colors['blue']}Web Search{self.colors['reset']} - For current information")
        print(f"  💡 {self.colors['green']}Direct LLM{self.colors['reset']} - For technical queries")
        print(f"  ⚡ {self.colors['yellow']}Enhanced LLM{self.colors['reset']} - For moderate confidence queries")
        print(f"  🛠️  {self.colors['magenta']}Tool Selection{self.colors['reset']} - For ambiguous queries")
        print()
        print("Commands:")
        print("  'help' - Show example queries")
        print("  'test' - Run predefined test cases")
        print("  'analyze <query>' - Analyze a specific query without executing")
        print("  'quit' or 'exit' - Exit the demo")
        print()
    
    def print_help(self):
        """Print example queries for each route type."""
        examples = {
            "Web Search Examples (🔍)": [
                "what's the weather today?",
                "latest news about AI",
                "current bitcoin price",
                "search for Python 3.12 features",
                "what happened this week in tech?"
            ],
            "Direct LLM Examples (💡)": [
                "how to write a python function",
                "git merge vs rebase difference",
                "bash command to list files recursively",
                "explain regex patterns",
                "linux file permissions chmod"
            ],
            "Enhanced LLM Examples (⚡)": [
                "explain machine learning concepts",
                "database design best practices",
                "web development security tips",
                "software architecture patterns",
                "cloud computing benefits"
            ],
            "Tool Selection Examples (🛠️)": [
                "help me with this problem",
                "I need assistance",
                "what should I do?",
                "unclear request here"
            ]
        }
        
        print(f"{self.colors['bold']}📝 Example Queries by Route Type:{self.colors['reset']}")
        print()
        
        for category, queries in examples.items():
            print(f"{self.colors['cyan']}{category}{self.colors['reset']}")
            for query in queries:
                print(f"  • {query}")
            print()
    
    def analyze_query(self, query: str, show_details: bool = True) -> Dict[str, Any]:
        """Analyze a query and display routing information."""
        result = self.router.classify_query(query)
        
        if show_details:
            self.display_routing_analysis(query, result)
        
        return result
    
    def display_routing_analysis(self, query: str, result: Dict[str, Any]):
        """Display detailed routing analysis."""
        route = result['route']
        reason = result['reason']
        confidence = result['confidence']
        scores = result.get('scores', {})
        flags = result.get('flags', {})
        
        # Route-specific colors and icons
        route_info = {
            'web_search': ('🔍', self.colors['blue']),
            'direct_llm': ('💡', self.colors['green']),
            'enhanced_llm': ('⚡', self.colors['yellow']),
            'tool_selection': ('🛠️', self.colors['magenta'])
        }
        
        icon, color = route_info.get(route, ('❓', self.colors['red']))
        
        print(f"\n{self.colors['bold']}Query Analysis:{self.colors['reset']}")
        print(f"📝 Query: '{query}'")
        print(f"{icon} {color}Route: {route.upper()}{self.colors['reset']}")
        print(f"🎯 Reason: {reason}")
        print(f"📊 Confidence: {confidence}")
        
        print(f"\n{self.colors['bold']}Pattern Scores:{self.colors['reset']}")
        for pattern_type, score in scores.items():
            bar_length = int(score / 5)  # Scale to 0-20 chars
            bar = "█" * bar_length + "░" * (20 - bar_length)
            print(f"  {pattern_type.replace('_', ' ').title()}: {score:5.1f} |{bar}|")
        
        print(f"\n{self.colors['bold']}Flags:{self.colors['reset']}")
        for flag, value in flags.items():
            status = "✅" if value else "❌"
            print(f"  {status} {flag.replace('_', ' ').title()}: {value}")
        
        # Show enhanced prompt sample
        enhanced_prompt = self.router.get_enhanced_prompt(query, result)
        print(f"\n{self.colors['bold']}Enhanced Prompt Preview:{self.colors['reset']}")
        preview = enhanced_prompt.split('\n')[0]  # First line only
        if len(preview) > 100:
            preview = preview[:97] + "..."
        print(f"  {preview}")
    
    def execute_query_demo(self, query: str):
        """Demonstrate query execution (simulated)."""
        result = self.analyze_query(query, show_details=False)
        route = result['route']
        
        print(f"\n{self.colors['bold']}🚀 Simulating Query Execution:{self.colors['reset']}")
        
        if route == 'web_search':
            print(f"{self.colors['blue']}🔍 Executing web search...{self.colors['reset']}")
            try:
                search_result = self.web_handler.search_web(query)
                if search_result['success']:
                    print(f"✅ Web search successful!")
                    print(f"📄 Source: {search_result.get('source', 'Unknown')}")
                    content = search_result.get('content', '')
                    if len(content) > 200:
                        content = content[:197] + "..."
                    print(f"📝 Content: {content}")
                else:
                    print(f"⚠️ Web search failed: {search_result.get('error', 'Unknown error')}")
            except Exception as e:
                print(f"❌ Web search error: {e}")
        
        elif route == 'direct_llm':
            print(f"{self.colors['green']}💡 Using direct LLM processing...{self.colors['reset']}")
            enhanced_prompt = self.router.get_enhanced_prompt(query, result)
            print("✅ Enhanced prompt generated for high-confidence technical query")
            print("🤖 LLM would receive optimized system prompt")
            
        elif route == 'enhanced_llm':
            print(f"{self.colors['yellow']}⚡ Using enhanced LLM processing...{self.colors['reset']}")
            enhanced_prompt = self.router.get_enhanced_prompt(query, result)
            print("✅ Enhanced prompt generated for moderate-confidence query")
            print("🤖 LLM would receive context-aware system prompt")
            
        else:  # tool_selection
            print(f"{self.colors['magenta']}🛠️ Falling back to tool selection...{self.colors['reset']}")
            print("✅ Query would be processed through original ContextAgent")
            print("🤖 LLM would analyze and select appropriate tools")
    
    def run_test_cases(self):
        """Run predefined test cases to demonstrate routing accuracy."""
        test_cases = [
            ("what's the weather today?", "web_search", "Time-sensitive current information"),
            ("how to write a python function", "direct_llm", "High-confidence technical query"),
            ("explain machine learning", "enhanced_llm", "Moderate-confidence educational query"),
            ("help me with this", "tool_selection", "Ambiguous request requiring analysis"),
            ("search for latest AI news", "web_search", "Explicit web search request"),
            ("git merge vs rebase", "direct_llm", "Technical comparison query"),
        ]
        
        print(f"{self.colors['bold']}🧪 Running Test Cases:{self.colors['reset']}")
        print()
        
        correct = 0
        total = len(test_cases)
        
        for query, expected_route, description in test_cases:
            result = self.router.classify_query(query)
            actual_route = result['route']
            
            status = "✅" if actual_route == expected_route else "❌"
            color = self.colors['green'] if actual_route == expected_route else self.colors['red']
            
            print(f"{status} {color}{query}{self.colors['reset']}")
            print(f"    Expected: {expected_route} | Actual: {actual_route}")
            print(f"    {description}")
            print()
            
            if actual_route == expected_route:
                correct += 1
        
        accuracy = (correct / total) * 100
        print(f"{self.colors['bold']}📊 Test Results: {accuracy:.1f}% accuracy ({correct}/{total}){self.colors['reset']}")
        
        if accuracy >= 80:
            print(f"{self.colors['green']}🎉 Excellent routing accuracy!{self.colors['reset']}")
        elif accuracy >= 60:
            print(f"{self.colors['yellow']}⚠️ Good routing accuracy with room for improvement{self.colors['reset']}")
        else:
            print(f"{self.colors['red']}🚨 Routing accuracy needs improvement{self.colors['reset']}")
    
    def run_interactive_demo(self):
        """Run the interactive demo loop."""
        self.print_header()
        
        while True:
            try:
                user_input = input(f"{self.colors['cyan']}demo> {self.colors['reset']}").strip()
                
                if not user_input:
                    continue
                
                if user_input.lower() in ['quit', 'exit', 'q']:
                    print(f"{self.colors['green']}👋 Thanks for trying the smart query routing demo!{self.colors['reset']}")
                    break
                
                elif user_input.lower() == 'help':
                    self.print_help()
                
                elif user_input.lower() == 'test':
                    self.run_test_cases()
                
                elif user_input.lower().startswith('analyze '):
                    query = user_input[8:].strip()
                    if query:
                        self.analyze_query(query)
                    else:
                        print(f"{self.colors['yellow']}Please provide a query to analyze.{self.colors['reset']}")
                
                else:
                    # Treat as a query to route and simulate
                    self.analyze_query(user_input)
                    self.execute_query_demo(user_input)
                
            except KeyboardInterrupt:
                print(f"\n{self.colors['green']}👋 Demo interrupted. Goodbye!{self.colors['reset']}")
                break
            except Exception as e:
                print(f"{self.colors['red']}❌ Error: {e}{self.colors['reset']}")


def main():
    """Main entry point for the demo."""
    try:
        demo = RoutingDemo()
        demo.run_interactive_demo()
    except ImportError as e:
        print(f"❌ Import error: {e}")
        print("Make sure you're running this from the cli-FSD root directory.")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()