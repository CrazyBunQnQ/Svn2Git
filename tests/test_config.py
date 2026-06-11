from pathlib import Path

import pytest

from svn2git.config import ConfigError, load_config, parse_config


FIXTURES = Path(__file__).parent / "fixtures"


def test_loads_repository_modules_with_repo_remote():
    config = load_config(FIXTURES / "application_modules.yml")

    suite = config.repositories["suite"]
    targets = suite.expand_targets()

    assert suite.svn_url == "https://svn.example.com/repos/main"
    assert suite.git_remote_url == "ssh://git.example.com/suite.git"
    assert [target.name for target in targets] == ["suite:billing", "suite:reporting"]
    assert [target.git_path for target in targets] == ["Q:\\svn2git-fixture\\git\\Suite", "Q:\\svn2git-fixture\\git\\Suite"]
    assert [target.target_path for target in targets] == ["modules/billing", "modules/reporting"]
    assert targets[0].svn_project_path == "Q:\\svn2git-fixture\\svn\\Billing"
    assert targets[0].git_remote_url == "ssh://git.example.com/suite.git"
    assert targets[0].branch_overrides["dev"].svn_url == "https://svn.example.com/repos/billing-dev"
    assert targets[0].branch_overrides["dev"].svn_project_path == "Q:\\svn2git-fixture\\svn\\BillingDev"
    assert targets[0].full_sync_interval == 1000


def test_repository_branch_override_keeps_213_branch_as_string():
    config = load_config(FIXTURES / "application_singularity.yml")

    common_target, framework_target = config.repositories["singularity"].expand_targets()
    common_override = common_target.branch_overrides["2.13"]
    framework_override = framework_target.branch_overrides["platform_2.13"]

    assert common_target.target_path == "."
    assert common_override.svn_url == "https://192.168.0.182:8443/repo/codes/SafeMg/Singularity/Common/2.13/common"
    assert common_override.svn_project_path == "F:\\SvnTest\\SingularityCommon-2.13"
    assert common_override.dir_suffix == "common"
    assert framework_target.target_path == "."
    assert framework_override.svn_url == "https://192.168.0.182:8443/repo/codes/SafeMg/SMPlatform/branches/platform_2.13"
    assert framework_override.svn_project_path == "F:\\SvnTest\\SingularityFramework-2.13"
    assert framework_override.dir_regex == r".*/branches/([^/]+)/.*"
    assert framework_override.branch_name == "2.13"


def test_rejects_legacy_submodules_configuration():
    with pytest.raises(ConfigError, match="submodules.*modules"):
        load_config(FIXTURES / "application_submodules.yml")


def test_missing_module_path_is_rejected():
    with pytest.raises(ConfigError, match="suite.billing.svn_project_path"):
        load_config(FIXTURES / "application_invalid_submodule.yml")


def test_legacy_repository_without_submodules():
    config = load_config(FIXTURES / "application_legacy.yml")

    legacy = config.repositories["legacy"]
    targets = legacy.expand_targets()

    assert len(targets) == 1
    assert targets[0].name == "legacy"
    assert targets[0].git_path == "Q:\\svn2git-fixture\\git\\Legacy"
    assert targets[0].full_sync_interval == 1000


def test_git_default_email_suffix_is_parsed():
    config = parse_config(
        {
            "git": {
                "default_email_suffix": "icssla.com",
            },
            "svn_git_mapping": {
                "legacy": {
                    "svn_url": "https://svn.example.com/repos/main",
                    "svn_project_path": "Q:\\svn2git-fixture\\svn\\Legacy",
                    "git_project_path": "Q:\\svn2git-fixture\\git\\Legacy",
                }
            },
        }
    )

    assert config.default_email_suffix == "icssla.com"


def test_repository_service_paths_are_distinct_from_target_repository():
    config = parse_config(
        {
            "svn_git_mapping": {
                "service": {
                    "svn_url": "https://svn.example.com/repos/main",
                    "svn_project_path": "Q:\\svn2git-fixture\\svn\\Service",
                    "git_repository_path": "Q:\\svn2git-fixture\\repos\\Service.git",
                    "git_worktree_path": "Q:\\svn2git-fixture\\worktrees\\Service",
                    "state_path": "Q:\\svn2git-fixture\\state\\Service",
                    "dir_regx": ".*/branches/([^/]+).*",
                }
            }
        }
    )

    service = config.repositories["service"]
    targets = service.expand_targets()

    assert service.git_repository_path == "Q:\\svn2git-fixture\\repos\\Service.git"
    assert service.git_worktree_path == "Q:\\svn2git-fixture\\worktrees\\Service"
    assert service.state_path == "Q:\\svn2git-fixture\\state\\Service"
    assert service.git_project_path == "Q:\\svn2git-fixture\\worktrees\\Service"
    assert targets[0].git_repository_path == "Q:\\svn2git-fixture\\repos\\Service.git"
    assert targets[0].git_path == "Q:\\svn2git-fixture\\worktrees\\Service"
    assert targets[0].state_path == "Q:\\svn2git-fixture\\state\\Service"


