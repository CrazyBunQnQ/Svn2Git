import pytest

from svn2git.jobs import JobRunner, SyncJob


def test_sync_job_records_trigger_metadata():
    job = SyncJob(repo_name="suite", trigger_source="cli", dry_run=True)

    assert job.repo_name == "suite"
    assert job.target_revision is None
    assert job.trigger_source == "cli"
    assert job.dry_run is True
    assert job.status == "queued"


def test_job_runner_runs_queued_job_and_records_success():
    calls = []
    runner = JobRunner(lambda job: calls.append(job.repo_name) or "rendered plan")
    job = runner.enqueue(SyncJob(repo_name="suite", trigger_source="cli", dry_run=True))

    results = runner.run_pending()

    assert calls == ["suite"]
    assert results == [job]
    assert job.status == "succeeded"
    assert job.result == "rendered plan"
    assert job.error is None


def test_job_runner_records_failure_status_and_error_text():
    def fail(job):
        raise RuntimeError("sync failed")

    runner = JobRunner(fail)
    job = runner.enqueue(SyncJob(repo_name="suite", trigger_source="server", dry_run=False))

    results = runner.run_pending()

    assert results == [job]
    assert job.status == "failed"
    assert job.error == "sync failed"


def test_job_runner_merges_duplicate_queued_jobs_with_highest_revision():
    runner = JobRunner(lambda job: "ok")

    first = runner.enqueue(SyncJob(repo_name="suite", git_branch="dev", target_revision=41, trigger_source="server"))
    second = runner.enqueue(SyncJob(repo_name="suite", git_branch="dev", target_revision=42, trigger_source="hook"))

    assert second is first
    assert first.target_revision == 42
    assert len(runner.queued_jobs) == 1


def test_job_runner_keeps_different_repo_or_branch_jobs_separate():
    runner = JobRunner(lambda job: "ok")

    suite_dev = runner.enqueue(SyncJob(repo_name="suite", git_branch="dev", trigger_source="server"))
    suite_release = runner.enqueue(SyncJob(repo_name="suite", git_branch="release", trigger_source="server"))
    archive_dev = runner.enqueue(SyncJob(repo_name="archive", git_branch="dev", trigger_source="server"))

    assert runner.queued_jobs == [suite_dev, suite_release, archive_dev]


def test_job_runner_does_not_run_job_when_lock_is_active():
    runner = JobRunner(lambda job: pytest.fail("locked job should not run"))
    runner.acquire_lock("suite", "dev")
    job = runner.enqueue(SyncJob(repo_name="suite", git_branch="dev", trigger_source="server"))

    results = runner.run_pending()

    assert results == []
    assert job.status == "queued"
    assert runner.queued_jobs == [job]


def test_job_runner_stores_completed_jobs_by_id():
    runner = JobRunner(lambda job: "rendered plan")
    job = runner.enqueue(SyncJob(repo_name="suite", trigger_source="server"))

    runner.run_pending()

    assert runner.get_job(job.id) is job
    assert runner.get_job(job.id).result == "rendered plan"


def test_job_runner_returns_none_for_unknown_job_id():
    runner = JobRunner(lambda job: "ok")

    assert runner.get_job("missing") is None
