# skillsmith

Runtime skill composition service. Gives your coding agent access to a curated corpus of engineering skills — testing patterns, error handling, deployment recipes, observability, security, and more — composed dynamically per task.

The runtime holds **no generative LLM** — only an embedding service. Your agent calls the API and does its own assembly inside its own prompt context.

> **60% smaller prompts. 25% faster runs. Same model — and answers improve, not degrade.**
> — see `docs/experiments/poc-composed-vs-flat.md` §13

---

## Quickstart

**1. Clone into your tools directory**

```bash
cd ~/dev          # or wherever you keep tools
git clone https://github.com/nrmeyers/skillsmith.git
cd skillsmith
```

**2. Open your coding harness of choice** (Claude Code, Cursor, Gemini CLI, Continue.dev, etc.)

**3. Tell your agent to install**

```
Install this tool by following INSTALL.md
```

That's it. The agent reads `INSTALL.md`, detects your hardware, pulls the embedding model, seeds the corpus, and wires itself up. Total time: 3–5 minutes on a warm machine.

---

## Requirements

- Python 3.12+ with [`uv`](https://github.com/astral-sh/uv)
- An embedding service matching your hardware (see [Platform Setup](#platform-setup))
- A supported coding harness (Claude Code, Cursor, Gemini CLI, Continue.dev, OpenCode, Aider, Cline)

---

## Platform Setup

The runtime requires only an embedding service. The install agent handles configuration automatically, but here's the reference:

| Preset | Hardware | Embedding backend | RAM / VRAM minimum |
|--------|----------|-------------------|--------------------|
| `cpu` | Any x86_64 / ARM64 | Ollama on CPU | 8 GB RAM |
| `apple-silicon` | Apple M1/M2/M3/M4 | Ollama (Metal) | 8 GB unified |
| `nvidia` | NVIDIA GPU (CUDA) | Ollama (CUDA) | 4 GB VRAM |
| `radeon` | AMD Radeon dGPU or iGPU | LM Studio (Vulkan) | 4 GB VRAM |

All presets use `qwen3-embedding:0.6b` (1024-dim). `cpu`, `apple-silicon`, and `nvidia` use Ollama at `localhost:11434`; `radeon` uses LM Studio's Vulkan backend at `localhost:1234`.

**Ollama presets** — pull the embedding model once:
```bash
ollama pull qwen3-embedding:0.6b
```

**Radeon preset** — open LM Studio, search for `qwen3-embedding:0.6b`, download the Q8 variant, and start the local server.

For authoring (generating new skills via the LLM pipeline), you also need a chat model. Authoring is optional — the service runs fine with the pre-seeded corpus and no generation model.

---

## Manual setup (without the agent)

```bash
uv sync
uv tool install --editable .   # puts `skillsmith` in PATH system-wide
skillsmith setup
skillsmith serve
```

`skillsmith setup` walks an interactive composer (`write-env` → `seed-corpus` → `install-packs` → `install-mcp` → `install-rules`). The `install-packs` step prompts you to pick which in-tree packs to install.

**Headless one-liner** — clone, install every in-tree pack non-interactively, no prompts:

```bash
uv sync
uv run python -m skillsmith.install install-packs --packs all --non-interactive
```

This walks `src/skillsmith/_packs/*/pack.yaml`, ingests every pack into the local LadybugDB + DuckDB corpus, and runs one bulk reembed at the end. Use when scripting CI environments, container builds, or fresh dev machines.

---

## Packs shipping in-tree

The corpus is split into **packs** — opt-in groups of related skills. As of 2026-05-05, `main` ships:

| Pack | Tier | Skills | Status |
|---|---|---:|---|
| `meta` | system | – | always-on |
| `conventions` | system | – | always-on |
| `core` | foundation | 12 | always-on |
| `engineering` | foundation | 5 | default-on |
| `documentation` | foundation | 4 | opt-in |
| `refactoring` | foundation | 4 | opt-in |
| `performance` | foundation | 4 | opt-in |
| `python` | language | 5 | opt-in |
| `typescript` | language | 5 | opt-in |
| `nodejs` | language | 5 | opt-in |
| `go` | language | 5 | opt-in |
| `rust` | language | 5 | opt-in |

Authored against authoritative upstream docs per the R1–R8 quality contract in `src/skillsmith/_packs/meta/sys-skill-authoring-rules.md`. Each pack ships with `.qa.md` reports under `docs/skill-review-history/` documenting the independent Critic review verdicts.

To author a new pack, see `docs/PACK-AUTHORING.md` and the latest session handoff under `docs/session-handoff-*.md`.

---

## Run via container (no Python required)

For evaluators or CI environments:

```bash
podman compose up -d         # or: docker compose up -d
curl http://localhost:47950/health
```

This brings up:
- `skillsmith` — FastAPI service on port 47950, with the pre-seeded corpus baked in
- `ollama` — Ollama on port 11434 with `qwen3-embedding:0.6b` auto-pulled on first start

Persistent state:
- `./data` is bind-mounted into the container — runtime ingestions persist on the host
- Ollama models live in a named volume (`skillsmith-ollama-models`) — not re-pulled on restart

```bash
podman compose down              # stop, keep volumes
podman compose down -v           # stop and remove ollama-models volume
```

---

## Test

```bash
uv run ruff check .
uv run ruff format --check .
uv run pyright
uv run pytest                    # unit tests only
uv run pytest -m integration     # requires Ollama with qwen3-embedding:0.6b
```

---

## Configuration

Environment variables (written automatically by `skillsmith install write-env`):

| Variable | Default | Purpose |
|----------|---------|---------|
| `RUNTIME_EMBED_BASE_URL` | `http://localhost:11434` | Embedding endpoint (`http://localhost:1234` for radeon preset) |
| `RUNTIME_EMBEDDING_MODEL` | `qwen3-embedding:0.6b` | Embedding model for retrieve / compose |
| `LADYBUG_DB_PATH` | `./data/ladybug` | LadybugDB directory |
| `DUCKDB_PATH` | `./data/skills.duck` | DuckDB vector + telemetry store |
| `AUTHORING_MODEL` | `qwen/qwen3.6-35b-a3b` | Model for skill generation (authoring only) |
| `CRITIC_MODEL` | `qwen/qwen3.6-35b-a3b` | Model for authoring critic (authoring only) |
| `AUTHORING_EMBEDDING_MODEL` | `qwen3-embedding:0.6b` | Authoring-pipeline embedding model (authoring only) |
| `DEDUP_HARD_THRESHOLD` | `0.92` | Dedup hard cosine threshold |
| `DEDUP_SOFT_THRESHOLD` | `0.80` | Dedup soft cosine threshold |
| `BOUNCE_BUDGET` | `3` | Max retrieval bounces |
| `LOG_LEVEL` | `INFO` | Log verbosity |

---

## Architecture

- **Embedding service** — `qwen3-embedding:0.6b` (1024-dim). Backend-agnostic: Ollama, LM Studio, vLLM all work via the OpenAI-compatible `/v1/embeddings` API.
- **DuckDB** — 1024-dim L2-normalized fragment vectors, BM25 FTS index, and composition traces.
- **LadybugDB (Kùzu)** — skill graph (Skill → SkillVersion → Fragment).
- **Retrieval** — hybrid BM25 + dense cosine search fused via Reciprocal Rank Fusion (RRF). Token-literal queries ("JWT", "Prisma") surface via BM25; semantic queries surface via dense.
- **Compose flow** — agent → `POST /compose` → embed task → hybrid retrieve → hydrate fragments → return raw concatenated text. Agent assembles in its own prompt context.
- **No generative LLM in the runtime path.**

---

## Empirical results

See `docs/experiments/poc-composed-vs-flat.md` §13. Headline:

> **60% smaller prompts. 25% faster runs. Same model — and answers improve, not degrade.**

Reproduce: `AGENT_MODEL=qwen/qwen3.6-35b-a3b uv run python -m eval.run_poc --n 3` (requires running skillsmith + LM Studio with the agent model loaded).
