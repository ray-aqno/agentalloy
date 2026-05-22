# Skillsmith install/uninstall sandbox

A hermetic podman playground for practicing install and uninstall flows
without polluting your host system. Built around your local checkout so
edits are live.

## One-time setup

From the repo root:

```bash
podman build -t skillsmith-sandbox -f tests/sandbox/Containerfile .
# Optional but recommended — keeps pulled ollama models across runs
# so you're not redownloading Qwen3-Embedding-0.6B every time.
podman volume create skillsmith-ollama-cache
```

## Drop into a fresh sandbox

```bash
podman run --rm -it \
  -v "$(pwd):/src:ro" \
  -v "$(pwd)/tests/sandbox:/sandbox:ro" \
  -v skillsmith-ollama-cache:/root/.ollama \
  skillsmith-sandbox

# Inside the container:
source /sandbox/helpers.sh
ss-install        # editable-install skillsmith from /src
ollama-up         # background ollama daemon
```

Now you've got a real `skillsmith` on the PATH, a real ollama running,
and a fresh `$HOME`. Try whatever — install, uninstall, mess with state,
nuke it and start over.

## Useful helpers (after `source /sandbox/helpers.sh`)

| Function | What it does |
|---|---|
| `ss-install` | Editable-install skillsmith from the mounted source |
| `ss-clean` | Wipe `~/.config/skillsmith` + `~/.local/share/skillsmith` — back to "first run" |
| `ss-state` | Pretty-print `install-state.json` |
| `ss-pending` | Just `.pending_pack_selection` from the state file |
| `ss-pid` | Just `.spawned_ollama_pid` from the state file |
| `ss-models` | What ollama has cached locally |
| `ss-procs` | Running ollama / llama-server / skillsmith processes |
| `ollama-up` / `ollama-down` | Start/stop the daemon manually |

The two `ss-pending` / `ss-pid` helpers exist because those are the new
state fields the PR introduced — handy for peeking at whether the
handoff fired the way you expected.

## Iterating

The host's `~/dev/skillsmith` is mounted at `/src`. Edit files on the
host, then re-run `ss-install` inside the container to refresh the
editable install. No rebuild needed.

Exit and re-run `podman run ...` whenever you want a totally fresh
`$HOME` — every container start is a new install.

## Cleanup

```bash
podman rmi skillsmith-sandbox
podman volume rm skillsmith-ollama-cache
```

## Caveats

- CPU only (no GPU passthrough configured — add `--device nvidia.com/gpu=all`
  if you want it).
- No systemd, so `--service persistent` won't work. Use `--service manual`
  during setup.
- Rootless podman caps memlock at ~12 GB. Fine for the 600 MB embed model,
  not for stacking a full LLM on top.
