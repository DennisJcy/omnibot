from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TESTS = ROOT / "tests"


def test_tests_are_split_into_expected_top_level_directories():
    for name in ["unit", "e2e", "fixtures", "release", "reports"]:
        assert (TESTS / name).is_dir(), name


def test_no_legacy_directory_remains():
    assert not (TESTS / "legacy").exists(), "tests/legacy/ should not exist; legacy scripts are deleted"


def test_no_active_python_tests_remain_in_tests_root():
    root_py = sorted(path.name for path in TESTS.glob("*.py"))
    assert root_py == [], f"unexpected .py files in tests/ root: {root_py}"


def test_release_docs_do_not_reference_removed_paths():
    docs = [ROOT / "AGENTS.md", TESTS / "release" / "README.md"]
    combined = "\n".join(path.read_text(encoding="utf-8") for path in docs)
    assert "tests/legacy/" not in combined


def test_feature_matrix_does_not_define_standalone_snapshot_case():
    text = (TESTS / "e2e" / "feature_matrix_test.py").read_text(encoding="utf-8")
    assert 'FeatureCase("snapshot' not in text
    assert '"snapshot_token_content_read"' not in text


def test_active_tests_do_not_execute_removed_commands():
    self_path = Path(__file__).resolve()
    forbidden_command_literals = [
        '"switch-tab"',
        '"focus-tab"',
        "'switch-tab'",
        "'focus-tab'",
        '"scan"',
        "'scan'",
        '"full-scan"',
        "'full-scan'",
    ]
    active_roots = [TESTS / "unit", TESTS / "e2e", TESTS / "release"]
    offenders = []
    for root in active_roots:
        for path in root.rglob("*.py"):
            if path.resolve() == self_path:
                continue
            lines = path.read_text(encoding="utf-8").splitlines()
            for line in lines:
                stripped = line.strip()
                if stripped.startswith("#") or stripped.startswith("//"):
                    continue
                if not any(marker in line for marker in ("run_omnibot", "subprocess.run", "Popen")):
                    continue
                for forbidden in forbidden_command_literals:
                    if forbidden in line:
                        offenders.append((path.relative_to(ROOT).as_posix(), forbidden, line.strip()))
    assert offenders == [], f"removed commands executed in active tests: {offenders}"
