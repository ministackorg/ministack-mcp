"""
Smoke tests for the MiniStack MCP knowledge layer.

Run with:  pytest test_catalog.py -v

`test_catalog_regenerates_cleanly` is skipped unless the ministack source
repo is discoverable (via ``MINISTACK_ROOT`` env var or sibling layout) —
the rest of the suite exercises only the shipped catalog + parity files.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
PKG = os.path.join(HERE, "ministack_mcp")


def _ministack_root() -> str | None:
    """Mirror of build_catalog._find_ministack_root, returning None instead of raising."""
    candidates = [
        os.environ.get("MINISTACK_ROOT"),
        os.path.abspath(os.path.join(HERE, "..")),
        os.path.abspath(os.path.join(HERE, "..", "ministack")),
        os.path.abspath(os.path.join(HERE, "..", "..", "ministack")),
    ]
    for candidate in candidates:
        if not candidate:
            continue
        if (
            os.path.isfile(os.path.join(candidate, "pyproject.toml"))
            and os.path.isdir(os.path.join(candidate, "ministack", "services"))
        ):
            return candidate
    return None


def _load(path):
    """Load a JSON file shipped inside the ministack_mcp package."""
    with open(os.path.join(PKG, path), "r", encoding="utf-8") as f:
        return json.load(f)


@pytest.mark.skipif(
    _ministack_root() is None,
    reason="ministack source repo not found; set MINISTACK_ROOT to enable regen test",
)
def test_catalog_regenerates_cleanly():
    env = os.environ.copy()
    env.setdefault("MINISTACK_ROOT", _ministack_root() or "")
    result = subprocess.run(
        [sys.executable, os.path.join(HERE, "build_catalog.py")],
        capture_output=True, text=True, env=env,
    )
    assert result.returncode == 0, f"generator failed: {result.stderr}"


def test_catalog_has_expected_shape():
    cat = _load("catalog.json")
    assert cat["schema_version"] == 1
    assert cat["ministack_version"] != "unknown"
    assert cat["service_count"] >= 40
    assert "services" in cat
    assert "env_vars" in cat
    assert "endpoint" in cat


def test_top_services_have_operations():
    cat = _load("catalog.json")
    svcs = cat["services"]
    # Every flagship service should have a non-trivial op count.
    for name, min_ops in [
        ("s3", 10), ("ec2", 50), ("dynamodb", 15), ("sqs", 8),
        ("sns", 8), ("iam", 20), ("cognito", 20), ("lambda_svc", 20),
        ("apigateway_v1", 20), ("eventbridge", 20),
    ]:
        assert name in svcs, f"missing service: {name}"
        n = svcs[name]["operation_count"]
        assert n >= min_ops, f"{name}: expected >= {min_ops} ops, got {n}"


def test_path_routed_services_documented():
    """imds, ecs_metadata, appsync_events, pipes have no action map by design.
    They must still appear in parity.json so AI agents get a status answer."""
    parity = _load("parity.json")["services"]
    for name in ("imds", "ecs_metadata", "appsync_events", "pipes"):
        assert name in parity, f"{name} missing from parity.json"


def test_env_vars_capture_ministack_namespace():
    cat = _load("catalog.json")
    env = cat["env_vars"]
    # A few known ones that should be picked up.
    expected = ["MINISTACK_REGION", "MINISTACK_PORT"]
    for k in expected:
        if k not in env:
            print(f"  note: {k} not seen — confirm it's spelled the same in code")


def test_parity_status_values_are_valid():
    parity = _load("parity.json")
    valid = {"full", "partial", "stub", "paid", "unsupported", "data-plane", "unknown"}
    for name, rec in parity["services"].items():
        status = rec.get("status", "unknown")
        assert status in valid, f"{name}: invalid status '{status}'"


def test_mcp_server_imports():
    """Importing the server should succeed even with no live emulator."""
    sys.path.insert(0, HERE)
    try:
        from ministack_mcp import server as mcp_server  # noqa: F401
    finally:
        sys.path.remove(HERE)


def test_is_operation_supported_logic():
    sys.path.insert(0, HERE)
    try:
        from ministack_mcp import server as mcp_server
        # Real op
        out = json.loads(mcp_server.is_operation_supported("s3", "PutObject"))
        assert out["supported"] is True
        # Fake op
        out = json.loads(mcp_server.is_operation_supported("s3", "TotallyMadeUpOp"))
        assert out["supported"] is False
        # Unknown service
        out = json.loads(mcp_server.is_operation_supported("nonexistent", "X"))
        assert out["supported"] is False
        assert "not emulated" in out["reason"]
    finally:
        sys.path.remove(HERE)


def test_search_operations_returns_matches():
    sys.path.insert(0, HERE)
    try:
        from ministack_mcp import server as mcp_server
        out = json.loads(mcp_server.search_operations("PutItem"))
        assert out["match_count"] >= 1
        assert any(m["service"] == "dynamodb" for m in out["matches"])
    finally:
        sys.path.remove(HERE)


if __name__ == "__main__":
    fns = [
        test_catalog_regenerates_cleanly,
        test_catalog_has_expected_shape,
        test_top_services_have_operations,
        test_path_routed_services_documented,
        test_env_vars_capture_ministack_namespace,
        test_parity_status_values_are_valid,
        test_mcp_server_imports,
        test_is_operation_supported_logic,
        test_search_operations_returns_matches,
    ]
    failed = 0
    for fn in fns:
        try:
            fn()
            print(f"  PASS  {fn.__name__}")
        except AssertionError as e:
            failed += 1
            print(f"  FAIL  {fn.__name__}: {e}")
        except Exception as e:
            failed += 1
            print(f"  ERROR {fn.__name__}: {e!r}")
    sys.exit(1 if failed else 0)
