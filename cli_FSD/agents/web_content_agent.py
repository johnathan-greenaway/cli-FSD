"""Web Content Agent for efficient web browsing and parsing.

This module provides a client to interact with the web content API
and integrate the results with the small context agent.
"""

import requests
import json
import logging
import os
from typing import Dict, Any, Optional, List, Union
from urllib.parse import urlparse
import re

# Configure logging
logging.basicConfig(level=logging.INFO,
                   format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class WebContentAgent:
    """Agent for efficient web content processing."""
    
    def __init__(self, api_base_url: str = "http://localhost:5000"):
        """Initialize the web content agent.
        
        Args:
            api_base_url: Base URL of the web content API
        """
        self.api_base_url = api_base_url
        self.endpoint = f"{api_base_url}/fetch_web_content"
        self.session = requests.Session()
        self.file_operations = {
            'read': self._read_file,
            'write': self._write_file,
            'append': self._append_file,
            'delete': self._delete_file
        }
        self.content_cache = {}
        self.last_operation = None
        self.last_url = None
    
    def _extract_story_number(self, query: str) -> Optional[int]:
        """Extract a story number from a query.
        
        Args:
            query: The query to extract from
            
        Returns:
            Story number if found, None otherwise
        """
        # Look for patterns like "story 5", "story #5", "story5", etc.
        patterns = [
            r'story\s*#?\s*(\d+)',
            r'#?\s*(\d+)\s*on',
            r'number\s*#?\s*(\d+)',
            r'item\s*#?\s*(\d+)'
        ]
        
        for pattern in patterns:
            match = re.search(pattern, query.lower())
            if match:
                try:
                    return int(match.group(1))
                except ValueError:
                    continue
        
        return None
    
    def _get_story_url(self, story_number: int, base_url: str) -> str:
        """Get the URL for a specific story number.
        
        Args:
            story_number: The story number to get
            base_url: The base URL of the site
            
        Returns:
            URL for the specific story
        """
        if 'news.ycombinator.com' in base_url:
            return f"https://news.ycombinator.com/item?id={story_number}"
        elif 'reddit.com' in base_url:
            return f"https://reddit.com/comments/{story_number}"
        return base_url
    
    def _read_file(self, filepath: str) -> Dict[str, Any]:
        """Read a file's contents.
        
        Args:
            filepath: Path to the file to read
            
        Returns:
            Dictionary containing file contents and metadata
        """
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()
            return {
                'success': True,
                'content': content,
                'filepath': filepath,
                'operation': 'read'
            }
        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'filepath': filepath,
                'operation': 'read'
            }
    
    def _write_file(self, filepath: str, content: str) -> Dict[str, Any]:
        """Write content to a file.
        
        Args:
            filepath: Path to write to
            content: Content to write
            
        Returns:
            Dictionary containing operation result
        """
        try:
            os.makedirs(os.path.dirname(filepath), exist_ok=True)
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(content)
            return {
                'success': True,
                'filepath': filepath,
                'operation': 'write'
            }
        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'filepath': filepath,
                'operation': 'write'
            }
    
    def _append_file(self, filepath: str, content: str) -> Dict[str, Any]:
        """Append content to a file.
        
        Args:
            filepath: Path to append to
            content: Content to append
            
        Returns:
            Dictionary containing operation result
        """
        try:
            with open(filepath, 'a', encoding='utf-8') as f:
                f.write(content)
            return {
                'success': True,
                'filepath': filepath,
                'operation': 'append'
            }
        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'filepath': filepath,
                'operation': 'append'
            }
    
    def _delete_file(self, filepath: str) -> Dict[str, Any]:
        """Delete a file.
        
        Args:
            filepath: Path to delete
            
        Returns:
            Dictionary containing operation result
        """
        try:
            os.remove(filepath)
            return {
                'success': True,
                'filepath': filepath,
                'operation': 'delete'
            }
        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'filepath': filepath,
                'operation': 'delete'
            }
    
    def handle_file_operation(self, operation: str, filepath: str, content: Optional[str] = None) -> Dict[str, Any]:
        """Handle file operations.
        
        Args:
            operation: Operation to perform ('read', 'write', 'append', 'delete')
            filepath: Path to operate on
            content: Content for write/append operations
            
        Returns:
            Dictionary containing operation result
        """
        if operation not in self.file_operations:
            return {
                'success': False,
                'error': f'Invalid operation: {operation}',
                'filepath': filepath,
                'operation': operation
            }
        
        if operation in ['write', 'append'] and content is None:
            return {
                'success': False,
                'error': f'Content required for {operation} operation',
                'filepath': filepath,
                'operation': operation
            }
        
        return self.file_operations[operation](filepath, content) if content else self.file_operations[operation](filepath)
    
    def parse_command(self, command: str) -> Dict[str, Any]:
        """Parse a command string into an operation.
        
        Args:
            command: Command string to parse
            
        Returns:
            Dictionary containing parsed command details
        """
        # Basic command parsing
        parts = command.strip().split()
        if not parts:
            return {'error': 'Empty command'}
        
        operation = parts[0].lower()
        
        # Handle file operations
        if operation in self.file_operations:
            if len(parts) < 2:
                return {'error': f'Missing filepath for {operation} operation'}
            
            filepath = parts[1]
            content = ' '.join(parts[2:]) if len(parts) > 2 else None
            
            return {
                'type': 'file_operation',
                'operation': operation,
                'filepath': filepath,
                'content': content
            }
        
        # Handle web content operations
        if operation in ['fetch', 'browse', 'search']:
            if len(parts) < 2:
                return {'error': f'Missing URL/query for {operation} operation'}
            
            url_or_query = parts[1]
            mode = parts[2] if len(parts) > 2 else 'basic'
            
            return {
                'type': 'web_operation',
                'operation': operation,
                'url_or_query': url_or_query,
                'mode': mode
            }
        
        return {'error': f'Unknown operation: {operation}'}
    
    def execute_command(self, command: str) -> Dict[str, Any]:
        """Execute a parsed command.
        
        Args:
            command: Command string to execute
            
        Returns:
            Dictionary containing execution result
        """
        parsed = self.parse_command(command)
        if 'error' in parsed:
            return parsed
        
        # Check for story number in the command
        story_number = self._extract_story_number(command)
        if story_number and parsed['type'] == 'web_operation':
            # If we have a story number and the last URL, use it to construct the story URL
            if self.last_url:
                parsed['url_or_query'] = self._get_story_url(story_number, self.last_url)
        
        if parsed['type'] == 'file_operation':
            return self.handle_file_operation(
                parsed['operation'],
                parsed['filepath'],
                parsed.get('content')
            )
        
        if parsed['type'] == 'web_operation':
            # Store the operation and URL for context
            self.last_operation = parsed['operation']
            self.last_url = parsed['url_or_query']
            
            if parsed['operation'] == 'fetch':
                response = self.fetch_content(parsed['url_or_query'], parsed['mode'])
            elif parsed['operation'] == 'browse':
                response = self.browse(parsed['url_or_query'], parsed['mode'])
            elif parsed['operation'] == 'search':
                response = self.search_for_information([parsed['url_or_query']], parsed['mode'])
            
            # Cache the response
            if response and not response.get('error'):
                self.content_cache[parsed['url_or_query']] = response
            
            return response
        
        return {'error': 'Failed to execute command'}
    
    def fetch_content(self, url: str, mode: str = "basic", use_cache: bool = True) -> Dict[str, Any]:
        """Fetch and process web content.
        
        Args:
            url: URL to fetch
            mode: Processing mode ('basic', 'detailed', or 'summary')
            use_cache: Whether to use cached content if available
            
        Returns:
            Processed content as dictionary
        """
        # Validate URL
        try:
            parsed = urlparse(url)
            if not parsed.scheme or not parsed.netloc:
                error_msg = f"Invalid URL format: {url}"
                logger.error(error_msg)
                return {"error": error_msg}
        except Exception as e:
            error_msg = f"Error parsing URL {url}: {e}"
            logger.error(error_msg)
            return {"error": error_msg}
        
        # Validate mode
        if mode not in ["basic", "detailed", "summary"]:
            error_msg = f"Invalid mode: {mode}. Must be one of: basic, detailed, summary"
            logger.error(error_msg)
            return {"error": error_msg}
        
        # Try using direct fetcher first if available
        try:
            from ..web_fetcher import fetcher
            logger.info(f"Using direct web fetcher for {url}")
            return fetcher.fetch_and_process(url, mode, use_cache)
        except ImportError:
            logger.warning("WebContentFetcher module not available, falling back to API")
        except Exception as e:
            logger.warning(f"Direct fetching failed: {e}, falling back to API")
        
        # Fall back to API request
        try:
            logger.info(f"Making API request to {self.endpoint}")
            payload = {
                "url": url,
                "mode": mode,
                "use_cache": use_cache
            }
            
            response = self.session.post(self.endpoint, json=payload, timeout=30)
            response.raise_for_status()
            
            return response.json()
            
        except requests.exceptions.RequestException as e:
            error_msg = f"API request error: {e}"
            logger.error(error_msg)
            return {"error": error_msg}
        except json.JSONDecodeError as e:
            error_msg = f"Error parsing API response: {e}"
            logger.error(error_msg)
            return {"error": error_msg}
    
    def format_for_context(self, content: Dict[str, Any], priority: str = "important") -> Dict[str, Any]:
        """Format web content for the small context protocol.
        
        Args:
            content: Web content dictionary
            priority: Message priority ('critical', 'important', or 'supplementary')
            
        Returns:
            Formatted message for the small context agent
        """
        if "error" in content:
            return {
                "timestamp": content.get("timestamp", 0),
                "priority": "important",
                "token_count": len(content["error"]) // 4,  # Rough estimate
                "content": f"Error fetching {content.get('url', 'URL')}: {content['error']}",
                "entities": [content.get("url", "")],
                "relationships": []
            }
        
        # Check if it's an array (special case for HN and other sites)
        if isinstance(content, list):
            # Handle list of items (e.g., HN stories)
            main_content = "Content summary:\n\n"
            entities = []
            relationships = []
            
            for i, item in enumerate(content[:15]):  # Limit to first 15 items for reasonable context
                if isinstance(item, dict):
                    # Handle story format
                    if "title" in item:
                        main_content += f"{i+1}. {item.get('title', 'No title')}"
                        if "url" in item and item["url"]:
                            main_content += f" - {item['url']}\n"
                            entities.append(item["url"])
                        else:
                            main_content += "\n"
                            
                        # Add metadata if available
                        if "metadata" in item and isinstance(item["metadata"], dict):
                            meta_string = ", ".join([f"{k}: {v}" for k, v in item["metadata"].items()])
                            if meta_string:
                                main_content += f"   {meta_string}\n"
                        main_content += "\n"
            
            # Rough token count estimate
            token_count = len(main_content) // 4
            
            return {
                "timestamp": content[0].get("timestamp", 0) if content and isinstance(content[0], dict) else 0,
                "priority": priority,
                "token_count": token_count,
                "content": main_content,
                "entities": entities,
                "relationships": relationships
            }
        
        # Create formatted message based on content type
        if content.get("content_type") == "webpage":
            # Basic info about the page
            main_content = f"URL: {content.get('url', 'Unknown URL')}\nTitle: {content.get('title', 'No title')}\n\n"
            
            # Add structured content based on what's available
            if "text_content" in content and content["text_content"]:
                main_content += content["text_content"][:1000]  # Limit to first 1000 chars
                if len(content["text_content"]) > 1000:
                    main_content += "...(truncated)"
            elif "structured_content" in content:
                for item in content["structured_content"][:10]:  # Limit to first 10 items
                    if item.get("type") == "heading":
                        main_content += f"\n## {item.get('text', '')}\n"
                    elif item.get("type") == "paragraph":
                        main_content += f"{item.get('text', '')}\n\n"
                    elif item.get("type") == "list":
                        main_content += "\n"
                        for list_item in item.get("items", []):
                            main_content += f"- {list_item}\n"
                        main_content += "\n"
                    elif item.get("type") == "story":
                        # Handle special story format (e.g., from HN)
                        main_content += f"\n## {item.get('title', 'No title')}\n"
                        if item.get("url"):
                            main_content += f"URL: {item['url']}\n"
                        if "metadata" in item and isinstance(item["metadata"], dict):
                            for key, value in item["metadata"].items():
                                main_content += f"{key}: {value}\n"
                        main_content += "\n"
            
            # Add links if available
            entities = [content.get("url", "")]
            relationships = []
            
            if "links" in content and isinstance(content["links"], list):
                main_content += "\nLinks:\n"
                for i, link in enumerate(content["links"][:5]):  # Limit to first 5 links
                    if isinstance(link, dict) and "url" in link:
                        link_text = link.get("text", link["url"])
                        main_content += f"- {link_text}: {link['url']}\n"
                        entities.append(link["url"])
                        relationships.append({
                            "source": content.get("url", ""),
                            "target": link["url"],
                            "type": "links_to"
                        })
                    elif isinstance(link, str):
                        main_content += f"- {link}\n"
                        entities.append(link)
                        relationships.append({
                            "source": content.get("url", ""),
                            "target": link,
                            "type": "links_to"
                        })
                    
                    if i >= 4:  # Only show 5 links
                        break
            
            # Rough token count estimate
            token_count = len(main_content) // 4
            
            return {
                "timestamp": content.get("timestamp", 0),
                "priority": priority,
                "token_count": token_count,
                "content": main_content,
                "entities": entities,
                "relationships": relationships
            }
        
        # Default format for unknown content types
        return {
            "timestamp": content.get("timestamp", 0),
            "priority": priority,
            "token_count": len(str(content)) // 4,  # Rough estimate
            "content": json.dumps(content, indent=2),
            "entities": [content.get("url", "")],
            "relationships": []
        }
    
    def browse(self, url: str, mode: str = "basic") -> Dict[str, Any]:
        """Browse a webpage and format it for the context agent.
        
        Args:
            url: URL to browse
            mode: Processing mode ('basic', 'detailed', or 'summary')
            
        Returns:
            Formatted message for the small context agent
        """
        content = self.fetch_content(url, mode)
        return self.format_for_context(content)
    
    def search_for_information(self, urls: List[str], query: str) -> Dict[str, Any]:
        """Search multiple pages for specific information.
        
        Args:
            urls: List of URLs to search
            query: Information to search for
            
        Returns:
            Combined results formatted for the context agent
        """
        results = []
        entities = []
        relationships = []
        
        for url in urls:
            content = self.fetch_content(url, "basic")
            if "error" in content:
                results.append(f"Error from {url}: {content['error']}")
                continue
                
            # Simple matching for the query
            if "text_content" in content:
                text = content["text_content"]
                if query.lower() in text.lower():
                    # Find the paragraph containing the query
                    paragraphs = text.split('\n\n')
                    matching_paragraphs = []
                    
                    for p in paragraphs:
                        if query.lower() in p.lower():
                            matching_paragraphs.append(p)
                    
                    if matching_paragraphs:
                        results.append(f"Found in {url}: {matching_paragraphs[0]}")
                        entities.append(url)
                        
                        # Add relationship between query and URL
                        relationships.append({
                            "source": query,
                            "target": url,
                            "type": "found_in"
                        })
        
        if not results:
            results = ["No matching information found in the provided URLs."]
        
        combined_content = f"Search for '{query}':\n\n" + "\n\n".join(results)
        
        return {
            "timestamp": 0,  # Will be set by context agent
            "priority": "important",
            "token_count": len(combined_content) // 4,
            "content": combined_content,
            "entities": entities,
            "relationships": relationships
        }


# Example usage
if __name__ == "__main__":
    agent = WebContentAgent()
    result = agent.browse("https://example.com", "basic")
    print(json.dumps(result, indent=2))