from __future__ import annotations

import argparse
import sys
from pathlib import Path

from svn2git.commands import CommandRunner, DryRunRunner
from svn2git.config import ConfigError, load_config
from svn2git.jobs import JobRunner, SyncJob, load_entries, selected_repo_names
from svn2git.service import SyncService


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
    sync_parser.add_argument("--no-push", action="store_true")

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
            job_runner = JobRunner(
                lambda job: service.sync(
                    config,
                    job.repo_name,
                    load_entries(config, job.repo_name, runner, args.log_xml, job.dry_run),
                    dry_run=job.dry_run,
                    push=not args.no_push,
                ).render()
            )
            for repo_name in selected_repo_names(config, args.repo):
                job_runner.enqueue(SyncJob(repo_name=repo_name, trigger_source="cli", dry_run=args.dry_run))
            for job in job_runner.run_pending():
                if job.result:
                    print(job.result)
                if job.status == "failed":
                    raise ValueError(job.error or "sync failed")
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


_load_entries = load_entries


if __name__ == "__main__":
    raise SystemExit(main())
