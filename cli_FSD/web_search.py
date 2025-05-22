"""Web Search Handler for cli-FSD.

This module provides direct web search capabilities for queries routed to
web search without requiring LLM tool selection. It handles current information
queries that require real-time or recent data.
"""

import requests
import json
import logging
from typing import Dict, Any, Optional, List
from urllib.parse import quote_plus, urljoin
from bs4 import BeautifulSoup

# Configure logging
logger = logging.getLogger(__name__)


class WebSearchHandler:
    """Handler for direct web search operations."""
    
    def __init__(self):
        """Initialize the web search handler."""
        self.duckduckgo_api = "https://api.duckduckgo.com/"
        self.wikipedia_api = "https://en.wikipedia.org/api/rest_v1/page/summary/"
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'cli-FSD/2.1 (https://github.com/wazacraft/cli-FSD)'
        })
    
    def search_web(self, query: str) -> Dict[str, Any]:
        """
        Perform web search for the given query.
        
        Args:
            query: Search query string
            
        Returns:
            Dictionary containing search results and metadata
        """
        logger.info(f"Performing web search for: {query}")
        
        # Try DuckDuckGo instant answer first
        ddg_result = self._search_duckduckgo_instant(query)
        if ddg_result['success'] and ddg_result['content']:
            return ddg_result
        
        # Try Wikipedia for factual queries
        wiki_result = self._search_wikipedia(query)
        if wiki_result['success'] and wiki_result['content']:
            return wiki_result
        
        # If automated search fails, provide search guidance
        return self._provide_search_guidance(query)
    
    def _search_duckduckgo_instant(self, query: str) -> Dict[str, Any]:
        """
        Search using DuckDuckGo Instant Answer API.
        
        Args:
            query: Search query
            
        Returns:
            Dictionary with search results
        """
        try:
            params = {
                'q': query,
                'format': 'json',
                'no_html': '1',
                'skip_disambig': '1'
            }
            
            response = self.session.get(self.duckduckgo_api, params=params, timeout=10)
            response.raise_for_status()
            
            data = response.json()
            
            # Check for instant answer
            if data.get('Answer'):
                return {
                    'success': True,
                    'source': 'DuckDuckGo Instant Answer',
                    'content': data['Answer'],
                    'url': data.get('AnswerURL', ''),
                    'type': 'instant_answer'
                }
            
            # Check for abstract (Wikipedia-style)
            if data.get('Abstract'):
                return {
                    'success': True,
                    'source': data.get('AbstractSource', 'DuckDuckGo'),
                    'content': data['Abstract'],
                    'url': data.get('AbstractURL', ''),
                    'type': 'abstract'
                }
            
            # Check for definition
            if data.get('Definition'):
                return {
                    'success': True,
                    'source': data.get('DefinitionSource', 'DuckDuckGo'),
                    'content': data['Definition'],
                    'url': data.get('DefinitionURL', ''),
                    'type': 'definition'
                }
            
            # Check for related topics
            if data.get('RelatedTopics'):
                topics = []
                for topic in data['RelatedTopics'][:3]:  # Limit to first 3
                    if isinstance(topic, dict) and topic.get('Text'):
                        topics.append(topic['Text'])
                
                if topics:
                    return {
                        'success': True,
                        'source': 'DuckDuckGo Related Topics',
                        'content': '\n\n'.join(topics),
                        'url': '',
                        'type': 'related_topics'
                    }
            
            return {'success': False, 'content': '', 'error': 'No instant answer available'}
            
        except requests.RequestException as e:
            logger.error(f"DuckDuckGo API error: {e}")
            return {'success': False, 'content': '', 'error': f'DuckDuckGo API error: {e}'}
        except json.JSONDecodeError as e:
            logger.error(f"DuckDuckGo JSON decode error: {e}")
            return {'success': False, 'content': '', 'error': f'JSON decode error: {e}'}
    
    def _search_wikipedia(self, query: str) -> Dict[str, Any]:
        """
        Search Wikipedia for factual information.
        
        Args:
            query: Search query
            
        Returns:
            Dictionary with Wikipedia results
        """
        try:
            # Clean query for Wikipedia
            wiki_query = query.replace('what is ', '').replace('who is ', '').strip()
            encoded_query = quote_plus(wiki_query)
            
            url = urljoin(self.wikipedia_api, encoded_query)
            response = self.session.get(url, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                
                # Extract summary information
                title = data.get('title', '')
                extract = data.get('extract', '')
                page_url = data.get('content_urls', {}).get('desktop', {}).get('page', '')
                
                if extract and len(extract.strip()) > 50:  # Meaningful content
                    return {
                        'success': True,
                        'source': 'Wikipedia',
                        'content': f"{title}\n\n{extract}",
                        'url': page_url,
                        'type': 'wikipedia_summary'
                    }
            
            return {'success': False, 'content': '', 'error': 'No Wikipedia article found'}
            
        except requests.RequestException as e:
            logger.error(f"Wikipedia API error: {e}")
            return {'success': False, 'content': '', 'error': f'Wikipedia API error: {e}'}
        except json.JSONDecodeError as e:
            logger.error(f"Wikipedia JSON decode error: {e}")
            return {'success': False, 'content': '', 'error': f'JSON decode error: {e}'}
    
    def _provide_search_guidance(self, query: str) -> Dict[str, Any]:
        """
        Provide search guidance when automated search fails.
        
        Args:
            query: Original search query
            
        Returns:
            Dictionary with search guidance
        """
        guidance = f"""I wasn't able to find specific information for "{query}" through automated search.

Here are some suggestions for finding this information:

1. **Web Search**: Try searching for "{query}" on:
   - Google: https://www.google.com/search?q={quote_plus(query)}
   - DuckDuckGo: https://duckduckgo.com/?q={quote_plus(query)}
   - Bing: https://www.bing.com/search?q={quote_plus(query)}

2. **Specific Sources**: Depending on your query, try:
   - Wikipedia: https://en.wikipedia.org/wiki/{quote_plus(query.replace(' ', '_'))}
   - News sources for current events
   - Official websites for product/service information
   - Academic sources for research topics

3. **Refine Your Query**: Try:
   - Adding more specific terms
   - Using synonyms or alternative phrases
   - Breaking complex queries into simpler parts"""
        
        return {
            'success': True,
            'source': 'cli-FSD Search Guidance',
            'content': guidance,
            'url': '',
            'type': 'search_guidance'
        }
    
    def get_search_suggestions(self, query: str) -> List[str]:
        """
        Get search suggestions for improving query results.
        
        Args:
            query: Original query
            
        Returns:
            List of suggested search terms
        """
        suggestions = []
        
        # Add quotes for exact phrases
        if ' ' in query and '"' not in query:
            suggestions.append(f'"{query}"')
        
        # Add site-specific searches
        if any(word in query.lower() for word in ['definition', 'meaning', 'what is']):
            suggestions.append(f"site:wikipedia.org {query}")
        
        if any(word in query.lower() for word in ['news', 'current', 'latest']):
            suggestions.append(f"{query} news")
            suggestions.append(f"{query} 2024")
        
        if any(word in query.lower() for word in ['how to', 'tutorial', 'guide']):
            suggestions.append(f"{query} tutorial")
            suggestions.append(f"{query} step by step")
        
        return suggestions[:5]  # Limit to 5 suggestions


def format_search_response(search_result: Dict[str, Any]) -> str:
    """
    Format search results for display to user.
    
    Args:
        search_result: Result from WebSearchHandler.search_web()
        
    Returns:
        Formatted string for display
    """
    if not search_result.get('success'):
        return f"Search failed: {search_result.get('error', 'Unknown error')}"
    
    content = search_result.get('content', '')
    source = search_result.get('source', 'Unknown')
    url = search_result.get('url', '')
    result_type = search_result.get('type', 'search_result')
    
    formatted = f"📊 **{source}**\n\n{content}"
    
    if url:
        formatted += f"\n\n🔗 **Source**: {url}"
    
    # Add type-specific formatting
    if result_type == 'instant_answer':
        formatted = f"💡 **Quick Answer**\n\n{content}"
        if url:
            formatted += f"\n\n🔗 More info: {url}"
    elif result_type == 'wikipedia_summary':
        formatted = f"📚 **Wikipedia Summary**\n\n{content}"
        if url:
            formatted += f"\n\n🔗 Full article: {url}"
    elif result_type == 'search_guidance':
        formatted = f"🔍 **Search Guidance**\n\n{content}"
    
    return formatted


# Demo function for testing
def demo_web_search():
    """Interactive demo for testing web search functionality."""
    handler = WebSearchHandler()
    
    print("Web Search Handler Demo")
    print("=" * 50)
    print("Enter search queries to test web search (type 'quit' to exit)")
    
    while True:
        query = input("\nSearch Query: ").strip()
        if query.lower() in ['quit', 'exit', 'q']:
            break
            
        if not query:
            continue
            
        print("\nSearching...")
        result = handler.search_web(query)
        formatted_result = format_search_response(result)
        print(f"\n{formatted_result}")


if __name__ == "__main__":
    demo_web_search()