"""Centralized execution manager for handling commands with proper mode checking.

This module provides a unified interface for executing commands, scripts, and tools
based on the current execution mode (safe, autopilot, or normal).
"""

import subprocess
import logging
import os
import tempfile
from typing import Any, Optional, Dict, List, Tuple
from datetime import datetime
from collections import deque
import time

logger = logging.getLogger(__name__)


class CommandQueue:
    """Queue for managing commands in autopilot mode."""
    
    def __init__(self):
        self.queue = deque()
        self.history = []
        self.failed_commands = []
        
    def add(self, command: str, description: str = None):
        """Add a command to the queue."""
        self.queue.append({
            'command': command,
            'description': description or f"Execute: {command[:50]}...",
            'timestamp': datetime.now().isoformat()
        })
        
    def get_next(self) -> Optional[Dict]:
        """Get the next command from the queue."""
        if self.queue:
            return self.queue.popleft()
        return None
        
    def execute_all(self, execution_manager, config) -> List[Dict]:
        """Execute all queued commands."""
        results = []
        while self.queue:
            cmd_info = self.get_next()
            if cmd_info:
                result = execution_manager.execute_command(
                    cmd_info['command'],
                    config,
                    description=cmd_info['description']
                )
                results.append({
                    'command': cmd_info['command'],
                    'result': result,
                    'timestamp': datetime.now().isoformat()
                })
                self.history.append(results[-1])
                
                # Track failures
                if isinstance(result, str) and result.startswith("Error"):
                    self.failed_commands.append(cmd_info)
                    
        return results


