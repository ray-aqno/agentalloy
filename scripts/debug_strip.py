#!/usr/bin/env python3
"""Debug the actual stripping process."""
import re
import subprocess

# Get original content
result = subprocess.run(
    ['git', 'show', 'HEAD:src/agentalloy/_packs/ui-design/ui-design-states-and-variants.yaml'],
    capture_output=True, text=True, cwd='/home/nmeyers/dev/agentalloy'
)
original = result.stdout

# Apply strip_jsx logic
def strip_jsx(text):
    # Figure regex
    text = re.sub(
        r'<Figure[^>]*>\s*\n(.*?)\s*\n\s*</Figure>',
        r'\1',
        text,
        flags=re.DOTALL
    )
    return text

stripped = strip_jsx(original)

# Check results
print(f"Original <Figure count: {original.count('<Figure')}")
print(f"Original </Figure count: {original.count('</Figure')}")
print(f"Stripped <Figure count: {stripped.count('<Figure')}")
print(f"Stripped </Figure count: {stripped.count('</Figure')}")

# Show what happened to Figure 4 (around line 256)
orig_lines = original.split('\n')
stripped_lines = stripped.split('\n')

# Find where Figure 4 was in original (line 256)
print(f"\nOriginal line 256: {orig_lines[255][:60]}")
print(f"Original line 273: {orig_lines[272][:60]}")

# In stripped, find the corresponding area
# The stripped file should be shorter
print(f"\nOriginal lines: {len(orig_lines)}")
print(f"Stripped lines: {len(stripped_lines)}")

# Check if Figure 4 content is still in stripped
if '<Figure hint="Hover over this button' in stripped:
    print("\nFigure 4 STILL PRESENT in stripped!")
    idx = stripped.index('<Figure hint="Hover over this button')
    print(f"Position: {idx}")
    print(f"Context: {repr(stripped[idx:idx+100])}")
else:
    print("\nFigure 4 was stripped correctly")

# Also check for remaining Figure tags
for i, line in enumerate(stripped_lines):
    if '<Figure' in line:
        print(f"Remaining <Figure at stripped line {i+1}: {line[:60]}")
