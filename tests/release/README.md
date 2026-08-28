# Release Test Gates

Run the canonical preflight from the repository root:

```bash
python3 tests/release/preflight.py
```

The preflight runs:

```bash
uv run python -m pytest tests/unit -q
python3 tests/e2e/feature_matrix_test.py --no-playwright
python3 tests/e2e/full_workflow_test.py --no-playwright
```

Specialty gates are available when touched code requires them:

```bash
python3 tests/e2e/popup_modal_test.py -v
python3 tests/e2e/read_real_sites_matrix_test.py
python3 tests/e2e/verify_workflow_matrix_test.py
```

E2E gates require a connected Chromium extension and must use source checkout commands unless `OMNIBOT_CMD` points at the binary being validated.

Use `--unit-only` for quick local checks (not a release substitute). Use `--skip-e2e` to run only unit tests during development.
