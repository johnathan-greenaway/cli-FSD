"""Redis cache implementation for Small Context Protocol."""

import json
import sys
import time
import redis
from typing import Dict, List, Optional, Any
from dataclasses import dataclass

@dataclass
class CachedContent:
    """Container for cached webpage content."""
    url: str
    title: str
    headlines: List[str]
    paragraphs: List[str]
    timestamp: float

class ContentCache:
    """Redis-based cache for webpage content."""
    
    def __init__(self, host='localhost', port=None, db=0):
        # Try ports starting from 6379 until we find an available one
        if port is None:
            port = 6379
            while port < 6479:  # Try up to port 6479
                try:
                    self.redis = redis.Redis(host=host, port=port, db=db, decode_responses=True)
                    # Test connection
                    self.redis.ping()
                    print(f"Connected to Redis on port {port}", file=sys.stderr)
                    break
                except redis.ConnectionError:
                    port += 1
                    continue
            else:
                raise redis.ConnectionError("Could not find an available Redis port")
        else:
            self.redis = redis.Redis(host=host, port=port, db=db, decode_responses=True)
        self.content_key = "small_context:content:{url}"
        self.index_key = "small_context:content_index"
    
    def cache_content(self, content: CachedContent) -> None:
        """Cache webpage content with Redis."""
        # Store the full content
        key = self.content_key.format(url=content.url)
        self.redis.hset(key, mapping={
            'url': content.url,
            'title': content.title,
            'headlines': json.dumps(content.headlines),
            'paragraphs': json.dumps(content.paragraphs),
            'timestamp': str(content.timestamp)
        })
        
        # Add to index
        self.redis.zadd(self.index_key, {content.url: content.timestamp})
        
        # Expire after 1 hour
        self.redis.expire(key, 3600)
    
    def get_content(self, url: str) -> Optional[CachedContent]:
        """Retrieve cached content for URL."""
        key = self.content_key.format(url=url)
        data = self.redis.hgetall(key)
        
        if not data:
            return None
            
        return CachedContent(
            url=data['url'],
            title=data['title'],
            headlines=json.loads(data['headlines']),
            paragraphs=json.loads(data['paragraphs']),
            timestamp=float(data['timestamp'])
        )
    
    def get_recent_content(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get recently cached content."""
        # Get recent URLs
        urls = self.redis.zrevrange(self.index_key, 0, limit-1)
        
        results = []
        for url in urls:
            content = self.get_content(url)
            if content:
                results.append({
                    'url': content.url,
                    'title': content.title,
                    'headline_count': len(content.headlines),
                    'paragraph_count': len(content.paragraphs)
                })
        
        return results
    
    def select_content(self, url: str, selection: Dict[str, List[int]]) -> Dict[str, Any]:
        """Get selected portions of cached content.
        
        Args:
            url: The webpage URL
            selection: Dict with optional keys:
                - headlines: List of headline indices to include
                - paragraphs: List of paragraph indices to include
        """
        content = self.get_content(url)
        if not content:
            return {
                "type": "error",
                "url": url,
                "timestamp": time.time(),
                "error": "Content not found in cache"
            }
            
        result = {
            "type": "webpage",
            "url": content.url,
            "title": content.title,
            "timestamp": content.timestamp,
            "content": []
        }
        
        # Add selected headlines as stories
        if 'headlines' in selection:
            for idx in selection['headlines']:
                if 0 <= idx < len(content.headlines):
                    result['content'].append({
                        "type": "story",
                        "title": content.headlines[idx],
                        "url": "",
                        "metadata": {}
                    })
                    
        # Add selected paragraphs as sections
        if 'paragraphs' in selection:
            for idx in selection['paragraphs']:
                if 0 <= idx < len(content.paragraphs):
                    result['content'].append({
                        "type": "section",
                        "blocks": [{
                            "type": "content_block",
                            "text": content.paragraphs[idx],
                            "links": [],
                            "metadata": {}
                        }]
                    })
                    
        return result
