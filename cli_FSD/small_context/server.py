"""Small Context Protocol MCP Server Implementation."""

import json
import sys
import asyncio
import aiohttp
import os
import time
import socket
import subprocess
from bs4 import BeautifulSoup
from urllib.parse import urlparse
from typing import Dict, List, Any, Optional
from dataclasses import dataclass
from datetime import datetime
import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from small_context.cache import ContentCache, CachedContent

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
        with socket.socket() as s:
            s.bind(('', 0))
            port = s.getsockname()[1]
        
        self.redis_process = subprocess.Popen(
            ['redis-server', '--port', str(port), '--daemonize', 'no'],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        
        await asyncio.sleep(1)
        self.cache = ContentCache(port=port)
    
    async def start(self):
        """Start the server and initialize services."""
        await self._start_redis()
        await self._process_stdin()
    
    async def stop(self):
        """Stop the server and cleanup resources."""
        if self.redis_process:
            self.redis_process.terminate()
            self.redis_process.wait()
    
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
            
            for selector in [
                '#cookie-consent', '.cookie-banner', '.cookie-notice',
                '.consent-overlay', '.modal', '.popup', '.overlay',
                '#gdpr', '.gdpr', '.subscription-overlay', '.paywall',
                '.ad-overlay'
            ]:
                for element in soup.select(selector):
                    element.decompose()
            
            title = soup.title.string.strip() if soup.title else ''
            
            paragraphs = []
            content_selectors = [
                '.Page-content', '.Article', '.RichTextStoryBody',
                'article', '[role="article"]', '.article', '.story',
                '.post', 'main', '[role="main"]', '#main', '.main',
                '#content', '.content', '.entry-content', '.post-content',
                '.article-body', '.article-content', '.story-body',
                '.story-content', '.news-article'
            ]
            
            for selector in content_selectors:
                content_area = soup.select_one(selector)
                if content_area:
                    for p in content_area.find_all(['p', 'div.paragraph']):
                        text = p.get_text().strip()
                        if text and len(text) > 20:
                            paragraphs.append(text)
                    if paragraphs:
                        break
            
            if not paragraphs:
                for p in soup.find_all('p'):
                    text = p.get_text().strip()
                    if text and len(text) > 20:
                        paragraphs.append(text)
            
            entities = []
            headline_selectors = [
                '.Page-headline', 'h1.headline', '.article-headline',
                '.story-headline', '.post-headline', '.entry-title',
                'h1.title', 'h1[itemprop="headline"]', 'h1'
            ]
            
            for selector in headline_selectors:
                headline = soup.select_one(selector)
                if headline:
                    text = headline.get_text().strip()
                    if text:
                        entities.append(text)
                        break
            
            for h in soup.find_all(['h2', 'h3']):
                text = h.get_text().strip()
                if text:
                    entities.append(text)
            
            cached_content = CachedContent(
                url=url,
                title=title,
                headlines=entities,
                paragraphs=paragraphs,
                timestamp=time.time()
            )
            self.cache.cache_content(cached_content)
            
            return {
                "url": url,
                "title": title,
                "headline_count": len(entities),
                "paragraph_count": len(paragraphs),
                "headlines": entities,
                "paragraphs": paragraphs
            }
            
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
                "error": error_msg,
                "url": url
            }
    
    def _handle_select_content(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Select specific content from cached webpage."""
        url = args["url"]
        selection = args["selection"]
        
        result = self.cache.select_content(url, selection)
        if "error" in result:
            return result
            
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
    server = SmallContextServer()
    try:
        asyncio.run(server.start())
    except KeyboardInterrupt:
        asyncio.run(server.stop())
