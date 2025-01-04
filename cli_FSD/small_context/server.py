"""Small Context Protocol MCP Server Implementation."""

import json
import sys
import asyncio
import aiohttp
import os
import time
from bs4 import BeautifulSoup
from urllib.parse import urlparse
from typing import Dict, List, Any, Optional
from dataclasses import dataclass
from datetime import datetime

@dataclass
class Message:
    """Message container with metadata."""
    timestamp: float
    priority: str
    token_count: int
    content: str
    entities: List[str]
    relationships: List[Dict[str, str]]

class ContextState:
    """Manages context state and messages."""
    def __init__(self, max_tokens: int = 4096):
        self.max_tokens = max_tokens
        self.messages: List[Message] = []
        self.current_tokens = 0

    def add_message(self, message: Message) -> None:
        """Add a message with priority-based pruning."""
        if self.current_tokens + message.token_count > self.max_tokens:
            self._prune_context(message.token_count)
        
        self.messages.append(message)
        self.current_tokens += message.token_count
        self._sort_by_priority()

    def _prune_context(self, required_tokens: int) -> None:
        """Remove low priority messages to free up space."""
        priority_values = {"critical": 3, "important": 2, "supplementary": 1}
        
        # Sort by priority (highest to lowest) and timestamp (newest to oldest)
        self.messages.sort(
            key=lambda m: (priority_values[m.priority], -m.timestamp),
            reverse=True
        )
        
        while self.current_tokens + required_tokens > self.max_tokens:
            if not self.messages:
                break
            removed = self.messages.pop()
            self.current_tokens -= removed.token_count

    def _sort_by_priority(self) -> None:
        """Sort messages by priority and timestamp."""
        priority_values = {"critical": 3, "important": 2, "supplementary": 1}
        self.messages.sort(
            key=lambda m: (priority_values[m.priority], -m.timestamp),
            reverse=True
        )

    def clear(self) -> None:
        """Clear all messages."""
        self.messages = []
        self.current_tokens = 0

