from __future__ import annotations

from pathlib import Path

from svn2git.commands import CommandRunner, DryRunRunner
from svn2git.config import SyncTarget


class GitRepositoryManager:
    def __init__(self, runner: CommandRunner | DryRunRunner) -> None:
        self.runner = runner

    def prepare(self, target: SyncTarget, branch: str) -> None:
        repository = self._repository(target)
        worktree = target.git_path
        cloned = False
        if not self._is_worktree(worktree):
            if not repository:
                if not isinstance(self.runner, DryRunRunner):
                    raise RuntimeError(f"sync worktree is not a git repository: {worktree}")
            else:
                self.runner.require(["git", "clone", repository, worktree])
                cloned = True
        if repository and not cloned:
            self._ensure_origin(worktree, repository)
            self.runner.require(["git", "fetch", "origin"], cwd=worktree)
        self.checkout_branch(worktree, branch)

    def commit_and_push(self, target: SyncTarget, branch: str, message: str, author: str | None = None, push: bool = True) -> bool:
        worktree = target.git_path
        self.runner.require(["git", "add", "."], cwd=worktree)
        diff_result = self.runner.run(["git", "diff", "--cached", "--quiet"], cwd=worktree)
        if diff_result.exit_code == 0 and not diff_result.stdout.startswith("DRY-RUN "):
            return False
        commit_command = ["git", "commit"]
        if author:
            commit_command.extend(["--author", author])
        commit_command.extend(["-m", message])
        self.runner.require(commit_command, cwd=worktree)
        if push:
            repository = self._repository(target)
            if repository:
                self.runner.require(["git", "push", "origin", branch], cwd=worktree)
            else:
                self.runner.require(["git", "push", "--all"], cwd=worktree)
        return True

    def checkout_branch(self, worktree: str, branch: str) -> None:
        result = self.runner.run(["git", "rev-parse", "--verify", branch], cwd=worktree)
        command = ["git", "checkout", branch] if result.exit_code == 0 else ["git", "checkout", "-B", branch]
        self.runner.require(command, cwd=worktree)

    def _is_worktree(self, worktree: str) -> bool:
        if isinstance(self.runner, DryRunRunner):
            return self.runner.run(["git", "rev-parse", "--is-inside-work-tree"], cwd=worktree).exit_code == 0
        if not Path(worktree).exists():
            return False
        return self.runner.run(["git", "rev-parse", "--is-inside-work-tree"], cwd=worktree).exit_code == 0

    def _ensure_origin(self, worktree: str, repository: str) -> None:
        result = self.runner.run(["git", "remote", "get-url", "origin"], cwd=worktree)
        if result.exit_code != 0:
            self.runner.require(["git", "remote", "add", "origin", repository], cwd=worktree)
            return
        remote_url = result.stdout.strip()
        if remote_url.startswith("DRY-RUN "):
            return
        if not self._same_repository(remote_url, repository):
            raise RuntimeError(f"origin remote mismatch: {remote_url} != {repository}")

    def _repository(self, target: SyncTarget) -> str | None:
        return target.git_repository_path or target.git_remote_url

    def _same_repository(self, left: str, right: str) -> bool:
        if "://" in left or "://" in right or "@" in left or "@" in right:
            return left == right
        return self._normalize_path(left) == self._normalize_path(right)

    def _normalize_path(self, value: str) -> str:
        return str(Path(value.replace("/", "\\")).as_posix()).rstrip("/").casefold()
