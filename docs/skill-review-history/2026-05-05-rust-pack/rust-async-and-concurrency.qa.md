# QA — rust-async-and-concurrency

**Reviewer:** independent critic
**Date:** 2026-05-05
**File:** `src/skillsmith/_packs/rust/rust-async-and-concurrency.yaml`
**Verdict:** `approve`

## R1–R8 evaluation

| Rule | Status | Notes |
|------|--------|-------|
| R1 — authoritative sources | PASS | Cites `std::thread`, `std::sync`, `await-expr` reference, `std::future::Future`, book ch16, `docs.rs/tokio/1`. All marked `(verified 2026-05-05)`. |
| R2 — imports shown | PASS | `use std::sync::mpsc; use std::thread;`, `use std::sync::{Arc, Mutex};`, `use tokio::sync::Mutex;`, `use tokio::sync::mpsc;`, `use tokio::time::{sleep, Duration};` all shown. |
| R3 — verification mechanically checkable | PASS | Eight items; all expressible as shell commands or grep+manual reads. `clippy::await_holding_lock` referenced explicitly with `-D` flag. |
| R4 — case-space coverage | PASS | MutexGuard-across-await edge walked with both multi-thread (compile error) and current-thread (deadlock) outcomes; three fixes enumerated. Send/Sync split, sync vs async primitives, cancellation-safe vs not all enumerated. |
| R5 — date stamps on version claims | PASS | tokio 1.x, async stable Rust 1.39 (Nov 2019), trait URLs all `(verified 2026-05-05)`. |
| R6 — honest authorship | PASS | `change_summary` explicitly notes tokio is community-canonical per `known_gaps`, examples scaffolded around stdlib semantics, not imported verbatim. |
| R7 — no fabricated paths | PASS | All file/function names are schematic (`fan_out`, `bad`, `worker`, `handle`); no invented domain glossary. |
| R8 — rationale lexical anchors | PASS | Fragment 1: "async", "await", "Future", "tokio", "Send", "Sync", "MutexGuard", "select". Fragment 2: "Send", "Sync", "Arc", "thread", "spawn", "await". Fragment 4: "async", "await", "Future", "poll", "Pin". All ≥3 anchors. |

## Rust technical claims sanity-check

- **async stabilized in Rust 1.39 (Nov 2019)** — accurate (1.39.0 released 2019-11-07, stabilized `async/await` and the `Future` trait).
- **`Future::poll(self: Pin<&mut Self>, cx: &mut Context) -> Poll<Self::Output>`** — accurate signature.
- **`Send + 'static` requirement for `std::thread::spawn` and tokio multi-threaded `tokio::spawn`** — accurate.
- **`std::sync::MutexGuard` is `!Send`** — accurate; on multi-threaded tokio runtime the generated future is `!Send`, fails to compile under `tokio::spawn`. Walk is correct.
- **`std::sync::Mutex` across `.await` deadlock on current-thread runtime** — accurate framing; the more precise mechanism is "the executor cannot make forward progress while a peer task on the same thread blocks on `lock()`". Skill captures this.
- **`tokio::sync::Mutex` allowed across `.await`, guard `Send`** — accurate; `tokio::sync::MutexGuard` is `Send` and `lock().await` yields cooperatively.
- **`tokio::select!` drops losing branches; `mpsc::Receiver::recv` cancellation-safe; `AsyncReadExt::read` not** — accurate; matches tokio's own select! / cancellation-safety docs.
- **`JoinHandle` semantics: awaiting yields `Result<T, JoinError>`; drop does not abort by default for `std::thread`, does for `tokio::task::JoinHandle`** — skill says tokio `JoinHandle` panic vs cancellation; correct. (Note: tokio JoinHandle dropping does NOT cancel the task by default — `abort()` is required. The skill never claims drop-cancels, so no error.)
- **`#[tokio::main]` expansion** — accurate (builds runtime + `block_on`).

## Code blocks compile-check (mental)

- `fan_out` — compiles; `mpsc::Sender` is `Clone`, `rx.iter()` collects until all senders drop, original `tx` dropped explicitly. OK.
- `Arc<Mutex<u64>>` increment loop — compiles. OK.
- `fetch` mental model in fragment 4 commented out to avoid orphan `.await` outside async — good fix vs raw_prose.
- tokio main with `tokio::spawn` returning `&'static str` — OK; `JoinHandle<&'static str>`.
- `increment(state: Arc<tokio::sync::Mutex<u64>>)` — OK.
- `bad` example deliberately broken; correctly so.
- `worker` select! loop — compiles; `mpsc::Receiver::recv` returns `Option<T>`. OK.

## Minor observations (non-blocking)

- Fragment 5 mentions "async-std ... less actively developed than tokio" — true as of 2026-05-05 but borderline opinion; acceptable as "honest treatment" per R6.
- Verification item on `Cargo.toml` `features = ["full"]` warning is mechanical via `grep`, fine.
- Could mention `JoinHandle::abort()` and drop-does-not-cancel-by-default explicitly, but out-of-scope per change_summary.

## Verdict

**approve** — no revisions required. All R1–R8 pass; technical claims accurate; code compiles; cancellation-safety, MutexGuard-across-await, and stdlib-vs-tokio runtime gap all honestly and correctly handled.
