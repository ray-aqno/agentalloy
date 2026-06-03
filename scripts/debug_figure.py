#!/usr/bin/env python3
"""Debug Figure regex matching."""
import re

# Simulated content similar to the YAML
content = """  <Figure hint="Hover over this button to see the background color change">

  <Example>
    {
      <div className="grid place-items-center">
        <button className="rounded-full bg-sky-500 px-5 py-2 text-sm leading-5 font-semibold text-white hover:bg-sky-700">
          Save changes
        </button>
      </div>
    }
  </Example>

  ```html
  <!-- [!code classes:hover:bg-sky-700] -->
  <button class="bg-sky-500 hover:bg-sky-700 ...">Save changes</button>
  ```

  </Figure>"""

print("=== Original ===")
print(content)
print()

# Test Figure regex
pattern = r'<Figure[^>]*>\s*\n(.*?)\s*\n\s*</Figure>'
m = re.search(pattern, content, re.DOTALL)
if m:
    print("=== MATCH ===")
    print(f"Full match: {repr(m.group(0)[:100])}...")
    print(f"Group 1: {repr(m.group(1)[:100])}...")
else:
    print("=== NO MATCH ===")

# Try a more flexible pattern
pattern2 = r'<Figure[^>]*>.*?</Figure>'
m2 = re.search(pattern2, content, re.DOTALL)
if m2:
    print("\n=== MATCH2 ===")
    print(f"Full match: {repr(m2.group(0)[:100])}...")
else:
    print("\n=== NO MATCH2 ===")
