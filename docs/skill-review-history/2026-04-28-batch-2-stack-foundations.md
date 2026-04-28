# Adversarial Review — Batch 2: Stack Foundations

**Date:** 2026-04-28
**Reviewer:** Claude Opus 4.7
**Skills:** prisma-orm-patterns, postgres-deep-patterns, mongodb-patterns, mocha-chai-sinon, podman-rootless, claude-api-patterns, vite-config-and-build, opentelemetry-nodejs

**Method:** For each skill, identify SPECIFIC technical issues, weak claims, missing critical content, internal inconsistency, and pack-placement concerns. Track patterns across the batch for prompt improvement.

---

## prisma-orm-patterns

### Issues

1. **Soft-delete extension is incomplete** (seq 5). Override only intercepts `findMany` + `findFirst` + `delete`. Missing: `findUnique`, `findUniqueOrThrow`, `deleteMany`, `update` (where=deletedAt is null), `count`. A real soft-delete extension covers all read paths or it leaks deleted rows. **Severity: bug. Fix in revision.**

2. **Generator name is borderline.** I wrote `provider = "prisma-client"`. Prisma still defaults to `prisma-client-js`; the `prisma-client` (no `-js`) generator is newer (ESM-friendly) but not yet the default in `prisma init`. Should clarify — old projects will see `prisma-client-js`, new projects can opt into `prisma-client`. **Severity: clarity. Fix.**

3. **`Prisma.PrismaClientKnownRequestError` import path** mentioned in the guardrail table but no example shows the import. Readers will try `import { Prisma } from '@prisma/client'` (works) vs. `from './generated/prisma'` (also works, depends on output config). Should add the import line to one example. **Severity: minor.**

4. **End-to-end stock decrement example uses `new Decimal(0)`** without showing the import. Real code: `import { Prisma } from '@prisma/client'; const zero = new Prisma.Decimal(0);`. **Severity: minor. Fix in revision.**

### Strengths

- ID strategy table is genuinely useful (cuid vs uuid vs autoincrement guidance).
- Connection pool / PgBouncer note in production rule.
- "Why not `db push` in production" is concrete.

---

## postgres-deep-patterns

### Issues

1. **PgBouncer flag understated.** I wrote `?pgbouncer=true` but didn't mention the corresponding need in newer Prisma to also set `directUrl` for migrations. Without `directUrl`, `migrate deploy` fails through PgBouncer's transaction-mode pooling. **Severity: bug. Fix.**

2. **`INCLUDE` syntax is Postgres 11+** (covering indexes). Should mention version. **Severity: minor. Fix.**

3. **Advisory lock key collision risk** not addressed. `hashtext('SKU-' || $1)` returns int4 — collisions are possible. For unique-key locking, either use bigint advisory locks (key1, key2 form: `pg_advisory_lock(key1 int, key2 int)`) or accept the small collision rate. **Severity: clarity. Fix.**

4. **No mention of `pg_stat_statements`** — the single best Postgres perf tool ("which queries take total most time"). **Severity: missing content. Fix.**

5. **`OFFSET` warning** is correct but doesn't mention that with a LIMIT, modern Postgres has an "Offset" plan node that does still scan past rows. The fix language is right; just slightly stronger framing. **Severity: nit.**

### Strengths

- EXPLAIN ANALYZE table mapping signal → action is high-value.
- Index type table covers the actual decision a user makes.
- Worker-queue pattern with `SKIP LOCKED` is canonical.

---

## mongodb-patterns

### Issues

1. **`Decimal128` example uses `NumberDecimal('19.99')`** which is mongo-shell syntax, not Node-driver syntax. Node driver: `import { Decimal128 } from 'mongodb'; new Decimal128('19.99')` (or `Decimal128.fromString('19.99')`). **Severity: bug. Fix in revision.**