class ExecutionManager:
    """Centralized manager for all command and script execution."""
    
    def __init__(self):
        self.execution_log = []
        self.command_queue = CommandQueue()
        self.retry_config = {
            'max_retries': 3,
            'base_delay': 1,  # seconds
            'max_delay': 30,
            'exponential_base': 2
        }
        
    def execute_with_mode(self, command: str, config: Any, **kwargs) -> str:
        """
        Central execution function that respects the current mode.
        
        Args:
            command: Command to execute
            config: Configuration object with mode settings
            **kwargs: Additional arguments like description, script_type, etc.
            
        Returns:
            Command output or error message
        """
        description = kwargs.get('description', f"Execute command: {command[:50]}...")
        script_type = kwargs.get('script_type', 'bash')
        requires_confirmation = kwargs.get('requires_confirmation', True)
        
        # Log the execution attempt
        self._log_execution(command, config.autopilot_mode, config.safe_mode)
        
        # Handle different modes
        if config.autopilot_mode:
            # In autopilot mode, execute without confirmation
            print(f"{config.CYAN}[AUTOPILOT] {description}{config.RESET}")
            return self._execute_command_internal(command, config, script_type=script_type)
            
        elif config.safe_mode:
            # In safe mode, always require confirmation
            if self._get_user_confirmation(command, description, config):
                return self._execute_command_internal(command, config, script_type=script_type)
            else:
                return "Command execution cancelled by user."
                
        else:
            # Normal mode - use requires_confirmation flag
            if requires_confirmation:
                if self._get_user_confirmation(command, description, config):
                    return self._execute_command_internal(command, config, script_type=script_type)
                else:
                    return "Command execution cancelled by user."
            else:
                return self._execute_command_internal(command, config, script_type=script_type)
    
    def execute_command(self, command: str, config: Any, **kwargs) -> str:
        """Execute a shell command with proper mode handling."""
        return self.execute_with_mode(command, config, script_type='bash', **kwargs)
        
    def execute_script(self, script: str, config: Any, **kwargs) -> str:
        """Execute a script with proper mode handling."""
        # Determine script type
        script_type = "python" if script.startswith("#!/usr/bin/env python") else "bash"
        ext = "py" if script_type == "python" else "sh"
        
        # Create temporary file
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        temp_file_path = f".temp_script_{timestamp}.{ext}"
        
        try:
            # Write script to file
            with open(temp_file_path, 'w') as f:
                f.write(script)
            
            # Make executable if bash script
            if script_type == "bash":
                os.chmod(temp_file_path, 0o755)
            
            # Prepare command
            if script_type == "python":
                command = f"python {temp_file_path}"
            else:
                command = f"./{temp_file_path}"
            
            # Execute with mode handling
            return self.execute_with_mode(command, config, 
                                         description=f"Execute {script_type} script",
                                         **kwargs)
        finally:
            # Clean up temp file
            if os.path.exists(temp_file_path):
                try:
                    os.remove(temp_file_path)
                except:
                    pass
    
    def queue_command(self, command: str, description: str = None):
        """Add a command to the execution queue."""
        self.command_queue.add(command, description)
        
    def execute_queue(self, config: Any) -> List[Dict]:
        """Execute all queued commands."""
        if config.autopilot_mode:
            print(f"{config.CYAN}[AUTOPILOT] Executing {len(self.command_queue.queue)} queued commands...{config.RESET}")
            return self.command_queue.execute_all(self, config)
        else:
            print(f"{config.YELLOW}Command queue execution requires autopilot mode.{config.RESET}")
            return []
    
    def execute_with_retry(self, command: str, config: Any, **kwargs) -> str:
        """
        Execute a command with exponential backoff retry logic.
        
        Args:
            command: Command to execute
            config: Configuration object
            **kwargs: Additional arguments
            
        Returns:
            Command output or error message
        """
        max_retries = kwargs.get('max_retries', self.retry_config['max_retries'])
        base_delay = self.retry_config['base_delay']
        max_delay = self.retry_config['max_delay']
        
        for attempt in range(max_retries):
            try:
                result = self.execute_with_mode(command, config, **kwargs)
                
                # Check if result indicates success
                if not (isinstance(result, str) and result.startswith("Error")):
                    return result
                    
                # If it's the last attempt, return the error
                if attempt == max_retries - 1:
                    return result
                    
                # Calculate delay with exponential backoff
                delay = min(base_delay * (self.retry_config['exponential_base'] ** attempt), max_delay)
                print(f"{config.YELLOW}Attempt {attempt + 1} failed. Retrying in {delay} seconds...{config.RESET}")
                time.sleep(delay)
                
            except Exception as e:
                if attempt == max_retries - 1:
                    return f"Error after {max_retries} attempts: {str(e)}"
                    
                delay = min(base_delay * (self.retry_config['exponential_base'] ** attempt), max_delay)
                print(f"{config.YELLOW}Attempt {attempt + 1} failed with exception. Retrying in {delay} seconds...{config.RESET}")
                time.sleep(delay)
                
        return f"Error: Command failed after {max_retries} attempts"
    
    def _execute_command_internal(self, command: str, config: Any, script_type: str = 'bash') -> str:
        """Internal method to actually execute the command."""
        try:
            # Log command execution
            print(f"{config.GREEN}Executing: {command}{config.RESET}")
            
            # Execute command
            process = subprocess.Popen(
                command,
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
                universal_newlines=True
            )
            
            output_lines = []
            error_lines = []
            
            # Stream output
            while True:
                output = process.stdout.readline()
                if output == '' and process.poll() is not None:
                    break
                if output:
                    output_lines.append(output.strip())
                    print(output.strip())
            
            # Check for errors
            stderr = process.stderr.read()
            if stderr:
                error_lines.append(stderr.strip())
                print(f"{config.RED}Error: {stderr}{config.RESET}")
            
            # Wait for process to complete
            return_code = process.wait()
            
            if return_code != 0:
                error_msg = f"Command failed with return code {return_code}"
                if error_lines:
                    error_msg += f"\nErrors:\n" + "\n".join(error_lines)
                return error_msg
                
            return "\n".join(output_lines) if output_lines else "Command executed successfully."
            
        except subprocess.TimeoutExpired:
            return f"Error: Command timed out"
        except Exception as e:
            return f"Error executing command: {str(e)}"
    
    def _get_user_confirmation(self, command: str, description: str, config: Any) -> bool:
        """Get user confirmation for command execution."""
        print(f"\n{config.YELLOW}{description}{config.RESET}")
        print(f"Command: {command}")
        response = input("Do you want to proceed? (yes/no): ").strip().lower()
        return response in ['yes', 'y']
    
    def _log_execution(self, command: str, autopilot: bool, safe_mode: bool):
        """Log command execution for debugging."""
        log_entry = {
            'timestamp': datetime.now().isoformat(),
            'command': command,
            'autopilot': autopilot,
            'safe_mode': safe_mode
        }
        self.execution_log.append(log_entry)
        logger.info(f"Execution logged: {log_entry}")
    
    def get_execution_history(self) -> List[Dict]:
        """Get the execution history."""
        return self.execution_log
    
    def clear_history(self):
        """Clear the execution history."""
        self.execution_log = []
        self.command_queue.history = []


# Global instance for singleton pattern
_execution_manager = None


def get_execution_manager() -> ExecutionManager:
    """Get or create the global execution manager instance."""
    global _execution_manager
    if _execution_manager is None:
        _execution_manager = ExecutionManager()
    return _execution_manager