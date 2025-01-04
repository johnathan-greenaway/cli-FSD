"""Small Context Protocol Implementation.

This module implements an efficient protocol for managing information processing
in small-context LLMs (2k-8k tokens). It focuses on token efficiency and
context preservation through structured message handling and priority-based
context management.
"""

import json
import time
import requests
from typing import Dict, List, Optional, Union
from dataclasses import dataclass
from enum import Enum
from bs4 import BeautifulSoup
from urllib.parse import urlparse

class WebBrowser:
    """Handles web browsing and content extraction."""
    
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
    
    def browse(self, url: str) -> Dict[str, str]:
        """Browse a webpage and extract relevant content.
        
        Args:
            url: The URL to browse
            
        Returns:
            Dict containing extracted title and main content
        """
        try:
            # Validate URL
            parsed = urlparse(url)
            if not parsed.scheme or not parsed.netloc:
                raise ValueError("Invalid URL format")
                
            response = self.session.get(url, timeout=10)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Extract title
            title = soup.title.string if soup.title else ''
            
            # Extract main content (p tags)
            paragraphs = []
            for p in soup.find_all('p'):
                text = p.get_text().strip()
                if text and len(text) > 20:  # Filter out short/empty paragraphs
                    paragraphs.append(text)
            
            content = ' '.join(paragraphs)
            
            # Extract key entities (h1, h2, h3 tags)
            entities = []
            for h in soup.find_all(['h1', 'h2', 'h3']):
                text = h.get_text().strip()
                if text:
                    entities.append(text)
            
            return {
                'title': title,
                'content': content,
                'url': url,
                'entities': entities
            }
            
        except (requests.RequestException, ValueError) as e:
            return {
                'title': 'Error',
                'content': f'Failed to fetch {url}: {str(e)}',
                'url': url,
                'entities': []
            }

class MessageType(str, Enum):
    """Message type indicators."""
    CHUNK = "chunk"
    COMPLETE = "complete"

class Priority(int, Enum):
    """Priority levels for context management."""
    CRITICAL = 1  # Preserve across context
    IMPORTANT = 2  # Preserve when possible
    SUPPLEMENTARY = 3  # Drop first when needed

@dataclass
class Header:
    """Message header containing metadata."""
    priority: Priority
    token_count: int
    type: MessageType
    timestamp: float = None

    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = time.time()

    def to_dict(self) -> Dict:
        """Convert header to dictionary format."""
        return {
            "priority": self.priority.value,
            "token_count": self.token_count,
            "type": self.type.value,
            "timestamp": self.timestamp
        }

@dataclass
class Content:
    """Message content with structured information."""
    summary: str
    entities: List[str]
    relationships: List[Dict[str, str]]
    core_data: str

    def to_dict(self) -> Dict:
        """Convert content to dictionary format."""
        return {
            "summary": self.summary,
            "entities": self.entities,
            "relationships": self.relationships,
            "core_data": self.core_data
        }

class Message:
    """Protocol message container."""
    
    def __init__(
        self,
        header: Header,
        content: Content
    ):
        self.header = header
        self.content = content

    @classmethod
    def create(
        cls,
        core_data: str,
        priority: Priority = Priority.IMPORTANT,
        entities: List[str] = None,
        relationships: List[Dict[str, str]] = None,
        summary: str = None
    ) -> 'Message':
        """Create a new message with computed metadata."""
        token_count = cls._estimate_tokens(core_data)
        msg_type = (MessageType.CHUNK if token_count > 2048 
                   else MessageType.COMPLETE)
        
        if summary is None:
            summary = cls._generate_summary(core_data)
            
        header = Header(
            priority=priority,
            token_count=token_count,
            type=msg_type
        )
        
        content = Content(
            summary=summary,
            entities=entities or [],
            relationships=relationships or [],
            core_data=core_data
        )
        
        return cls(header, content)

    def to_dict(self) -> Dict:
        """Convert message to dictionary format."""
        return {
            "header": self.header.to_dict(),
            "content": self.content.to_dict()
        }

    @staticmethod
    def _estimate_tokens(text: str) -> int:
        """Estimate token count for a text string.
        
        This is a simple estimation - replace with actual tokenizer
        implementation for production use.
        """
        return len(text.split()) * 1.3  # Rough estimate

    @staticmethod
    def _generate_summary(text: str, max_words: int = 50) -> str:
        """Generate a concise summary of the text.
        
        Args:
            text: Text to summarize
            max_words: Maximum words in summary
            
        Returns:
            Summarized text string
        """
        words = text.split()
        if len(words) <= max_words:
            return text
        return ' '.join(words[:max_words]) + '...'

