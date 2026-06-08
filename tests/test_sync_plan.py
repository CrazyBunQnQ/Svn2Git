from pathlib import Path

from svn2git.config import load_config
from svn2git.planner import build_sync_plan
from svn2git.svn_log import parse_svn_log_xml


FIXTURES = Path(__file__).parent / "fixtures"


def test_submodule_sync_plan_includes_parent_and_submodules():
    config = load_config(FIXTURES / "application_submodules.yml")
    entries = parse_svn_log_xml((FIXTURES / "svn_log.xml").read_text(encoding="utf-8"))

    plan = build_sync_plan(config, "suite", entries, dry_run=True, target_overrides=_tmp_targets(config))

    assert [target.name for target in plan.targets] == ["suite", "suite:billing", "suite:reporting"]
    assert "modules/billing" in plan.render()
    assert "modules/reporting" in plan.render()
    assert "SVN version 41" in plan.render()


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


def test_submodule_plan_skips_unrelated_revisions():
    config = load_config(FIXTURES / "application_submodules.yml")
    entries = parse_svn_log_xml((FIXTURES / "svn_log.xml").read_text(encoding="utf-8"))

    plan = build_sync_plan(config, "suite", entries, dry_run=True, target_overrides=_tmp_targets(config))
    billing_revisions = plan.target_plans[1].revisions
    reporting_revisions = plan.target_plans[2].revisions

    assert [revision.revision for revision in billing_revisions] == [41]
    assert [revision.revision for revision in reporting_revisions] == [42]
    assert billing_revisions[0].svn_url == "https://svn.example.com/repos/billing-dev"
    assert billing_revisions[0].svn_project_path == "Q:\\svn2git-fixture\\svn\\BillingDev"
    assert "svn source: https://svn.example.com/repos/billing-dev Q:\\svn2git-fixture\\svn\\BillingDev" in plan.render()


def _tmp_targets(config):
    overrides = {}
    for index, target in enumerate(config.repositories["suite"].expand_targets()):
        object.__setattr__(target, "git_path", f"Z:\\isolated-test\\target-{index}")
        overrides[target.name] = target
    return overrides
