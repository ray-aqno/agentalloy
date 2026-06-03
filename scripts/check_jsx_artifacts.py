#!/usr/bin/env python3
"""Check for JSX artifacts in Batch B skill files."""
import re
from pathlib import Path

files = [
    Path("src/agentalloy/_packs/nextjs/nextjs-isr-and-revalidation.yaml"),
    Path("src/agentalloy/_packs/data-engineering/data-engineering-dbt-incremental.yaml"),
    Path("src/agentalloy/_packs/webhooks/webhooks-idempotency.yaml"),
]

for fpath in files:
    content = fpath.read_text()
    print(f"=== {fpath} ===")
    
    # Check for details tag
    for i, line in enumerate(content.split('\n'), 1):
        if '<details' in line or '</details>' in line:
            print(f"  line {i}: details tag: {line.strip()[:80]}")
        if ':::tip' in line or ':::info' in line or ':::note' in line or ':::caution' in line or ':::warning' in line:
            print(f"  line {i}: docusaurus marker: {line.strip()[:80]}")
    print()
