# QA — rust-error-handling

**Reviewed:** 2026-05-05
**File:** `src/skillsmith/_packs/rust/rust-error-handling.yaml`
**Verdict:** `revise` (line-level only, 1 nit)

## Rule scorecard

| Rule | Result | Notes |
|------|--------|-------|
| R1 — authoritative sources cited | PASS | Cites std::result, std::option, Book ch09, Rust Reference operator-expr question-mark; verified 2026-05-05 against curated rust.yaml topic `error_handling_and_exceptions`. |
| R2 — non-stdlib names show `use` | PASS | `use thiserror::Error;`, `use anyhow::{Context, Result};` shown in their respective example blocks. `std::io`, `std::num::ParseIntError` also imported. |
| R3 — verification mechanically checkable | PASS | All seven items are concrete shell/cargo invocations (`cargo clippy`, `grep -nE`, `cargo check`). No vague items. |
| R4 — case-space coverage + edge trace | PASS | Walks the missing-`From`-impl edge case explicitly with the compiler error message. Covers Result/Option/`?`/From/thiserror/anyhow/panic decision matrix incl. library vs application split. |
| R5 — version/date stamps | PASS | thiserror 1.x and anyhow 1.x both annotated `(verified 2026-05-05)`. No bare unverified version claims. |
| R6 — honest authorship + community vs stdlib | PASS | `change_summary` says "Initial authoring 2026-05-05" (not "imported"). thiserror/anyhow flagged inline as "community crate ... not stdlib" at first mention in each section. |
| R7 — no fabricated paths | PASS | Examples use generic names (`MyError`, `parse_config`, `load_config`); no invented domain glossary or repo-specific paths. |
| R8 — rationale lexical anchors | PASS | Sequence-1 rationale contains "Rust", "error", "Result", "Option", "?", "panic", "unwrap" — well above the ≥3 floor. Sequence-7 rationale on panic policy contains "panic", "unwrap", "expect", "error", "library", "Result". |

## Technical sanity check

- `?` desugar to `From::from(e)` early return — accurate per Rust Reference operator-expr question-mark. Match arms shown match the reference desugaring (modulo `Try` trait machinery, which is the right level of abstraction for a teaching example).
- `thiserror::Error` derive: `#[derive(Error)]` does generate `impl std::error::Error` with `source()` driven by `#[from]`/`#[source]`; `#[from]` does generate the `From` impl. Accurate.
- `anyhow::Result<T>` is `Result<T, anyhow::Error>` — accurate (type alias in `anyhow` crate root).
- `anyhow::Context` trait — accurate. It is implemented for both `Result<T, E>` (where `E: StdError + Send + Sync + 'static`) AND `Option<T>` (mapping `None` to an error). Skill only demonstrates the `Result` form, which is fine; no incorrect claim made.
- `Box<dyn Error>` vs typed errors guidance — accurate, matches community consensus and Book ch09.
- `panic!` library-vs-application policy — accurate.
- `#[from]` semantics — accurate.

## Code-block compile check

All blocks compile under stable Rust assuming the obvious surrounding context (a `User` struct with `is_admin: bool` and `email: Option<String>` for sequence 2; a `Config` type and `toml` dep for sequence 5). These are pedagogical placeholders, not fabricated paths — R7 unaffected.

## Findings (1 nit, line-level)

**N1 — `map_err` example discards the source error and hardcodes `0`** (sequence 6, raw_prose line ~146).

```rust
let n: u32 = raw.trim().parse()
    .map_err(|e| MyError::InvalidPort(0))?;
```

The closure binds `e` but never uses it, and `InvalidPort(0)` hardcodes `0` rather than reflecting the input. This compiles but reads as a copy-paste artifact and slightly undercuts the section's claim that `map_err` "preserves the chain structure" — here the source `ParseIntError` is dropped on the floor. Two acceptable fixes:

- Suppress the unused binding and explain: `.map_err(|_e| MyError::InvalidPort(0))?` with a comment that the original parse error is intentionally discarded because the variant carries domain meaning, not the raw cause; OR
- Make the example faithful: introduce a `Parse(ParseIntError)` variant and use `.map_err(MyError::Parse)?`, or have `InvalidPort` carry the offending string: `InvalidPort(String)` and `.map_err(|_| MyError::InvalidPort(raw.trim().to_string()))?`.

Either is a one-line fix. No structural rework.

## Verdict

`revise` — apply N1 line-level fix and ship. All R1–R8 pass; technical claims accurate; verification fragment is excellent.
