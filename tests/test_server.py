from pathlib import Path

from svn2git.server import handle_sync_request


FIXTURES = Path(__file__).parent / "fixtures"


def test_handle_sync_request_preserves_sync_route_message():
    response = handle_sync_request(
        "suite",
        config_path=FIXTURES / "application_modules.yml",
        log_xml_path=FIXTURES / "svn_log.xml",
        dry_run=True,
    )

    assert response.status_code == 200
    assert "同步仓库任务 succeeded" in response.body
    assert "modules/billing" in response.body


def test_handle_sync_request_reports_missing_repo():
    response = handle_sync_request(
        "missing",
        config_path=FIXTURES / "application_modules.yml",
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
        config_path=FIXTURES / "application_modules.yml",
        log_xml_path=None,
        dry_run=False,
    )

    assert response.status_code == 200
    assert calls == ["real"]


def test_handle_sync_request_all_loads_each_repo_log_without_all_repository(monkeypatch):
    requested_urls = []

    class FakeCommandRunner:
        def require(self, args, cwd=None):
            requested_urls.append(args[2])

            class Result:
                stdout = '<log version="1"><logentry revision="1"><author>alice</author><msg>x</msg><paths /></logentry></log>'

            return Result()

        def run(self, args, cwd=None):
            class Result:
                exit_code = 0
                stdout = "ok"
                stderr = ""

            return Result()

    class FakePlan:
        def __init__(self, repo_name):
            self.repo_name = repo_name

        def render(self):
            return f"plan {self.repo_name}"

    class FakeSyncService:
        def __init__(self, runner):
            pass

        def sync(self, config, repo_name, entries, dry_run=False, push=True):
            return FakePlan(repo_name)

    monkeypatch.setattr("svn2git.server.CommandRunner", FakeCommandRunner)
    monkeypatch.setattr("svn2git.server.SyncService", FakeSyncService)

    response = handle_sync_request(
        "all",
        config_path=FIXTURES / "application_modules.yml",
        log_xml_path=None,
        dry_run=False,
    )

    assert response.status_code == 200
    assert "plan suite" in response.body
    assert "plan archive" in response.body
    assert requested_urls == [
        "https://svn.example.com/repos/main",
        "https://svn.example.com/repos/billing-dev",
        "https://svn.example.com/repos/archive",
    ]


def test_handle_sync_request_routes_through_job_runner(monkeypatch):
    created_jobs = []

    class FakeJobRunner:
        def __init__(self, executor):
            self.executor = executor

        def enqueue(self, job):
            created_jobs.append(job)
            return job

        def run_pending(self):
            job = created_jobs[-1]
            job.result = "job plan"
            job.status = "succeeded"
            return [job]

    monkeypatch.setattr("svn2git.server.JobRunner", FakeJobRunner)

    response = handle_sync_request(
        "suite",
        config_path=FIXTURES / "application_modules.yml",
        log_xml_path=FIXTURES / "svn_log.xml",
        dry_run=True,
    )

    assert response.status_code == 200
    assert created_jobs[0].repo_name == "suite"
    assert created_jobs[0].trigger_source == "server"
    assert created_jobs[0].dry_run is True
    assert "job plan" in response.body
