from __future__ import annotations

from dataclasses import dataclass
from itertools import count
from pathlib import Path
from typing import Callable

from svn2git.commands import CommandRunner, DryRunRunner
from svn2git.config import AppConfig, RepositoryConfig
from svn2git.svn_client import SvnClient
from svn2git.svn_log import LogEntry, parse_svn_log_xml


@dataclass
class SyncJob:
    repo_name: str
    trigger_source: str
    git_branch: str = "*"
    target_revision: int | None = None
    dry_run: bool = False
    status: str = "queued"
    result: str | None = None
    error: str | None = None
    id: str | None = None

    @property
    def lock_key(self) -> tuple[str, str]:
        return self.repo_name, self.git_branch


class JobRunner:
    def __init__(self, executor: Callable[[SyncJob], str]) -> None:
        self.executor = executor
        self.queued_jobs: list[SyncJob] = []
        self._active_locks: set[tuple[str, str]] = set()
        self._ids = count(1)

    def enqueue(self, job: SyncJob) -> SyncJob:
        for queued in self.queued_jobs:
            if queued.lock_key == job.lock_key:
                queued.target_revision = self._highest_revision(queued.target_revision, job.target_revision)
                return queued
        if job.id is None:
            job.id = f"job-{next(self._ids)}"
        self.queued_jobs.append(job)
        return job

    def run_pending(self) -> list[SyncJob]:
        completed = []
        remaining = []
        for job in self.queued_jobs:
            if job.lock_key in self._active_locks:
                remaining.append(job)
                continue
            self.acquire_lock(*job.lock_key)
            try:
                job.status = "running"
                job.result = self.executor(job)
                job.status = "succeeded"
            except Exception as exc:
                job.error = str(exc)
                job.status = "failed"
            finally:
                self.release_lock(*job.lock_key)
            completed.append(job)
        self.queued_jobs = remaining
        return completed

    def acquire_lock(self, repo_name: str, git_branch: str = "*") -> None:
        self._active_locks.add((repo_name, git_branch))

    def release_lock(self, repo_name: str, git_branch: str = "*") -> None:
        self._active_locks.discard((repo_name, git_branch))

    def _highest_revision(self, left: int | None, right: int | None) -> int | None:
        if left is None:
            return right
        if right is None:
            return left
        return max(left, right)


def selected_repo_names(config: AppConfig, repo_name: str) -> list[str]:
    if repo_name == "all":
        return list(config.repositories)
    if repo_name not in config.repositories:
        raise ValueError(f"repository not found: {repo_name}")
    return [repo_name]


def load_entries(
    config: AppConfig,
    repo_name: str,
    runner: CommandRunner | DryRunRunner,
    log_xml_path: str | Path | None,
    dry_run: bool,
) -> list[LogEntry]:
    if log_xml_path:
        return parse_svn_log_xml(Path(log_xml_path).read_text(encoding="utf-8"))
    if dry_run:
        raise ValueError("--log-xml is required for dry-run sync")
    repository = config.repositories[repo_name]
    client = SvnClient(runner)
    entries = []
    for svn_url in svn_log_urls(repository):
        entries.extend(parse_svn_log_xml(client.log_xml(svn_url, config.svn_username, config.svn_password)))
    return entries


def svn_log_urls(repository: RepositoryConfig) -> list[str]:
    urls = []
    for target in repository.expand_targets():
        urls.append(target.svn_url)
        urls.extend(override.svn_url for override in target.branch_overrides.values() if override.svn_url)
    return list(dict.fromkeys(urls))
