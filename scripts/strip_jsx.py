#!/usr/bin/env python3
"""Strip framework-specific JSX artifacts from YAML skill files.

Phase 3 (JSX Stripping) — Batch A: Complex JSX
Handles: ::note, :::caution, :::warning, <Tabs>, <TabItem>, <Figure>,
         <Example>, <TipBad>, <TipGood>, <Callout>, <Term>,
         <import />, <CopilotBeta />
"""

import re
from pathlib import Path


def strip_jsx(text: str) -> str:
    """Strip JSX artifacts from prose text.

    IMPORTANT: This operates on prose content only. It should NOT be applied
    to content inside fenced code blocks (``` ... ```).
    """

    # 1. Handle Docusaurus-style callout blocks (with optional indentation)
    # ::note blocks
    text = re.sub(
        r'::note\s*\n(.*?)\s*:::',
        lambda m: '> **Note:** ' + m.group(1).strip().replace('\n\n', '\n'),
        text,
        flags=re.DOTALL
    )
    # :::caution blocks
    text = re.sub(
        r':::caution\s*\n(.*?)\s*:::',
        lambda m: '> **Warning:** ' + m.group(1).strip().replace('\n\n', '\n'),
        text,
        flags=re.DOTALL
    )
    # :::warning blocks
    text = re.sub(
        r':::warning\s*\n(.*?)\s*:::',
        lambda m: '> **Warning:** ' + m.group(1).strip().replace('\n\n', '\n'),
        text,
        flags=re.DOTALL
    )

    # 2. Handle <details>/<summary> blocks (with optional attributes)
    text = re.sub(
        r'<details[^>]*>\s*\n\s*<summary[^>]*>(.*?)</summary>\s*\n\s*(.*?)\s*\n\s*</details>',
        lambda m: f'\n## {m.group(1).strip()}\n\n{m.group(2).strip()}\n',
        text,
        flags=re.DOTALL
    )

    # 3. Handle <Tabs>/<TabItem> blocks
    def replace_tabs(match):
        full = match.group(0)
        tab_items = []
        pattern = r'<TabItem[^>]*value="([^"]*)"[^>]*>(.*?)</TabItem>'
        for m in re.finditer(pattern, full, re.DOTALL):
            label = m.group(1)
            content = m.group(2).strip()
            tab_items.append((label, content))
        if not tab_items:
            return match.group(0)
        result = ''
        for label, content in tab_items:
            result += f'\n```{label}\n{content}\n```\n'
        return result

    text = re.sub(r'<Tabs[^>]*>.*?</Tabs>', replace_tabs, text, flags=re.DOTALL)

    # 4. Handle <Figure>...</Figure> blocks (presentation wrapper, just unwrap)
    text = re.sub(
        r'<Figure[^>]*>\s*\n(.*?)\s*\n\s*</Figure>',
        r'\1',
        text,
        flags=re.DOTALL
    )

    # 5. Handle <Example>...</Example> blocks
    # Just unwrap - the content is already formatted code
    text = re.sub(
        r'<Example[^>]*>\s*\n(.*?)\s*\n\s*</Example>',
        r'\1',
        text,
        flags=re.DOTALL
    )

    # 6. Handle <TipBad>...</TipBad> blocks
    # Also strip inner {<>...<>/} JSX fragment syntax
    def replace_tip_bad(match):
        content = match.group(1).strip()
        content = re.sub(r'\{\s*<>\s*(.*?)\s*</>\s*\}', r'\1', content, flags=re.DOTALL)
        return '> **Bad:** ' + content

    text = re.sub(r'<TipBad[^>]*>(.*?)</TipBad>', replace_tip_bad, text, flags=re.DOTALL)

    # 7. Handle <TipGood>...</TipGood> blocks
    def replace_tip_good(match):
        content = match.group(1).strip()
        content = re.sub(r'\{\s*<>\s*(.*?)\s*</>\s*\}', r'\1', content, flags=re.DOTALL)
        return '> **Good:** ' + content

    text = re.sub(r'<TipGood[^>]*>(.*?)</TipGood>', replace_tip_good, text, flags=re.DOTALL)

    # 8. Handle inline <Term id="...">...</Term>
    text = re.sub(r'<Term[^>]*>(.*?)</Term>', r'\1', text)

    # 9. Handle <import ... />
    text = re.sub(r'<import[^>]*/>', '', text)

    # 10. Handle <CopilotBeta ... />
    text = re.sub(r'<CopilotBeta[^>]*/>', '', text)

    # 11. Handle <Callout type="info">...</Callout>
    text = re.sub(
        r'<Callout[^>]*type="info"[^>]*>\s*\n?\s*(.*?)\s*\n?\s*</Callout>',
        r'> **Note:** \1',
        text,
        flags=re.DOTALL
    )

    # 12. Handle <Callout type="warning">...</Callout>
    text = re.sub(
        r'<Callout[^>]*type="warning"[^>]*>\s*\n?\s*(.*?)\s*\n?\s*</Callout>',
        r'> **Warning:** \1',
        text,
        flags=re.DOTALL
    )

    # 13. Handle <CodeTabs>...</CodeTabs> (similar to Tabs)
    text = re.sub(r'<CodeTabs[^>]*>.*?</CodeTabs>', '', text, flags=re.DOTALL)

    # 14. Handle <Lightbox ... /> self-closing tags (Docusaurus image embeds)
    text = re.sub(r'<Lightbox[^>]*/>', '', text)

    # 15. Handle <a href="...">text</a> — strip the tag but keep the text content
    # Uses non-greedy .*? with DOTALL to handle multi-line and backslash-escaped quotes
    text = re.sub(r'<a\s+href=".*?"[^>]*>(.*?)\s*</a>', r'\1', text, flags=re.DOTALL)

    # 15b. Handle <a href='...'>text</a> — same with single quotes
    text = re.sub(r"<a\s+href='.*?'[^>]*>(.*?)\s*</a>", r'\1', text, flags=re.DOTALL)

    # 16. Handle leftover closing </a> tags (from partial stripping)
    text = re.sub(r'</a\s*>', '', text, flags=re.IGNORECASE)

    # 17. Handle <Link href="...">text</Link> — strip the tag but keep the text content
    text = re.sub(r'<Link\s+href="[^"]*"\s*>(.*?)\s*</Link>', r'\1', text, flags=re.DOTALL)

    # 18. Handle leftover fragments like `.yml'>` — clean up stray attribute closures
    text = re.sub(r"\s*'\s*>", '', text)

    return text


