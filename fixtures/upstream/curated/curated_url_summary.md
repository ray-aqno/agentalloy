# Curated URL Summary

Generated: 2026-05-01. All URLs verified with HEAD requests; non-2xx/3xx entries pruned before final write.

| language | total URLs | survived | killed | known_gaps count |
|----------|-----------|---------|--------|-----------------|
| Python | 48 | 48 | 0 | 3 |
| Java | 34 | 34 | 0 | 4 |
| Go | 48 | 48 | 1 | 3 |
| TypeScript | 27 | 27 | 1 | 4 |
| Node.js | 36 | 36 | 0 | 3 |
| Rust | 39 | 39 | 1 | 4 |
| C# | 35 | 35 | 0 | 3 |
| Ruby | 22 | 22 | 4 | 5 |
| PHP | 35 | 35 | 0 | 4 |
| Swift | 28 | 28 | 1 | 4 |

## Pruned URLs

- **Go** `topics.testing_idioms`: `https://go.dev/blog/fuzzing-beta` — URL moved; `go.dev/doc/fuzz/` retained
- **TypeScript** `canonical.spec_or_standard`: `https://github.com/microsoft/TypeScript/blob/main/doc/spec-ARCHIVED.md` — archived spec GitHub path not resolvable; set to null
- **Rust** `topics.typing_and_generics`: `https://doc.rust-lang.org/reference/generics.html` — reference section path incorrect; removed (book chapter retained)
- **Ruby** (4 pruned): `docs.ruby-lang.org/en/master/` class pages for Queue, RBS, Minitest, and Logger all returned 404 — the `/en/master/` tree does not expose class pages at these paths. Topics left with empty URL lists; known_gap added.
- **Swift** `canonical.release_notes`: `https://www.swift.org/blog/swift-6-is-here/` — blog post 404; replaced with blog index `https://www.swift.org/blog/`

## Notes

- **Ruby**: 4 class-page URLs killed; `docs.ruby-lang.org/en/master/` URL structure differs from what was expected. Authors should supplement with `ruby-doc.org` for class-level stdlib pages.
- **TypeScript**: No surviving formal spec URL; the TSPL equivalent is the handbook + release notes. `spec_or_standard` set to null.
- All other languages: 100% URL survival rate after pruning.
