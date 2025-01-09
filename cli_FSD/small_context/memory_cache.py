"""In-memory cache implementation for Small Context Protocol."""

from typing import Dict, List, Any, Optional
from dataclasses import dataclass
import time

@dataclass
class InMemoryCachedContent:
    """Content cache structure."""
    url: str
    title: str
    headlines: List[str]
    paragraphs: List[str]
    timestamp: float

class InMemoryCache:
    """Simple in-memory cache implementation."""
    
    def __init__(self):
        self._cache: Dict[str, InMemoryCachedContent] = {}
    
    def cache_content(self, content: InMemoryCachedContent) -> None:
        """Cache content in memory."""
        self._cache[content.url] = content
    
    def select_content(self, url: str, selection: Dict[str, List[int]]) -> Dict[str, Any]:
        """Select specific content from cache."""
        if url not in self._cache:
            return {
                "error": "Content not found in cache"
            }
            
        cached = self._cache[url]
        content = []
        
        # Add selected headlines
        if "headlines" in selection:
            for idx in selection["headlines"]:
                if 0 <= idx < len(cached.headlines):
                    content.append({
                        "type": "headline",
                        "text": cached.headlines[idx]
                    })
        
        # Add selected paragraphs
        if "paragraphs" in selection:
            for idx in selection["paragraphs"]:
                if 0 <= idx < len(cached.paragraphs):
                    content.append({
                        "type": "paragraph",
                        "text": cached.paragraphs[idx]
                    })
        
        return {
            "url": url,
            "title": cached.title,
            "content": content,
            "timestamp": time.time()
        }
