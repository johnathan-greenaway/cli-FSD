#!/usr/bin/env python3

"""Test script for JSON extraction functionality."""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'cli_FSD'))

from cli_FSD.script_handlers import extract_json_from_response

def test_json_extraction():
    """Test the JSON extraction from various response formats."""
    
    # Test case 1: JSON in markdown code block (the failing case)
    response1 = '''To review the files in the `/RAG-chat` directory, I will create a simple bash script that lists all files and directories within this directory. Here is a JSON object that describes the creation of this script:

```json
{
    "tool": "file_operation",
    "operation": "write",
    "filepath": "/home/icarus/Local-Projects-WSL/RAG-chat/list_files.sh",
    "content": "#!/bin/bash\\n\\n# List all files and directories in the current directory\\nls -la",
    "description": "Create a bash script that lists all files and directories in the /RAG-chat directory."
}
```

This JSON object describes a bash script that will list all files and directories with detailed information.'''

    print("🧪 Testing JSON extraction from markdown response:")
    print("Input:", repr(response1[:100] + "..."))
    
    extracted = extract_json_from_response(response1)
    print("Extracted JSON:", extracted)
    
    if extracted:
        try:
            import json
            parsed = json.loads(extracted)
            print("✅ Successfully parsed JSON:", parsed.get('tool', 'Unknown'))
            return True
        except json.JSONDecodeError as e:
            print("❌ Failed to parse extracted JSON:", e)
            return False
    else:
        print("❌ No JSON extracted")
        return False

def test_multiple_formats():
    """Test various JSON response formats."""
    
    test_cases = [
        # Case 1: Simple markdown block
        {
            'name': 'Markdown JSON block',
            'response': '```json\n{"tool": "test", "value": 123}\n```',
            'expected_tool': 'test'
        },
        
        # Case 2: Plain code block
        {
            'name': 'Plain code block',
            'response': '```\n{"tool": "browse_web", "url": "example.com"}\n```',
            'expected_tool': 'browse_web'
        },
        
        # Case 3: Direct JSON
        {
            'name': 'Direct JSON',
            'response': '{"tool": "generate_script", "operation": "create"}',
            'expected_tool': 'generate_script'
        },
        
        # Case 4: Mixed content
        {
            'name': 'Mixed content',
            'response': 'Here is the solution:\n\n```json\n{"tool": "execute_command", "command": "ls -la"}\n```\n\nThis will work.',
            'expected_tool': 'execute_command'
        }
    ]
    
    print("\n🔬 Testing multiple JSON formats:")
    
    all_passed = True
    
    for i, case in enumerate(test_cases, 1):
        print(f"\nTest {i}: {case['name']}")
        extracted = extract_json_from_response(case['response'])
        
        if extracted:
            try:
                import json
                parsed = json.loads(extracted)
                actual_tool = parsed.get('tool', 'Unknown')
                expected_tool = case['expected_tool']
                
                if actual_tool == expected_tool:
                    print(f"✅ Passed - Tool: {actual_tool}")
                else:
                    print(f"❌ Failed - Expected: {expected_tool}, Got: {actual_tool}")
                    all_passed = False
            except json.JSONDecodeError as e:
                print(f"❌ Failed to parse JSON: {e}")
                all_passed = False
        else:
            print("❌ No JSON extracted")
            all_passed = False
    
    return all_passed

if __name__ == "__main__":
    print("🚀 Testing JSON Extraction Fix")
    print("=" * 50)
    
    # Test the original failing case
    test1_result = test_json_extraction()
    
    # Test multiple formats
    test2_result = test_multiple_formats()
    
    print(f"\n📊 Results:")
    print(f"Original case: {'✅ PASS' if test1_result else '❌ FAIL'}")
    print(f"Multiple formats: {'✅ PASS' if test2_result else '❌ FAIL'}")
    
    if test1_result and test2_result:
        print(f"\n🎉 All tests passed! JSON extraction fix is working.")
    else:
        print(f"\n🚨 Some tests failed. Need further debugging.")