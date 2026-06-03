#!/usr/bin/env python3
"""Debug Figure regex with actual file content."""
import re

# Read original content from git
import subprocess
result = subprocess.run(
    ['git', 'show', 'HEAD:src/agentalloy/_packs/ui-design/ui-design-states-and-variants.yaml'],
    capture_output=True, text=True, cwd='/home/nmeyers/dev/agentalloy'
)
content = result.stdout

# Find the Figure block starting around line 256
lines = content.split('\n')
for i, line in enumerate(lines):
    if '<Figure hint="Hover over this button' in line and i > 200:
        print(f"Found Figure at line {i+1}:")
        # Show context
        for j in range(i, min(i+15, len(lines))):
            print(f"  {j+1}: {lines[j][:80]}")
        print()
        
        # Try to find closing </Figure>
        for j in range(i+1, min(i+50, len(lines))):
            if '</Figure>' in lines[j]:
                print(f"Found </Figure> at line {j+1}")
                print(f"  {j+1}: {lines[j][:80]}")
                break
        
        # Try regex match
        block = '\n'.join(lines[i:i+50])
        m = re.search(r'<Figure[^>]*>.*?</Figure>', block, re.DOTALL)
        if m:
            print(f"Regex matched! End pos: {m.end()}")
            print(f"Match ends with: {repr(block[m.end()-20:m.end()])}")
        else:
            print("Regex did NOT match")
        break
