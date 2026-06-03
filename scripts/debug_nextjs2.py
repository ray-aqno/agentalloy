#!/usr/bin/env python3
"""Debug why JSX detection fails for nextjs file."""
import re

fpath = 'src/agentalloy/_packs/nextjs/nextjs-csp-and-security-headers.yaml'
content = open(fpath).read()
lines = content.split('\n')

in_code = False
for i, line in enumerate(lines):
    stripped = line.strip()
    if stripped.startswith('```'):
        in_code = not in_code
        print(f"Line {i+1}: FENCE -> in_code={in_code}")
    if i >= 590 and i <= 620:
        print(f"Line {i+1}: in_code={in_code} | {line[:70]}")
