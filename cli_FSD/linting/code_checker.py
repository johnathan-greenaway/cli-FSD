import os
import sys
from pylint.lint import Run
from pylint.reporters import JSONReporter
import io
from flake8.api import legacy as flake8
import rich
from rich.console import Console
from rich.progress import Progress, SpinnerColumn
from rich.panel import Panel
from rich.syntax import Syntax

console = Console()

class CodeChecker:
    def __init__(self):
        self.console = Console()
        
    def lint_code(self, code: str, language: str, is_autopilot: bool = False) -> dict:
        """Lint code using appropriate linter."""
        results = {
            'errors': [],
            'warnings': [],
            'style_issues': []
        }
        
        with Progress(
            SpinnerColumn(),
            *Progress.get_default_columns(),
            transient=True
        ) as progress:
            task = progress.add_task("[cyan]Linting code...", total=None)
            
            if language.lower() in ['python', 'py']:
                results = self._lint_python(code)
            elif language.lower() in ['bash', 'sh']:
                results = self._lint_shell(code, is_autopilot)
                
            progress.update(task, completed=True)
            
        return results
    
    def _lint_python(self, code: str) -> dict:
        """Lint Python code using Pylint and Flake8."""
        results = {
            'errors': [],
            'warnings': [],
            'style_issues': []
        }
        
        # Create temporary file
        temp_file = '_temp_lint.py'
        try:
            with open(temp_file, 'w') as f:
                f.write(code)
            
            # Run Pylint with JSON reporter
            json_reporter = JSONReporter()
            run = Run([temp_file], reporter=json_reporter, do_exit=False)
            
            # Process Pylint messages
            for message in json_reporter.messages:
                if message.category in ('error', 'fatal'):
                    results['errors'].append(f"Line {message.line}: {message.message}")
                elif message.category == 'warning':
                    results['warnings'].append(f"Line {message.line}: {message.message}")
                else:
                    results['style_issues'].append(f"Line {message.line}: {message.message}")
            
            # Run Flake8
            style_guide = flake8.get_style_guide()
            flake8_report = style_guide.check_files([temp_file])
            
            # Add Flake8 results
            for entry in flake8_report.get_statistics(''):
                results['style_issues'].append(entry)
                
        finally:
            if os.path.exists(temp_file):
                os.remove(temp_file)
                
        return results
    
    def _lint_shell(self, code: str, is_autopilot: bool = False) -> dict:
        """Lint shell scripts using basic checks and shellcheck if available."""
        results = {
            'errors': [],
            'warnings': [],
            'style_issues': []
        }
        
        # Basic shell script validation
        lines = code.split('\n')
        for i, line in enumerate(lines, 1):
            # Check for basic syntax errors
            if line.strip():
                if line.count('"') % 2 != 0 and line.count("'") % 2 != 0:
                    results['errors'].append(f"Line {i}: Unmatched quotes")
                if line.strip().endswith('\\') and i == len(lines):
                    results['errors'].append(f"Line {i}: Line continuation at end of file")
                if '`' in line:
                    results['warnings'].append(f"Line {i}: Consider using $() instead of backticks")
        
        # Check for shellcheck
        shellcheck_available = os.system('which shellcheck > /dev/null 2>&1') == 0
        if not shellcheck_available:
            results['style_issues'].append(
                "Note: shellcheck not found - advanced shell script linting unavailable"
            )
            return results
            
        # Create temporary file for shellcheck
        temp_file = '_temp_lint.sh'
        try:
            with open(temp_file, 'w') as f:
                f.write(code)
                
            # Run shellcheck with appropriate settings based on mode
            import subprocess
            cmd = ['shellcheck']
            if is_autopilot:
                # In autopilot mode, only show errors (ignore warnings and style issues)
                cmd.extend(['-S', 'error', '-e', 'SC2148'])  # Exclude shebang warning in autopilot mode
            else:
                # In normal mode, show warnings and above
                cmd.extend(['-S', 'warning'])
            cmd.append(temp_file)
            
            process = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=False
            )
            
            # Process shellcheck output
            if process.stdout:
                for line in process.stdout.split('\n'):
                    line = line.strip()
                    if not line:
                        continue
                    if 'error' in line.lower():
                        results['errors'].append(line)
                    elif 'warning' in line.lower():
                        results['warnings'].append(line)
                    else:
                        results['style_issues'].append(line)
                    
        except Exception as e:
            results['warnings'].append(f"Shellcheck error: {str(e)}")
            
        finally:
            if os.path.exists(temp_file):
                os.remove(temp_file)
                
        return results
    
    def display_results(self, results: dict, code: str, language: str):
        """Display linting results in a formatted way."""
        # Show code with syntax highlighting
        self.console.print("\n[bold]Code Analysis[/bold]")
        self.console.print(Panel(
            Syntax(code, language, theme="monokai"),
            title="Source Code"
        ))
        
        # Show results in organized sections
        has_issues = False
        
        if results['errors']:
            has_issues = True
            self.console.print("\n[bold red]Critical Issues:[/bold red]")
            for error in results['errors']:
                self.console.print(f"❌ {error}")
                
        if results['warnings']:
            has_issues = True
            self.console.print("\n[bold yellow]Warnings:[/bold yellow]")
            for warning in results['warnings']:
                self.console.print(f"⚠️  {warning}")
        
        # Only show style issues if there are actual style issues (not just notes)
        style_issues = [issue for issue in results['style_issues'] 
                       if not issue.startswith('Note:')]
        if style_issues:
            has_issues = True
            self.console.print("\n[bold blue]Style Suggestions:[/bold blue]")
            for issue in style_issues:
                self.console.print(f"ℹ️  {issue}")
        
        # Show notes separately and last
        notes = [issue for issue in results['style_issues'] 
                if issue.startswith('Note:')]
        if notes:
            self.console.print("\n[bold cyan]Notes:[/bold cyan]")
            for note in notes:
                self.console.print(f"📝 {note}")
        
        if not has_issues:
            self.console.print("\n[bold green]No issues found! ✨[/bold green]")
