#!/usr/bin/env python3
"""
Version bumping script for cli-FSD project.
Usage: python scripts/bump_version.py [major|minor|patch]
"""

import sys
import os
import re
from pathlib import Path

def read_version(version_file):
    """Read the current version from the version file."""
    with open(version_file, "r") as f:
        content = f.read()
    version_match = re.search(r"__version__ = ['\"]([^'\"]*)['\"]", content, re.M)
    if version_match:
        return version_match.group(1)
    raise ValueError(f"Unable to find version string in {version_file}")

def write_version(version_file, new_version):
    """Write the new version to the version file."""
    with open(version_file, "r") as f:
        content = f.read()
    
    new_content = re.sub(
        r"__version__ = ['\"]([^'\"]*)['\"]",
        f'__version__ = "{new_version}"',
        content,
        re.M
    )
    
    with open(version_file, "w") as f:
        f.write(new_content)

def bump_version(current_version, bump_type):
    """Bump the version according to the specified bump type."""
    major, minor, patch = map(int, current_version.split('.'))
    
    if bump_type == "major":
        major += 1
        minor = 0
        patch = 0
    elif bump_type == "minor":
        minor += 1
        patch = 0
    elif bump_type == "patch":
        patch += 1
    else:
        raise ValueError(f"Unknown bump type: {bump_type}")
    
    return f"{major}.{minor}.{patch}"

def main():
    """Main function for the version bumping script."""
    if len(sys.argv) != 2 or sys.argv[1] not in ["major", "minor", "patch"]:
        print("Usage: python scripts/bump_version.py [major|minor|patch]")
        sys.exit(1)
    
    bump_type = sys.argv[1]
    project_root = Path(__file__).parent.parent
    version_file = project_root / "cli_FSD" / "version.py"
    
    current_version = read_version(version_file)
    new_version = bump_version(current_version, bump_type)
    
    write_version(version_file, new_version)
    print(f"Version bumped from {current_version} to {new_version}")

if __name__ == "__main__":
    main()