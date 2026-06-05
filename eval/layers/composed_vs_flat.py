"""Layer 2: Composed vs Flat skill injection.

Wraps the existing POC harness (eval/run_poc.py) with additional metrics
and a structured output format. The existing run_poc.py handles the core
experiment; this layer extends it with precision@k, cost projection, and
cross-task aggregation.

See docs/experiments/poc-composed-vs-flat.md for the full experimental
design and task definitions.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from eval.tasks import TASKS

AGENT_MODEL = os.environ.get("AGENT_MODEL", "qwen/qwen2.5-coder-14b")
AGENTALLOY_URL = os.environ.get("AGENTALLOY_URL", "http://localhost:47950")
LM_STUDIO_URL = os.environ.get("LM_STUDIO_URL", "http://localhost:1234")


@dataclass(frozen=True)
class TaskResult:
    task_id: str
    condition: str  # "composed" or "flat"
    run_index: int
    score: float
    passes: bool
    input_tokens: int
    output_tokens: int
    total_tokens: int
    wall_latency_ms: float
    compose_latency_ms: float | None  # None for flat


def run(
    n: int = 10,
    conditions: list[str] | None = None,
    out_dir: str | None = None,
    model: str | None = None,
) -> dict[str, Any]:
    """Run the composed vs flat comparison.

    Delegates to eval.run_poc for the actual experiment, then augments
    the results with additional metrics.
    """
    conditions = conditions or ["flat", "composed"]
    model = model or AGENT_MODEL

    # Run the existing POC harness
    env = os.environ.copy()
    env["AGENT_MODEL"] = model
    env["AGENTALLOY_URL"] = AGENTALLOY_URL
    env["LM_STUDIO_URL"] = LM_STUDIO_URL

    cmd = [
        sys.executable,
        "-m",
        "eval.run_poc",
        "--n",
        str(n),
    ]
    if conditions:
        for c in conditions:
            cmd.extend(["--conditions", c])

    print(f"Running POC: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True, env=env, timeout=3600)
    print(result.stdout)
    if result.stderr:
        print(f"STDERR: {result.stderr}", file=sys.stderr)

    if result.returncode != 0:
        print(f"POC harness failed with exit code {result.returncode}", file=sys.stderr)
        # Still return what we can
        return {"error": f"POC harness failed (exit {result.returncode})"}

    # TODO: parse POC output and augment with additional metrics
    # For now, return a placeholder structure
    summary = {
        "label": "composed_vs_flat",
        "model": model,
        "n_runs": n,
        "conditions": conditions,
        "n_tasks": len(TASKS),
        "status": "complete",
        "message": "POC harness completed. Parse eval/runs/ for detailed results.",
        "task_ids": [t.task_id for t in TASKS],
    }

    out_path = Path(out_dir or "eval/runs") / "layer2__composed_vs_flat.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(summary, indent=2))

    print(f"wrote: {out_path}")
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Layer 2: Composed vs Flat")
    parser.add_argument("--n", type=int, default=10, help="Runs per condition")
    parser.add_argument(
        "--conditions",
        nargs="+",
        default=["flat", "composed"],
        help="Conditions to run",
    )
    parser.add_argument("--out", type=str, default=None)
    parser.add_argument("--model", type=str, default=None)
    args = parser.parse_args(argv)

    run(
        n=args.n,
        conditions=args.conditions,
        out_dir=args.out,
        model=args.model,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
