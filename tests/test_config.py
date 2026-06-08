from pathlib import Path

import pytest

from svn2git.config import ConfigError, load_config


FIXTURES = Path(__file__).parent / "fixtures"


def test_load_repository_with_submodules():
    config = load_config(FIXTURES / "application_submodules.yml")

    suite = config.repositories["suite"]
    targets = suite.expand_targets()

    assert suite.svn_url == "https://svn.example.com/repos/main"
    assert [target.name for target in targets] == ["suite", "suite:billing", "suite:reporting"]
    assert [target.git_path for target in targets[1:]] == ["Q:\\svn2git-fixture\\git\\Suite\\modules\\billing", "Q:\\svn2git-fixture\\git\\Suite\\modules\\reporting"]
    assert targets[1].svn_project_path == "Q:\\svn2git-fixture\\svn\\Billing"
    assert targets[1].git_remote_url == "ssh://git.example.com/suite/billing.git"
    assert targets[1].branch_overrides["dev"].svn_url == "https://svn.example.com/repos/billing-dev"
    assert targets[1].branch_overrides["dev"].svn_project_path == "Q:\\svn2git-fixture\\svn\\BillingDev"


def test_repository_branch_override_keeps_213_branch_as_string():
    config = load_config(FIXTURES / "application_singularity.yml")

    target = config.repositories["singularity"].expand_targets()[0]
    common_override = target.branch_overrides["2.13"]
    framework_override = target.branch_overrides["platform_2.13"]

    assert common_override.svn_url == "https://192.168.0.182:8443/repo/codes/SafeMg/Singularity/Common/2.13/common"
    assert common_override.svn_project_path == "F:\\SvnTest\\SingularityCommon-2.13"
    assert common_override.dir_suffix == "common"
    assert framework_override.svn_url == "https://192.168.0.182:8443/repo/codes/SafeMg/SMPlatform/branches/platform_2.13"
    assert framework_override.svn_project_path == "F:\\SvnTest\\SingularityFramework-2.13"
    assert framework_override.dir_regex == r".*/branches/([^/]+)/.*"
    assert framework_override.branch_name == "2.13"


def test_missing_submodule_path_is_rejected():
    with pytest.raises(ConfigError, match="suite.billing.svn_project_path"):
        load_config(FIXTURES / "application_invalid_submodule.yml")


def test_legacy_repository_without_submodules():
    config = load_config(FIXTURES / "application_legacy.yml")

    legacy = config.repositories["legacy"]
    targets = legacy.expand_targets()

    assert len(targets) == 1
    assert targets[0].name == "legacy"
    assert targets[0].git_path == "Q:\\svn2git-fixture\\git\\Legacy"
