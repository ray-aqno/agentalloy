# QA Report: go-concurrency-and-context

- **Verdict:** revise
- **Reviewer:** independent critic (Claude agent, 2026-05-05)

## R1–R8 findings

- **R1 — PASS.** change_summary cites Go spec §Go_statements, pkg.go.dev/sync, pkg.go.dev/context, Effective Go concurrency, and the Go pipelines blog, all canonical go.dev / pkg.go.dev URLs, and is verified 2026-05-05 against the curated fixture topic `concurrency_and_async`. URLs match `fixtures/upstream/curated/go.yaml` exactly.
- **R2 — FAIL (minor).** The `select`-with-timeout example (fragment 5, line ~229) and the `fetchUser` example (fragment 7, line ~275) DO show their `import` blocks — good. However `errgroup.Group` is referenced in two fragments (sync rationale seq 6, anti-patterns / pipelines seq 8) and never demonstrated in code with its `import "golang.org/x/sync/errgroup"` line. R2 says non-stdlib names need an import shown at least once in the skill; `errgroup` is the only non-stdlib name and lacks one.
- **R3 — PARTIAL FAIL.** Verification is mostly mechanically checkable (grep for `defer cancel`, grep for `context.Context` struct fields, grep `func f(m sync.Mutex)` value receivers). Two items are vague: (a) "Channel ownership is documented: exactly one goroutine sends, exactly one closes" — there is no mechanical check for "documented"; (b) "Every `go func` either selects on `ctx.Done()` / a stop channel, or runs over a finite input and returns" — the second clause ("finite input") is not grep-checkable. Tighten or split.
- **R4 — PASS.** Goroutine example shows both a leak path and a cancellation-aware fix; select example covers cancellation, timeout, and non-blocking-default discussion; anti-patterns enumerate 7 distinct failure modes including loop-capture, mutex-by-value, double-close, and missed `cancel()`. Edge cases for goroutine-leak are explicitly traced.
- **R5 — PARTIAL FAIL.** "Go 1.22+ scoped per-iteration" is a version claim; the change_summary's `verified 2026-05-05` covers the curated fixture but does not anchor *this specific Go version claim*. R5 wants the version claim itself date-stamped or version-anchored inline. Add `(verified 2026-05-05 against go.dev/blog/loopvar-preview-in-go-1.22 / go1.22 release notes)` next to the loop-variable bullet, or move into a `## Verified` footer.
- **R6 — PASS.** change_summary says `Initial authoring 2026-05-05` and `author: navistone`. Honest — this is original authoring scaffolded against a curated source list, not an import.
- **R7 — PASS.** No fabricated paths or invented domain glossary. All names (`errgroup.Group`, `context.WithTimeout`, `sync.Mutex`, `ctx.Done()`, `pg_advisory_lock`-style, etc.) are real Go stdlib / x/sync APIs. The only file-path-shaped string is the curated fixture path, which exists.
- **R8 — PASS.** Rationale fragments are saturated with the obvious-query keywords: seq 1 contains "goroutines", "channels", "context", "cancellation", "concurrency"; seq 4 contains "channel", "buffering", "ownership", "synchronization"; seq 6 contains "channels", "mutex", "WaitGroup", "errgroup", "concurrency"; seq 8 contains "pipeline", "fan-out", "fan-in", "concurrent", "channels", "errgroup", "cancellation". Comfortably above the three-keyword floor.

## Technical correctness

