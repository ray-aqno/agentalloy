"""Install CLI — idempotent subcommands for the INSTALL.md runbook.

Usage::

    python -m agentalloy.install <subcommand> [args]

Subcommands are organised under ``agentalloy.install.subcommands``.
Each module exposes ``add_parser(subparsers)`` and ``run(args) -> int``.
"""
