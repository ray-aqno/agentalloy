# QA Report: rust-ownership-and-borrowing

- **Verdict:** approve
- **Reviewer:** independent critic (Claude agent, 2026-05-05)

## R1–R8 findings

- **R1 PASS** — change_summary cites book ch04, reference/lifetime-elision, std::cell, std::rc, std::sync::Arc, all marked `verified 2026-05-05` and cross-checked against `fixtures/upstream/curated/rust.yaml` topic `memory_and_performance`. Scope exclusions (unsafe deep-dive, async lifetimes) declared.
- **R2 N/A** — only stdlib types (`Rc`, `Arc`, `Cell`, `RefCell`, `Mutex`, `RwLock`, `Cow`, `String`, `Vec`, `Box`); no third-party imports needed. Reader will reach for these via prelude or `std::` paths.
- **R3 PASS** — every verification item is mechanically checkable: `cargo clippy -- -D warnings`, `grep -n 'Rc<RefCell<'`, `cargo check` after lifetime/clone removal, presence/absence of `// SAFETY:` comments, `Box<dyn Trait>` audit. No vague items.
- **R4 PASS** — covers move vs Copy, `&T`/`&mut T` aliasing rules, NLL, three lifetime-elision rules in order, struct field lifetimes, full Rc/Arc/Cell/RefCell/Mutex/RwLock surface, re-borrow, splitting borrows, iterator invalidation, Cow, plus seven anti-patterns. Edge cases walked (return-reference-to-local, self-referential structs, `for x in &v { v.push(...) }`).
- **R5 PASS** — NLL "stable since Rust 1.36, verified 2026-05-05" inline. No other version-specific numerics.
- **R6 PASS** — `change_summary` says "Initial authoring 2026-05-05"; not labelled imported.
- **R7 PASS** — no invented paths, file names, or domain glossary. All names (`Parser<'src>`, `first_word`, `longest`) are conventional textbook examples.
- **R8 PASS** — rationale fragment 1 contains "ownership", "borrow", "borrow checker", "reference", "lifetime", "Rust" (>3). Rationale fragment 5 contains "ownership", "Rc", "Arc", "RefCell", "borrow checker", "interior mutability". Lexical anchors strong for likely queries ("how does Rust ownership work", "when to use Rc vs Arc", "borrow checker fight").

## Technical correctness

- Line 51 — NLL stabilized in Rust 1.36 (July 2019). Accurate.
- Line 55–59 — Lifetime-elision rules and their ordering match the Rust Reference (`reference/lifetime-elision.html`): per-input lifetime → single-input propagated to outputs → `&self`/`&mut self` propagated to outputs. Accurate.
- Line 86 — `RefCell` "moves a compile-time guarantee to a runtime panic" — accurate; `borrow`/`borrow_mut` panic on dynamic violation.
- Line 93 — Re-borrow `&mut *r`: accurate description; the implicit reborrow at method-call sites is what makes `r.method(); r.method();` work.
- Line 94 — Disjoint-field borrow splitting through struct field paths is supported by the borrow checker (also via pattern matching). Accurate. Note: this only works for direct field access, not through `Vec`/`HashMap` indexing — not claimed here, no error.
- Line 104 — `unsafe` "does not turn off aliasing rules" — accurate. Stacked Borrows / Tree Borrows operational semantics (Miri) treat aliasing UB as UB regardless of `unsafe` block. The block only enables specific operations; it does not relax the aliasing model.
- Line 106 — `Box<dyn Trait>` vs `impl Trait`: accurate. `impl Trait` in return position is monomorphized (static dispatch, no allocation); `Box<dyn>` is dynamic dispatch with allocation. The "heterogeneous return types" framing is the canonical motivation.
- Code blocks: all compile under modern Rust (2021/2024 edition). The `println!("{r1:?} {r2:?}")` shorthand requires Rust 1.58+ for captured identifiers — universally available in 2026, no need to date-stamp.
- Move example (line 23–27) — accurate; the commented-out `println!("{s}")` would indeed produce `error[E0382]: borrow of moved value`.

## Required revisions

None. Verdict is approve.

## Summary

Skill is technically accurate, well-scoped, and clears R1–R8 cleanly. Stdlib-only scope makes R2 trivially satisfied. Verification fragments are unusually crisp — every item is a one-line shell check or build-pass observation. No fabricated terms, no version drift, no over-claiming. Approve as written.
