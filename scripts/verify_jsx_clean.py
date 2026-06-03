#!/usr/bin/env python3
"""Verify JSX stripping results for Batch A skills."""
import re
from pathlib import Path

packs = Path('/home/nmeyers/dev/agentalloy/src/agentalloy/_packs')
jsx_c = {'Callout','CodeTabs','TabItem','Term','details','import','CopilotBeta'}
jsx_re = re.compile(r'<[A-Z][a-zA-Z0-9]*(?:\s+[^>]*)?/?>')
doc_re = re.compile(r'::note|:::caution|:::warning')

files = [
    packs/'linting/linting-typescript-eslint.yaml',
    packs/'ui-design/ui-design-states-and-variants.yaml',
    packs/'rest/rest-versioning-and-compatibility.yaml',
    packs/'nextjs/nextjs-csp-and-security-headers.yaml',
]

for f in files:
    content = f.read_text()
    lines = content.split('\n')
    code_depth = 0
    prose = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith('```'):
            rest = stripped[3:]
            rest_stripped = rest.strip()
            has_lang = bool(re.match(r'[a-zA-Z]', rest_stripped))
            if has_lang:
                code_depth += 1
            else:
                if code_depth > 0:
                    code_depth -= 1
                else:
                    code_depth += 1
            continue
        if code_depth == 0:
            prose.append(line)

    prose_text = '\n'.join(prose)

    jsx_tags = [t for t in jsx_re.findall(prose_text) if t.split()[0].lstrip('<') in jsx_c]
    doc_markers = doc_re.findall(prose_text)

    status = 'CLEAN' if not jsx_tags and not doc_markers else 'ISSUES'
    print(f'{f.name}: {status}  JSX={jsx_tags}  DOC={doc_markers}')
