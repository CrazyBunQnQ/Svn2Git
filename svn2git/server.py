from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from svn2git.commands import CommandRunner, DryRunRunner
from svn2git.config import ConfigError, load_config
from svn2git.service import SyncService
from svn2git.svn_log import parse_svn_log_xml


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
        if log_xml_path is None:
            from svn2git.svn_client import SvnClient

            entries = parse_svn_log_xml(SvnClient(runner).log_xml(config.repositories[repo_name].svn_url))
        else:
            entries = parse_svn_log_xml(Path(log_xml_path).read_text(encoding="utf-8"))
        service = SyncService(runner)
        plans = []
        repo_names = config.repositories.keys() if repo_name == "all" else [repo_name]
        for current_repo_name in repo_names:
            plans.append(service.sync(config, current_repo_name, entries, dry_run=dry_run).render())
    except (ConfigError, ValueError) as exc:
        return Response(500, f"同步仓库失败: {exc}")

    return Response(200, "已调起同步仓库任务，请稍后查看 Git 远程仓库状态\n" + "\n".join(plans))
