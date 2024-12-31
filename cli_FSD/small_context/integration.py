"""Integration examples for the Small Context Protocol.

This module provides practical examples and utilities for integrating
the Small Context Protocol with LLM systems and other components.
"""

from typing import Dict, List, Any
from .protocol import (
    SmallContextProtocol,
    Priority,
    Message
)

class LLMIntegration:
    """Example integration with LLM systems."""
    
    def __init__(self, max_tokens: int = 4096):
        self.protocol = SmallContextProtocol(max_tokens)
        
    async def process_conversation(
        self,
        messages: List[Dict[str, str]],
        system_context: str = None
    ) -> Dict[str, Any]:
        """Process a conversation with context management.
        
        Args:
            messages: List of message dictionaries with 'role' and 'content'
            system_context: Optional system context/instructions
            
        Returns:
            Processed conversation with managed context
        """
        # Clear previous context
        self.protocol.clear_context()
        
        # Add system context if provided
        if system_context:
            self.protocol.process_input(
                system_context,
                priority=Priority.CRITICAL
            )
        
        # Process each message
        processed_messages = []
        for msg in messages:
            priority = (Priority.IMPORTANT if msg['role'] == 'user'
                      else Priority.SUPPLEMENTARY)
            
            result = self.protocol.process_input(
                msg['content'],
                priority=priority
            )
            
            if isinstance(result, list):
                processed_messages.extend(result)
            else:
                processed_messages.append(result)
        
        return {
            'messages': [m.to_dict() for m in processed_messages],
            'context': self.protocol.get_context()
        }

class FileProcessor:
    """Example integration for processing file content."""
    
    def __init__(self, max_tokens: int = 4096):
        self.protocol = SmallContextProtocol(max_tokens)
    
    def process_file(
        self,
        content: str,
        metadata: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """Process file content with context management.
        
        Args:
            content: File content string
            metadata: Optional file metadata
            
        Returns:
            Processed content with context management
        """
        # Extract entities and relationships from metadata
        entities = []
        relationships = []
        
        if metadata:
            if 'path' in metadata:
                entities.append(f"file:{metadata['path']}")
            if 'type' in metadata:
                entities.append(f"type:{metadata['type']}")
            if 'references' in metadata:
                for ref in metadata['references']:
                    relationships.append({
                        'type': 'references',
                        'source': metadata['path'],
                        'target': ref
                    })
        
        # Process content
        result = self.protocol.process_input(
            content,
            priority=Priority.IMPORTANT,
            entities=entities,
            relationships=relationships
        )
        
        return {
            'processed': result.to_dict() if isinstance(result, Message)
                        else [m.to_dict() for m in result],
            'context': self.protocol.get_context()
        }

class APIIntegration:
    """Example integration for API handling."""
    
    def __init__(self, max_tokens: int = 4096):
        self.protocol = SmallContextProtocol(max_tokens)
    
    async def process_request(
        self,
        endpoint: str,
        method: str,
        data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Process API request with context management.
        
        Args:
            endpoint: API endpoint
            method: HTTP method
            data: Request data
            
        Returns:
            Processed request with context management
        """
        # Create relationships for API context
        relationships = [{
            'type': 'api_call',
            'source': endpoint,
            'method': method
        }]
        
        # Process request data
        result = self.protocol.process_input(
            str(data),
            priority=Priority.IMPORTANT,
            entities=[f"endpoint:{endpoint}", f"method:{method}"],
            relationships=relationships
        )
        
        return {
            'request': result.to_dict() if isinstance(result, Message)
                      else [m.to_dict() for m in result],
            'context': self.protocol.get_context()
        }