class SmallContextServer:
    """MCP Server implementation for Small Context Protocol."""
    
    def __init__(self):
        self.contexts: Dict[str, ContextState] = {}
        self.session: Optional[aiohttp.ClientSession] = None
        self.cache = ContentCache()
    
    async def start(self):
        """Start the server and initialize HTTP session."""
        self.session = aiohttp.ClientSession(headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate',
            'DNT': '1',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1'
        })
        await self._process_stdin()
    
    async def stop(self):
        """Stop the server and cleanup resources."""
        if self.session:
            await self.session.close()
    
    async def _process_stdin(self):
        """Process MCP protocol messages from stdin."""
        while True:
            try:
                line = await asyncio.get_event_loop().run_in_executor(None, sys.stdin.readline)
                if not line:
                    break
                    
                request = json.loads(line)
                response = await self._handle_request(request)
                
                print(json.dumps(response))
                sys.stdout.flush()
                
            except Exception as e:
                print(json.dumps({
                    "error": {
                        "code": "internal_error",
                        "message": str(e)
                    }
                }), flush=True)
    
    async def _handle_request(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """Handle incoming MCP requests."""
        method = request.get("method")
        
        if method == "list_tools":
            return self._list_tools()
        elif method == "call_tool":
            return await self._call_tool(request["params"])
        else:
            return {
                "error": {
                    "code": "method_not_found",
                    "message": f"Unknown method: {method}"
                }
            }
    
    def _list_tools(self) -> Dict[str, Any]:
        """List available tools and their schemas."""
        return {
            "tools": [
                {
                    "name": "create_context",
                    "description": "Create a new context window",
                    "input_schema": {
                        "type": "object",
                        "properties": {
                            "context_id": {
                                "type": "string",
                                "description": "Unique identifier for this context"
                            },
                            "max_tokens": {
                                "type": "number",
                                "description": "Maximum tokens for this context",
                                "default": 4096
                            }
                        },
                        "required": ["context_id"]
                    }
                },
                {
                    "name": "browse_web",
                    "description": "Browse a webpage and add its content to context",
                    "input_schema": {
                        "type": "object",
                        "properties": {
                            "url": {
                                "type": "string",
                                "description": "URL to browse"
                            },
                            "priority": {
                                "type": "string",
                                "enum": ["critical", "important", "supplementary"],
                                "default": "important"
                            },
                            "context_id": {
                                "type": "string",
                                "description": "Optional context ID to add content to"
                            }
                        },
                        "required": ["url"]
                    }
                },
                {
                    "name": "add_message",
                    "description": "Add a message to a context window",
                    "input_schema": {
                        "type": "object",
                        "properties": {
                            "context_id": {
                                "type": "string",
                                "description": "Context identifier"
                            },
                            "content": {
                                "type": "string",
                                "description": "Message content"
                            },
                            "priority": {
                                "type": "string",
                                "enum": ["critical", "important", "supplementary"],
                                "default": "important"
                            },
                            "entities": {
                                "type": "array",
                                "items": {"type": "string"},
                                "default": []
                            },
                            "relationships": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "type": {"type": "string"},
                                        "source": {"type": "string"},
                                        "target": {"type": "string"}
                                    }
                                },
                                "default": []
                            }
                        },
                        "required": ["context_id", "content"]
                    }
                },
                {
                    "name": "get_context",
                    "description": "Get current state of a context window",
                    "input_schema": {
                        "type": "object",
                        "properties": {
                            "context_id": {
                                "type": "string",
                                "description": "Context identifier"
                            }
                        },
                        "required": ["context_id"]
                    }
                },
                {
                    "name": "clear_context",
                    "description": "Clear a context window",
                    "input_schema": {
                        "type": "object",
                        "properties": {
                            "context_id": {
                                "type": "string",
                                "description": "Context identifier"
                            }
                        },
                        "required": ["context_id"]
                    }
                },
                {
                    "name": "get_recent_content",
                    "description": "Get list of recently browsed content",
                    "input_schema": {
                        "type": "object",
                        "properties": {
                            "limit": {
                                "type": "number",
                                "description": "Maximum number of items to return",
                                "default": 10
                            }
                        }
                    }
                },
                {
                    "name": "select_content",
                    "description": "Select specific content from a cached webpage",
                    "input_schema": {
                        "type": "object",
                        "properties": {
                            "url": {
                                "type": "string",
                                "description": "URL of the webpage"
                            },
                            "selection": {
                                "type": "object",
                                "properties": {
                                    "headlines": {
                                        "type": "array",
                                        "items": {"type": "number"},
                                        "description": "Indices of headlines to include"
                                    },
                                    "paragraphs": {
                                        "type": "array",
                                        "items": {"type": "number"},
                                        "description": "Indices of paragraphs to include"
                                    }
                                }
                            }
                        },
                        "required": ["url", "selection"]
                    }
                }
            ]
        }
    
    async def _call_tool(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle tool execution requests."""
        tool_name = params["name"]
        args = params["arguments"]
        
        handlers = {
            "create_context": self._handle_create_context,
            "browse_web": self._handle_browse_web,
            "add_message": self._handle_add_message,
            "get_context": self._handle_get_context,
            "clear_context": self._handle_clear_context,
            "get_recent_content": self._handle_get_recent_content,
            "select_content": self._handle_select_content
        }
        
        handler = handlers.get(tool_name)
        if not handler:
            return {
                "error": {
                    "code": "method_not_found",
                    "message": f"Unknown tool: {tool_name}"
                }
            }
        
        if asyncio.iscoroutinefunction(handler):
            result = await handler(args)
        else:
            result = handler(args)
            
        # Format the result for MCP response
        if isinstance(result, dict) and "error" in result:
            return {
                "error": {
                    "code": "tool_error",
                    "message": result["error"]
                }
            }
        else:
            # For browse_web, return the content in the expected format
            if tool_name == "browse_web" and isinstance(result, dict):
                if "error" in result:
                    return {
                        "error": {
                            "code": "tool_error",
                            "message": result["error"]
                        }
                    }
                if "content" in result:
                    return {
                        "result": {
                            "content": [
                                {
                                    "type": "text",
                                    "text": result["content"]
                                }
                            ]
                        }
                    }
            # For other tools, return the JSON result
            return {
                "result": {
                    "content": json.dumps(result)
                }
            }
    
    def _handle_create_context(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Create a new context window."""
        context_id = args["context_id"]
        max_tokens = args.get("max_tokens", 4096)
        
        if context_id in self.contexts:
            return {
                "error": "Context already exists",
                "context_id": context_id
            }
        
        self.contexts[context_id] = ContextState(max_tokens)
        return {
            "message": "Context created successfully",
            "context_id": context_id,
            "max_tokens": max_tokens
        }
    
    async def _handle_browse_web(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Browse a webpage and extract content."""
        url = args["url"]
        priority = args.get("priority", "important")
        context_id = args.get("context_id")
        
        try:
            # Validate URL
            parsed = urlparse(url)
            if not parsed.scheme or not parsed.netloc:
                raise ValueError("Invalid URL format")
            
            print(f"Fetching URL: {url}", file=sys.stderr)
            # Fetch webpage
            async with self.session.get(url, timeout=30, ssl=False, allow_redirects=True, max_redirects=5) as response:
                response.raise_for_status()
                print(f"Response status: {response.status}", file=sys.stderr)
                print(f"Final URL after redirects: {str(response.url)}", file=sys.stderr)
                html = await response.text()
                
                # Wait a bit for any dynamic content to load
                await asyncio.sleep(2)
                
                # Try to get updated content
                try:
                    updated_response = await self.session.get(str(response.url), timeout=30, ssl=False)
                    updated_html = await updated_response.text()
                    if len(updated_html) > len(html):
                        print("Found updated content after waiting", file=sys.stderr)
                        html = updated_html
                except Exception as e:
                    print(f"Error getting updated content: {str(e)}", file=sys.stderr)
                print(f"Response length: {len(html)}", file=sys.stderr)
            print(f"Response content preview: {html[:500]}", file=sys.stderr)
            
            # Parse content
            print("Parsing content with BeautifulSoup", file=sys.stderr)
            soup = BeautifulSoup(html, 'html.parser')
            
            # Try to remove common overlay elements that might block content
            for selector in [
                '#cookie-consent',
                '.cookie-banner',
                '.cookie-notice',
                '.consent-overlay',
                '.modal',
                '.popup',
                '.overlay',
                '#gdpr',
                '.gdpr',
                '.subscription-overlay',
                '.paywall',
                '.ad-overlay'
            ]:
                for element in soup.select(selector):
                    print(f"Removing overlay element: {selector}", file=sys.stderr)
                    element.decompose()
            
            # Add base URL for relative paths
            base_tag = soup.find('base')
            base_url = base_tag['href'] if base_tag and 'href' in base_tag.attrs else str(response.url)
            print(f"Using base URL: {base_url}", file=sys.stderr)
            
            # Check for meta refresh redirects
            meta_refresh = soup.find('meta', attrs={'http-equiv': 'refresh'})
            if meta_refresh:
                content = meta_refresh.get('content', '')
                if content:
                    try:
                        # Parse meta refresh content (e.g., "0;url=https://example.com")
                        redirect_url = content.split('url=')[1].strip()
                        # Handle relative URLs
                        if not redirect_url.startswith(('http://', 'https://')):
                            # Get the base URL
                            base_url = str(response.url)
                            if redirect_url.startswith('/'):
                                # Absolute path
                                parsed_base = urlparse(base_url)
                                redirect_url = f"{parsed_base.scheme}://{parsed_base.netloc}{redirect_url}"
                            else:
                                # Relative path
                                redirect_url = f"{base_url.rstrip('/')}/{redirect_url.lstrip('/')}"
                        print(f"Found meta refresh redirect to: {redirect_url}", file=sys.stderr)
                        
                        # Follow the redirect
                        async with self.session.get(redirect_url, timeout=30, ssl=False, allow_redirects=True, max_redirects=5) as response:
                            response.raise_for_status()
                            print(f"Response status after meta refresh: {response.status}", file=sys.stderr)
                            html = await response.text()
                            print(f"Response length after meta refresh: {len(html)}", file=sys.stderr)
                            
                        # Re-parse the content
                        soup = BeautifulSoup(html, 'html.parser')
                    except Exception as e:
                        print(f"Error following meta refresh: {str(e)}", file=sys.stderr)
            
            # Extract title
            title = soup.title.string if soup.title else ''
            if title:
                title = title.strip()
                print(f"Found title: {title}", file=sys.stderr)
            
            # Extract main content
            print("Extracting content", file=sys.stderr)
            paragraphs = []
            
            # Try different content selectors
            content_selectors = [
                # AP News specific
                '.Page-content',
                '.Article',
                '.RichTextStoryBody',
                # Common article containers
                'article',
                '[role="article"]',
                '.article',
                '.story',
                '.post',
                # Main content areas
                'main',
                '[role="main"]',
                '#main',
                '.main',
                # Generic content containers
                '#content',
                '.content',
                '.entry-content',
                '.post-content',
                # News specific
                '.article-body',
                '.article-content',
                '.story-body',
                '.story-content',
                '.news-article'
            ]
            
            for selector in content_selectors:
                print(f"Trying selector: {selector}", file=sys.stderr)
                content_area = soup.select_one(selector)
                if content_area:
                    # Extract paragraphs from the content area
                    for p in content_area.find_all(['p', 'div.paragraph']):
                        text = p.get_text().strip()
                        if text and len(text) > 20:
                            paragraphs.append(text)
                    if paragraphs:
                        break
            
            # Fallback to all paragraphs if no content found
            if not paragraphs:
                print("Falling back to all paragraphs", file=sys.stderr)
                for p in soup.find_all('p'):
                    text = p.get_text().strip()
                    if text and len(text) > 20:
                        paragraphs.append(text)
            
            print(f"Found {len(paragraphs)} paragraphs", file=sys.stderr)
            if paragraphs:
                print(f"First paragraph: {paragraphs[0]}", file=sys.stderr)
            
            # Extract entities (headings and metadata)
            print("Extracting entities", file=sys.stderr)
            entities = []
            
            # Try to get headline from various selectors
            headline_selectors = [
                '.Page-headline',
                'h1.headline',
                '.article-headline',
                '.story-headline',
                '.post-headline',
                '.entry-title',
                'h1.title',
                'h1[itemprop="headline"]',
                'h1'  # Fallback to first h1
            ]
            
            for selector in headline_selectors:
                headline = soup.select_one(selector)
                if headline:
                    break
            if headline:
                text = headline.get_text().strip()
                if text:
                    entities.append(text)
                    print(f"Found headline: {text}", file=sys.stderr)
            
            # Then get other headings
            for h in soup.find_all(['h1', 'h2', 'h3']):
                text = h.get_text().strip()
                if text:
                    entities.append(text)
                    print(f"Found heading: {text}", file=sys.stderr)
            
            # Format content for readability
            if title:
                formatted_content = [f"Title: {title}"]
            else:
                formatted_content = []
            
            if entities:
                formatted_content.append("\nHeadlines:")
                formatted_content.extend(f"- {entity}" for entity in entities)
            
            if paragraphs:
                formatted_content.append("\nContent:")
                formatted_content.extend(paragraphs)
            
            content = '\n'.join(formatted_content)
            
            # Create a new context if none provided
            if not context_id:
                context_id = f"web_{int(time.time())}"
                self.contexts[context_id] = ContextState()
            
            # Add content to context
            if context_id in self.contexts:
                message = Message(
                    timestamp=time.time(),
                    priority=priority,
                    token_count=len(content.split()) * 1.3,  # Rough estimation
                    content=content,
                    entities=entities,
                    relationships=[{"type": "source", "url": url}]
                )
                self.contexts[context_id].add_message(message)
            
            # Cache the content
            cached_content = CachedContent(
                url=url,
                title=title,
                headlines=entities,
                paragraphs=paragraphs,
                timestamp=time.time()
            )
            self.cache.cache_content(cached_content)
            
            # Return preview
            return {
                "context_id": context_id,
                "url": url,
                "title": title,
                "headline_count": len(entities),
                "paragraph_count": len(paragraphs),
                "preview": content[:500] + "..." if len(content) > 500 else content
            }
            
        except Exception as e:
            error_msg = str(e)
            if isinstance(e, aiohttp.ClientError):
                if "SSL" in error_msg:
                    error_msg = "SSL certificate verification failed. The site might be using an invalid certificate."
                elif "DNS" in error_msg:
                    error_msg = "Could not resolve the domain name. Please check if the URL is correct."
                elif "timeout" in error_msg.lower():
                    error_msg = "The request timed out. The site might be slow or unresponsive."
                elif "too many redirects" in error_msg.lower():
                    error_msg = "Too many redirects. The site might be in a redirect loop."
                else:
                    error_msg = f"Network error: {error_msg}"
            elif isinstance(e, ValueError):
                error_msg = f"Invalid URL format: {error_msg}"
            
            print(f"Error details: {str(e)}", file=sys.stderr)
            return {
                "error": error_msg,
                "url": url
            }
    
    def _handle_add_message(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Add a message to a context window."""
        context_id = args["context_id"]
        content = args["content"]
        priority = args.get("priority", "important")
        entities = args.get("entities", [])
        relationships = args.get("relationships", [])
        
        context = self.contexts.get(context_id)
        if not context:
            return {
                "error": "Context not found",
                "context_id": context_id
            }
        
        # Estimate tokens (simple word-based estimation)
        token_count = len(content.split()) * 1.3
        
        message = Message(
            timestamp=datetime.now().timestamp(),
            priority=priority,
            token_count=int(token_count),
            content=content,
            entities=entities,
            relationships=relationships
        )
        
        context.add_message(message)
        
        return {
            "message": "Message added successfully",
            "context_id": context_id,
            "current_tokens": context.current_tokens,
            "max_tokens": context.max_tokens
        }
    
    def _handle_get_context(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Get current state of a context window."""
        context_id = args["context_id"]
        
        context = self.contexts.get(context_id)
        if not context:
            return {
                "error": "Context not found",
                "context_id": context_id
            }
        
        return {
            "context_id": context_id,
            "messages": [
                {
                    "timestamp": msg.timestamp,
                    "priority": msg.priority,
                    "token_count": msg.token_count,
                    "content": msg.content,
                    "entities": msg.entities,
                    "relationships": msg.relationships
                }
                for msg in context.messages
            ],
            "current_tokens": context.current_tokens,
            "max_tokens": context.max_tokens
        }
    
    def _handle_clear_context(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Clear a context window."""
        context_id = args["context_id"]
        
        context = self.contexts.get(context_id)
        if not context:
            return {
                "error": "Context not found",
                "context_id": context_id
            }
        
        context.clear()
        return {
            "message": "Context cleared successfully",
            "context_id": context_id
        }
    
    def _handle_get_recent_content(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Get list of recently browsed content."""
        limit = args.get("limit", 10)
        return {
            "recent_content": self.cache.get_recent_content(limit)
        }
    
    def _handle_select_content(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Select specific content from cached webpage."""
        url = args["url"]
        selection = args["selection"]
        
        # Get selected content
        result = self.cache.select_content(url, selection)
        if "error" in result:
            return result
            
        # Format for readability
        formatted_content = []
        for item in result["content"]:
            if item["type"] == "headline":
                formatted_content.append(f"# {item['text']}")
            else:
                formatted_content.append(item["text"])
        
        return {
            "url": result["url"],
            "title": result["title"],
            "content": "\n\n".join(formatted_content)
        }

if __name__ == "__main__":
    # Add the parent directory to Python path for imports
    sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    
    server = SmallContextServer()
    try:
        asyncio.run(server.start())
    except KeyboardInterrupt:
        print("Server stopped by user", file=sys.stderr)
    finally:
        asyncio.run(server.stop())
