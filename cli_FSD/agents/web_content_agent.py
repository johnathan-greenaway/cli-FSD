"""Web Content Agent for efficient web browsing and parsing.

This module provides a client to interact with the web content API
and integrate the results with the small context agent.
"""

import requests
import json
import logging
from typing import Dict, Any, Optional, List
from urllib.parse import urlparse

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