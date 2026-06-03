#!/usr/bin/env python3
"""Check which JSX elements are in prose vs code blocks."""
fpath = 'src/agentalloy/_packs/nextjs/nextjs-csp-and-security-headers.yaml'
content = open(fpath).read()
lines = content.split('\n')

# Show lines around 545-548
for i in range(543, min(548, len(lines))):
    print(f"Line {i+1}: {repr(lines[i])}")

print()

# Check for JSX elements outside code blocks
in_code = False
for i, line in enumerate(lines, 1):
    stripped = line.strip()
    if stripped.startswith('```'):
        in_code = not in_code
        print(f"Line {i}: FENCE (now in_code={in_code})")
    if '<Script' in line and not in_code:
        print(f"Line {i}: PROSE <Script> -> {stripped[:80]}")
