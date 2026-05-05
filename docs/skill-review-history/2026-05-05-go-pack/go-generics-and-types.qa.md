# QA Report: go-generics-and-types

- **Verdict:** revise
- **Reviewer:** independent critic (Claude agent, 2026-05-05)

## R1–R8 findings

- **R1 (sourcing):** Pass. change_summary cites go.dev/ref/spec#Type_parameter_declarations, pkg.go.dev/golang.org/x/exp/constraints, go.dev/blog/intro-generics, and go.dev/doc/faq#generics, with `verified 2026-05-05` stamp tied to fixtures/upstream/curated/go.yaml topic `typing_and_generics`. Sources match the curated registry entry.
- **R2 (imports for non-stdlib):** Fail. The skill references `golang.org/x/exp/constraints.Ordered`, `constraints.Ordered`, `Integer`, `Float`, `Signed`, `Unsigned`, `Complex` in the Constraints section (line 75/231) and Anti-patterns (line 147/314) but never shows an `import "golang.org/x/exp/constraints"` line. This is the canonical R2 violation — non-stdlib name used without an import once. `any`, `comparable` are predeclared (stdlib) and need no import.
- **R3 (verification mechanically checkable):** Mostly pass. Items are post-conditions a reviewer can grep for: receiver-only type params, no `any(x).(T)` in generic body, tilde-vs-plain. One soft item — "No interface type would have served the same goal more clearly" — is judgment, not mechanical, but is bounded enough to keep.
- **R4 (case-space):** Pass. Covers `any`, `comparable` (with the slice/map/func exclusions and the runtime-panic edge), custom unions (`~int | ~int32 | ...`), tilde semantics for named types, inference failure modes (return-only T, `nil` *T), and method-type-parameter prohibition.
- **R5 (date-stamp version claims):** Marginal. "Go 1.18" is stated as the introduction version (line 17/167) without `(verified YYYY-MM-DD)` inline; the change_summary date covers it transitively but the rule asks for inline stamping on numeric version thresholds. Recommend adding `(Go 1.18, March 2022)` once.
- **R6 (honest authorship):** Pass. `Initial authoring 2026-05-05` accurately labels novel scaffolding around upstream concepts; no "imported" mislabel.
- **R7 (no fabricated terms/paths):** Pass. All names (`Map`, `Stack`, `Sum`, `Unique`, `Number`) are illustrative, no invented file paths or domain glossary.
- **R8 (lexical anchors in rationale):** Pass. Fragment 1 contains "generics", "type parameters", "constraint", "interface{}", "any" — ≥3 obvious-query keywords. Fragment 6 ("When NOT to use generics") has "generics", "type information", "interface{}", "constraints". Fragment 7 ("Generic types vs interfaces") has "generics", "interfaces", "type", "constraint", "monomorphizing". All clear the bar.

## Technical correctness

- Line 17/167: "Go added type parameters in 1.18" — correct (Go 1.18, March 15 2022).
- Line 115/277: "interfaces with non-comparable dynamic types … runtime-panic on `==`" — correct; this is the long-standing Go behavior and is exactly the footgun `comparable` was tightened (Go 1.20) to address statically.
- Line 145/312: "Go does *not* allow type parameters on methods (only on the receiver type)" — correct as of Go 1.22; accepted proposal (#49085) exists but is unimplemented.
- Line 69/225: `~int` semantics ("any type whose underlying type is `int`") — correct.
- Line 119/284: "single function with dictionary-style dispatch (or, for some shapes, monomorphizes)" — substantively correct but imprecise; the actual mechanism is GCshape stenciling (a single instantiation per gc-shape, parameterized by a dictionary). The current phrasing reads as if monomorphization is an alternative path, when it is more accurately "GCshape-equivalent types share a stencil." Acceptable for a domain skill, but a one-line tightening would be more accurate.
- Line 149/316: "package-level type parameters are not allowed" / "`var Cache[T any] = ...` does not work" — correct.
- All code blocks (Map, Stack, Sum, Unique) compile under Go 1.18+. Verified mentally: `Stack[T]` receiver methods well-formed; `Unique` reuses `xs[:0]` correctly; `Map` shape standard.
- Line 88/247: "Explicit type arguments go in the same brackets at the call site: `Map[int, string](nums, intToString)`" — correct syntax.

## Required revisions

1. **Add an `import` block once for `golang.org/x/exp/constraints`** (R2). In sequence 3 (Constraints are interfaces) or sequence 8 (Anti-patterns), add a small block such as:
   ```go
   import "golang.org/x/exp/constraints"

   func Min[T constraints.Ordered](a, b T) T {
       if a < b { return a }
       return b
   }
   ```
   This satisfies R2 and gives readers a copy-pastable Ordered example, which the skill currently only names.
2. **Date-stamp the Go 1.18 claim** (R5). In `raw_prose` line 17 and fragment-1 line 167, change "Go added type parameters in 1.18." to "Go added type parameters in 1.18 (March 2022)." or append `(verified 2026-05-05)`.
3. **Tighten the dispatch claim** (technical precision, not an R-rule). Line 119 / fragment-6 line 284: change "single function with dictionary-style dispatch (or, for some shapes, monomorphizes)" to "single function per GCshape with dictionary-passing for type-specific operations; types sharing a GCshape share the stencil." Optional but recommended — the current wording survives, the revised wording is correct.

## Summary

Solid skill, technically sound, well-scoped, and lexically anchored. One R2 violation (no import shown for `golang.org/x/exp/constraints` despite repeated references) and one minor R5 lapse (the Go 1.18 date is not stamped inline). Both are line-level fixes; verdict is `revise`, not reject. The dispatch-mechanism wording is imprecise relative to GCshape stenciling but not wrong enough to block.
