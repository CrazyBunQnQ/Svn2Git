from pathlib import Path

import pytest

from svn2git.config import load_config
from svn2git.reverse_sync import ReverseSyncRequest, plan_reverse_sync, service_generated_commit


FIXTURES = Path(__file__).parent / "fixtures"
ROOT = Path(__file__).parents[1]


def test_service_generated_commit_marker_is_skipped():
    assert service_generated_commit("Patch\n\nSvn2Git-Origin: svn") is True


def test_legacy_svn_version_commit_is_skipped():
    assert service_generated_commit("SVN version 41: Add billing feature") is True


def test_reverse_sync_maps_module_path_to_branch_override_source():
    config = load_config(FIXTURES / "application_modules.yml")
    request = ReverseSyncRequest(
        repo_name="suite",
        git_branch="dev",
        commit_sha="abc123",
        commit_message="Patch billing",
        changed_paths=("modules/billing/src/app.py",),
    )

    plan = plan_reverse_sync(config, request)

    assert plan.target_name == "suite:billing"
    assert plan.svn_project_path == "Q:\\svn2git-fixture\\svn\\BillingDev"
    assert plan.svn_path == Path("src/app.py")
    assert "Git commit: abc123" in plan.commit_message
    assert "Svn2Git-Origin: git" in plan.commit_message


def test_reverse_sync_maps_git_branch_name_to_override_key():
    config = load_config(FIXTURES / "application_singularity.yml")
    request = ReverseSyncRequest(
        repo_name="singularity",
        git_branch="2.13",
        commit_sha="abc123",
        commit_message="Patch framework",
        changed_paths=("platform-resource/src/Fix.java",),
        module_hint="framework",
    )

    plan = plan_reverse_sync(config, request)

    assert plan.target_name == "singularity:framework"
    assert plan.svn_project_path == "F:\\SvnTest\\SingularityFramework-2.13"
    assert plan.svn_branch == "platform_2.13"


def test_reverse_sync_requires_module_hint_for_root_target_modules():
    config = load_config(FIXTURES / "application_singularity.yml")
    request = ReverseSyncRequest(
        repo_name="singularity",
        git_branch="2.13",
        commit_sha="abc123",
        commit_message="Patch root module",
        changed_paths=("src/Fix.java",),
    )

    with pytest.raises(ValueError, match="module_hint"):
        plan_reverse_sync(config, request)


def test_reverse_sync_rejects_unmatched_changed_path():
    config = load_config(FIXTURES / "application_modules.yml")
    request = ReverseSyncRequest(
        repo_name="suite",
        git_branch="dev",
        commit_sha="abc123",
        commit_message="Patch unknown",
        changed_paths=("unknown/path.py",),
    )

    with pytest.raises(ValueError, match="does not match"):
        plan_reverse_sync(config, request)


def test_reverse_sync_rejects_later_unmatched_changed_path():
    config = load_config(FIXTURES / "application_modules.yml")
    request = ReverseSyncRequest(
        repo_name="suite",
        git_branch="dev",
        commit_sha="abc123",
        commit_message="Patch mixed",
        changed_paths=("modules/billing/src/app.py", "unknown/path.py"),
    )

    with pytest.raises(ValueError, match="does not match"):
        plan_reverse_sync(config, request)


def test_reverse_sync_rejects_mixed_target_changed_paths():
    config = load_config(FIXTURES / "application_modules.yml")
    request = ReverseSyncRequest(
        repo_name="suite",
        git_branch="dev",
        commit_sha="abc123",
        commit_message="Patch mixed targets",
        changed_paths=("modules/billing/src/app.py", "modules/reporting/report.txt"),
    )

    with pytest.raises(ValueError, match="mixed reverse targets"):
        plan_reverse_sync(config, request)


def test_client_hooks_call_service_without_local_svn_mutation():
    for hook in [ROOT / "hooks" / "Platform" / "pre-commit", ROOT / "hooks" / "Singularity" / "pre-commit"]:
        content = hook.read_text(encoding="utf-8")
        assert ".svn_path" not in content
        assert "svn update" not in content
        assert "svn commit" not in content
        assert "192.168.1.58" not in content
        assert "SVN2GIT_SERVICE_URL" in content
        assert "SVN2GIT_REPO_NAME" in content
        assert "/reverse-sync/" in content


def test_pre_push_hooks_reject_direct_push_with_service_message():
    for hook in [ROOT / "hooks" / "Platform" / "pre-push", ROOT / "hooks" / "Singularity" / "pre-push"]:
        content = hook.read_text(encoding="utf-8")
        assert "service-owned reverse sync" in content
        assert "SVN2GIT_SERVICE_URL" in content
        assert "exit 1" in content


def test_server_side_hook_templates_are_parameterized():
    pre_receive = (ROOT / "hooks" / "templates" / "pre-receive").read_text(encoding="utf-8")
    post_receive = (ROOT / "hooks" / "templates" / "post-receive").read_text(encoding="utf-8")

    assert "SVN2GIT_SERVICE_URL" in pre_receive
    assert "SVN2GIT_REPO_NAME" in pre_receive
    assert "/reverse-sync/" in pre_receive
    assert "Svn2Git-Origin: svn" in pre_receive
    assert "SVN2GIT_SERVICE_URL" in post_receive
    assert "SVN2GIT_REPO_NAME" in post_receive
    assert "/sync/" in post_receive
