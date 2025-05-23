"""Smart Query Router for cli-FSD.

This module provides intelligent query classification and routing to solve
inappropriate tool selection by AI agents. It implements pre-processing
query analysis to route queries to appropriate handlers before LLM processing.
"""

import re
import logging
from typing import Dict, Any, List, Tuple
from datetime import datetime

# Configure logging
logger = logging.getLogger(__name__)


class QueryRouter:
    """Intelligent query classification and routing decision engine."""
    
    def __init__(self):
        """Initialize the query router with pattern definitions."""
        # Current information patterns - require real-time or recent data
        self.current_info_patterns = [
            r'\b(weather|temperature|forecast)\b',
            r'\b(news|breaking|latest|current events)\b',
            r'\b(stock price|market|trading|cryptocurrency|crypto)\b',
            r'\b(today|now|current|recent|this week|this month)\b',
            r'\b(what\'s happening|what happened)\b',
            r'\b(latest version|newest|most recent)\b',
            r'\b(exchange rate|currency|bitcoin|ethereum)\b',
            r'\b(live|real-time|up-to-date)\b'
        ]
        
        # Code help patterns - programming and technical queries
        self.code_help_patterns = [
            r'\b(bash|shell|terminal|command line)\b',
            r'\b(python|javascript|java|c\+\+|rust|go|node\.js)\b',
            r'\b(function|variable|loop|if statement|class|method)\b',
            r'\b(syntax|error|debug|fix|troubleshoot)\b',
            r'\b(how do I|how to|example of)\b.*\b(code|script|command)\b',
            r'\b(git|docker|kubernetes|npm|pip|yarn)\b',
            r'\b(regex|regular expression)\b',
            r'\b(ls|cd|mkdir|rm|cp|mv|chmod|chown|grep|find|awk|sed)\b',
            r'\b(list files|change directory|make directory)\b',
            r'\b(permissions|executable|script)\b',
            r'\b(api|rest|http|json|xml)\b',
            r'\b(database|sql|query|select|insert|update)\b'
        ]
        
        # System operations patterns - file and system management
        self.system_ops_patterns = [
            r'\b(file|directory|folder|path)\b',
            r'\b(create|delete|move|copy|rename)\b',
            r'\b(permissions|chmod|chown)\b',
            r'\b(process|kill|ps|top|htop)\b',
            r'\b(disk space|memory|cpu|system info)\b',
            r'\b(install|uninstall|package|apt|yum|brew)\b',
            r'\b(service|daemon|systemctl|crontab)\b',
            r'\b(network|port|ping|curl|wget)\b'
        ]
        
        # Simple command patterns - operations that should use basic commands
        self.simple_command_patterns = [
            r'\bls\b',
            r'\bdir\b',
            r'\blist files\b',
            r'\bshow files\b',
            r'\bview files\b',
            r'\b(list|show|view|display|see|review)\b.*\b(file|files|directory|directories|folder|folders)\b',
            r'\b(review|check|examine)\b.*\b(file|files|directory|directories|repo|repository)\b',
            r'\b(show|list)\b.*\b(content|contents)\b',
            r'\b(what|what\'s)\b.*\b(file|files)\b.*\b(in|inside|are)\b',
            r'\b(what|what\'s)\b.*\b(in|inside)\b.*\b(directory|folder|repo|repository)\b',
            r'\bwhat files are in\b',
            r'\bwhat files are\b.*\b(directory|folder)\b',
            r'\b(count|how many)\b.*\b(file|files)\b',
            r'\b(find|search)\b.*\b(file|files)\b.*\b(in|inside)\b',
            r'\b(copy|cp|move|mv)\b.*\b(file|files)\b',
            r'\b(add|append|insert)\b.*\b(content|contents|text)\b.*\b(to|into)\b',
            r'\breview.*files.*repo\b',
            r'\breview.*files.*directory\b',
            r'\bshow.*files.*in\b',
            r'\blist.*files.*in\b',
            r'\bshow files in\b',
            r'\bview.*files.*in.*folder\b'
        ]
        
        # Web search indicators - explicit search requests
        self.web_search_indicators = [
            r'\b(search|find|lookup|look up)\b',
            r'\b(google|bing|duckduckgo)\b',
            r'\b(what is|who is|where is|when is)\b(?!.*\b(file|files|directory|folder)\b)',
            r'\b(definition|meaning|explain)\b',
            r'\b(website|url|link)\b'
        ]
        
        # Browse tool indicators - explicit browse tool requests
        self.browse_tool_indicators = [
            r'\b(use|using)\s+(the\s+)?browse(r)?\s+tool\b',
            r'\bbrowse\s+tool\b',
            r'\b(browse|visit|go to|open)\s+(website|site|url|page)\b',
            r'\bweb\s+browser\b',
            r'\bbrowse\s+(to|for)\b'
        ]
        
        # High confidence topics for internal knowledge
        self.high_confidence_topics = [
            'python', 'javascript', 'bash', 'git', 'linux', 'programming',
            'syntax', 'function', 'variable', 'loop', 'command', 'script',
            'file', 'directory', 'regex', 'json', 'api', 'http'
        ]
        
        # Low confidence topics requiring external data
        self.low_confidence_topics = [
            'weather', 'news', 'stock', 'price', 'current', 'today',
            'latest', 'recent', 'breaking', 'live', 'real-time'
        ]
    
    def classify_query(self, query: str) -> Dict[str, Any]:
        """
        Main classification logic to analyze query and determine routing.
        
        Args:
            query: User input query string
            
        Returns:
            Dictionary containing routing information
        """
        query_lower = query.lower()
        
        # Check for explicit tool usage requests first
        explicit_tool_request = None
        if any(phrase in query_lower for phrase in ['use the browse tool', 'using the browse tool', 'use browse tool', 'browse tool']):
            explicit_tool_request = 'browse_web'
        elif any(phrase in query_lower for phrase in ['use the file tool', 'using the file tool', 'file tool']):
            explicit_tool_request = 'file_operation'
        elif any(phrase in query_lower for phrase in ['use the command tool', 'using the command tool', 'command tool']):
            explicit_tool_request = 'command'
        
        # If explicit tool request found, route to tool_selection with metadata
        if explicit_tool_request:
            return {
                'route': 'tool_selection',
                'reason': 'explicit_tool_request',
                'confidence': 'high',
                'metadata': {
                    'requested_tool': explicit_tool_request,
                    'user_explicit_request': True
                }
            }
        
        # Calculate pattern scores
        current_info_score = self._calculate_pattern_score(query_lower, self.current_info_patterns)
        code_help_score = self._calculate_pattern_score(query_lower, self.code_help_patterns)
        system_ops_score = self._calculate_pattern_score(query_lower, self.system_ops_patterns)
        simple_command_score = self._calculate_pattern_score(query_lower, self.simple_command_patterns)
        web_search_score = self._calculate_pattern_score(query_lower, self.web_search_indicators)
        browse_tool_score = self._calculate_pattern_score(query_lower, self.browse_tool_indicators)
        
        # Assess internal confidence
        internal_confidence = self._assess_internal_confidence(query_lower)
        
        # Check for time sensitivity
        is_time_sensitive = self._is_time_sensitive(query_lower)
        
        # Check for explicit web search request
        explicit_web_search = web_search_score > 30 or any(
            indicator in query_lower for indicator in ['search for', 'look up', 'find information about']
        )
        
        # Make routing decision
        route_info = self._make_routing_decision(
            current_info_score, code_help_score, system_ops_score, simple_command_score,
            internal_confidence, is_time_sensitive, explicit_web_search, browse_tool_score
        )
        
        # Add scoring details for debugging
        route_info.update({
            'scores': {
                'current_info': current_info_score,
                'code_help': code_help_score,
                'system_ops': system_ops_score,
                'simple_command': simple_command_score,
                'web_search': web_search_score,
                'browse_tool': browse_tool_score,
                'internal_confidence': internal_confidence
            },
            'flags': {
                'time_sensitive': is_time_sensitive,
                'explicit_web_search': explicit_web_search
            }
        })
        
        logger.info(f"Query classified: '{query}' -> Route: {route_info['route']}")
        return route_info
    
    def _calculate_pattern_score(self, query: str, patterns: List[str]) -> float:
        """
        Calculate pattern matching score for given patterns.
        
        Args:
            query: Query string to analyze
            patterns: List of regex patterns to match
            
        Returns:
            Pattern matching score (0-100)
        """
        total_matches = 0
        total_weight = 0
        
        for pattern in patterns:
            matches = len(re.findall(pattern, query, re.IGNORECASE))
            if matches > 0:
                # Weight based on pattern importance and frequency
                weight = min(matches * 10, 50)  # Cap at 50 per pattern
                total_matches += matches
                total_weight += weight
        
        # Normalize score to 0-100 range
        max_possible_score = len(patterns) * 50
        if max_possible_score > 0:
            score = min((total_weight / max_possible_score) * 100, 100)
        else:
            score = 0
            
        return score
    
    def _assess_internal_confidence(self, query: str) -> float:
        """
        Assess confidence in answering query from internal knowledge.
        
        Args:
            query: Query string to analyze
            
        Returns:
            Confidence score (0-100)
        """
        high_confidence_matches = sum(1 for topic in self.high_confidence_topics if topic in query)
        low_confidence_matches = sum(1 for topic in self.low_confidence_topics if topic in query)
        
        # Base confidence calculation (more generous for technical topics)
        if high_confidence_matches > 0:
            base_confidence = min(high_confidence_matches * 30 + 40, 95)
        else:
            base_confidence = 50  # Neutral confidence
        
        # Reduce confidence for low-confidence topics
        if low_confidence_matches > 0:
            confidence_reduction = min(low_confidence_matches * 20, 60)
            base_confidence = max(base_confidence - confidence_reduction, 10)
        
        return base_confidence
    
    def _is_time_sensitive(self, query: str) -> bool:
        """
        Determine if query requires time-sensitive information.
        
        Args:
            query: Query string to analyze
            
        Returns:
            True if query is time-sensitive
        """
        time_indicators = [
            'today', 'now', 'current', 'latest', 'recent', 'this week',
            'this month', 'this year', 'breaking', 'live', 'real-time',
            'up-to-date', 'just happened', 'happening now'
        ]
        
        return any(indicator in query for indicator in time_indicators)
    
    def _make_routing_decision(self, current_info_score: float, code_help_score: float,
                             system_ops_score: float, simple_command_score: float, internal_confidence: float,
                             is_time_sensitive: bool, explicit_web_search: bool, browse_tool_score: float) -> Dict[str, Any]:
        """
        Make final routing decision based on all factors.
        
        Args:
            current_info_score: Score for current information patterns
            code_help_score: Score for code help patterns
            system_ops_score: Score for system operations patterns
            simple_command_score: Score for simple command patterns
            internal_confidence: Internal knowledge confidence
            is_time_sensitive: Whether query is time-sensitive
            explicit_web_search: Whether user explicitly requested web search
            
        Returns:
            Dictionary with routing decision and metadata
        """
        # Priority 1: Browse tool indicators (even without explicit "use tool" phrase)
        if browse_tool_score > 30:
            return {
                'route': 'tool_selection',
                'reason': 'browse_tool_indicators',
                'confidence': 'high',
                'metadata': {
                    'suggested_tool': 'browse_web',
                    'browse_score': browse_tool_score
                }
            }
        
        # Priority 2: Explicit web search requests
        if explicit_web_search:
            return {
                'route': 'web_search',
                'reason': 'explicit_web_search_request',
                'confidence': 'high'
            }
        
        # Priority 2: Simple command operations (highest priority for basic file operations)
        if simple_command_score > 0.5:
            return {
                'route': 'simple_command',
                'reason': 'simple_file_or_command_operation',
                'confidence': 'high'
            }
        
        # Priority 3: Time-sensitive queries
        if is_time_sensitive or current_info_score > 50:
            return {
                'route': 'web_search',
                'reason': 'time_sensitive_or_current_info',
                'confidence': 'high'
            }
        
        # Priority 4: High-confidence technical queries (adjusted thresholds)
        if (code_help_score > 10 or system_ops_score > 8) and internal_confidence >= 50:
            return {
                'route': 'direct_llm',
                'reason': 'high_confidence_technical',
                'confidence': 'high'
            }
        
        # Priority 5: Moderate confidence queries with enhancement (adjusted threshold)
        if internal_confidence > 40 or code_help_score > 5 or system_ops_score > 5:
            return {
                'route': 'enhanced_llm',
                'reason': 'moderate_confidence',
                'confidence': 'medium'
            }
        
        # Default: Tool selection fallback
        return {
            'route': 'tool_selection',
            'reason': 'low_confidence_or_ambiguous',
            'confidence': 'low'
        }
    
    def get_enhanced_prompt(self, original_message: str, route_info: Dict[str, Any]) -> str:
        """
        Generate route-specific enhanced prompts for LLM processing.
        
        Args:
            original_message: Original user query
            route_info: Routing information from classify_query
            
        Returns:
            Enhanced system prompt for the route
        """
        route = route_info.get('route', 'tool_selection')
        
        prompt_templates = {
            'simple_command': """This query is asking for a simple file or command operation that should be handled with basic commands.
Provide the exact command(s) needed, such as 'ls', 'cat', 'find', 'cp', 'mv', etc.
Do NOT create scripts or complex solutions - use the most basic, direct approach.
If multiple commands are needed, chain them together simply (e.g., ls -la /path/to/directory).

For file listing: use 'ls' with appropriate flags
For viewing file contents: use 'cat' or 'head'  
For copying files: use 'cp'
For moving files: use 'mv'
For finding files: use 'find' or 'locate'

User query: {query}""",
            
            'direct_llm': """The user's query appears to be about technical topics you have strong knowledge of.
Use your internal knowledge to provide a comprehensive answer.
Do NOT suggest using external tools unless absolutely necessary.
Focus on giving direct, actionable advice based on your training.

User query: {query}""",
            
            'web_search': """This query requires current, real-time, or very recent information that you likely don't have.
Use web search tools to find up-to-date information.
Focus on reliable, authoritative sources.

User query: {query}""",
            
            'enhanced_llm': """You have moderate confidence in answering this query from your training data.
Provide the best answer you can from your knowledge.
If you're unsure about current information, mention that your knowledge has a cutoff date.
Only suggest external tools if the query clearly requires real-time or very recent information.

User query: {query}""",
            
            'tool_selection': """Analyze this query carefully to determine the best approach.
Consider whether you can answer from your training data or if external tools are needed.
If using tools, choose the most appropriate ones for the task.

User query: {query}"""
        }
        
        template = prompt_templates.get(route, prompt_templates['tool_selection'])
        return template.format(query=original_message)


def demo_routing():
    """Interactive demo for testing query routing."""
    router = QueryRouter()
    
    print("Smart Query Router Demo")
    print("=" * 50)
    print("Enter queries to see routing decisions (type 'quit' to exit)")
    
    while True:
        query = input("\nQuery: ").strip()
        if query.lower() in ['quit', 'exit', 'q']:
            break
            
        if not query:
            continue
            
        route_info = router.classify_query(query)
        
        print(f"\nRouting Decision:")
        print(f"  Route: {route_info['route']}")
        print(f"  Reason: {route_info['reason']}")
        print(f"  Confidence: {route_info['confidence']}")
        print(f"  Scores: {route_info['scores']}")
        print(f"  Flags: {route_info['flags']}")


if __name__ == "__main__":
    demo_routing()