2. **Profile setter signature** drifted between driver versions. v6+ `db.setProfilingLevel(level, options)` where `level: 'off' | 'slow_only' | 'all'` and options has `slowms`. The shell-style `db.setProfilingLevel(1, {slowms: 100})` works in shell but the Node driver wants the named string. **Severity: bug.**

3. **No mention of `Stable API`** (versioned API). Recent Atlas pushes `serverApi: { version: '1', strict: true }` for forward compatibility. Worth a one-liner in setup. **Severity: missing.**

4. **Mongoose vs. driver section** is opinionated but reasonable; could be more decisive ("default to driver for TS, Mongoose for legacy or simple CRUD apps"). Nit.

5. **Unbounded array warning** (16 MB doc limit) is the right anti-pattern. Could add the canonical pattern: when arrays grow, switch to a separate collection with a parent ID. **Severity: nice-to-have.**

### Strengths

- Embed-vs-reference framing is the right mental model.
- Aggregation pipeline section ordering rules (`$match` first, etc.) is the actual perf-critical knowledge.
- Multikey index gotcha (only one per compound) is a footgun worth flagging.

---

## mocha-chai-sinon

### Issues

1. **`loader: 'tsx'` in `.mocharc.cjs` is wrong syntax.** Mocha's `--loader` flag passes through to Node's `--experimental-loader`. The current correct value for tsx is `'tsx'` directly via `--import tsx` (Node 20+) NOT a `loader:` field. The `.mocharc.cjs` `loader` option exists but tsx doesn't ship as a loader — you use `--import tsx` in the script. **Severity: bug. Fix.**

   Actually, tsx CAN be used as a Node ESM loader: `--import tsx` (Node 20+) or `--loader tsx` (legacy). The `.mocharc.cjs` `loader` field corresponds to Node's `--experimental-loader`, which tsx supports under the legacy path but recommends `--import` now. Better: drop the `loader` field and use a script-side `tsx mocha` runner, or use ts-node's loader. **Fix in revision: switch to either `tsx` script wrapper or ts-node loader for clarity.**

2. **`chai-as-promised` is needed for `.to.be.rejectedWith`** — I mention it but the examples in seq 2 use it BEFORE seq 3 introduces it. Reorder or move the `use(chaiAsPromised)` to the setup fragment. **Severity: small. Fix.**

3. **`.nycrc.json`** uses `@istanbuljs/nyc-config-typescript` — that exists but requires `ts-node`. With tsx-based runs, coverage instrumentation needs `c8` instead of `nyc`. Big config gap. **Severity: clarity. Fix in revision: mention c8 alternative.**

4. **`mock` example** shows `mock.expects().once().withArgs()` followed by `mock.verify()` — but `withArgs` returns the expectation for further chaining, so `.once()` must be on the expectation not on the verify. The example is correct but easy to misread. Nit.

### Strengths

- Sandbox vs `sinon.restore()` distinction is correctly flagged as the safer pattern.
- Test-file structure recommendations (one assertion per `it`, naming) are sound.
- Async-test patterns table prevents the most common async footgun.

---

## podman-rootless

### Issues

1. **`podman compose` built-in subcommand is misleading.** As of podman 4.x/5.x, `podman compose` shells out to whatever compose tool is on PATH (docker-compose or podman-compose). It's not a native implementation. Should clarify. **Severity: clarity. Fix.**

2. **`PublishPort=80` workaround** mentions `sysctl net.ipv4.ip_unprivileged_port_start=80` but the cleaner answer is bind to high port + reverse proxy, OR `setcap cap_net_bind_service=+ep` on the binary. The sysctl change is system-wide. Should soften that recommendation. **Severity: clarity.**

3. **Mac note is too brief.** macOS users get a Linux VM via `podman machine`; volumes, networking, and resource sizing all behave differently. A sentence on the Mac caveat is enough but currently absent. **Severity: missing.**

4. **`AutoUpdate=registry`** is exactly right but the note about needing the `podman-auto-update.timer` enabled at the user scope buried in seq 4. Could be a callout. Nit.

