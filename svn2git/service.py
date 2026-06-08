from __future__ import annotations

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

    def sync(self, config: AppConfig, repo_name: str, entries: list[LogEntry], dry_run: bool = False) -> SyncPlan:
        plan = build_sync_plan(config, repo_name, entries, dry_run=dry_run)

        parent = plan.targets[0]
        submodules = [target for target in plan.targets if target.is_submodule]
        for submodule in submodules:
            self._ensure_submodule(parent, submodule)

        for target_plan in plan.target_plans:
            self._sync_target(target_plan.target, target_plan.revisions, dry_run)

        if submodules:
            paths = [submodule.git_submodule_path for submodule in submodules if submodule.git_submodule_path]
            self.runner.require(["git", "add", ".gitmodules", *paths], cwd=parent.git_path)
            self.runner.require(["git", "commit", "-m", "Update submodule pointers for SVN sync"], cwd=parent.git_path)

        return plan

    def _ensure_submodule(self, parent: SyncTarget, submodule: SyncTarget) -> None:
        if not submodule.git_remote_url or not submodule.git_submodule_path:
            return
        self.runner.require(
            ["git", "submodule", "add", submodule.git_remote_url, submodule.git_submodule_path],
            cwd=parent.git_path,
        )
        self.runner.require(["git", "submodule", "update", "--init", submodule.git_submodule_path], cwd=parent.git_path)

    def _sync_target(self, target: SyncTarget, revisions, dry_run: bool) -> None:
        for revision in revisions:
            source_target = replace(
                target,
                svn_url=revision.svn_url,
                svn_project_path=revision.svn_project_path,
                dir_regex=revision.dir_regex,
                dir_suffix=revision.dir_suffix,
            )
            self._checkout_branch(target, revision.git_branch)
            self.runner.require(["svn", "update", "-r", str(revision.revision), source_target.svn_project_path])
            if not dry_run:
                self.file_synchronizer.apply_entry(source_target, revision.entry)
            self.runner.require(["git", "add", "."], cwd=target.git_path)
            message = f"SVN version {revision.revision}"
            if revision.message:
                message = f"{message}: {revision.message}"
            self.runner.require(["git", "commit", "-m", message], cwd=target.git_path)
            self.runner.require(["git", "push", "--all"], cwd=target.git_path)

    def _checkout_branch(self, target: SyncTarget, branch: str) -> None:
        result = self.runner.run(["git", "rev-parse", "--verify", branch], cwd=target.git_path)
        command = ["git", "checkout", branch] if result.exit_code == 0 else ["git", "checkout", "-B", branch]
        self.runner.require(command, cwd=target.git_path)