class ContextManager:
    """Manages context window and information preservation."""
    
    def __init__(self, max_tokens: int = 4096):
        self.max_tokens = max_tokens
        self.context_buffer: List[Message] = []
        self._current_tokens = 0

    def add_message(self, message: Message) -> None:
        """Add a message to the context buffer with priority handling."""
        new_size = self._current_tokens + message.header.token_count
        
        if new_size > self.max_tokens:
            self._prune_context(new_size - self.max_tokens)
            
        self.context_buffer.append(message)
        self._current_tokens += message.header.token_count
        self._sort_by_priority()

    def get_context(self) -> List[Message]:
        """Get current context buffer."""
        return self.context_buffer

    def clear_context(self) -> None:
        """Clear the context buffer."""
        self.context_buffer = []
        self._current_tokens = 0

    def _prune_context(self, tokens_to_free: int) -> None:
        """Remove low priority messages to free up tokens."""
        # Sort by priority (highest to lowest) and timestamp (newest to oldest)
        sorted_msgs = sorted(
            self.context_buffer,
            key=lambda m: (m.header.priority.value, -m.header.timestamp)
        )
        
        freed_tokens = 0
        keep_msgs = []
        
        for msg in sorted_msgs:
            if (msg.header.priority == Priority.CRITICAL or 
                freed_tokens >= tokens_to_free):
                keep_msgs.append(msg)
            else:
                freed_tokens += msg.header.token_count
                
        self.context_buffer = keep_msgs
        self._current_tokens = sum(m.header.token_count for m in keep_msgs)

    def _sort_by_priority(self) -> None:
        """Sort context buffer by priority and timestamp."""
        self.context_buffer.sort(
            key=lambda m: (m.header.priority.value, -m.header.timestamp)
        )

class SmallContextProtocol:
    """Main protocol implementation for small-context LLMs."""
    
    def __init__(self, max_tokens: int = 4096):
        self.context_manager = ContextManager(max_tokens)
        self.web_browser = WebBrowser()
        
    def process_input(
        self,
        text: str,
        priority: Priority = Priority.IMPORTANT,
        entities: List[str] = None,
        relationships: List[Dict[str, str]] = None
    ) -> Union[Message, List[Message]]:
        """Process input text into protocol message(s)."""
        message = Message.create(
            core_data=text,
            priority=priority,
            entities=entities,
            relationships=relationships
        )
        
        if message.header.type == MessageType.COMPLETE:
            self.context_manager.add_message(message)
            return message
            
        # Handle chunking for large messages
        return self._chunk_message(message)
    
    def browse_web(self, url: str, priority: Priority = Priority.IMPORTANT) -> Message:
        """Browse a webpage and process its content into the context.
        
        Args:
            url: The URL to browse
            priority: Priority level for the web content
            
        Returns:
            Message object containing the processed web content
        """
        # Fetch and extract web content
        web_data = self.web_browser.browse(url)
        
        # Create relationships for the web content
        relationships = [{
            'type': 'source',
            'url': web_data['url']
        }]
        
        # Process the content into a message
        message = Message.create(
            core_data=web_data['content'],
            priority=priority,
            entities=web_data['entities'],
            relationships=relationships,
            summary=web_data['title']
        )
        
        # Add to context
        self.context_manager.add_message(message)
        return message
    
    def get_context(self) -> List[Dict]:
        """Get current context in dictionary format."""
        return [msg.to_dict() for msg in self.context_manager.get_context()]
    
    def clear_context(self) -> None:
        """Clear the current context."""
        self.context_manager.clear_context()
        
    def _chunk_message(self, message: Message) -> List[Message]:
        """Split large message into chunks."""
        chunks = []
        text = message.content.core_data
        chunk_size = 1500  # Target tokens per chunk
        
        while text:
            # Create chunk with reduced content
            chunk_text = self._extract_chunk(text, chunk_size)
            chunk = Message.create(
                core_data=chunk_text,
                priority=message.header.priority,
                entities=message.content.entities,
                relationships=message.content.relationships
            )
            
            chunks.append(chunk)
            self.context_manager.add_message(chunk)
            
            # Remove processed chunk from text
            text = text[len(chunk_text):].strip()
            
        return chunks
    
    @staticmethod
    def _extract_chunk(text: str, target_tokens: int) -> str:
        """Extract a chunk of text targeting specific token count."""
        words = text.split()
        chunk_words = words[:int(target_tokens / 1.3)]  # Rough token estimation
        return ' '.join(chunk_words)
