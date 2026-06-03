#!/usr/bin/env python3
"""Debug code fence tracking for nextjs file."""
fpath = 'src/agentalloy/_packs/nextjs/nextjs-csp-and-security-headers.yaml'
content = open(fpath).read()
lines = content.split('\n')

in_code = False
for i, line in enumerate(lines):
    stripped = line.strip()
    if stripped.startswith('```'):
        in_code = not in_code
        print(f"Line {i+1}: FENCE -> in_code={in_code} | {stripped[:60]}")
        if i >= 555 and i <= 630:
            print(f"  ^^^ toggled")
