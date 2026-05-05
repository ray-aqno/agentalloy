# QA Report: go-testing-idioms

- **Verdict:** revise
- **Reviewer:** independent critic (Claude agent, 2026-05-05)

## R1–R8 findings

- **R1:** Pass. `change_summary` cites pkg.go.dev/testing, go.dev/doc/code#Testing, go.dev/doc/fuzz/, all dated `verified 2026-05-05` and cross-referenced to `fixtures/upstream/curated/go.yaml` topic `testing_idioms` (confirmed line 46–49). Stable stdlib API; tier-appropriate.
- **R2:** N/A — only `testing` and `strings` (stdlib). Imports nonetheless shown in fragments 3, 4, 6, 7, 8 — exemplary.
- **R3:** One violation. Last Verification item (raw_prose line 200 / fragment 10): "Tests are split between `package foo` (internal) and `package foo_test` (external) deliberately, not by accident" — "deliberately" is intent, not mechanically checkable. Drop or rewrite.
- **R4:** Pass. Covers table-driven, `t.Run`, `t.Helper`, `t.Parallel` (with loop-pin caveat), `t.Cleanup`, `t.TempDir`, benchmarks (with `ResetTimer`/`ReportAllocs`/sub-benchmarks/sink), fuzzing (seed corpus + regression path). Anti-patterns enumerate edge cases (helper-defer, global-with-parallel, benchmark dead-code elimination).
- **R5:** Pass. "Go 1.18+ fuzzing" and "Go 1.22+ loop variable scoping" are version-stamped facts; `change_summary` carries `2026-05-05`. Acceptable.
- **R6:** Pass. `change_summary` says "Initial authoring 2026-05-05" — honest, not mislabelled as import.
- **R7:** Pass. Examples use generic `Parse`, `New`, `Server` — schematic, no fabricated paths or domain terms.
- **R8:** Pass. Rationale fragment 1 contains "testing", "test", "table-driven", "subtests", "t.Run", "t.Helper", "benchmarks", "fuzzing", "parallel" — well above the 3-keyword floor; >150 words.

## Technical correctness

- `b.N` runner-chosen, ~1s target — correct (line 138, 345).
- `b.ResetTimer()` after setup — correct placement (line 143, 355).
- Fuzz introduced Go 1.18, corpus path `testdata/fuzz/FuzzXxx/...` — correct (line 161, 174, 376, 391).
- Go 1.22 per-iteration loop var scoping for `for ... range` — correct (line 114, 315). Note (not a defect): the plain `for i := 0; i < b.N; i++` benchmark form was never affected by the old loop-var bug; skill correctly applies the pin discussion only to the `range cases` loop.
- `t.Parallel()` requires opt-in across all peers to actually parallelize — correct.
- `t.Cleanup` LIFO and subtest scoping — correct (line 134, 338).
- `var sink` / `runtime.KeepAlive` to defeat dead-code elimination — correct (line 155, 367, 188, 406).
- All code blocks compile given the surrounding `Parse`/`New`/`Server` are user-supplied stubs.

## Required revisions

1. raw_prose line 200 and fragment 10 (sequence 10): Remove or rewrite the final Verification item. Suggested replacement: `Files declaring 'package foo_test' import the package under test only via its public API (no references to unexported identifiers).` That is grep-checkable. Alternatively, drop the bullet — the package-mode discussion in fragment 2 already covers the choice.

## Summary

Strong, idiomatic, technically accurate Go testing pack. Code compiles, version claims check out, anti-patterns are real failure modes. Single R3 defect: one Verification item is intent-not-observation. Fix that line in both `raw_prose` and fragment 10 and the skill ships.
