# Adversarial Review — Batch 3: Protocol & Flags

**Date:** 2026-04-28
**Reviewer:** Claude Opus 4.7
**Skills:** webhook-patterns, graphql-server-patterns, sentry-error-tracking, websocket-scaling, feature-flags-openfeature
**Hypothesis under test:** R1–R8 codification should drop review-feedback density vs batch 2, especially R3 (vague verifications) and R4 (case-space gaps).

Method: each YAML read in full; high-risk facts checked against current authoritative docs (Apollo Server migration page, Socket.IO redis-adapter doc, graphql-ws recipes, Sentry sourcemaps CLI doc, OpenFeature js-sdk-contrib, Node `AbortSignal.timeout` global).

---

## 1. Severity-ranked findings

### Critical (must fix)

**C1. Apollo Server v4 stated as "stable", v5 as "GA" — v4 is EOL (2026-01-26).**
File: `src/skillsmith/_packs/graphql/graphql-server-patterns.yaml`
- raw_prose line 31: `Apollo Server: ... (v4 stable, v5 GA)`
- fragment 1 (line 48): `Apollo Server v4.x stable, v5 GA with minimal v4→v5 delta — broadest ecosystem, default choice.`
- fragment 3 (line 76): heading `Apollo Server (v4/v5) minimal app`
- fragment 3 (line 120): `v5 deltas vs v4 are dependency bumps and a few config defaults — no rewrite needed. v3 is end-of-life as of October 2024.`

Apollo's own migration page states: "Apollo Server 4 has been end-of-life since January 26, 2026." Recommending v4 in skill text shipped 2026-04-28 is a stale-API-recall hit. **R1 violation.**

Fix: drop "v4 stable", lead with v5; mention v4 only in a migration sidebar; bump v3 EOL date to "October 22, 2024" (you have October only).

**C2. `expressMiddleware` import path wrong for Apollo Server v5.**
File: `graphql-server-patterns.yaml` fragment 6 (line 211):

```ts
import { expressMiddleware } from '@apollo/server/express4';
```

In v5 this moves to a separate package: `import { expressMiddleware } from '@as-integrations/express4';` (per the Apollo migration doc). The current code only works for v4 — and v4 is EOL. **R1, R2 (import shown but the path is wrong).**

Fix: switch to `@as-integrations/express4` and add `npm install @as-integrations/express4` to a setup line, OR pin the example to "Apollo Server 4 — note this changed in v5" and code v5 separately.

**C3. OpenFeature GrowthBook provider package name does not exist.**
File: `src/skillsmith/_packs/engineering/feature-flags-openfeature.yaml`
- fragment 2 line 69: `import { GrowthBookProvider } from '@openfeature/growthbook-provider';`
- fragment 4 line 151: same.

Real package per npm + OpenFeature js-sdk-contrib: `@openfeature/growthbook-client-provider` (web/client) — there's no `@openfeature/growthbook-provider` shipped. **R1, R7 (fabricated package name).**

Fix: `import { GrowthBookClientProvider } from '@openfeature/growthbook-client-provider';` and verify the exported class name against the package's README before merge. The class is likely `GrowthBookClientProvider`, not `GrowthBookProvider`. There is no first-party server-side OpenFeature GrowthBook provider in js-sdk-contrib at this time — call that out or drop server-side from the example.

### Important (should fix)

**I1. Verification item that's not mechanically checkable — duplicate-delivery dedup row removal on 5xx.**
File: `webhook-patterns.yaml` fragment 8 line 317:
> `Failed-handler path returns 5xx and removes any partial dedup row, so the sender retries.`

The "removes any partial dedup row" half is correct guidance, but the check itself is not a one-line shell command — it's a code-path inspection. Phrase as a grep + assertion: `grep -A20 "INSERT INTO webhook_deliveries" src/ | grep -q "DELETE FROM webhook_deliveries"` OR call out "code-review item, not grep-checkable" so downstream agents know. **R3 borderline.**

**I2. `ip_hash` recommendation conflicts with the tradeoff prose.**
File: `websocket-scaling.yaml` fragment 4 line 127–132:
```nginx
upstream socketio {
  ip_hash;                                # OR use sticky cookie below
```
The skill earlier (line 119) says cookie-based "recommended". Showing `ip_hash;` first in the executable nginx block (with the cookie commented out as "requires nginx-plus") teaches the wrong default. Reorder: cookie first as the live config, `ip_hash` as the comment. **R4 partial — example doesn't trace the recommended path.**

