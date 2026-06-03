"""JSX check on parsed YAML content (handles literal block scalars properly)."""
import re
import yaml
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PACKS_DIR = REPO_ROOT / "src" / "agentalloy" / "_packs"

JSX_COMPONENTS = {
    "Callout", "CodeTabs", "TabItem", "Term", "details", "import", "CopilotBeta",
    "Lightbox", "FAQ", "File", "SnowflakeColumn", "Incrementalpredicates",
    "Tabs", "Figure", "Example", "TipBad", "TipGood",
}

BATCH_C_FILES = [
    PACKS_DIR / "data-engineering" / "data-engineering-dbt-models.yaml",
    PACKS_DIR / "webhooks" / "webhooks-signature-verification.yaml",
]

# Standard HTML tags to ignore
STANDARD_HTML = {
    'a', 'abbr', 'acronym', 'address', 'area', 'article', 'aside', 'audio',
    'b', 'base', 'bdi', 'bdo', 'big', 'blink', 'blockquote', 'body', 'br',
    'button', 'canvas', 'caption', 'center', 'cite', 'code', 'col', 'colgroup',
    'content', 'data', 'datalist', 'dd', 'del', 'details', 'dfn', 'dialog',
    'dir', 'div', 'dl', 'dt', 'element', 'em', 'embed', 'fieldset',
    'figcaption', 'figure', 'footer', 'form', 'frame', 'frameset', 'h1', 'h2',
    'h3', 'h4', 'h5', 'h6', 'head', 'header', 'hgroup', 'hr', 'html', 'i',
    'iframe', 'img', 'input', 'ins', 'kbd', 'label', 'legend', 'li', 'link',
    'main', 'map', 'mark', 'marquee', 'menu', 'menuitem', 'meta', 'meter',
    'nav', 'nobr', 'noembed', 'noframes', 'noscript', 'object', 'ol',
    'optgroup', 'option', 'output', 'p', 'param', 'picture', 'plaintext',
    'pre', 'progress', 'q', 'rp', 'rt', 'rtc', 'ruby', 's', 'samp', 'script',
    'section', 'select', 'shadow', 'slot', 'small', 'source', 'spacer', 'span',
    'strike', 'strong', 'style', 'sub', 'summary', 'sup', 'table', 'tbody',
    'td', 'template', 'textarea', 'tfoot', 'th', 'thead', 'time', 'title',
    'tr', 'track', 'tt', 'u', 'ul', 'var', 'video', 'wbr', 'xml',
}

JSX_RE = re.compile(r'</?[A-Za-z][a-zA-Z0-9]*(?:\s+[^>]*)?/?>')


def check_content_for_jsx(label, content):
    """Check content for JSX artifacts. Returns list of (location, tag) tuples."""
    if not content:
        return []
    issues = []

    # Track code block depth
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
            for m in JSX_RE.finditer(line):
                tag = m.group(0)
                tag_name = tag.split()[0].lstrip('<')
                if tag_name not in STANDARD_HTML:
                    issues.append((label, i+1, tag))

    # Check for Docusaurus markers
    for m in re.finditer(r'::note|:::caution|:::warning', content):
        pos = m.start()
        lines_before = content[:pos].split('\n')
        code_depth = 0
        for line in lines_before[:-1]:
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
        if code_depth == 0:
            issues.append((label, 0, m.group(0)))

    return issues


def check_for_leftover_jsx(label, content):
    """Check for leftover fragments from JSX stripping."""
    if not content:
        return []
    issues = []
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
            # Look for patterns like `.yml'>` (leftover from JSX attributes)
            if re.search(r'\.\w+\'?>\s*$', stripped):
                issues.append((label, i+1, f"LEFTOVER: {stripped[:80]}"))
    return issues


print("=" * 60)
print("JSX Artifact Check — Batch C (navistone)")
print("Checking parsed YAML content (raw_prose + fragments)")
print("=" * 60)

all_ok = True
for filepath in BATCH_C_FILES:
    print(f"\n--- {filepath.relative_to(REPO_ROOT)} ---")

    # Check YAML validity
    try:
        data = yaml.safe_load(filepath.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            print(f"  FAIL: Not a valid YAML dict")
            all_ok = False
            continue
        print(f"  YAML: OK")
    except Exception as e:
        print(f"  FAIL: YAML parse error: {e}")
        all_ok = False
        continue

    # Check raw_prose
    raw = data.get("raw_prose", "")
    issues = check_content_for_jsx("raw_prose", raw)
    issues += check_for_leftover_jsx("raw_prose", raw)
    if issues:
        print(f"  raw_prose issues:")
        for label, line, tag in issues:
            print(f"    Line {line}: {tag}")
        all_ok = False
    else:
        print(f"  raw_prose: CLEAN")

    # Check fragments
    fragments = data.get("fragments", [])
    frag_issues = []
    for frag in fragments:
        content = frag.get("content", "")
        seq = frag.get("sequence", "?")
        issues = check_content_for_jsx(f"fragment seq={seq}", content)
        issues += check_for_leftover_jsx(f"fragment seq={seq}", content)
        frag_issues.extend(issues)

    if frag_issues:
        print(f"  fragment issues:")
        for label, line, tag in frag_issues:
            print(f"    {label} Line {line}: {tag}")
        all_ok = False
    else:
        print(f"  fragments: CLEAN")

print("\n" + "=" * 60)
if all_ok:
    print("RESULT: ALL CLEAN")
else:
    print("RESULT: ISSUES FOUND")
print("=" * 60)
