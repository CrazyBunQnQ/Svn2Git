from pathlib import Path


ROOT = Path(__file__).parents[1]


def test_readme_documents_service_owned_paths():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")

    assert "服务自有 SVN 工作副本" in readme
    assert "服务自有 Git 同步工作树" in readme
    assert "目标 Git 仓库" in readme
    assert "service state" in readme
    assert "git_project_path" not in readme


def test_service_architecture_doc_covers_operational_boundaries():
    doc = (ROOT / "docs" / "service-architecture.md").read_text(encoding="utf-8")

    assert "SVN working copies are service-owned" in doc
    assert "Git sync worktrees are service-owned" in doc
    assert "Target Git repositories are developer-facing" in doc
    assert "checkpoints" in doc
    assert "job runner" in doc
    assert "hook modes" in doc


def test_migration_doc_covers_legacy_path_split():
    doc = (ROOT / "docs" / "migration-working-tree-to-service.md").read_text(encoding="utf-8")

    assert "git_project_path" in doc
    assert "git_repository_path" in doc
    assert "git_worktree_path" in doc
    assert "state_path" in doc
    assert "bare repository" in doc
    assert "不要手动修改服务自有目录" in doc


def test_example_config_uses_explicit_service_paths():
    example = (ROOT / "config" / "application.yml.example").read_text(encoding="utf-8")

    assert "git_repository_path" in example
    assert "git_worktree_path" in example
    assert "state_path" in example
    assert "git_project_path" not in example
