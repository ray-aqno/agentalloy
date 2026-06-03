#!/usr/bin/env python3
"""Debug Figure regex with actual file content."""
import re
import subprocess

# Get original content from git
result = subprocess.run(
    ['git', 'show', 'HEAD:src/agentalloy/_packs/ui-design/ui-design-states-and-variants.yaml'],
    capture_output=True, text=True, cwd='/home/nmeyers/dev/agentalloy'
)
content = result.stdout

# Find all Figure blocks
print("=== Finding Figure blocks ===")
for i, m in enumerate(re.finditer(r'<Figure[^>]*>.*?</Figure>', content, re.DOTALL)):
    start_line = content[:m.start()].count('\n') + 1
    end_line = content[:m.end()].count('\n') + 1
    print(f"Figure {i+1}: lines {start_line}-{end_line}")
    print(f"  Start: {repr(content[m.start():m.start()+60])}")
    print(f"  End: {repr(content[m.end()-40:m.end()])}")
    print()

# Find all Example blocks
print("=== Finding Example blocks ===")
for i, m in enumerate(re.finditer(r'<Example[^>]*>.*?</Example>', content, re.DOTALL)):
    start_line = content[:m.start()].count('\n') + 1
    end_line = content[:m.end()].count('\n') + 1
    print(f"Example {i+1}: lines {start_line}-{end_line}")
    print(f"  Start: {repr(content[m.start():m.start()+60])}")
    print(f"  End: {repr(content[m.end()-40:m.end()])}")
    print()
