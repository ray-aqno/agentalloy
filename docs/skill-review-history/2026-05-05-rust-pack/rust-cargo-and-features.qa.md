# QA Report: rust-cargo-and-features

- **Verdict:** approve
- **Reviewer:** independent critic (Claude agent, 2026-05-05)

## R1–R8 findings
- R1: PASS — change_summary cites doc.rust-lang.org/cargo (index, manifest, features, workspaces, semver) with `(verified 2026-05-05)` and ties back to fixtures/upstream/curated/rust.yaml `packaging_and_dependency_management`.
- R2: N/A — TOML/shell only, no language imports needed.
- R3: PASS — every Verification item is a one-line shell check (`cargo build`, `grep -nE '"\*"'`, `git ls-files Cargo.lock`, `cargo tree --duplicates`, `cargo deny check`, `grep -n 'resolver'`, `cargo publish --dry-run`). Last item ("No feature *removes* behavior") is borderline-vague but framed as a reviewable post-condition with concrete locus (`#[cfg(feature = ...)]` blocks); acceptable.
- R4: PASS — covers Cargo.toml structure, additive feature design, workspaces with inheritance, lockfile-for-libraries, SemVer + version operators, profiles. Walks the unification edge case (crate A enables `serde/std`, crate B `no_std`) end-to-end.
- R5: PASS — `(verified 2026-05-05)` stamps on workspace inheritance Rust 1.64+ (line 100, 301), feature syntax reference (line 81, 284), lockfile-for-libraries 2023 guidance (line 138, 342), version-requirements reference (line 150, 357).
- R6: PASS — change_summary states "Initial authoring 2026-05-05"; honest scaffold authorship.
- R7: PASS — all crate names (`serde`, `tokio`, `serde_json`, `proptest`, `cc`) are canonical; example crate `my_crate` is generic.
- R8: PASS — rationale fragment seq 1 contains "cargo", "Cargo.toml", "features", "workspace", "dependency"; seq 5 contains "Cargo.lock", "lockfile", "cargo update", "workspace".

## Technical correctness
- Caret semantics for 1.x, 0.x, 0.0.x (line 152, 359): correct per Cargo SemVer reference.
- Tilde `~1.2.3` ≡ `>=1.2.3, <1.3.0` (line 153, 360): correct.
- `dep:` and `?/` feature syntax (lines 84–85, 287–288): correct; explanation of the implicit-feature footgun is accurate.
- Workspace metadata inheritance landed in cargo 1.64 / Rust 1.64 (Sept 2022) — line 100, 301: correct.
- Feature unification description (line 87, 290): correct.
- `cargo yank` semantics (line 158, 374): correct (hides from new resolves, tarball preserved).
- `panic = "abort"` profile flag and library caveat (line 180, 399): correct.
- Resolver-2 statement at line 134/335 ("Single-crate 2021 and 2024 edition projects get resolver 2 automatically") is correct for single packages; workspaces still need explicit `resolver = "2"` even on edition 2021, which the skill already enforces in the example and Verification checklist. No correction needed.
- TOML blocks (lines 23–56, 72–79, 102–130, 164–178, 275–281, 303–331, 383–397): all parse.
- `cargo update --precise X.Y.Z -p crate_name` (line 140, 344): correct flag order accepted by cargo.

## Required revisions
None. (Optional polish: the Verification item "No feature *removes* behavior" could be tightened to a `rg '#\[cfg\(not\(feature' src/` style check, but it remains reviewable as written.)

## Summary
The skill is technically accurate across every load-bearing claim — caret/tilde semantics, `dep:`/`?/` feature syntax, workspace inheritance Rust 1.64+, feature unification, `cargo yank`, lockfile-for-libraries 2023 guidance. R1–R8 all satisfied; verification items are mechanically checkable and TOML examples parse. Approve as-is.
