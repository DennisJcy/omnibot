from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

OLD_NAME_NEEDLES = (
    "omni-browser",
    "omni_browser",
    "Omni Browser",
    "OmniBrowse",
    "omnibrowse",
    "OMNI_BROWSER",
    "omni-browser-extension-path",
    "@omni-browser",
)

TEXT_FILE_SUFFIXES = {
    ".cfg",
    ".css",
    ".html",
    ".js",
    ".json",
    ".lock",
    ".md",
    ".pem",
    ".py",
    ".spec",
    ".toml",
    ".txt",
    ".yaml",
    ".yml",
}

SKIPPED_DIRS = {
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    ".worktrees",
    "__pycache__",
    "build",
    "dist",
    "node_modules",
}

SELF_PATH = Path(__file__).resolve()


def iter_source_text_files():
    for path in ROOT.rglob("*"):
        if not path.is_file():
            continue
        if path.resolve() == SELF_PATH:
            continue
        if any(part in SKIPPED_DIRS for part in path.parts):
            continue
        if path.suffix not in TEXT_FILE_SUFFIXES:
            continue
        yield path


def test_project_metadata_uses_omnibot_names():
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")

    assert 'name = "omnibot"' in pyproject
    assert 'omnibot = "omnibot:main"' in pyproject
    assert 'include = ["omnibot", "omnibot.*"]' in pyproject
    assert 'omnibot = ["sop/*.md"' in pyproject


def test_python_package_and_extension_paths_use_omnibot():
    assert (ROOT / "src" / "omnibot" / "__init__.py").exists()
    assert (ROOT / "src" / "omnibot" / "server.py").exists()
    assert (ROOT / "browser-extension" / "manifest.json").exists()
    assert not (ROOT / "src" / "omni_browser").exists()
    assert not (ROOT / "src" / "omni_browser.egg-info").exists()


def test_runtime_names_use_omnibot_command():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")

    assert "omnibot snapshot" in readme
    assert "omnibot doctor" in readme
    assert "omnibot skills install" in readme


def test_no_source_controlled_old_product_names_remain():
    offenders = []
    for path in iter_source_text_files():
        text = path.read_text(encoding="utf-8", errors="ignore")
        for needle in OLD_NAME_NEEDLES:
            if needle in text:
                offenders.append(f"{path.relative_to(ROOT)} contains {needle}")

    assert offenders == []