def test_repository_service_paths_are_inherited_by_modules():
    config = parse_config(
        {
            "svn_git_mapping": {
                "suite": {
                    "svn_url": "https://svn.example.com/repos/main",
                    "svn_project_path": "Q:\\svn2git-fixture\\svn\\Suite",
                    "git_repository_path": "Q:\\svn2git-fixture\\repos\\Suite.git",
                    "git_worktree_path": "Q:\\svn2git-fixture\\worktrees\\Suite",
                    "state_path": "Q:\\svn2git-fixture\\state\\Suite",
                    "modules": {
                        "billing": {
                            "svn_project_path": "Q:\\svn2git-fixture\\svn\\Billing",
                            "target_path": "modules/billing",
                        }
                    },
                }
            }
        }
    )

    billing = config.repositories["suite"].expand_targets()[0]

    assert billing.git_repository_path == "Q:\\svn2git-fixture\\repos\\Suite.git"
    assert billing.git_path == "Q:\\svn2git-fixture\\worktrees\\Suite"
    assert billing.state_path == "Q:\\svn2git-fixture\\state\\Suite"


def test_rejects_target_repository_matching_sync_worktree():
    with pytest.raises(ConfigError, match="git_repository_path.*git_worktree_path"):
        parse_config(
            {
                "svn_git_mapping": {
                    "service": {
                        "svn_url": "https://svn.example.com/repos/main",
                        "svn_project_path": "Q:\\svn2git-fixture\\svn\\Service",
                        "git_repository_path": "Q:\\svn2git-fixture\\git\\Service",
                        "git_worktree_path": "Q:\\svn2git-fixture\\git\\Service",
                    }
                }
            }
        )


def test_rejects_target_repository_without_explicit_sync_worktree():
    with pytest.raises(ConfigError, match="git_worktree_path"):
        parse_config(
            {
                "svn_git_mapping": {
                    "service": {
                        "svn_url": "https://svn.example.com/repos/main",
                        "svn_project_path": "Q:\\svn2git-fixture\\svn\\Service",
                        "git_repository_path": "Q:\\svn2git-fixture\\repos\\Service.git",
                        "git_project_path": "Q:\\svn2git-fixture\\git\\Service",
                    }
                }
            }
        )


def test_full_sync_interval_can_be_configured_per_repository_and_module():
    config = parse_config(
        {
            "svn_git_mapping": {
                "suite": {
                    "svn_url": "https://svn.example.com/repos/main",
                    "svn_project_path": "Q:\\svn2git-fixture\\svn\\Suite",
                    "git_project_path": "Q:\\svn2git-fixture\\git\\Suite",
                    "full_sync_interval": 500,
                    "modules": {
                        "billing": {
                            "svn_project_path": "Q:\\svn2git-fixture\\svn\\Billing",
                            "target_path": "modules/billing",
                            "full_sync_interval": 100,
                        },
                        "reporting": {
                            "svn_project_path": "Q:\\svn2git-fixture\\svn\\Reporting",
                            "target_path": "modules/reporting",
                        },
                    },
                }
            }
        }
    )

    billing, reporting = config.repositories["suite"].expand_targets()

    assert config.repositories["suite"].full_sync_interval == 500
    assert billing.full_sync_interval == 100
    assert reporting.full_sync_interval == 500


def test_full_sync_interval_rejects_negative_values():
    with pytest.raises(ConfigError, match="full_sync_interval"):
        parse_config(
            {
                "svn_git_mapping": {
                    "legacy": {
                        "svn_url": "https://svn.example.com/repos/main",
                        "svn_project_path": "Q:\\svn2git-fixture\\svn\\Legacy",
                        "git_project_path": "Q:\\svn2git-fixture\\git\\Legacy",
                        "full_sync_interval": -1,
                    }
                }
            }
        )
