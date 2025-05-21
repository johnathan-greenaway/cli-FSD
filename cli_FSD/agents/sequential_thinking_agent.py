"""Sequential Thinking Agent for CLI-FSD.

This module provides an agent that implements sequential thinking capabilities
for breaking down complex problems and maintaining context through multiple steps.
"""

import json
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime

# Configure logging
logging.basicConfig(level=logging.INFO,
                   format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class ThoughtData:
    """Data structure for a single thought in the sequential thinking process."""
    
    def __init__(self,
                 thought: str,
                 thought_number: int,
                 total_thoughts: int,
                 next_thought_needed: bool,
                 is_revision: bool = False,
                 revises_thought: Optional[int] = None,
                 branch_from_thought: Optional[int] = None,
                 branch_id: Optional[str] = None,
                 needs_more_thoughts: bool = False):
        self.thought = thought
        self.thought_number = thought_number
        self.total_thoughts = total_thoughts
        self.next_thought_needed = next_thought_needed
        self.is_revision = is_revision
        self.revises_thought = revises_thought
        self.branch_from_thought = branch_from_thought
        self.branch_id = branch_id
        self.needs_more_thoughts = needs_more_thoughts
        self.timestamp = datetime.now().isoformat()

class SequentialThinkingAgent:
    """Agent for implementing sequential thinking capabilities."""
    
    def __init__(self):
        """Initialize the sequential thinking agent."""
        self.thought_history: List[ThoughtData] = []
        self.branches: Dict[str, List[ThoughtData]] = {}
        self.is_enabled = False
        self.allow_llm_choice = False
    
    def enable(self, allow_llm_choice: bool = False) -> None:
        """Enable sequential thinking.
        
        Args:
            allow_llm_choice: Whether to allow the LLM to choose when to use sequential thinking
        """
        self.is_enabled = True
        self.allow_llm_choice = allow_llm_choice
        logger.info("Sequential thinking enabled")
    
    def disable(self) -> None:
        """Disable sequential thinking."""
        self.is_enabled = False
        self.allow_llm_choice = False
        logger.info("Sequential thinking disabled")
    
    def process_thought(self, input_data: Dict[str, Any]) -> Dict[str, Any]:
        """Process a new thought in the sequence.
        
        Args:
            input_data: Dictionary containing thought data
            
        Returns:
            Dictionary containing processing results
        """
        try:
            # Validate required fields
            required_fields = ['thought', 'thoughtNumber', 'totalThoughts', 'nextThoughtNeeded']
            for field in required_fields:
                if field not in input_data:
                    raise ValueError(f"Missing required field: {field}")
            
            # Create thought data object
            thought_data = ThoughtData(
                thought=input_data['thought'],
                thought_number=input_data['thoughtNumber'],
                total_thoughts=input_data['totalThoughts'],
                next_thought_needed=input_data['nextThoughtNeeded'],
                is_revision=input_data.get('isRevision', False),
                revises_thought=input_data.get('revisesThought'),
                branch_from_thought=input_data.get('branchFromThought'),
                branch_id=input_data.get('branchId'),
                needs_more_thoughts=input_data.get('needsMoreThoughts', False)
            )
            
            # Update total thoughts if needed
            if thought_data.thought_number > thought_data.total_thoughts:
                thought_data.total_thoughts = thought_data.thought_number
            
            # Add to history
            self.thought_history.append(thought_data)
            
            # Handle branching
            if thought_data.branch_from_thought and thought_data.branch_id:
                if thought_data.branch_id not in self.branches:
                    self.branches[thought_data.branch_id] = []
                self.branches[thought_data.branch_id].append(thought_data)
            
            # Format the thought for display
            formatted_thought = self._format_thought(thought_data)
            logger.info(formatted_thought)
            
            return {
                'status': 'success',
                'thought_number': thought_data.thought_number,
                'total_thoughts': thought_data.total_thoughts,
                'next_thought_needed': thought_data.next_thought_needed,
                'branches': list(self.branches.keys()),
                'thought_history_length': len(self.thought_history),
                'formatted_thought': formatted_thought
            }
            
        except Exception as e:
            logger.error(f"Error processing thought: {str(e)}")
            return {
                'status': 'error',
                'error': str(e)
            }
    
    def _format_thought(self, thought_data: ThoughtData) -> str:
        """Format a thought for display.
        
        Args:
            thought_data: The thought data to format
            
        Returns:
            Formatted string representation of the thought
        """
        # Determine thought type and context
        if thought_data.is_revision:
            prefix = "🔄 Revision"
            context = f" (revising thought {thought_data.revises_thought})"
        elif thought_data.branch_from_thought:
            prefix = "🌿 Branch"
            context = f" (from thought {thought_data.branch_from_thought}, ID: {thought_data.branch_id})"
        else:
            prefix = "💭 Thought"
            context = ""
        
        # Create header
        header = f"{prefix} {thought_data.thought_number}/{thought_data.total_thoughts}{context}"
        
        # Create border
        border = "─" * (max(len(header), len(thought_data.thought)) + 4)
        
        # Format the thought
        return f"""
┌{border}┐
│ {header} │
├{border}┤
│ {thought_data.thought.ljust(len(border) - 2)} │
└{border}┘"""
    
    def get_thought_history(self) -> List[Dict[str, Any]]:
        """Get the complete thought history.
        
        Returns:
            List of dictionaries containing thought history
        """
        return [
            {
                'thought': t.thought,
                'thought_number': t.thought_number,
                'total_thoughts': t.total_thoughts,
                'next_thought_needed': t.next_thought_needed,
                'is_revision': t.is_revision,
                'revises_thought': t.revises_thought,
                'branch_from_thought': t.branch_from_thought,
                'branch_id': t.branch_id,
                'needs_more_thoughts': t.needs_more_thoughts,
                'timestamp': t.timestamp
            }
            for t in self.thought_history
        ]
    
    def clear_history(self) -> None:
        """Clear the thought history and branches."""
        self.thought_history = []
        self.branches = {}
        logger.info("Thought history cleared") 