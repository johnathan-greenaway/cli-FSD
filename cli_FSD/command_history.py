import os
import json
from typing import List, Optional
from difflib import get_close_matches

class CommandHistory:
    def __init__(self, history_file: str = ".command_history.json"):
        self.history_file = history_file
        self.commands: List[str] = []
        self.current_index = -1
        self.load_history()

    def load_history(self):
        """Load command history from file."""
        if os.path.exists(self.history_file):
            try:
                with open(self.history_file, 'r') as f:
                    self.commands = json.load(f)
            except json.JSONDecodeError:
                self.commands = []
        self.current_index = len(self.commands)

    def save_history(self):
        """Save command history to file."""
        with open(self.history_file, 'w') as f:
            json.dump(self.commands, f)

    def add_command(self, command: str):
        """Add a command to history."""
        if command and (not self.commands or command != self.commands[-1]):
            self.commands.append(command)
            self.current_index = len(self.commands)
            self.save_history()

    def get_previous(self) -> Optional[str]:
        """Get previous command in history."""
        if self.current_index > 0:
            self.current_index -= 1
            return self.commands[self.current_index]
        return None

    def get_next(self) -> Optional[str]:
        """Get next command in history."""
        if self.current_index < len(self.commands) - 1:
            self.current_index += 1
            return self.commands[self.current_index]
        return None

    def fuzzy_search(self, query: str, n: int = 5) -> List[str]:
        """Perform fuzzy search on command history."""
        if not query:
            return []
        return get_close_matches(query, self.commands, n=n, cutoff=0.6)

    def clear_history(self):
        """Clear command history."""
        self.commands = []
        self.current_index = -1
        self.save_history() 