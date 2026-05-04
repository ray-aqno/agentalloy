Your job is to author new skills using the methodology in
docs/SKILL-AUTHORING-METHODOLOGY.md, applying the local-LLM routing
established post-pilot.

Read these in order before starting:
1. docs/SKILL-AUTHORING-METHODOLOGY.md (your playbook — read end-to-end)
2. docs/skillsmith-authoring-reference.md (schema + R1–R8 contract)
3. docs/PACK-AUTHORING.md (pack-level structure)
4. docs/skillsmith-pack-inventory.md (priority list — pick from here)
5. docs/skillsmith-model-selection.md (model-routing rationale)
6. experiments/skill-tax/reviews/_POC_FINAL.md §1, §4, §9 (pilot findings)
7. experiments/skill-tax/skills/webhook-patterns.yaml (gold-standard reference)
8. prompts/skill-author/README.md (the per-tier prompt index)

Verify each CLI command in SKILL-AUTHORING-METHODOLOGY.md Appendix B
against the actual code before relying on it. If any invocation differs
from what the methodology doc says, update the methodology doc.

For every skill you author, do this exactly:

1. Identify the pack tier from docs/skillsmith-pack-inventory.md or
   pack.yaml.
2. Look up the matching tier-prompt at prompts/skill-author/<tier>.md.
3. Layer that tier-prompt on top of fixtures/skill-authoring-agent.md
   when running the local authoring agent. The tier-prompt's source
   policy (fetch / no-fetch) and refuse-clauses are non-optional.
4. Use the local model recommended in SKILL-AUTHORING-METHODOLOGY.md
   §2.1a for that tier. Do not substitute a smaller model.
5. After QA gate, before ingest, apply the §3.4a stop-the-line gate:
   inspect the verification fragment for quoted source snippets with
   date-stamps. If absent and the author was a local model, manually
   route to pending-revision/ regardless of the gate's verdict.

Priority queue by : skillsmith-pack-inventory.md


Stop and ask before:
- Running any --force ingest
- Running reembed --all
- Deprecating an existing skill
- Any QA verdict that hits needs-human/
- Authoring a skill at protocol or domain tier when fetch fails or
  the canonical doc URL has been deprecated
- Promoting a skill whose verification fragment has uncited claims

Report after each phase: what you did, what tests passed, what's
pending operator review. Specifically:

- Phase 1 (design): which cognitive shape the skill targets, which
  tier prompt you'll use, which canonical sources you'll cite
- Phase 2 (authoring): which local model produced the YAML, which
  tier prompt was layered, whether mandatory fetches succeeded
- Phase 3 (QA gate): the verdict, blocking_issues addressed, bounce
  count, whether §3.4a stop-the-line gate flagged anything
- Phase 4 (ingest): the SkillVersion ID, change_summary text
- Phase 5 (embed): confirmation that fragments are no longer zero-vector
- Phase 6 (retrieval verify): the queries tested, the top-K hits
  returned, any tag/vector/filter misses
- Phase 7 (promote): pack manifest update, semver bump, commit hash

For the first 2–3 packs you author, treat every skill as calibration:
operator reviews every fragment before commit. After calibration, the
routing rule above can run with less per-skill operator time but the
§3.4a stop-the-line gate remains permanent for any local-author skill.
