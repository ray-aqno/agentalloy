import yaml, re
from pathlib import Path

packs = Path('/home/nmeyers/dev/agentalloy/src/agentalloy/_packs')
files = [
    packs/'linting/linting-typescript-eslint.yaml',
    packs/'ui-design/ui-design-states-and-variants.yaml',
    packs/'rest/rest-versioning-and-compatibility.yaml',
    packs/'nextjs/nextjs-csp-and-security-headers.yaml',
]
jsx_c = {'Callout','CodeTabs','TabItem','Term','details','import','CopilotBeta'}
jsx_re = re.compile(r'<[A-Z][a-zA-Z0-9]*(?:\s+[^>]*)?/?>')
doc_re = re.compile(r'::note|:::caution|:::warning')

for f in files:
    data = yaml.safe_load(f.read_text())
    print(f'{f.name}: {len(data.get("fragments",[]))} frags')
    raw = data.get('raw_prose', '')
    raw_jsx = [t for t in jsx_re.findall(raw) if t.split()[0].lstrip('<') in jsx_c]
    raw_doc = doc_re.findall(raw)
    for frag in data.get('fragments', []):
        content = frag.get('content', '')
        f_jsx = [t for t in jsx_re.findall(content) if t.split()[0].lstrip('<') in jsx_c]
        f_doc = doc_re.findall(content)
        if f_jsx or f_doc:
            print(f'  frag {frag.get("sequence")}: JSX={f_jsx} DOC={f_doc}')
    if raw_jsx or raw_doc:
        print(f'  raw: JSX={raw_jsx} DOC={raw_doc}')