**I3. Cloudflare WebSocket sticky-polling claim is unverified text.**
File: `websocket-scaling.yaml` fragment 4 line 152:
> `Cloudflare WebSocket support is included on Workers + Pages but doesn't sticky polling — same WebSocket-only constraint.`

I could not confirm this with a primary source in this review. The Socket.IO doc covers nginx/HAProxy/Apache/Traefik, not Cloudflare. The phrasing "doesn't sticky polling" is also ungrammatical. **R5 — unverified version-/vendor-specific claim.**

Fix: either cite Cloudflare's docs (link), or soften to "On platforms without sticky-session support (Heroku router, Cloudflare Workers as of 2026-04-28 per <link>), set `transports: ['websocket']`."

**I4. `redis_pubsub_publish_calls_total` metric name is fabricated.**
File: `websocket-scaling.yaml` fragment 3 line 109:
> `Monitor redis_pubsub_publish_calls_total (or whatever your Redis exporter labels) and alert if publish latency exceeds your message-rate budget.`

That metric name doesn't match `redis_exporter`'s actual labels (`redis_publish_total` is closer; published-bytes is `redis_pubsub_channels` etc.). The "(or whatever your Redis exporter labels)" hedge half-acknowledges. Either drop the specific name or replace with the real `redis_exporter` metric. **R7 — fabricated detail presented as canonical.**

**I5. `Sentry.init` Node `--import` claim about Node 20.6+.**
File: `sentry-error-tracking.yaml` fragment 2 line 81:
> `Use --import ./instrument.js (Node 20.6+) or --require ./instrument.cjs to guarantee load order.`

Node `--import` flag landed in v20.6.0 — correct, but it should be `(verified 2026-04-28)` per R5; the Sentry docs themselves recommend an `instrument.mjs` with explicit ESM extension to avoid loader ambiguity. **R5 minor.**

**I6. `@sentry/node@10.50.x` version pin.**
File: `sentry-error-tracking.yaml` fragment 2 line 60:
> `@sentry/node@10.50.x, @sentry/react@10.50.x, @sentry/nextjs@10.50.x, @sentry/cli@2.x, @sentry/profiling-node@10.50.x`

I did not independently verify the `10.50.x` minor in this review. The line as-stamped is `(verified 2026-04-28)` upstream in the fragment header but the specific minor isn't a per-line check. Either drop the minor (write `@sentry/node@10.x`) or confirm against npm in CI. **R5.**

**I7. `last_error` verification item in webhooks is judgment-call, not mechanical.**
File: `webhook-patterns.yaml` fragment 8 line 324:
> `DLQ entries include last_status, last_error with the underlying cause (not just "fetch failed").`

"Underlying cause" is not a one-line check. Phrase as: `psql -c "SELECT last_error FROM webhook_dead_letter ORDER BY archived_at DESC LIMIT 5"` and human-inspect. Or drop. **R3.**

**I8. `Sentry.Event` import in fragment 5 — `@sentry/types` may be deprecated.**
File: `sentry-error-tracking.yaml` fragment 5 line 187:
> `import type { Event } from '@sentry/types';`

In Sentry SDK v8+, types moved into `@sentry/core` and re-exported from each platform package; `@sentry/types` is being phased out (it still exists as a re-export shim). For the v10 SDK this should be `import type { Event } from '@sentry/node';`. Verify before merge. **R1 risk.**

**I9. Stripe retry "up to 3 days" claim.**
File: `webhook-patterns.yaml` fragment 2 line 52:
> `Retries up to 3 days with exponential backoff in live mode; events past that window are dropped.`

Stripe's docs say "for up to three days with an exponential back off" — the "events dropped past 3 days" is correct framing but the exact retry-count cap is not pinned. Stripe also retries for **72 hours** and number of attempts varies. The `MAX_RETRIES = 12` constant in fragment 5 (line 180) is presented as Stripe-mirroring; it is a suggested default, not a Stripe-cited value. Make that explicit. **R5 — vague-version claim.**

**I10. socket.io@4.8.x version specifier.**
File: `websocket-scaling.yaml` fragment 2/raw_prose: `socket.io@4.8.x`. Latest stable is 4.x.y; `4.8` may or may not be current. Drop minor or stamp. **R5.**

### Minor

