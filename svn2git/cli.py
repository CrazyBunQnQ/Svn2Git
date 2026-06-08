from __future__ import annotations

import argparse
import sys
from pathlib import Path

from svn2git.commands import CommandRunner, DryRunRunner
from svn2git.config import ConfigError, load_config
from svn2git.service import SyncService
from svn2git.svn_client import SvnClient
from svn2git.svn_log import parse_svn_log_xml


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="svn2git")
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate_parser = subparsers.add_parser("validate-config")
    validate_parser.add_argument("--config", required=True)

    sync_parser = subparsers.add_parser("sync")
    sync_parser.add_argument("--config", required=True)
    sync_parser.add_argument("--repo", required=True)
    sync_parser.add_argument("--log-xml")
    sync_parser.add_argument("--dry-run", action="store_true")

    args = parser.parse_args(argv)
    try:
        if args.command == "validate-config":
            load_config(args.config)
            print("config ok")
            return 0
        if args.command == "sync":
            config = load_config(args.config)
            runner = DryRunRunner() if args.dry_run else CommandRunner()
            service = SyncService(runner)
            if args.repo == "all":
                for repo_name in config.repositories:
                    entries = _load_entries(config, repo_name, runner, args.log_xml, args.dry_run)
                    plan = service.sync(config, repo_name, entries, dry_run=args.dry_run)
                    print(plan.render())
                if isinstance(runner, DryRunRunner):
                    _print_commands(runner)
                return 0
            entries = _load_entries(config, args.repo, runner, args.log_xml, args.dry_run)
            plan = service.sync(config, args.repo, entries, dry_run=args.dry_run)
            print(plan.render())
            if isinstance(runner, DryRunRunner):
                _print_commands(runner)
            return 0
    except (ConfigError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    return 2


def _print_commands(runner: DryRunRunner) -> None:
    print("Commands:")
    for command in runner.commands:
        location = f" [{command.cwd}]" if command.cwd else ""
        print(f"- {' '.join(command.args)}{location}")


def _load_entries(config, repo_name: str, runner, log_xml: str | None, dry_run: bool):
    if log_xml:
        return parse_svn_log_xml(Path(log_xml).read_text(encoding="utf-8"))
    if dry_run:
        raise ValueError("--log-xml is required for dry-run sync")
    repository = config.repositories[repo_name]
    return parse_svn_log_xml(SvnClient(runner).log_xml(repository.svn_url))


if __name__ == "__main__":
    raise SystemExit(main())
