from pathlib import Path

from svn2git.config import BranchOverride, load_config
from svn2git.planner import build_sync_plan
from svn2git.svn_log import ChangedPath, LogEntry, parse_svn_log_xml


FIXTURES = Path(__file__).parent / "fixtures"


def test_module_sync_plan_includes_modules_without_submodule_language():
    config = load_config(FIXTURES / "application_modules.yml")
    entries = parse_svn_log_xml((FIXTURES / "svn_log.xml").read_text(encoding="utf-8"))

    plan = build_sync_plan(config, "suite", entries, dry_run=True, target_overrides=_tmp_targets(config))

    assert [target.name for target in plan.targets] == ["suite:billing", "suite:reporting"]
    assert "modules/billing" in plan.render()
    assert "modules/reporting" in plan.render()
    assert "SVN version 41" in plan.render()
    assert "submodule:" not in plan.render()


def test_legacy_repository_without_submodules_has_single_target():
    config = load_config(FIXTURES / "application_legacy.yml")
    entries = parse_svn_log_xml((FIXTURES / "svn_log.xml").read_text(encoding="utf-8"))

    plan = build_sync_plan(config, "legacy", entries, dry_run=True)

    assert [target.name for target in plan.targets] == ["legacy"]
    assert "Q:\\svn2git-fixture\\git\\Legacy" in plan.render()


def test_sync_plan_skips_revisions_at_or_before_svn_version(tmp_path):
    config = load_config(FIXTURES / "application_legacy.yml")
    entries = parse_svn_log_xml((FIXTURES / "svn_log.xml").read_text(encoding="utf-8"))
    legacy = config.repositories["legacy"]
    target = legacy.expand_targets()[0]
    object.__setattr__(target, "git_path", str(tmp_path))
    (tmp_path / ".svn_version").write_text("41", encoding="utf-8")

    plan = build_sync_plan(config, "legacy", entries, dry_run=True, target_overrides={"legacy": target})

    assert [revision.revision for revision in plan.target_plans[0].revisions] == [42]


def test_module_checkpoint_does_not_skip_other_modules(tmp_path):
    config = load_config(FIXTURES / "application_modules.yml")
    entries = parse_svn_log_xml((FIXTURES / "svn_log.xml").read_text(encoding="utf-8"))
    targets = config.repositories["suite"].expand_targets()
    overrides = {}
    for target in targets:
        object.__setattr__(target, "git_path", str(tmp_path))
        overrides[target.name] = target
    version_dir = tmp_path / ".svn_versions"
    version_dir.mkdir()
    (version_dir / "suite_billing").write_text("41", encoding="utf-8")

    plan = build_sync_plan(config, "suite", entries, dry_run=True, target_overrides=overrides)

    assert [revision.revision for revision in plan.target_plans[0].revisions] == []
    assert [revision.revision for revision in plan.target_plans[1].revisions] == [42]


def test_module_plan_skips_unrelated_revisions():
    config = load_config(FIXTURES / "application_modules.yml")
    entries = parse_svn_log_xml((FIXTURES / "svn_log.xml").read_text(encoding="utf-8"))

    plan = build_sync_plan(config, "suite", entries, dry_run=True, target_overrides=_tmp_targets(config))
    billing_revisions = plan.target_plans[0].revisions
    reporting_revisions = plan.target_plans[1].revisions

    assert [revision.revision for revision in billing_revisions] == [41]
    assert [revision.revision for revision in reporting_revisions] == [42]
    assert billing_revisions[0].svn_url == "https://svn.example.com/repos/billing-dev"
    assert billing_revisions[0].svn_project_path == "Q:\\svn2git-fixture\\svn\\BillingDev"
    assert "svn source: https://svn.example.com/repos/billing-dev Q:\\svn2git-fixture\\svn\\BillingDev" in plan.render()


def test_module_plan_matches_branch_override_without_module_name_segment(tmp_path):
    config = load_config(FIXTURES / "application_modules.yml")
    billing = config.repositories["suite"].modules["billing"]
    object.__setattr__(
        billing,
        "branch_overrides",
        {
            "platform_2.13": BranchOverride(
                svn_url="https://svn.example.com/repos/platform_213",
                svn_project_path="Q:\\svn2git-fixture\\svn\\Platform213",
                dir_regex=r".*/branches/([^/]+)/.*",
                branch_name="2.13",
            )
        },
    )
    targets = config.repositories["suite"].expand_targets()
    overrides = {}
    for target in targets:
        object.__setattr__(target, "git_path", str(tmp_path))
        overrides[target.name] = target
    entries = [
        LogEntry(
            revision=213,
            author="alice",
            date=None,
            message="Framework patch",
            changed_paths=[ChangedPath("/repo/project/branches/platform_2.13/platform-resource/src/Fix.java", "M")],
        )
    ]

    plan = build_sync_plan(config, "suite", entries, dry_run=True, target_overrides=overrides)

    assert [revision.git_branch for revision in plan.target_plans[0].revisions] == ["2.13"]


def test_repository_branch_overrides_resolve_common_and_framework_213_sources(tmp_path):
    config = load_config(FIXTURES / "application_singularity.yml")
    entries = parse_svn_log_xml((FIXTURES / "svn_log_singularity.xml").read_text(encoding="utf-8"))
    targets = config.repositories["singularity"].expand_targets()
    overrides = {}
    for target in targets:
        object.__setattr__(target, "git_path", str(tmp_path))
        overrides[target.name] = target

    plan = build_sync_plan(config, "singularity", entries, dry_run=True, target_overrides=overrides)
    common_revision = plan.target_plans[0].revisions[0]
    framework_revision = plan.target_plans[1].revisions[0]

    assert [target.name for target in plan.targets] == ["singularity:common", "singularity:framework"]
    assert common_revision.branches == ("2.13",)
    assert common_revision.git_branch == "2.13"
    assert common_revision.svn_url == "https://192.168.0.182:8443/repo/codes/SafeMg/Singularity/Common/2.13/common"
    assert common_revision.svn_project_path == "F:\\SvnTest\\SingularityCommon-2.13"
    assert common_revision.dir_suffix == "common"
    assert framework_revision.branches == ("2.13",)
    assert framework_revision.git_branch == "2.13"
    assert framework_revision.svn_url == "https://192.168.0.182:8443/repo/codes/SafeMg/SMPlatform/branches/platform_2.13"
    assert framework_revision.svn_project_path == "F:\\SvnTest\\SingularityFramework-2.13"
    assert framework_revision.dir_regex == r".*/branches/([^/]+)/.*"
    assert framework_revision.dir_suffix is None


def _tmp_targets(config):
    overrides = {}
    for index, target in enumerate(config.repositories["suite"].expand_targets()):
        object.__setattr__(target, "git_path", f"Z:\\isolated-test\\repo-{index}")
        overrides[target.name] = target
    return overrides
