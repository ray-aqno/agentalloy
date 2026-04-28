# Third-Party Licenses

skillsmith bundles content adapted from third-party open-source projects. This file
records the upstream source, license, and the skill YAML(s) that derive from it.

Per-skill provenance is also stamped in the skill's `change_summary` field.

---

## mattpocock/skills

- Upstream: https://github.com/mattpocock/skills
- Commit: `5fed805a92ddf70dedf1f32c6aadb2a08aaf4d9c` (snapshot date: 2026-04-28)
- License: MIT
- Copyright (c) 2026 Matt Pocock

### Derived skills

| skillsmith YAML | Upstream SKILL.md | Adaptation |
|---|---|---|
| `src/skillsmith/_packs/core/caveman.yaml` | `skills/productivity/caveman/SKILL.md` | Faithful port; partitioned into 5 fragments matching the original section structure. |
| `src/skillsmith/_packs/core/grill-me.yaml` | `skills/productivity/grill-me/SKILL.md` | Upstream prose (~4 lines) preserved verbatim in fragment 2; rationale, example session, and anti-patterns authored by skillsmith. |
| `src/skillsmith/_packs/engineering/zoom-out.yaml` | `skills/engineering/zoom-out/SKILL.md` | Upstream prompt (~1 line) preserved verbatim in fragment 2; rationale, schematic example, and anti-patterns authored by skillsmith. Example uses placeholder terms. |
| `src/skillsmith/_packs/core/test-driven-development.yaml` | `skills/engineering/tdd/SKILL.md` | Existing skill; fragment 8 ("Anti-Pattern: Horizontal Slices" / tracer-bullet rules / per-cycle checklist) and matching `raw_prose` extension adapted from upstream. Fragments 1–7 are pre-existing skillsmith authoring. |
| `src/skillsmith/_packs/core/debugging-strategies.yaml` | `skills/engineering/diagnose/SKILL.md` | Existing skill; fragments 16 ("Build a Feedback Loop First") and 17 ("Phases After the Loop Exists") plus the matching `raw_prose` extension adapted from upstream. Fragments 1–15 are pre-existing skillsmith authoring. |
| `src/skillsmith/_packs/core/planning-and-task-breakdown.yaml` | `skills/engineering/to-issues/SKILL.md` | Existing skill; fragment 14 ("Tracer-Bullet Slices and HITL/AFK Tagging") and matching `raw_prose` extension adapted from upstream. Fragments 1–13 are pre-existing skillsmith authoring. |

### License text

```
MIT License

Copyright (c) 2026 Matt Pocock

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```
