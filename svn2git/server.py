from __future__ import annotations

from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from svn2git.commands import CommandRunner, DryRunRunner
from svn2git.config import ConfigError, load_config
from svn2git.jobs import JobRunner, SyncJob, load_entries, selected_repo_names
from svn2git.reverse_sync import ReverseSyncRequest, plan_reverse_sync
from svn2git.service import SyncService


@dataclass(frozen=True)
class Response:
    status_code: int
    body: str


class SyncServiceApp:
    def __init__(self, config_path: str | Path, log_xml_path: str | Path | None = None, dry_run: bool = False) -> None:
        self.config_path = Path(config_path)
        self.log_xml_path = Path(log_xml_path) if log_xml_path else None
        self.dry_run = dry_run
        self.jobs: dict[str, Response] = {}

    def handle(self, method: str, path: str) -> Response:
        parsed = urlparse(path)
        route = parsed.path.strip("/")
        if method == "GET" and route == "health":
            return Response(200, "ok")
        if method == "POST" and route == "sync":
            return self._trigger("all")
        if method == "POST" and route.startswith("sync/"):
            return self._trigger(route.split("/", 1)[1])
        if method == "POST" and route.startswith("reverse-sync/"):
            return self._reverse_sync(route.split("/", 1)[1], "")
        if method == "GET" and route.startswith("jobs/"):
            repo_name = route.split("/", 1)[1]
            return self.jobs.get(repo_name) or Response(404, "job status not found")
        return Response(404, "not found")

    def _trigger(self, repo_name: str) -> Response:
        response = handle_sync_request(repo_name, self.config_path, self.log_xml_path, dry_run=self.dry_run)
        body = f"job_id={repo_name}\n{response.body}"
        recorded = Response(response.status_code, body)
        self.jobs[repo_name] = recorded
        return recorded

    def _reverse_sync(self, repo_name: str, body: str) -> Response:
        config = load_config(self.config_path)
        values = _parse_body(body)
        request = ReverseSyncRequest(
            repo_name=repo_name,
            git_branch=values.get("branch", "master"),
            commit_sha=values.get("commit", "unknown"),
            commit_message=values.get("message", "Reverse sync"),
            changed_paths=tuple(path for path in values.get("paths", "").splitlines() if path),
            module_hint=values.get("module"),
        )
        try:
            plan = plan_reverse_sync(config, request)
        except ValueError as exc:
            return Response(400, str(exc))
        return Response(200, f"reverse-sync accepted: {plan.target_name} {plan.svn_path}")


def create_http_server(app: SyncServiceApp, host: str, port: int) -> ThreadingHTTPServer:
    class RequestHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            self._respond(app.handle("GET", self.path))

        def do_POST(self) -> None:
            length = int(self.headers.get("Content-Length", "0"))
            body = self.rfile.read(length).decode("utf-8") if length else ""
            if self.path.startswith("/reverse-sync/"):
                repo_name = self.path.strip("/").split("/", 1)[1]
                self._respond(app._reverse_sync(repo_name, body))
                return
            self._respond(app.handle("POST", self.path))

        def log_message(self, format: str, *args) -> None:
            return None

        def _respond(self, response: Response) -> None:
            encoded = response.body.encode("utf-8")
            self.send_response(response.status_code)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

    return ThreadingHTTPServer((host, port), RequestHandler)


def _parse_body(body: str) -> dict[str, str]:
    values = {}
    current_key = None
    for line in body.splitlines():
        if ":" in line:
            key, value = line.split(":", 1)
            current_key = key.strip()
            values[current_key] = value.strip()
        elif current_key:
            values[current_key] = f"{values[current_key]}\n{line}" if values[current_key] else line
    return values


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