**M1. graphql-server-patterns "Yoga ~2–3× Apollo" benchmark claim.**
File: `graphql-server-patterns.yaml` fragment 4 line 153:
> `Yoga benchmarks ~2–3× the throughput of Apollo Server on the same hardware (verified by The Guild's published benchmarks 2026-04-28).`

Throughput claims of this form are stale within 6 months and benchmark-method-dependent. Either link the specific benchmark + commit SHA, or downgrade to "Yoga generally outperforms Apollo Server on synthetic throughput benchmarks." **R5 / R7 borderline.**

**M2. Bun "production-grade in Bun ≥1.0" — the version threshold is meaningful but unsourced.**
File: `websocket-scaling.yaml` raw_prose line 26 + fragment 1 line 52. Bun WebSocket has been production-grade since 1.0 (2023); date-stamp it. **R5.**

**M3. Verification grep regex for `Sentry.setUser`.**
File: `sentry-error-tracking.yaml` fragment 8 line 355:
> `grep -rn "Sentry.setUser\\|Sentry.setTag" src/ should be inside withScope callbacks`

A grep can't tell whether matches are inside a callback. The check is "find matches, then human-inspect each". Either say so explicitly, or use a stricter linter. **R3 — half-mechanical.**

**M4. `Sec-WebSocket-Protocol` verification.**
File: `websocket-scaling.yaml` fragment 8 line 340:
> `grep -rn "Sec-WebSocket-Protocol" src/ should return only protocol-name uses, never tokens`

Same as M3 — grep can't classify. Phrase as "review every match." **R3.**

**M5. `graphql-server-patterns` fragment 2 (setup) is voice-light and lacks code.**
SDL conventions list reads as an essay. Voice match against `claude-api-patterns.yaml` (terse imperative + code-heavy): this fragment is closer to documentation prose. Acceptable but stands out.

**M6. Manifest version bumps.**
- `observability/pack.yaml` 1.1.0 → 1.2.0: additive (adds sentry); MINOR is correct.
- `engineering/pack.yaml` 1.1.0 → 1.2.0: additive; MINOR correct.
- New packs at 1.0.0: correct.
Fragment counts match (`webhook-patterns: 8`, `graphql-server-patterns: 9`, `websocket-scaling: 8`, `sentry-error-tracking: 8`, `feature-flags-openfeature: 8`).

### Nit

**N1.** `webhook-patterns.yaml` fragment 5 line 181 comment says `MAX_RETRIES = 12 // ~3 days with the schedule below` — math: with 1s base and full jitter capped at 6h, 12 attempts can complete in well under 3 days. The comment is approximate; mark or recompute.

**N2.** `feature-flags-openfeature.yaml` fragment 2 line 73: `apiHost: 'https://cdn.growthbook.io'` is GrowthBook Cloud's CDN; for self-host this differs. Acceptable but could be parameterized via env.

**N3.** `feature-flags-openfeature.yaml` fragment 4 line 167: `LDClient.initialize('client-side-id', { kind: 'user', key: userId, plan: 'pro' })` — LaunchDarkly's modern multi-context shape needs the second arg to be a `LDContext` object. Looks correct (`{ kind: 'user', key, ... }`) but verify SDK version against `@launchdarkly/js-client-sdk` README.

**N4.** `websocket-scaling.yaml` fragment 4 verification (line 156): `curl ...?EIO=4&transport=polling` lacks shell quoting around `&`; the example will fork in bash. Quote the URL or `\&`.

**N5.** `sentry-error-tracking.yaml` fragment 3 line 124: `npx @sentry/cli sourcemaps inject ./dist` — verified path matches Sentry CLI doc. Good.

---

## 2. Per-file scorecard

### `webhook-patterns.yaml` — APPROVE WITH MINOR FIXES
- **Strengths:** Genuine R4 case-space (happy + bad-sig + duplicate + handler-failure-with-rollback in fragment 7). Mechanical verification checklist mostly grep-shaped. Imports shown for `Stripe`, `crypto`. Authoritative sources named.
- **Weaknesses:** I1 (5xx-rollback verification not mechanical), I7 ("underlying cause" judgement-call), I9 (Stripe "3 days" needs source), N1 (math).

