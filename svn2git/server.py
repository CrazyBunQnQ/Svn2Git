from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from svn2git.commands import CommandRunner, DryRunRunner
from svn2git.config import ConfigError, load_config
from svn2git.jobs import JobRunner, SyncJob, load_entries, selected_repo_names
from svn2git.service import SyncService


@dataclass(frozen=True)
class Response:
    status_code: int
    body: str


def handle_sync_request(repo_name: str, config_path: str | Path, log_xml_path: str | Path | None, dry_run: bool = False) -> Response:
    try:
        config = load_config(config_path)
        if repo_name != "all" and repo_name not in config.repositories:
            return Response(404, "未找到仓库配置信息")
        runner = DryRunRunner() if dry_run else CommandRunner()
        service = SyncService(runner)
        job_runner = JobRunner(
            lambda job: service.sync(
                config,
                job.repo_name,
                load_entries(config, job.repo_name, runner, log_xml_path, job.dry_run),
                dry_run=job.dry_run,
            ).render()
        )
        for current_repo_name in selected_repo_names(config, repo_name):
            job_runner.enqueue(SyncJob(repo_name=current_repo_name, trigger_source="server", dry_run=dry_run))
        jobs = job_runner.run_pending()
    except (ConfigError, ValueError) as exc:
        return Response(500, f"同步仓库失败: {exc}")

    status_code = 500 if any(job.status == "failed" for job in jobs) else 200
    lines = []
    for job in jobs:
        lines.append(f"同步仓库任务 {job.status}: {job.repo_name}")
        if job.error:
            lines.append(job.error)
        if job.result:
            lines.append(job.result)
    return Response(status_code, "\n".join(lines))
