# Skill Naming Conventions

**skill_id:** sys-skill-naming
**category:** tooling
**always_apply:** false
**phase_scope:**
**category_scope:** tooling
**author:** navistone
**change_summary:** initial authoring 2026-05-04 — conventions pack, codifies skill_id, file-name, canonical_name, change_summary, and pack-name conventions used across the skillsmith corpus.

Names are queryable. A skill_id, a canonical_name, a pack name — each is hit by the routing classifier, the CLI install picker, and the human reviewer. Inconsistent naming defeats all three. This skill codifies the conventions.

## skill_id

Kebab-case, lowercase, ASCII only. Two to four hyphen-separated words. The id is the load-bearing identifier — it appears in `pack.yaml`, in DB foreign keys, in retrieval logs, and in filenames. Once shipped, do not rename — supersession is the right tool.

System skills MUST start with `sys-`. The bootstrap validator enforces this at ingest. Domain and workflow skills MUST NOT start with `sys-`.

Patterns — pick the most specific that fits:

- `<domain>-<aspect>-patterns` for collections of patterns: `webhook-patterns`, `python-async-patterns`, `fastapi-middleware-patterns`. The `-patterns` suffix signals a multi-pattern reference skill.
- `<domain>-<aspect>` for single-topic skills: `git-workflow-and-versioning`, `code-review-excellence`. No `-patterns` suffix when the skill teaches one thing.
- `sys-<rule-or-procedure>` for system skills: `sys-skill-authoring-rules`, `sys-r1-tiered-sourcing`. The `sys-` prefix is mandatory; the rest is descriptive.

Anti-patterns:

- `webhooks` (too generic — collides with the pack name)
- `webhook-patterns-v2` (versioning belongs in `change_summary`, not the id)
- `WebhookPatterns` (not kebab-case)
- `webhook_patterns` (underscore — kebab-case only)

## File names

A skill's source file is `<skill_id>.md` for system skills (bootstrap path) or `<skill_id>.yaml` for domain and workflow skills (install_pack path). The file name MUST match the `skill_id` exactly — no path drift. The pack.yaml `file:` field references this name.

System skill markdown for the `meta` and `conventions` packs lives at `src/skillsmith/_packs/<pack>/<skill_id>.md` even though the bootstrap loader does not require pack co-location. Co-location is organizational, not technical.

## canonical_name

Title-case, human-readable, descriptive. Length: roughly four to twelve words. Acronyms keep their conventional casing (`HMAC`, `JWT`, `OAuth`, `API`).

The canonical_name appears in the install picker, the routing trace, and the QA review surface. Make it scannable — a developer skimming a list of fifteen skills should be able to pick the right one in under three seconds.

Patterns:

- Reference skill: `Webhook Patterns (HMAC Signing, Replay Protection, FastAPI)`. Parenthetical adds the discriminating sub-topics.
- Single-topic skill: `Git Workflow and Versioning`. No parenthetical.
- System skill: `Skill Authoring Rules (R1–R8)`. Parenthetical signals the rule range.

## change_summary

One paragraph or one structured `change_summary:` block. Required content:

- Authorship date in ISO format (`2026-05-04`).
- One-sentence scope statement: what does this skill cover, and what does it NOT cover?
- For imported content: source path or URL plus the fragment range that is verbatim, per R6.
- For revisions: what changed since the previous version and why.

Anti-patterns: `Initial commit` (no scope), `Update skill` (no diff), `Imported from upstream` without naming the upstream (R6 violation).

## Pack names

Lowercase, kebab-case where multi-word, no version suffix. The pack name appears in `pack.yaml` `name:` and is the directory name under `_packs/`. Names: `core`, `engineering`, `meta`, `conventions`, `webhooks`, `python`, `fastapi-middleware`. Avoid `webhooks-v1` — versions belong in `pack.yaml` `version:`.

Single-word packs are preferred when one word covers the topic (`webhooks`, `python`, `react`). Multi-word kebab-case is acceptable when the topic genuinely needs disambiguation (`shadcn-ui`, `react-native`, `spring-boot`).

## domain_tags

See `sys-skill-tagging-rules` for the full tagging ruleset. Tags follow kebab-case lowercase ASCII conventions matching skill_ids.

## Verified

- skill_id format enforced by `src/skillsmith/bootstrap.py:152` (verified 2026-05-04).
- File-name match required by `src/skillsmith/install/subcommands/install_pack.py:215` (verified 2026-05-04).
- canonical_name patterns observed across `experiments/skill-tax/skills/*.yaml` (verified 2026-05-04).
