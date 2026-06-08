from pathlib import Path

from svn2git.server import handle_sync_request


FIXTURES = Path(__file__).parent / "fixtures"


def test_handle_sync_request_preserves_sync_route_message():
    response = handle_sync_request(
        "suite",
        config_path=FIXTURES / "application_submodules.yml",
        log_xml_path=FIXTURES / "svn_log.xml",
        dry_run=True,
    )

    assert response.status_code == 200
    assert "已调起同步仓库任务" in response.body
    assert "modules/billing" in response.body


def test_handle_sync_request_reports_missing_repo():
    response = handle_sync_request(
        "missing",
        config_path=FIXTURES / "application_submodules.yml",
        log_xml_path=FIXTURES / "svn_log.xml",
        dry_run=True,
    )

    assert response.status_code == 404
    assert "未找到仓库配置信息" in response.body


def test_handle_sync_request_uses_real_runner_when_not_dry_run(monkeypatch):
    calls = []

    class FakeCommandRunner:
        def __init__(self):
            calls.append("real")

        def require(self, args, cwd=None):
            class Result:
                stdout = (FIXTURES / "svn_log.xml").read_text(encoding="utf-8")

            return Result()

        def run(self, args, cwd=None):
            class Result:
                exit_code = 0
                stdout = "ok"
                stderr = ""

            return Result()

    class FakePlan:
        def render(self):
            return "fake plan"

    class FakeSyncService:
        def __init__(self, runner):
            assert isinstance(runner, FakeCommandRunner)

        def sync(self, config, repo_name, entries, dry_run=False):
            return FakePlan()

    monkeypatch.setattr("svn2git.server.CommandRunner", FakeCommandRunner)
    monkeypatch.setattr("svn2git.server.SyncService", FakeSyncService)

    response = handle_sync_request(
        "suite",
        config_path=FIXTURES / "application_submodules.yml",
        log_xml_path=None,
        dry_run=False,
    )

    assert response.status_code == 200
    assert calls == ["real"]
