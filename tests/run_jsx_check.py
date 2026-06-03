"""Quick JSX check for Batch C files."""
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


def extract_jsx_tags(content: str):
    """Return all JSX-like tags found in prose (outside code blocks)."""
    lines = content.split('\n')
    jsx_re = re.compile(r'</?[A-Za-z][a-zA-Z0-9]*(?:\s+[^>]*)?/?>')
    code_depth = 0
    prose_lines = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith('```'):
            rest = stripped[3:]
            rest_stripped = rest.strip()
            has_language = bool(re.match(r'[a-zA-Z]', rest_stripped))
            if has_language:
                code_depth += 1
            else:
                if code_depth > 0:
                    code_depth -= 1
                else:
                    code_depth += 1
            continue
        if code_depth == 0:
            prose_lines.append(line)
    prose = '\n'.join(prose_lines)
    return jsx_re.findall(prose)


def check_file(filepath):
    """Check a single YAML file for JSX artifacts. Returns list of hits."""
    content = filepath.read_text(encoding="utf-8")
    tags = extract_jsx_tags(content)
    jsx_components = [
        tag for tag in tags if tag.split()[0].lstrip("<") in JSX_COMPONENTS
    ]
    # Also check for Docusaurus markers
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
            jsx_components.append(m.group(0))
    return jsx_components


def check_all_jsx_in_prose(filepath):
    """Check for ANY JSX-like tags in prose, not just known components."""
    content = filepath.read_text(encoding="utf-8")
    lines = content.split('\n')
    jsx_re = re.compile(r'</?[A-Za-z][a-zA-Z0-9]*(?:\s+[^>]*)?/?>')
    code_depth = 0
    issues = []
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith('```'):
            rest = stripped[3:]
            rest_stripped = rest.strip()
            has_language = bool(re.match(r'[a-zA-Z]', rest_stripped))
            if has_language:
                code_depth += 1
            else:
                if code_depth > 0:
                    code_depth -= 1
                else:
                    code_depth += 1
            continue
        if code_depth == 0:
            for m in jsx_re.finditer(line):
                tag = m.group(0)
                tag_name = tag.split()[0].lstrip('<')
                # Skip standard HTML elements
                standard_html = {
                    'a', 'abbr', 'acronym', 'address', 'area', 'article', 'aside',
                    'audio', 'b', 'base', 'bdi', 'bdo', 'big', 'blink', 'blockquote',
                    'body', 'br', 'button', 'canvas', 'caption', 'center', 'cite',
                    'code', 'col', 'colgroup', 'content', 'data', 'datalist', 'dd',
                    'del', 'details', 'dfn', 'dialog', 'dir', 'div', 'dl', 'dt',
                    'element', 'em', 'embed', 'fieldset', 'figcaption', 'figure',
                    'footer', 'form', 'frame', 'frameset', 'h1', 'h2', 'h3', 'h4',
                    'h5', 'h6', 'head', 'header', 'hgroup', 'hr', 'html', 'i',
                    'iframe', 'img', 'input', 'ins', 'kbd', 'label', 'legend', 'li',
                    'link', 'main', 'map', 'mark', 'marquee', 'menu', 'menuitem',
                    'meta', 'meter', 'nav', 'nobr', 'noembed', 'noframes',
                    'noscript', 'object', 'ol', 'optgroup', 'option', 'output',
                    'p', 'param', 'picture', 'plaintext', 'pre', 'progress', 'q',
                    'rp', 'rt', 'rtc', 'ruby', 's', 'samp', 'script', 'section',
                    'select', 'shadow', 'slot', 'small', 'source', 'spacer', 'span',
                    'strike', 'strong', 'style', 'sub', 'summary', 'sup', 'table',
                    'tbody', 'td', 'template', 'textarea', 'tfoot', 'th', 'thead',
                    'time', 'title', 'tr', 'track', 'tt', 'u', 'ul', 'var',
                    'video', 'wbr', 'xml',
                }
                if tag_name not in standard_html:
                    issues.append((i+1, tag))
    return issues


print("=" * 60)
print("JSX Artifact Check — Batch C (navistone)")
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
    
    # Check known JSX components
    jsx = check_file(filepath)
    if jsx:
        print(f"  JSX COMPONENTS FOUND: {jsx}")
        all_ok = False
    else:
        print(f"  Known JSX components: CLEAN")
    
    # Check for ANY JSX-like tags in prose
    all_jsx = check_all_jsx_in_prose(filepath)
    if all_jsx:
        print(f"  ANY JSX tags in prose:")
        for line_num, tag in all_jsx:
            print(f"    Line {line_num}: {tag}")
        all_ok = False
    
    # Check for leftover fragments from JSX stripping
    content = filepath.read_text(encoding="utf-8")
    lines = content.split('\n')
    code_depth_check = 0
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith('```'):
            rest = stripped[3:]
            rest_stripped = rest.strip()
            has_language = bool(re.match(r'[a-zA-Z]', rest_stripped))
            if has_language:
                code_depth_check += 1
            else:
                if code_depth_check > 0:
                    code_depth_check -= 1
                else:
                    code_depth_check += 1
            continue
        if code_depth_check == 0:
            # Look for patterns like `.yml'>` (leftover from JSX attributes)
            if re.search(r'\.\w+\'?>\s*$', stripped):
                print(f"  LEFTOVER JSX fragment at line {i+1}: {stripped[:80]}...")
                all_ok = False

print("\n" + "=" * 60)
if all_ok:
    print("RESULT: ALL CLEAN")
else:
    print("RESULT: ISSUES FOUND")
print("=" * 60)
