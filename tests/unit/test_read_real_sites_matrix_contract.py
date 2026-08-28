from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "tests" / "e2e" / "read_real_sites_matrix_test.py"


def load_matrix_module():
    spec = importlib.util.spec_from_file_location("read_real_sites_matrix_test", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_run_read_closes_created_tab(monkeypatch):
    matrix = load_matrix_module()
    calls = []

    def fake_run(args, **kwargs):
        calls.append(args)
        if args[1] == "read":
            return SimpleNamespace(
                returncode=0,
                stdout=json.dumps({
                    "status": "success",
                    "content": "body text",
                    "metadata": {"created_tab": True, "tab_id": "edge:123"},
                }),
                stderr="",
            )
        return SimpleNamespace(returncode=0, stdout=json.dumps({"status": "success"}), stderr="")

    monkeypatch.setattr(matrix.subprocess, "run", fake_run)

    case = matrix.ReadCase(case_id="example", url="https://example.com")

    result = matrix.run_read(case, ["omnibot"], timeout=30)

    assert result["status"] == "success"
    assert calls == [
        ["omnibot", "read", "--json", "--screens", "2", "https://example.com"],
        ["omnibot", "close", "edge:123"],
    ]
    assert result["cleanup"]["status"] == "success"
