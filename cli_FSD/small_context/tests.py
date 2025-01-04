"""Tests for the Small Context Protocol implementation."""

import unittest
from .protocol import (
    SmallContextProtocol,
    Priority,
    Message,
    MessageType
)

class TestSmallContextProtocol(unittest.TestCase):
    """Test cases for protocol implementation."""
    
    def setUp(self):
        self.protocol = SmallContextProtocol(max_tokens=4096)
    
    def test_message_creation(self):
        """Test basic message creation."""
        text = "Test message content"
        message = Message.create(
            core_data=text,
            priority=Priority.IMPORTANT
        )
        
        self.assertEqual(message.content.core_data, text)
        self.assertEqual(message.header.priority, Priority.IMPORTANT)
        self.assertEqual(message.header.type, MessageType.COMPLETE)
        self.assertTrue(message.content.summary)
        self.assertIsInstance(message.content.entities, list)
        self.assertIsInstance(message.content.relationships, list)
    
    def test_context_management(self):
        """Test context management and pruning."""
        # Add messages until context is full
        for i in range(10):
            text = f"Test message {i} " * 100  # Create large message
            self.protocol.process_input(
                text,
                priority=Priority.SUPPLEMENTARY
            )
        
        # Add critical message
        critical_text = "Critical message"
        critical_msg = self.protocol.process_input(
            critical_text,
            priority=Priority.CRITICAL
        )
        
        context = self.protocol.get_context()
        
        # Verify critical message is preserved
        self.assertTrue(
            any(msg['content']['core_data'] == critical_text 
                for msg in context)
        )
    
    def test_message_chunking(self):
        """Test large message chunking."""
        # Create large text that should be chunked
        large_text = "Test message " * 1000
        
        result = self.protocol.process_input(large_text)
        
        # Verify chunking occurred
        self.assertTrue(isinstance(result, list))
        self.assertTrue(len(result) > 1)
        
        # Verify each chunk
        for chunk in result:
            self.assertTrue(
                chunk.header.token_count < 2048,
                "Chunk size should be within token limit"
            )
            
    def test_priority_ordering(self):
        """Test priority-based message ordering."""
        # Add messages with different priorities
        messages = [
            ("Low priority", Priority.SUPPLEMENTARY),
            ("High priority", Priority.CRITICAL),
            ("Medium priority", Priority.IMPORTANT)
        ]
        
        for text, priority in messages:
            self.protocol.process_input(text, priority=priority)
            
        context = self.protocol.get_context()
        
        # Verify ordering
        priorities = [msg['header']['priority'] for msg in context]
        self.assertEqual(
            priorities,
            sorted(priorities),  # Should be ordered from lowest to highest
            "Messages should be ordered by priority"
        )
    
    def test_context_pruning(self):
        """Test context pruning behavior."""
        # Fill context with supplementary messages
        for i in range(5):
            self.protocol.process_input(
                f"Supplementary message {i} " * 50,
                priority=Priority.SUPPLEMENTARY
            )
            
        # Add important message
        important_text = "Important message"
        self.protocol.process_input(
            important_text,
            priority=Priority.IMPORTANT
        )
        
        # Add large critical message that forces pruning
        critical_text = "Critical message " * 100
        self.protocol.process_input(
            critical_text,
            priority=Priority.CRITICAL
        )
        
        context = self.protocol.get_context()
        
        # Verify critical and important messages are preserved
        context_data = [msg['content']['core_data'] for msg in context]
        self.assertTrue(
            critical_text in context_data,
            "Critical message should be preserved"
        )
        self.assertTrue(
            important_text in context_data,
            "Important message should be preserved when possible"
        )

if __name__ == '__main__':
    unittest.main()
