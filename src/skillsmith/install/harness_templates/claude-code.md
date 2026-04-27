## Skill API access

A local skillsmith service is running at `http://localhost:{port}` exposing a curated corpus of engineering skills.

When you need procedural guidance on a coding task — testing patterns, error handling, deployment, observability, etc. — query the service:

```bash
curl -s -X POST http://localhost:{port}/compose \
  -H 'Content-Type: application/json' \
  -d '{"task": "<describe the task in one sentence>", "phase": "build"}'
```

Phases: `spec`, `design`, `build`, `qa`, `ops`. Pass `phase` matching the lifecycle stage of the task.

The response is a JSON object with `output` (concatenated raw fragments to inject into your context) and `source_skills` (which skills contributed). Read the `output` field and incorporate the guidance into your reasoning before generating code.

Health check: `curl -s http://localhost:{port}/health` should return `{"status":"ok"}`. If it doesn't, run `python -m skillsmith.install doctor` from the skillsmith repo to diagnose.