def process_file(filepath: Path) -> bool:
    """Process a single YAML file. Returns True if changed."""
    content = filepath.read_text()

    # Process the ENTIRE file content at once (not splitting on fragments:)
    # This handles JSX blocks that span the raw_prose/fragments boundary
    new_content = strip_jsx(content)

    if new_content == content:
        return False

    filepath.write_text(new_content)
    return True


def verify_file(filepath: Path) -> list[str]:
    """Verify a file has no remaining JSX artifacts. Returns list of issues."""
    content = filepath.read_text()
    issues = []

    # Check for JSX component tags in prose (outside code blocks)
    import re
    lines = content.split('\n')
    code_depth = 0
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith('```'):
            rest = stripped[3:]
            has_lang = bool(re.match(r'[a-zA-Z]', rest.strip()))
            if has_lang:
                code_depth += 1
            else:
                if code_depth > 0:
                    code_depth -= 1
                else:
                    code_depth += 1
            continue
        if code_depth == 0:
            for m in re.finditer(r'<[A-Z][a-zA-Z0-9]*', line):
                tag = m.group(0)
                tag_name = tag.lstrip('<').split()[0]
                jsx_components = {
                    'Callout', 'CodeTabs', 'TabItem', 'Term', 'File',
                    'SnowflakeColumn', 'Incrementalpredicates',
                    'Tabs', 'Figure', 'Example', 'TipBad', 'TipGood',
                }
                if tag_name in jsx_components:
                    issues.append(f"Line {i+1}: {tag}")

            for m in re.finditer(r'::note|:::caution|:::warning', line):
                issues.append(f"Line {i+1}: {m.group(0)}")

    return issues


def main():
    files = [
        Path('src/agentalloy/_packs/linting/linting-typescript-eslint.yaml'),
        Path('src/agentalloy/_packs/ui-design/ui-design-states-and-variants.yaml'),
        Path('src/agentalloy/_packs/rest/rest-versioning-and-compatibility.yaml'),
        Path('src/agentalloy/_packs/nextjs/nextjs-csp-and-security-headers.yaml'),
    ]

    for f in files:
        if not f.exists():
            print(f"NOT FOUND: {f.name}")
            continue
        print(f"Processing: {f.name}")
        changed = process_file(f)
        print(f"  {'CHANGED' if changed else 'no changes'}")

    # Verification
    print("\n--- Verification ---")
    all_clean = True
    for f in files:
        if not f.exists():
            continue
        issues = verify_file(f)
        if issues:
            print(f"  {f.name}: ISSUES:")
            for issue in issues:
                print(f"    {issue}")
            all_clean = False
        else:
            print(f"  {f.name}: CLEAN")

    return 0 if all_clean else 1


if __name__ == '__main__':
    exit(main())
