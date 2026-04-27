## Skill API access

A local skillsmith service is running at `http://localhost:{port}` exposing a curated corpus of engineering skills.

When you need procedural guidance on a coding task — testing patterns, error handling, deployment, observability, etc. — use your shell tool to query the service:

```bash
curl -s -X POST http://localhost:{port}/compose \
  -H 'Content-Type: application/json' \
  -d '{"task": "<describe the task in one sentence>", "phase": "build"}'
```

Phases: `spec`, `design`, `build`, `qa`, `ops`. Pass `phase` matching the lifecycle stage of the task.

The response is JSON with `output` (concatenated raw fragments) and `source_skills`. Read `output` and apply the guidance before generating code.

Health check: `curl -s http://localhost:{port}/health` returns `{"status":"ok"}`. If not, run `python -m skillsmith.install doctor` from the skillsmith repo.