5. **`:Z` mount flag for SELinux** mentioned but `:U` (UID-mapping) is the more common rootless need on Ubuntu where SELinux isn't enforcing. Worth one more sentence. **Severity: small.**

### Strengths

- Quadlet vs. `podman generate systemd` comparison is correct and current.
- Multi-stage Containerfile follows best practices (non-root user, minimal final stage).
- Real-world example using the user's own skillsmith service is concrete.

---

## claude-api-patterns

### Issues

1. **Tool execution loop has no max-iteration cap in the example** (seq 3). Mentioned in the verification checklist but not in the actual loop code. Without a cap, a runaway agent (model keeps calling tools indefinitely) costs money and time. Should add a `MAX_TURNS = 25` constant in the example. **Severity: bug. Fix.**

2. **Batch results streaming** — I wrote `for await (const result of results)` where `results = await client.messages.batches.results(batch.id)`. The SDK returns a stream of JSONL; usage might need `results.stream()` or similar. Need to verify against current SDK. **Severity: API drift risk. Fix to be explicit about JSONL stream parsing.**

3. **Cache verification example only shows logging** — doesn't show the diagnostic step of "run twice, second call should have cache_read > 0". Worth a small "smoke test" snippet. **Severity: small.**

4. **`stop_reason: 'refusal'`** — I list this in the guardrail. Need to verify it's actually a documented value (vs. `end_turn` with refusal text). Looking at fetched docs, `refusal` is listed in handling-stop-reasons. ✓

5. **No mention of structured outputs** as the "give me JSON I can trust" pattern. The user's batch list omitted it, but it's the modern alternative to writing manual JSON parsing prompts. Could add a one-line pointer. **Severity: missing — but out of scope for this skill specifically.**