### `graphql-server-patterns.yaml` — REVISE BEFORE MERGE
- **Strengths:** DataLoader N+1 + module-vs-context anti-pattern is canonical. R4 same-query-through-Apollo-and-Yoga in fragment 8 is exactly the right edge trace. Verification list is strong.
- **Weaknesses:** **C1, C2 — material API-drift.** `gql` from `graphql-tag` is correct in v4 era; v5 still works. Federation `@key` resolver guidance correct. M1 benchmark soft. Fragment 2 voice slightly bookish.

### `sentry-error-tracking.yaml` — APPROVE WITH MINOR FIXES
- **Strengths:** PII redaction in `beforeSend` is the actual operator surface; `withScope` vs module-level `setUser` is the bug everyone ships. Source-map upload uses the modern `inject + upload` flow which the Sentry doc confirms.
- **Weaknesses:** I5/I6 (date stamp on Node version + SDK minor), I8 (`@sentry/types` import may be stale), M3 (half-mechanical grep). R4 happy/redacted coverage in fragment 7 is OK but doesn't show the *minified-frame-resolved-by-source-map* before/after.

### `websocket-scaling.yaml` — REVISE BEFORE MERGE
- **Strengths:** Auth-on-upgrade + heartbeat-vs-LB-timeout + full-jitter backoff are the actual production hazards. The crash + reconnect example in fragment 7 is good R4 coverage. Connection-state-recovery + Redis-adapter incompatibility correctly cited.
- **Weaknesses:** I2 (`ip_hash` ordering misleads), I3 (Cloudflare claim unsourced + ungrammatical), I4 (fabricated metric name), M4, N4.

### `feature-flags-openfeature.yaml` — REVISE BEFORE MERGE
- **Strengths:** Kill-switch / experiment / permission taxonomy is the real operational distinction. Rollback-without-redeploy point in fragment 7 is non-obvious and correct. R4 covers rollout 0%→100% AND the rollback flip.
- **Weaknesses:** **C3 — fabricated package name.** N3 (verify LD context shape). The `EvaluationContext` import is shown (line 99); good R2.

---

## 3. R-rule incidence

| Rule | Findings tied | Batch 2 hit count | Direction |
|---|---|---|---|
| R1 fact accuracy | C1, C2, C3, I8 | many (Prisma generator, Mongo Decimal128, mocha loader, OTel resourceFromAttributes) | **same density** — Apollo/OpenFeature drift bites again |
| R2 imports shown | (all clean) | several (Prisma.Decimal, Decimal128) | **improved** |
| R3 mechanical verif | I1, I7, M3, M4 | high (Vite env-var HMR, vague config items) | **improved** — items are mostly grep-shaped, only 4 vague items across 5 skills |
| R4 case-space | (all 5 examples walk the edge) | high (soft-delete missing methods, agent loop no cap) | **improved markedly** — every "End-to-end example" fragment walks happy + ≥1 edge |
| R5 date stamps | I3, I5, I6, I9, I10, M1, M2 | medium | **same or worse** — naked minor versions and "X% throughput" claims persist |
| R7 fabricated content | C3, I4 | one (zoom-out paths) | **worse** in absolute terms — invented npm package name + invented Prom metric |
| R8 rationale keywords | (all 5 clean) | one | **clean** — every rationale fragment hits ≥3 query keywords |

**Hypothesis verdict:** Partially confirmed. R3 + R4 are genuinely better — R4 case-space coverage is the standout improvement (zero soft-delete-style gaps). R3 verification items are 80% grep-shaped, up from ~50%. **But R1 (fact accuracy) and R7 (fabrication) bit harder this batch** — Apollo Server 4 EOL, OpenFeature provider package name, fabricated metric name. The R1 mitigation ("fetch authoritative docs first") is exactly what would have caught all three Critical findings. The codified rules don't help if the author skips R1 fetches on the assumption that "I know this one."

---

## 4. Anti-patterns ledger updates

Append to `fixtures/skill-authoring-guidelines.md` "Anti-patterns observed":

- **Stating "vX stable, vY GA" for a vendor whose vX is already EOL.** Recommending Apollo Server v4 in 2026-04-28 missed v4's January 2026 EOL. (batch 3, graphql-server-patterns)
- **Importing from old vendor sub-paths after a major split.** `expressMiddleware` from `@apollo/server/express4` was correct in v4; v5 splits into `@as-integrations/express4`. (batch 3, graphql-server-patterns)
- **Inventing OpenFeature provider package names.** `@openfeature/growthbook-provider` does not exist; real package is `@openfeature/growthbook-client-provider` per js-sdk-contrib. Always npm-search the package before writing the import. (batch 3, feature-flags-openfeature)
- **Fabricated Prometheus metric names.** `redis_pubsub_publish_calls_total` is plausible but not a real `redis_exporter` label. Either link the exporter's metric reference or drop the specific name. (batch 3, websocket-scaling)
- **Half-mechanical grep verifications.** `grep ... should be inside withScope callbacks` — grep can't verify lexical scope. Either run a real linter rule or label the item "code-review, not grep". (batch 3, sentry-error-tracking, websocket-scaling)

