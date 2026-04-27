"""Install CLI — idempotent subcommands for the INSTALL.md runbook.

Usage::

    python -m skillsmith.install <subcommand> [args]

Subcommands are organised under ``skillsmith.install.subcommands``.
Each module exposes ``add_parser(subparsers)`` and ``run(args) -> int``.
"""