- **Loop variable capture / Go 1.22 (line 136 / seq 9).** Accurate. Go 1.22 (Feb 2024) made `for` loop variables scoped per-iteration via the `loopvar` change. The `i := i` rebinding workaround for older code is correct. Suggest anchoring with a release-notes link inline (R5).
- **`select` randomness (line 86 / seq 5).** Accurate per Go spec §Select_statements: "If multiple cases can proceed, a single one is chosen via a uniform pseudo-random selection."
- **`context.WithTimeout` cancel semantics (line 109 / seq 7).** Accurate. `defer cancel()` immediately after `WithTimeout` is the canonical pattern; `cancel` releases resources tied to the derived context even if the deadline fires.
- **`fetchUser` example (line 108–119).** Two minor issues: (1) `req, _ := http.NewRequestWithContext(...)` discards an error — fine for illustration but sloppy; consider adding `// error elided for brevity` or handling it. (2) The function signature returns `(*User, error)` but the body has no terminal `return` after the comment ellipsis. The code as shown will not compile. Either truncate explicitly with `// ... parse body ...\n\treturn nil, nil` or `panic("not implemented")`, or drop the return type from the signature. As written, R4-mental-walkthrough fails.
- **Channel ownership / close semantics (line 67 / seq 4).** Accurate: send on closed channel panics; close on nil channel panics; close-of-closed panics. The skill says "never send on a closed channel (it panics)" — correct.
- **errgroup semantics (line 95 / seq 6).** Accurate: `errgroup.Group` cancels siblings on first non-nil error when constructed via `errgroup.WithContext`. The skill should note that plain `new(errgroup.Group)` does NOT cancel — only the `WithContext` form does. Currently ambiguous; readers may use the zero value and lose the cancellation guarantee they were promised. Recommend one-line clarification in seq 6.
- **`errors.Join` Go 1.20+.** Not claimed in this skill — N/A. (The corresponding error-handling skill should cover it.)
- **Goroutine stack size (~2 KB, line 21).** Accurate as of current Go runtime (8 KB historically, lowered to 2 KB in Go 1.4+).
- **`sync.Mutex` copy-by-value (line 137).** Accurate; `go vet` flags this as `copylocks`. Worth mentioning `go vet` catches it — would convert R3 verification item into a one-line check (`go vet ./...` exits non-zero on copied locks).

## Required revisions (verdict=revise)

1. **fragment 7 (seq 7), `fetchUser` example (yaml line ~291):** add a terminal return so the example compiles. Replace the trailing `// ...` with:
   ```go
       defer resp.Body.Close()
       var u User
       if err := json.NewDecoder(resp.Body).Decode(&u); err != nil {
           return nil, err
       }
       return &u, nil
   ```
   and add `"encoding/json"` to the import block. Or, if you want to keep it shorter, change the signature to `func fetchUser(ctx context.Context, id string) error` and `return nil` at the end. Pick one — current form does not compile.
2. **fragment 6 (seq 6), errgroup bullet (yaml line ~259):** clarify that the cancel-on-first-error behavior requires `errgroup.WithContext`. Replace `like WaitGroup but each goroutine returns an error, and the group cancels on first error.` with `like WaitGroup but each goroutine returns an error, and — when constructed via errgroup.WithContext(parent) — the derived context is cancelled on the first non-nil error.`
3. **fragment 6 (seq 6) and/or anti-patterns (seq 9):** add an `import "golang.org/x/sync/errgroup"` reference once, ideally in a tiny errgroup snippet inside the sync-package fragment. Satisfies R2.
4. **fragment 9 (seq 9), loop-variable bullet (yaml line ~315):** anchor the version claim. Append `(Go 1.22 release notes, verified 2026-05-05: https://go.dev/doc/go1.22#language)` so R5 holds for the inline version claim.
5. **fragment 10 (seq 10), verification item 2 (yaml line ~324):** rewrite to a mechanical check. Replace `Channel ownership is documented: exactly one goroutine sends, exactly one closes.` with `For every make(chan ...) in this package, grep -n 'close(<chanName>)' returns exactly one site, and that site is in the goroutine that owns the sends.`
6. **fragment 10 (seq 10), verification item 1 (yaml line ~323):** split the two clauses or drop the "finite input" half. Replace with `Every 'go func' body contains either '<-ctx.Done()' / '<-stop' inside a select, or a bounded for/range over a closed input channel; verified by grep + manual scan.`
7. **fragment 10 (seq 10), optional addition:** add `go vet ./... reports zero copylocks findings (catches mutex-by-value copies).` — turns the mutex anti-pattern into a one-command verification.

## Summary

Skill is technically strong, well-scoped, and correctly cites canonical Go sources. Verdict is `revise` (not `approve`) for one compile-broken example (`fetchUser` lacks a terminal return), one missing nuance on `errgroup.WithContext`, one missing import for the only non-stdlib symbol, two vague verification items, and an unanchored Go-1.22 version claim. All seven fixes are line-level — no structural rework needed.
