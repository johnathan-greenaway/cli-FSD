"""LLM-based Smart Query Router for cli-FSD.

This module uses LLM intelligence to classify and route queries instead of
relying solely on pattern matching. It provides more accurate and nuanced
query understanding.
"""

import logging
from typing import Dict, Any, Optional
import json

# Configure logging
logger = logging.getLogger(__name__)


class LLMQueryRouter:
    """Intelligent LLM-based query classification and routing engine."""
    
    def __init__(self, chat_model=None, model_type='openai'):
        """Initialize the LLM query router.
        
        Args:
            chat_model: The initialized chat model to use
            model_type: Type of model ('openai', 'claude', 'ollama', 'groq')
        """
        self.chat_model = chat_model
        self.model_type = model_type
        
        # Classification prompt that instructs the LLM how to classify queries
        self.classification_prompt = """You are a query classification system. Analyze the user's query and classify it into one of these categories:

1. **web_browse** - User wants to browse websites, check online marketplaces (craigslist, ebay, amazon), view web pages, or access any specific website
2. **web_search** - User needs current information, news, weather, prices, or wants to search for information online
3. **file_operation** - User wants to work with files: list, read, create, edit, move, copy, delete files or directories
4. **system_command** - User wants to run system commands, bash commands, or perform system operations
5. **code_help** - User needs help with programming, coding, debugging, or technical explanations
6. **general_chat** - User has a general question that can be answered from training data

Respond with ONLY a JSON object in this exact format:
{{
  "category": "one_of_the_categories_above",
  "confidence": "high/medium/low",
  "reasoning": "brief explanation of why this category was chosen",
  "requires_tool": true/false,
  "suggested_tool": "browse_web/file_tool/command_tool/none"
}}

Examples:
- "find cool items on craigslist" -> category: "web_browse", requires_tool: true, suggested_tool: "browse_web"
- "what's the weather today" -> category: "web_search", requires_tool: true, suggested_tool: "browse_web"
- "list files in current directory" -> category: "file_operation", requires_tool: true, suggested_tool: "command_tool"
- "explain python decorators" -> category: "code_help", requires_tool: false, suggested_tool: "none"

User query: {query}"""

    def classify_query(self, query: str) -> Dict[str, Any]:
        """
        Use LLM to classify query and determine routing.
        
        Args:
            query: User input query string
            
        Returns:
            Dictionary containing routing information
        """
        try:
            # Format the classification prompt
            prompt = self.classification_prompt.format(query=query)
            
            # Get LLM classification
            if self.chat_model and self.model_type:
                # Import here to avoid circular imports
                from .chat_models import chat_with_model
                
                # Create a minimal config object for chat_with_model
                class MinimalConfig:
                    def __init__(self):
                        self.session_model = self.model_type
                        self.testing = True  # Disable loading animation
                
                config = MinimalConfig()
                config.session_model = self.model_type
                
                # Call chat_with_model with appropriate parameters
                response = chat_with_model(
                    message=prompt,
                    config=config,
                    chat_models={'model': self.chat_model},
                    system_prompt="You are a precise query classification system. Respond only with the requested JSON format."
                )
                
                # Parse the JSON response
                classification = self._parse_llm_response(response)
                
                if classification:
                    # Convert LLM classification to routing decision
                    route_info = self._convert_to_route(classification, query)
                    logger.info(f"LLM classified: '{query}' -> Category: {classification.get('category')}, Route: {route_info['route']}")
                    return route_info
            
            # Fallback to simple routing if LLM fails
            logger.warning("LLM classification failed, using fallback routing")
            return self._fallback_routing(query)
            
        except Exception as e:
            logger.error(f"Error in LLM query classification: {e}")
            return self._fallback_routing(query)
    
    def _parse_llm_response(self, response: str) -> Optional[Dict[str, Any]]:
        """Parse JSON response from LLM."""
        try:
            # Extract JSON from response (in case LLM adds extra text)
            json_start = response.find('{')
            json_end = response.rfind('}') + 1
            
            if json_start >= 0 and json_end > json_start:
                json_str = response[json_start:json_end]
                return json.loads(json_str)
            
            return None
        except json.JSONDecodeError:
            logger.error(f"Failed to parse LLM JSON response: {response}")
            return None
    
    def _convert_to_route(self, classification: Dict[str, Any], query: str) -> Dict[str, Any]:
        """Convert LLM classification to routing decision."""
        category = classification.get('category', 'general_chat')
        confidence = classification.get('confidence', 'medium')
        requires_tool = classification.get('requires_tool', False)
        suggested_tool = classification.get('suggested_tool', 'none')
        
        # Map categories to routes
        route_mapping = {
            'web_browse': 'tool_selection',
            'web_search': 'web_search',
            'file_operation': 'tool_selection',
            'system_command': 'tool_selection',
            'code_help': 'direct_llm' if confidence == 'high' else 'enhanced_llm',
            'general_chat': 'enhanced_llm'
        }
        
        route = route_mapping.get(category, 'tool_selection')
        
        # Build route info
        route_info = {
            'route': route,
            'reason': f'llm_classified_as_{category}',
            'confidence': confidence,
            'metadata': {
                'llm_category': category,
                'llm_reasoning': classification.get('reasoning', ''),
                'requires_tool': requires_tool
            }
        }
        
        # Add suggested tool for tool_selection routes
        if route == 'tool_selection' and suggested_tool != 'none':
            route_info['metadata']['suggested_tool'] = suggested_tool
            
        return route_info
    
    def _fallback_routing(self, query: str) -> Dict[str, Any]:
        """Simple fallback routing when LLM is unavailable."""
        query_lower = query.lower()
        
        # Simple keyword-based routing
        if any(word in query_lower for word in ['browse', 'website', 'craigslist', 'ebay', 'amazon']):
            return {
                'route': 'tool_selection',
                'reason': 'fallback_web_browse_keywords',
                'confidence': 'medium',
                'metadata': {'suggested_tool': 'browse_web'}
            }
        elif any(word in query_lower for word in ['weather', 'news', 'current', 'today', 'search']):
            return {
                'route': 'web_search',
                'reason': 'fallback_search_keywords',
                'confidence': 'medium'
            }
        elif any(word in query_lower for word in ['file', 'directory', 'ls', 'list', 'cat', 'read']):
            return {
                'route': 'tool_selection',
                'reason': 'fallback_file_keywords',
                'confidence': 'medium',
                'metadata': {'suggested_tool': 'file_tool'}
            }
        else:
            return {
                'route': 'enhanced_llm',
                'reason': 'fallback_default',
                'confidence': 'low'
            }
    
    def get_enhanced_prompt(self, original_message: str, route_info: Dict[str, Any]) -> str:
        """Generate route-specific enhanced prompts for LLM processing."""
        route = route_info.get('route', 'tool_selection')
        metadata = route_info.get('metadata', {})
        
        prompt_templates = {
            'tool_selection': """Based on analysis, this query requires using tools.
{tool_hint}
Analyze the query and select the appropriate tool(s) to complete the task.

User query: {query}""",
            
            'direct_llm': """This is a technical query you can answer directly from your knowledge.
Provide a comprehensive, accurate answer without suggesting external tools.

User query: {query}""",
            
            'web_search': """This query requires current or real-time information.
Use web search capabilities to find up-to-date information.

User query: {query}""",
            
            'enhanced_llm': """Answer this query using your knowledge.
If you're uncertain about current information, mention your knowledge cutoff.

User query: {query}"""
        }
        
        template = prompt_templates.get(route, prompt_templates['tool_selection'])
        
        # Add tool hint if available
        tool_hint = ""
        if metadata.get('suggested_tool'):
            tool_hints = {
                'browse_web': "The browse tool would be appropriate for accessing websites or online content.",
                'file_tool': "File operations tools would be appropriate for this task.",
                'command_tool': "System command tools would be appropriate for this task."
            }
            tool_hint = tool_hints.get(metadata['suggested_tool'], "")
        
        return template.format(query=original_message, tool_hint=tool_hint)