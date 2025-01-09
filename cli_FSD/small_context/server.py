"""Small Context Protocol MCP Server Implementation."""

import json
import sys
import asyncio
import aiohttp
import os
import time
import socket
import subprocess
from bs4 import BeautifulSoup, NavigableString
from urllib.parse import urlparse, urljoin
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime
import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from small_context.cache import ContentCache, CachedContent
from small_context.memory_cache import InMemoryCache, InMemoryCachedContent

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
        self.redis_process = None
        self.cache = None
        self.default_headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate',
            'DNT': '1',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1'
        }
        
    async def _start_redis(self):
        """Start Redis server on a dynamic port."""
        try:
            # Find an available port
            with socket.socket() as s:
                s.bind(('', 0))
                port = s.getsockname()[1]
            
            # Try to start Redis server
            try:
                self.redis_process = subprocess.Popen(
                    ['redis-server', '--port', str(port), '--daemonize', 'no'],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE
                )
                
                # Wait briefly for Redis to start
                await asyncio.sleep(1)
                
                # Check if process is still running
                if self.redis_process.poll() is not None:
                    stdout, stderr = self.redis_process.communicate()
                    print(json.dumps({
                        "warning": {
                            "code": "redis_start_failed",
                            "message": f"Redis failed to start: {stderr.decode()}. Using in-memory cache."
                        }
                    }), flush=True)
                    self.cache = InMemoryCache()
                    return
                
                # Initialize cache
                self.cache = ContentCache(port=port)
                
            except FileNotFoundError:
                print(json.dumps({
                    "warning": {
                        "code": "redis_not_found",
                        "message": "Redis server not found. Using in-memory cache."
                    }
                }), flush=True)
                
        except Exception as e:
            if self.redis_process:
                self.redis_process.terminate()
                self.redis_process.wait()
            print(json.dumps({
                "warning": {
                    "code": "redis_init_failed",
                    "message": f"Failed to initialize Redis: {str(e)}. Using in-memory cache."
                }
            }), flush=True)
    
    async def start(self, ready_callback=None):
        """Start the server and initialize services."""
        try:
            await self._start_redis()
            # Initialize default context
            self.contexts["default"] = ContextState()
            
            # Signal ready state
            if ready_callback:
                await ready_callback()
            
            # Start processing input
            await self._process_stdin()
            
        except Exception as e:
            print(json.dumps({
                "error": {
                    "code": "initialization_error",
                    "message": str(e)
                }
            }), flush=True)
            # Still signal ready even if there's an error, so the main loop can continue
            if ready_callback:
                await ready_callback()
    
    async def stop(self):
        """Stop the server and cleanup resources."""
        if self.redis_process:
            self.redis_process.terminate()
            self.redis_process.wait()
    
    async def _process_stdin(self):
        """Process both MCP protocol messages and CLI input."""
        while True:
            try:
                line = await asyncio.get_event_loop().run_in_executor(None, sys.stdin.readline)
                if not line or line.isspace():
                    continue
                
                # Try to parse as JSON for MCP protocol
                try:
                    request = json.loads(line)
                    response = await self._handle_request(request)
                    print(json.dumps(response))
                    sys.stdout.flush()
                    continue
                except json.JSONDecodeError:
                    # Not JSON, treat as CLI input
                    pass
                
                # Handle CLI input
                user_input = line.strip()
                if user_input.startswith("@"):
                    # Handle CLI command
                    response = await self._handle_cli_command(user_input[1:])
                    if response:
                        print(response)
                else:
                    # Handle regular input
                    response = await self._handle_cli_input(user_input)
                    if response:
                        print(response)
                
            except Exception as e:
                print(json.dumps({
                    "error": {
                        "code": "internal_error",
                        "message": str(e)
                    }
                }), flush=True)
    
    async def _handle_cli_command(self, command: str) -> Optional[str]:
        """Handle CLI commands."""
        parts = command.strip().split()
        if not parts:
            return None
            
        cmd = parts[0].lower()
        args = parts[1:]
        
        if cmd == "help":
            return """
Available commands:
  @help           - Show this help message
  @browse <url>   - Browse a webpage
  @select <url>   - Select content from cached webpage
  @clear          - Clear cached content
"""
        elif cmd == "browse" and args:
            url = args[0]
            result = await self._handle_browse_web({"url": url})
            if "error" in result:
                return f"Error: {result['error']}"
            return "Content cached successfully"
            
        elif cmd == "select" and args:
            url = args[0]
            result = self._handle_select_content({
                "url": url,
                "selection": {
                    "headlines": [0],
                    "paragraphs": [0]
                }
            })
            if "error" in result:
                return f"Error: {result['error']}"
            return "Content selected successfully"
            
        elif cmd == "clear":
            if self.cache:
                self.cache = InMemoryCache() if isinstance(self.cache, InMemoryCache) else ContentCache()
                return "Cache cleared"
            return "No cache available"
            
        return f"Unknown command: {cmd}"
    
    async def _handle_cli_input(self, text: str) -> Optional[str]:
        """Handle regular CLI input."""
        # Process as regular input, store in context
        if not text:
            return None
            
        # Get default context
        context = self.contexts["default"]
            
        # Create message with content analysis
        message = Message(
            timestamp=time.time(),
            priority="important",
            token_count=len(text.split()),
            content=text,
            entities=self._extract_entities(text),
            relationships=self._extract_relationships(text)
        )
        
        # Add to context
        context.add_message(message)
        
        # Return formatted context for display
        return self._format_context_summary(context)
    
    def _extract_entities(self, text: str) -> List[str]:
        """Extract key entities from text."""
        # Simple entity extraction based on capitalized words and technical terms
        entities = []
        words = text.split()
        for word in words:
            # Capture capitalized words (potential proper nouns)
            if word[0].isupper() and len(word) > 1:
                entities.append(word)
            # Capture technical terms
            elif any(tech in word.lower() for tech in ['api', 'url', 'http', 'json', 'xml', 'html']):
                entities.append(word)
        return list(set(entities))
    
    def _extract_relationships(self, text: str) -> List[Dict[str, str]]:
        """Extract relationships between entities."""
        relationships = []
        entities = self._extract_entities(text)
        
        # Look for relationships between entities
        for i, entity1 in enumerate(entities):
            for entity2 in entities[i+1:]:
                # Find text between entities that might indicate a relationship
                try:
                    start = text.index(entity1) + len(entity1)
                    end = text.index(entity2)
                    between = text[start:end].strip()
                    if between:
                        relationships.append({
                            "source": entity1,
                            "target": entity2,
                            "relation": between
                        })
                except ValueError:
                    continue
        
        return relationships
    
    def _format_context_summary(self, context: ContextState) -> str:
        """Format context state for display."""
        if not context.messages:
            return None
            
        # Get most recent messages
        recent_messages = sorted(
            context.messages,
            key=lambda m: m.timestamp,
            reverse=True
        )[:5]
        
        # Format summary
        summary = []
        for msg in recent_messages:
            summary.append(f"Content: {msg.content}")
            if msg.entities:
                summary.append(f"Entities: {', '.join(msg.entities)}")
            if msg.relationships:
                for rel in msg.relationships:
                    summary.append(
                        f"Relationship: {rel['source']} {rel['relation']} {rel['target']}"
                    )
            summary.append("")
        
        return "\n".join(summary) if summary else None
    
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
                    "name": "browse_web",
                    "description": "Browse a webpage and extract its content",
                    "input_schema": {
                        "type": "object",
                        "properties": {
                            "url": {
                                "type": "string",
                                "description": "URL to browse"
                            }
                        },
                        "required": ["url"]
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
            "browse_web": self._handle_browse_web,
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
            
        if isinstance(result, dict) and "error" in result:
            return {
                "error": {
                    "code": "tool_error",
                    "message": result["error"]
                }
            }
        
        return {
            "result": {
                "content": json.dumps(result)
            }
        }
    
    async def _handle_browse_web(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Browse a webpage and extract content."""
        url = args["url"]
        
        try:
            parsed = urlparse(url)
            if not parsed.scheme or not parsed.netloc:
                raise ValueError("Invalid URL format")
            
            async with aiohttp.ClientSession(headers=self.default_headers) as session:
                async with session.get(url, timeout=30, ssl=False, allow_redirects=True, max_redirects=5) as response:
                    response.raise_for_status()
                    html = await response.text()
                    
                    await asyncio.sleep(2)
                    
                    try:
                        async with session.get(str(response.url), timeout=30, ssl=False) as updated_response:
                            updated_html = await updated_response.text()
                            if len(updated_html) > len(html):
                                html = updated_html
                    except Exception:
                        pass
            
            soup = BeautifulSoup(html, 'html.parser')
            
            # Remove unwanted elements
            for selector in [
                '#cookie-consent', '.cookie-banner', '.cookie-notice',
                '.consent-overlay', '.modal', '.popup', '.overlay',
                '#gdpr', '.gdpr', '.subscription-overlay', '.paywall',
                '.ad-overlay', 'script', 'style', 'meta', 'link',
                'iframe', 'noscript', 'svg', 'footer', 'nav',
                '[role="complementary"]', '[role="navigation"]',
                '.sidebar', '.comments', '.related-articles',
                '.advertisement', '.social-share', '.newsletter'
            ]:
                for element in soup.select(selector):
                    element.decompose()
            
            # Extract title
            title = soup.title.string.strip() if soup.title else ''
            
            # Extract meaningful content
            def get_text_with_links(element) -> str:
                """Extract text while preserving links."""
                parts = []
                for child in element.children:
                    if isinstance(child, NavigableString):
                        text = child.strip()
                        if text:
                            parts.append(text)
                    elif child.name == 'a':
                        href = child.get('href', '')
                        if href:
                            if not href.startswith(('http://', 'https://')):
                                href = urljoin(url, href)
                            text = child.get_text().strip()
                            if text:
                                parts.append(f"{text} ({href})")
                    elif child.name not in ['script', 'style']:
                        text = child.get_text().strip()
                        if text:
                            parts.append(text)
                return ' '.join(parts)

            def is_meaningful(text: str) -> bool:
                """Check if text contains meaningful content."""
                if not text or len(text) < 20:
                    return False
                # Avoid navigation text, copyright notices, etc.
                skip_phrases = ['cookie', 'privacy policy', 'terms of service', 'all rights reserved',
                              'follow us', 'sign up', 'subscribe', 'advertisement']
                text_lower = text.lower()
                return not any(phrase in text_lower for phrase in skip_phrases)

            # Extract content into a structured format
            content = {
                "type": "webpage",
                "url": url,
                "title": soup.title.string.strip() if soup.title else '',
                "timestamp": time.time(),
                "content": []
            }

            # Extract main content based on common patterns
            def extract_content_block(element):
                """Extract content from an element into a structured format."""
                block = {
                    "type": "content_block",
                    "text": "",
                    "links": [],
                    "metadata": {}
                }
                
                # Extract text content
                text_parts = []
                for node in element.descendants:
                    if isinstance(node, NavigableString):
                        text = node.strip()
                        if text:
                            text_parts.append(text)
                    elif node.name == 'a':
                        href = node.get('href', '')
                        if href:
                            if not href.startswith(('http://', 'https://')):
                                href = urljoin(url, href)
                            text = node.get_text().strip()
                            if text:
                                text_parts.append(text)
                                block["links"].append({
                                    "text": text,
                                    "url": href
                                })
                
                block["text"] = " ".join(text_parts).strip()
                return block if block["text"] else None

            # Process content based on page structure
            if "news.ycombinator.com" in url:
                # Handle HN-specific structure
                stories = soup.select('tr.athing')
                for story in stories:
                    title_cell = story.select_one('td.title > span.titleline')
                    if title_cell and (title_link := title_cell.find('a')):
                        story_block = {
                            "type": "story",
                            "title": title_link.get_text().strip(),
                            "url": urljoin(url, title_link['href']) if title_link.get('href') else "",
                            "metadata": {}
                        }
                        
                        if meta_row := story.find_next_sibling('tr'):
                            if meta := meta_row.select_one('td.subtext'):
                                if points := meta.select_one('span.score'):
                                    story_block["metadata"]["points"] = points.get_text()
                                if author := meta.select_one('a.hnuser'):
                                    story_block["metadata"]["author"] = author.get_text()
                                if time_el := meta.select_one('span.age'):
                                    story_block["metadata"]["time"] = time_el.get_text()
                                if comments := meta.find_all('a')[-1]:
                                    story_block["metadata"]["comments"] = comments.get_text()
                        
                        content["content"].append(story_block)
            else:
                # Handle generic webpage structure
                for tag in soup.find_all(['article', 'main', '[role="main"]', '.content', '#content']):
                    section = {
                        "type": "section",
                        "blocks": []
                    }
                    
                    # Extract headings
                    for heading in tag.find_all(['h1', 'h2', 'h3']):
                        if block := extract_content_block(heading):
                            block["type"] = "heading"
                            section["blocks"].append(block)
                    
                    # Extract paragraphs and lists
                    for element in tag.find_all(['p', 'div', 'section', 'ul', 'ol']):
                        if block := extract_content_block(element):
                            section["blocks"].append(block)
                    
                    if section["blocks"]:
                        content["content"].append(section)
                
                # Fallback to any content if no structured content found
                if not content["content"]:
                    for tag in soup.find_all(['p', 'div', 'section']):
                        if block := extract_content_block(tag):
                            content["content"].append({
                                "type": "section",
                                "blocks": [block]
                            })
            
            # Cache the content
            # Create appropriate cache content based on cache type
            cache_content = InMemoryCachedContent if isinstance(self.cache, InMemoryCache) else CachedContent
            cached_content = cache_content(
                url=url,
                title=content["title"],
                headlines=[block["title"] for block in content["content"] if block.get("type") == "story"],
                paragraphs=[
                    f"{block['title']}\nURL: {block['url']}\n" + 
                    "\n".join(f"{k}: {v}" for k, v in block['metadata'].items())
                    for block in content["content"] if block.get("type") == "story"
                ],
                timestamp=content["timestamp"]
            )
            self.cache.cache_content(cached_content)
            
            return content
            
        except Exception as e:
            error_msg = str(e)
            if isinstance(e, aiohttp.ClientError):
                if "SSL" in error_msg:
                    error_msg = "SSL certificate verification failed"
                elif "DNS" in error_msg:
                    error_msg = "Could not resolve domain name"
                elif "timeout" in error_msg.lower():
                    error_msg = "Request timed out"
                elif "too many redirects" in error_msg.lower():
                    error_msg = "Too many redirects"
                else:
                    error_msg = f"Network error: {error_msg}"
            elif isinstance(e, ValueError):
                error_msg = f"Invalid URL format: {error_msg}"
            
            return {
                "type": "error",
                "url": url,
                "timestamp": time.time(),
                "error": error_msg
            }
    
    def _handle_select_content(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Select specific content from cached webpage."""
        url = args["url"]
        selection = args["selection"]
        
        result = self.cache.select_content(url, selection)
        if "error" in result:
            return {
                "type": "error",
                "url": url,
                "timestamp": time.time(),
                "error": result["error"]
            }
        
        # Create a new webpage response with selected content
        content = {
            "type": "webpage",
            "url": result["url"],
            "title": result["title"],
            "timestamp": time.time(),
            "content": []
        }
        
        # Convert cached content to structured format
        for item in result["content"]:
            if item["type"] == "headline":
                content["content"].append({
                    "type": "story",
                    "title": item["text"],
                    "url": "",
                    "metadata": {}
                })
            else:
                content["content"].append({
                    "type": "section",
                    "blocks": [{
                        "type": "content_block",
                        "text": item["text"],
                        "links": [],
                        "metadata": {}
                    }]
                })
        
        return content

if __name__ == "__main__":
    server = SmallContextServer()
    try:
        asyncio.run(server.start())
    except KeyboardInterrupt:
        asyncio.run(server.stop())
