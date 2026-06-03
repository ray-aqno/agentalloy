#!/usr/bin/env python3
"""Quick test for strip_jsx changes."""
import sys
sys.path.insert(0, '/home/nmeyers/dev/agentalloy/scripts')
from strip_jsx import strip_jsx

test_cases = [
    # Basic JSX stripping
    ('<Tabs><TabItem label="React">React content</TabItem></Tabs>', 'React content'),
    ('<Callout type="info">Info text</Callout>', '> **Note:** Info text'),
    # <a> tag stripping (paired)
    ('<a href="https://example.com">Click here</a>', 'Click here'),
    # Standalone <a> tag (no closing tag)
    ('via <a href="https://brew.sh/">Homebrew', 'via Homebrew'),
    # <Lightbox> stripping
    ('<Lightbox src="/img/test.png" title="test"/>', ''),
    # .yml'> artifact on its own line
    ('.yml\'>', ''),
    # <Link> tag stripping
    ('<Link href="https://example.com">Link text</Link>', 'Link text'),
]

passed = 0
failed = 0
for i, (input_text, expected) in enumerate(test_cases):
    result = strip_jsx(input_text)
    if result == expected:
        print(f'Test {i+1}: PASS')
        passed += 1
    else:
        print(f'Test {i+1}: FAIL')
        print(f'  Input:    {repr(input_text)}')
        print(f'  Expected: {repr(expected)}')
        print(f'  Got:      {repr(result)}')
        failed += 1

print(f'\n{passed}/{passed+failed} tests passed')
sys.exit(0 if failed == 0 else 1)