6. **The `Anthropic.Tool[]` type assertion in seq 3** writes `as const` (which I didn't actually do, looking again) — OK as-is. Nit removed.

### Strengths

- Cache breakpoint placement table (1 of 4 slots × system/tools/context/conv) is the practical mental model.
- Min cache size table sourced from current docs.
- Tool description vs. schema framing ("docstring quality matters more than schema") is the actual learning.

---

## vite-config-and-build

### Issues

1. **`vite-tsconfig-paths` recommendation** is good but doesn't mention that with TS 5.5+ `paths` and Vite resolution can disagree on `extends` chains. Worth a small note. **Severity: nit.**

2. **`pnpm build` recommendation** runs `tsc -b` first. Some projects use `vue-tsc` or `react-app-rewired` patterns. The default react-ts template uses `tsc -b`; correct for that template, slightly assumes it. Nit.

3. **`build.target: 'es2022'`** — Vite 6's default target follows web-features Baseline (Widely Available). Hardcoding `es2022` is fine but reduces feature usage. Could note "default is Baseline Widely Available; specify only if you need specific transforms". **Severity: clarity.**

4. **HMR for env-var changes** — I claimed in the verification checklist that env-var change requires server restart. Actually Vite watches `.env*` files and restarts the server automatically. **Severity: bug in checklist. Fix.**

5. **Bundle-analyzer plugin name** — `rollup-plugin-visualizer` is correct, works with Rolldown too. ✓

6. **`server.proxy` + WebSocket** — I show `ws: true` for `/ws` proxy. Correct but `changeOrigin: true` may not be needed for WS. Nit.

### Strengths

- Real config snippet covers the 90% case (proxy + aliases + manualChunks).
- Sourcemap upload guidance ("upload to error tracker, don't expose publicly") is the right tradeoff to surface.
- `import.meta.env` typing pattern is the canonical fix.

---

## opentelemetry-nodejs

### Issues

1. **`resourceFromAttributes`** is from `@opentelemetry/resources` v1.27+ — older OTel JS used the `Resource` class with `SemanticResourceAttributes` constants. New code should use the function form, but readers on older codebases will hit a different API. Should mention the version requirement. **Severity: clarity.**

2. **`ATTR_SERVICE_NAME`** vs. `SemanticResourceAttributes.SERVICE_NAME` — I used the new constant name. Good for current SDK. Add version note. **Severity: clarity. Fix.**

3. **Logs signal omitted.** I noted it's still maturing in OTel JS — true. But for completeness, the bridge from pino → OTel logs (`@opentelemetry/instrumentation-pino`) exists and could be mentioned. **Severity: missing.**

4. **`OTEL_EXPORTER_OTLP_ENDPOINT` semantics**: when you set this base URL, the SDK appends `/v1/traces`, `/v1/metrics`, `/v1/logs` automatically — but my code manually appends `/v1/traces`. Both work; the manual form is explicit but slightly verbose. Nit.

5. **Sampling note buried in guardrails.** Sampling is a fundamental decision; could be its own fragment. **Severity: structural — leaving as-is for this revision.**

6. **No mention of the OTel Collector** as the recommended deployment topology (apps → collector → backend). Worth a one-line pointer. **Severity: missing.**

### Strengths

- The `--import` vs. `--require` vs. "first import" comparison is the actual gotcha.
- Backend matrix (Honeycomb, Datadog, New Relic, Tempo) is what users actually need.
- Auto-instrumentation tuning (`ignoreIncomingRequestHook` for `/health`) is high-value.

---

## Cross-skill patterns (for prompt improvement)

### Patterns observed in this batch

1. **API-drift on details.** Several skills have small but real inaccuracies on current API shapes (Prisma generator name, Mongo `Decimal128`, mocha tsx loader, OTel resource factory). When authoring future skills against fast-moving APIs, fetch the current docs FIRST and quote them, rather than relying on knowledge that may be ~6 months stale.

2. **Examples that work in isolation but lack a critical edge case.** Soft-delete missing `findUnique`, agent loop missing max-iteration cap, embed example using shell syntax in driver code. **Recommendation for prompt:** add an explicit instruction: "every example must compile and run as written; trace through edge cases mentally before including".

3. **Verification checklist accuracy.** One skill's checklist had a wrong claim (Vite env-var HMR). **Recommendation for prompt:** treat the verification checklist as a contract — every item must be a thing the agent can mechanically check.

4. **Imports often elided.** Several examples show types like `Prisma.PrismaClientKnownRequestError` or `Decimal` without the corresponding `import` line. **Recommendation:** add: "every code block that uses a non-stdlib name must show the import once".

5. **Strong on architectural mental models, weaker on verifiable contracts.** All 8 skills succeed at framing the decisions a user makes (embed vs. reference, when to cache, sync vs. async loader). The weaknesses cluster in the line-by-line code accuracy. **Recommendation:** consider splitting authoring from verification — author against fetched docs, then have a separate "code-correctness" pass that runs the examples through a real compiler/runtime.

6. **No skill had a critical, "can't ship" issue.** All revisions are line-level fixes, not redesigns. The architecture/scope decisions held up. **Recommendation:** prompt's emphasis on stack alignment + when-to-use is working — keep it.

### Verdict

| Skill | Verdict | Bugs to fix in revision |
|---|---|---|
| prisma-orm-patterns | revise | soft-delete extension, generator-name clarity, Decimal import |
| postgres-deep-patterns | revise | PgBouncer + directUrl, INCLUDE version, pg_stat_statements |
| mongodb-patterns | revise | Decimal128 driver syntax, profiling level signature, Stable API note |
| mocha-chai-sinon | revise | tsx loader config, chai-as-promised ordering, c8 alternative |
| podman-rootless | revise | `podman compose` clarification, Mac caveat, port-binding alternatives |
| claude-api-patterns | revise | max iterations in loop, batch results streaming details |
| vite-config-and-build | revise | env-var HMR claim, target wording |
| opentelemetry-nodejs | revise | resourceFromAttributes version note, Collector topology mention |

All approved for ingest after a single revision pass.