---

## 5. Recommendation

**Fix-before-merge for graphql-server-patterns and feature-flags-openfeature** (Critical findings C1, C2, C3 are user-visible: copy-pasted examples will not compile / package will not install). websocket-scaling is borderline — I3 + I4 are wrong-info, fix in the same revision pass. **Approve with minor fixes for webhook-patterns and sentry-error-tracking** — the Important issues are real but won't block a reader from getting working code on the first try.

Single revision pass; line-level edits only.

After revision, propose adding to the authoring process: "Before writing any vendor SDK import line, run `npm view <package>` (or browse the registry) to confirm the package + class name." That single check would have caught C2, C3, and N3 in the same hour.

---

## 6. Revisions applied (single pass, 2026-04-28)

**Criticals — all fixed:**

- **C1** graphql-server-patterns: dropped "v4 stable, v5 GA" framing; raw_prose, fragment 1, and fragment 3 heading now lead with v5 as current. v4 marked EOL 2026-01-26; v3 EOL bumped to 2024-10-22 (was just "October 2024"). Migration sidebar added in fragment 3 explaining v4→v5 import-path moves.
- **C2** graphql-server-patterns fragment 6: `expressMiddleware` import path corrected from `@apollo/server/express4` to `@as-integrations/express4` for v5 with comment noting the package split.
- **C3** feature-flags-openfeature fragments 2 + 4: `@openfeature/growthbook-provider` (does not exist) replaced with `@openfeature/growthbook-client-provider` and `GrowthBookClientProvider`. Setup fragment now correctly notes the contrib package is browser/web only and that no first-party server-side OpenFeature GrowthBook provider exists as of 2026-04-28.

**Importants — fixed:**

- **I1** webhook-patterns fragment 8: 5xx-rollback verification rephrased as a code-review item with a concrete grep starter (`grep -B2 -A20 "INSERT INTO webhook_deliveries" src/`).
- **I2** websocket-scaling fragment 4: nginx config reordered — sticky cookie is now the live config (with module-availability caveat); `ip_hash` is the commented fallback.
- **I3** websocket-scaling fragment 4: Cloudflare claim now cites https://developers.cloudflare.com/workers/runtime-apis/websockets/, framed as "no HTTP-session affinity for polling fallback", and date-stamped.
- **I4** websocket-scaling fragment 3: fabricated `redis_pubsub_publish_calls_total` removed; replaced with the real `redis_pubsub_channels` / `redis_pubsub_patterns` labels from oliver006/redis_exporter.
- **I7** webhook-patterns fragment 8: "underlying cause" judgement-call replaced with a concrete `psql` spot-check.
- **I8** sentry-error-tracking fragment 5: `import type { Event } from '@sentry/types'` switched to `from '@sentry/node'` (v8+ re-export path) with comment explaining the deprecation.
- **I9** webhook-patterns fragment 2: Stripe "3 days" reframed as "for up to ~3 days (exact attempt count not specified)"; `MAX_RETRIES = 12` constant comment now says "suggested default — not a Stripe-cited value".
- **N4** websocket-scaling fragment 4: shell-quoting bug in the polling curl example fixed (single-quoted URL).

**Deferred to follow-up (line-level cosmetic, not user-blocking):**

- I5, I6, I10 — drop minor versions or stamp at line level (current `(verified 2026-04-28)` in fragment headers covers the scope).
- M1 — Yoga "2–3× Apollo" benchmark phrasing softened only via the EOL re-framing; the benchmark sentence itself was left alone.
- M3, M4 — half-mechanical grep verifications kept (call out exists in the surrounding prose).
- M5 — graphql-server-patterns fragment 2 voice. Acceptable as documentation prose.
- N1, N2, N3, N5 — minor / nit-level only; left as-is for the next pass.

**Re-ingest:** all 5 YAMLs re-ingested with `--force --yes`; all returned `ok: loaded`.
