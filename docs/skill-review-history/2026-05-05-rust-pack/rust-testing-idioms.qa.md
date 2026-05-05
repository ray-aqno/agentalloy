# QA — rust-testing-idioms.yaml

**Reviewer:** independent critic
**Date:** 2026-05-05
**Verdict:** **approve**

## R1–R8 results

| Rule | Result | Notes |
|------|--------|-------|
| R1 | PASS | Cites Book ch11, Reference attributes/testing, Cargo Book Tests, all `(verified 2026-05-05)` against `fixtures/upstream/curated/rust.yaml`. |
| R2 | PASS | `use proptest::prelude::*;`, `use criterion::{black_box, criterion_group, criterion_main, Criterion};`, `use tempfile::tempdir;`, `use std::sync::OnceLock;`, `use std::num::ParseIntError;`, `use mycrate::parse_config;` — every non-stdlib name imported once. |
| R3 | PASS | All 9 verification items are mechanically checkable (grep regexes, `cargo test` exit codes, file-presence checks). No "deliberately"/"where appropriate"/"correctly" intent phrasings. The Go pack failure mode ("deliberately, not by accident") does not recur here. |
| R4 | PASS | Covers `#[test]`, `#[cfg(test)]`, integration `tests/`, doc tests (with all 4 modifiers), `#[ignore]`, `#[should_panic]`, `Result`-returning tests, proptest, criterion bench. The `pub(crate)` edge case in integration tests is walked end-to-end including the `error[E0603]` message. |
| R5 | PASS | `OnceLock` Rust 1.70 dated; doc-test modifier list dated; sources dated. |
| R6 | PASS | proptest, quickcheck, criterion, tempfile all annotated "community-canonical, not stdlib". `change_summary` says "Initial authoring" — accurate, this is not an import. |
| R7 | PASS | `mycrate`, `parse_config`, `double`, `encode/decode` are obviously schematic placeholders. No fabricated crate names presented as canonical. |
| R8 | PASS | Rationale fragment contains "test" (many), "cargo test", "`#[test]`", "doc test/doc comments", "integration", "Rust", "`#[cfg(test)]`", "`tests/`", "`proptest`", "`unwrap`". Well over 3 obvious-query keywords; >180 words. |

## Rust technical accuracy

- `#[cfg(test)]` excluding test code from release — **accurate**.
- Each `tests/foo.rs` compiles as its own crate — **accurate** (Cargo Book confirms).
- Doc tests run as separate processes wrapped in implicit `fn main()` — **accurate** per rustdoc reference.
- Doc-test modifiers `ignore` / `no_run` / `compile_fail` / `should_panic` — **accurate** per rustdoc reference. (Other modifiers `edition2018`/`edition2021`/`test_harness` exist but are out-of-scope; omission acceptable.)
- `OnceLock` stabilized in Rust 1.70.0 (June 2023) — **accurate**.
- `cargo test -- --nocapture`, `--test-threads=1`, `--ignored` flag positions (after `--`) — **accurate**.
- `cargo test --test parser` (before `--`, applies to cargo) — **accurate**.
- `#[bench]` requires nightly; criterion is the stable substitute — **accurate**.
- `proptest!` macro shape with `#[test]` inside and `prop_assert_eq!` — **accurate**.
- `criterion::black_box` re-export is accurate; the parenthetical "now in `std::hint::black_box` on stable" is accurate (stabilized 1.66.0). The example imports from `criterion`, which compiles cleanly.
- Float `==` anti-pattern with `0.1 + 0.2 != 0.3` — **accurate**.
- `tests/common.rs` vs `tests/common/mod.rs` — **accurate** per Cargo Book.
- `assert_eq!`, `assert_ne!`, `assert!` produce diff-style messages — **accurate**.
- `index_panics_past_end`: indexing `Vec<i32>` past end panics with message containing "index out of bounds" — **accurate**.
- All code blocks compile (assuming the `mycrate::{parse_config, encode, decode, double}` placeholders).

## Minor observations (non-blocking)

- The `black_box` parenthetical could note that `criterion`'s re-export is what the example uses, but the current phrasing is not misleading.
- The verification regex `'== .*\.0\|\.0 =='` is a heuristic (will miss `0.5 == x`); acceptable as a starting filter, and the item is mechanically checkable as written.

## Verdict

**approve** — ship as-is. No revisions required.
