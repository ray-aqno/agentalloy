#!/usr/bin/env python3
"""Debug code fence detection."""
import re

fpath = 'src/agentalloy/_packs/nextjs/nextjs-csp-and-security-headers.yaml'
content = open(fpath).read()
lines = content.split('\n')

# Check lines around the code fence at 583
for i in range(580, min(590, len(lines))):
    stripped = lines[i].strip()
    print(f"Line {i+1}: startswith('```')={stripped.startswith('```')} | repr={repr(lines[i][:80])}")

print()

# Check if the content actually has ``` or different encoding
for i, line in enumerate(lines):
    stripped = line.strip()
    if '```' in stripped or '````' in stripped:
        print(f"Line {i+1}: has backticks: {repr(line[:80])}")
