"""Command-line interface for the Small Context Protocol."""

import argparse
import json
import sys
from typing import Dict, Any

from .protocol import SmallContextProtocol, Priority

def parse_priority(priority_str: str) -> Priority:
    """Convert priority string to Priority enum."""
    priority_map = {
        'critical': Priority.CRITICAL,
        'important': Priority.IMPORTANT,
        'supplementary': Priority.SUPPLEMENTARY
    }
    return priority_map.get(priority_str.lower(), Priority.IMPORTANT)

def process_input(args: argparse.Namespace) -> Dict[str, Any]:
    """Process input using the protocol."""
    protocol = SmallContextProtocol(max_tokens=args.max_tokens)
    
    # Read input
    if args.input_file:
        with open(args.input_file, 'r') as f:
            text = f.read()
    else:
        text = sys.stdin.read()
    
    # Parse entities and relationships if provided
    entities = args.entities.split(',') if args.entities else []
    relationships = []
    if args.relationships:
        try:
            relationships = json.loads(args.relationships)
        except json.JSONDecodeError:
            print("Error: Relationships must be valid JSON", file=sys.stderr)
            sys.exit(1)
    
    # Process through protocol
    result = protocol.process_input(
        text,
        priority=parse_priority(args.priority),
        entities=entities,
        relationships=relationships
    )
    
    # Format output
    if isinstance(result, list):
        return {
            'chunks': [msg.to_dict() for msg in result],
            'context': protocol.get_context()
        }
    else:
        return {
            'message': result.to_dict(),
            'context': protocol.get_context()
        }

def main():
    """Main CLI entrypoint."""
    parser = argparse.ArgumentParser(
        description='Process text using the Small Context Protocol'
    )
    
    parser.add_argument(
        '-i', '--input-file',
        help='Input file path (if not provided, reads from stdin)'
    )
    
    parser.add_argument(
        '-p', '--priority',
        choices=['critical', 'important', 'supplementary'],
        default='important',
        help='Message priority level'
    )
    
    parser.add_argument(
        '-e', '--entities',
        help='Comma-separated list of entities'
    )
    
    parser.add_argument(
        '-r', '--relationships',
        help='JSON string of relationship objects'
    )
    
    parser.add_argument(
        '-t', '--max-tokens',
        type=int,
        default=4096,
        help='Maximum tokens for context window'
    )
    
    parser.add_argument(
        '-o', '--output-file',
        help='Output file path (if not provided, prints to stdout)'
    )
    
    args = parser.parse_args()
    
    # Process input
    result = process_input(args)
    
    # Output result
    output = json.dumps(result, indent=2)
    if args.output_file:
        with open(args.output_file, 'w') as f:
            f.write(output)
    else:
        print(output)

if __name__ == '__main__':
    main()
