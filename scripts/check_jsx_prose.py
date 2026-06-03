#!/usr/bin/env python3
"""Check JSX elements in prose vs code blocks for a YAML file."""
import re
import sys

def check_file(fpath):
    content = open(fpath).read()
    lines = content.split('\n')
    
    # Track code block depth
    # In this YAML format:
    # - ``` (just backticks) toggles code block state
    # - ```language is always an opening fence (closes previous if any, opens new)
    code_depth = 0
    jsx_prose = []
    
    for i, line in enumerate(lines):
        stripped = line.strip()
        
        if stripped.startswith('```'):
            rest = stripped[3:]
            # Check if it's a language specifier (opening fence)
            # Language can be followed by filename, title, etc.
            rest_stripped = rest.strip()
            has_language = bool(re.match(r'[a-zA-Z]', rest_stripped))
            
            if has_language:
                # Opening fence - increases depth
                code_depth += 1
            else:
                # Just backticks - toggles depth
                if code_depth > 0:
                    code_depth -= 1
                else:
                    code_depth += 1
            continue
        
        if code_depth == 0:
            # In prose
            for m in re.finditer(r'<[A-Z][a-zA-Z0-9]*[^>]*/?>', line):
                jsx_prose.append((i+1, m.group(0)[:60]))
            for m in re.finditer(r'::note|:::caution|:::warning', line):
                jsx_prose.append((i+1, m.group(0)))
    
    return jsx_prose

for fpath in sys.argv[1:]:
    print(f"=== {fpath.split('/')[-1]} ===")
    results = check_file(fpath)
    if not results:
        print("  (clean)")
    else:
        for lineno, jsx in results:
            print(f"  Line {lineno}: {jsx}")
    print()
