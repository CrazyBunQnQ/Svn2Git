from pathlib import Path
from http.client import HTTPConnection
from threading import Thread

import svn2git.cli as cli
from svn2git.cli import main
from svn2git.server import Response, SyncServiceApp, create_http_server


FIXTURES = Path(__file__).parent / "fixtures"


def test_service_app_health_endpoint_returns_ok():
    app = SyncServiceApp(config_path=FIXTURES / "application_modules.yml")

    response = app.handle("GET", "/health")

    assert response.status_code == 200
    assert response.body == "ok"


def test_service_app_sync_endpoint_returns_job_status(monkeypatch):
    calls = []

    def fake_handle(repo_name, config_path, log_xml_path, dry_run=False):
        calls.append((repo_name, config_path, log_xml_path, dry_run))
        return Response(200, "同步仓库任务 succeeded: suite\nplan")

    monkeypatch.setattr("svn2git.server.handle_sync_request", fake_handle)
    app = SyncServiceApp(config_path=FIXTURES / "application_modules.yml", log_xml_path=FIXTURES / "svn_log.xml", dry_run=True)

    response = app.handle("POST", "/sync/suite")

    assert response.status_code == 200
    assert "job_id" in response.body
    assert "succeeded" in response.body
    assert calls == [("suite", FIXTURES / "application_modules.yml", FIXTURES / "svn_log.xml", True)]


def test_service_app_sync_all_endpoint_records_status(monkeypatch):
    def fake_handle(repo_name, config_path, log_xml_path, dry_run=False):
        return Response(200, "同步仓库任务 succeeded: suite\n同步仓库任务 succeeded: archive")

    monkeypatch.setattr("svn2git.server.handle_sync_request", fake_handle)
    app = SyncServiceApp(config_path=FIXTURES / "application_modules.yml", log_xml_path=FIXTURES / "svn_log.xml")

    response = app.handle("POST", "/sync")
    status = app.handle("GET", "/jobs/all")

    assert response.status_code == 200
    assert "job_id" in response.body
    assert status.status_code == 200
    assert "suite" in status.body
    assert "archive" in status.body


def test_service_app_unknown_repo_status_returns_404():
    app = SyncServiceApp(config_path=FIXTURES / "application_modules.yml")

    response = app.handle("GET", "/jobs/missing")

    assert response.status_code == 404


def test_create_http_server_binds_configured_host_and_port():
    app = SyncServiceApp(config_path=FIXTURES / "application_modules.yml")

    server = create_http_server(app, "127.0.0.1", 0)
    try:
        assert server.server_address[0] == "127.0.0.1"
        assert server.server_address[1] > 0
    finally:
        server.server_close()


def test_http_reverse_sync_endpoint_accepts_request(monkeypatch):
    app = SyncServiceApp(config_path=FIXTURES / "application_modules.yml")
    server = create_http_server(app, "127.0.0.1", 0)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    body = "branch: dev\ncommit: abc123\nmessage: Patch billing\npaths:\nmodules/billing/src/app.py"
    try:
        connection = HTTPConnection("127.0.0.1", server.server_address[1], timeout=5)
        connection.request("POST", "/reverse-sync/suite", body=body)
        response = connection.getresponse()
        payload = response.read().decode("utf-8")
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    assert response.status == 200
    assert "reverse-sync accepted" in payload


def test_cli_serve_validates_config_and_starts_server(monkeypatch):
    started = []

    class FakeServer:
        def serve_forever(self):
            started.append("serve")

    def fake_create_http_server(app, host, port):
        started.append((app.config_path, host, port))
        return FakeServer()

    monkeypatch.setattr("svn2git.cli.create_http_server", fake_create_http_server)

    exit_code = main(["serve", "--config", str(FIXTURES / "application_modules.yml"), "--host", "127.0.0.1", "--port", "0"])

    assert exit_code == 0
    assert started == [(FIXTURES / "application_modules.yml", "127.0.0.1", 0), "serve"]


def test_cli_serve_rejects_invalid_config(capsys):
    exit_code = main(["serve", "--config", str(FIXTURES / "application_invalid_submodule.yml")])

    assert exit_code == 2
    assert "suite.billing.svn_project_path" in capsys.readouterr().err
