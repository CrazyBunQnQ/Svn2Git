from __future__ import annotations

from collections import defaultdict
from dataclasses import replace

from svn2git.commands import CommandRunner, DryRunRunner
from svn2git.config import AppConfig, SyncTarget
from svn2git.files import FileSynchronizer
from svn2git.planner import SyncPlan, build_sync_plan
from svn2git.svn_log import LogEntry


class SyncService:
    def __init__(self, runner: CommandRunner | DryRunRunner, file_synchronizer: FileSynchronizer | None = None) -> None:
        self.runner = runner
        self.file_synchronizer = file_synchronizer or FileSynchronizer()

    def sync(self, config: AppConfig, repo_name: str, entries: list[LogEntry], dry_run: bool = False, push: bool = True) -> SyncPlan:
        plan = build_sync_plan(config, repo_name, entries, dry_run=dry_run)
        self._sync_plan(plan, dry_run, push)
        return plan

    def _sync_plan(self, plan: SyncPlan, dry_run: bool, push: bool) -> None:
        self._validate_module_targets(plan)
        batches = defaultdict(list)
        for target_plan in plan.target_plans:
            for revision in target_plan.revisions:
                batches[(target_plan.target.git_path, revision.git_branch, revision.revision)].append((target_plan.target, revision))

        configured_repos = set()
        for (_git_path, git_branch, _revision), items in batches.items():
            target = items[0][0]
            first_revision = items[0][1]
            if target.git_path not in configured_repos:
                self._ensure_remote(target)
                configured_repos.add(target.git_path)
            self._checkout_branch(target, git_branch)
            for item_target, revision in items:
                self._sync_target_revision(item_target, revision, dry_run)
            self.runner.require(["git", "add", "."], cwd=target.git_path)
            message = f"SVN version {first_revision.revision}"
            if first_revision.message:
                message = f"{message}: {first_revision.message}"
            self.runner.require(["git", "commit", "-m", message], cwd=target.git_path)
            if push:
                self.runner.require(["git", "push", "--all"], cwd=target.git_path)

    def _sync_target(self, target: SyncTarget, revisions, dry_run: bool) -> None:
        for revision in revisions:
            self._checkout_branch(target, revision.git_branch)
            self._sync_target_revision(target, revision, dry_run)

    def _sync_target_revision(self, target: SyncTarget, revision, dry_run: bool) -> None:
        source_target = replace(
            target,
            svn_url=revision.svn_url,
            svn_project_path=revision.svn_project_path,
            dir_regex=revision.dir_regex,
            dir_suffix=revision.dir_suffix,
        )
        self.runner.require(["svn", "update", "-r", str(revision.revision), source_target.svn_project_path])
        if not dry_run:
            self.file_synchronizer.apply_entry(source_target, revision.entry)

    def _validate_module_targets(self, plan: SyncPlan) -> None:
        seen_roots = set()
        for target in plan.targets:
            if not target.target_path:
                continue
            normalized = target.target_path.replace("\\", "/").strip("/")
            if normalized in {"", "."}:
                continue
            if normalized in seen_roots:
                raise ValueError(f"duplicate module target path: {target.target_path}")
            seen_roots.add(normalized)

    def _ensure_remote(self, target: SyncTarget) -> None:
        if not target.git_remote_url:
            return
        result = self.runner.run(["git", "remote", "get-url", "origin"], cwd=target.git_path)
        if result.exit_code != 0:
            self.runner.require(["git", "remote", "add", "origin", target.git_remote_url], cwd=target.git_path)
            return
        remote_url = result.stdout.strip()
        if remote_url.startswith("DRY-RUN "):
            return
        if remote_url != target.git_remote_url:
            raise RuntimeError(f"origin remote mismatch: {remote_url} != {target.git_remote_url}")

    def _checkout_branch(self, target: SyncTarget, branch: str) -> None:
        result = self.runner.run(["git", "rev-parse", "--verify", branch], cwd=target.git_path)
        command = ["git", "checkout", branch] if result.exit_code == 0 else ["git", "checkout", "-B", branch]
        self.runner.require(command, cwd=target.git_path)
