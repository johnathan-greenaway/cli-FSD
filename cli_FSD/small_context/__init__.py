"""Small Context Protocol package.

This package implements an efficient protocol for managing information
processing in small-context LLMs (2k-8k tokens).

Usage via CLI:
    process-context -i input.txt -p important -e "entity1,entity2" -o output.json
    echo "text" | process-context -p critical > output.json
"""

from .protocol import (
    SmallContextProtocol,
    Message,
    Priority,
    MessageType,
    ContextManager
)

from .integration import (
    LLMIntegration,
    FileProcessor,
    APIIntegration
)

__all__ = [
    'SmallContextProtocol',
    'Message',
    'Priority',
    'MessageType',
    'ContextManager',
    'LLMIntegration',
    'FileProcessor',
    'APIIntegration'
]

# CLI entrypoint
def main():
    from .cli import main as cli_main
    cli_main()
