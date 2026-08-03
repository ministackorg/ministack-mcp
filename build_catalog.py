"""
Build a static knowledge catalog for the MiniStack MCP server.

Scans the MiniStack codebase once at build time and produces:

  - mcp/catalog.json      machine-readable index of services, operations,
                          env vars, endpoint info, version stamp.

The MCP server reads this catalog at runtime and never re-parses the codebase.
That gives AI agents stable, version-pinned answers and avoids the AST
fragility of "parse-on-every-call".

Re-run after changing services or before publishing the MCP package:

    python mcp/build_catalog.py
"""

from __future__ import annotations

import ast
import datetime as dt
import glob
import json
import os
import re
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
# Catalog ships inside the package so it's bundled in the wheel.
OUT_PATH = os.path.join(_HERE, "ministack_mcp", "catalog.json")


def _find_ministack_root() -> str:
    """Locate the ministack source repo. Resolved lazily so importing this
    module doesn't fail when the ministack codebase isn't on disk (e.g.
    when the installed package is examined by tooling without a checkout).

    Precedence:
      1. ``MINISTACK_ROOT`` env var (explicit override).
      2. Parent dir (legacy monorepo layout: ``ministack/mcp/build_catalog.py``).
      3. Sibling dir ``../ministack`` (standalone layout:
         ``Downloads/ministack-mcp/`` next to ``Downloads/ministack/``).
      4. ``../../ministack`` (one extra level deep).
    """
    candidates = [
        os.environ.get("MINISTACK_ROOT"),
        os.path.abspath(os.path.join(_HERE, "..")),
        os.path.abspath(os.path.join(_HERE, "..", "ministack")),
        os.path.abspath(os.path.join(_HERE, "..", "..", "ministack")),
    ]
    for candidate in candidates:
        if not candidate:
            continue
        if (
            os.path.isfile(os.path.join(candidate, "pyproject.toml"))
            and os.path.isdir(os.path.join(candidate, "ministack", "services"))
        ):
            return candidate
    raise RuntimeError(
        "ministack source repo not found. Set MINISTACK_ROOT to its path "
        "(must contain pyproject.toml and ministack/services/)."
    )


def _paths():
    """Compute paths once when actually needed (lazy)."""
    root = _find_ministack_root()
    return {
        "ROOT": root,
        "SERVICES_DIR": os.path.join(root, "ministack", "services"),
        "MINISTACK_DIR": os.path.join(root, "ministack"),
        "PYPROJECT": os.path.join(root, "pyproject.toml"),
    }


# Module-level placeholders — resolved at build()-time, kept as None on import.
ROOT: str | None = None
SERVICES_DIR: str | None = None
MINISTACK_DIR: str | None = None
PYPROJECT: str | None = None

# CamelCase tokens beginning with a known AWS verb. Kept generous on purpose;
# the dict-key heuristic later filters false positives.
_AWS_VERBS = (
    "Accept", "Acknowledge", "Activate", "Add", "Admin", "Allocate", "Apply",
    "Approve", "Associate", "Assume", "Attach", "Authenticate", "Authorize",
    "Batch", "Begin", "Bulk", "Cancel", "Change", "Check", "Checkpoint", "Claim", "Clear",
    "Clone", "Close", "Commit", "Complete", "Confirm", "Connect", "Copy",
    "Count", "Create", "Deactivate", "Deauthorize", "Decrease", "Decrypt",
    "Delete", "Deliver", "Deploy", "Deprecate", "Deregister", "Describe",
    "Detach", "Detect", "Disable", "Disassociate", "Discover", "Dismiss",
    "Download", "Empty", "Enable", "Encrypt", "End", "Enroll", "Estimate",
    "Evaluate", "Execute", "Export", "Extend", "Filter", "Finalize", "Find",
    "Fork", "Forgot", "Generate", "Get", "Global", "Grant", "Head", "Heartbeat",
    "Identify", "Import", "Increase", "Index", "Inherit", "Initiate", "Inspect",
    "Invite", "Invoke", "Issue", "Join", "Label", "Launch", "Leave", "List",
    "Lock", "Login", "Logout", "Lookup", "Match", "Merge", "Modify", "Mount",
    "Move", "Mute", "Notify", "Open", "Pause", "Ping", "Poll", "Post",
    "Prepare", "Process", "Promote", "Provision", "Publish", "Purchase",
    "Purge", "Push", "Put", "Query", "Reactivate", "Reauthorize", "Reboot",
    "Receive", "Reconnect", "Record", "Recover", "Redeem", "Refresh",
    "Register", "Reject", "Release", "Reload", "Remove", "Rename", "Renew",
    "Replace", "Replicate", "Reply", "Report", "Request", "Resend", "Reset",
    "Resolve", "Respond", "Restart", "Restore", "Resume", "Retire", "Retry",
    "Return", "Revert", "Review", "Revoke", "Rollback", "Rotate", "Run",
    "Save", "Scan", "Schedule", "Search", "Select", "Send", "Set", "Setup",
    "Share", "Sign", "Skip", "Split", "Start", "Stop", "Submit", "Subscribe",
    "Suspend", "Switch", "Sync", "Tag", "Terminate", "Test", "Trace",
    "Transfer", "Translate", "Trigger", "Try", "Unassign", "Uncommit",
    "Undeploy", "Unlink", "Unlock", "Unmount", "Unregister", "Unsubscribe",
    "Unsuspend", "Untag", "Update", "Upgrade", "Upload", "Use", "Validate",
    "Verify", "View", "Wait", "Withdraw", "Write",
)
# Real AWS ops that are a bare verb with no trailing noun.
_BARE_VERB_OPS = frozenset({
    "Encrypt", "Decrypt", "Sign", "Verify", "Invoke", "Query", "Scan",
    "Subscribe", "Unsubscribe", "Publish", "Connect", "Heartbeat",
    "Send", "Receive",
})
_OP_RE = re.compile(r"^(?:" + "|".join(_AWS_VERBS) + r")[A-Z][A-Za-z0-9]*$")
_OP_FIND_RE = re.compile(
    # Use explicit lookaround so an underscore on the left (e.g. AWS doc URL
    # paths like `API_CheckpointDurableExecution.html`) doesn't suppress the
    # match — `\b` treats `_` as a word char so it wouldn't fire there.
    r"(?<![A-Za-z0-9])(?:" + "|".join(_AWS_VERBS) + r")[A-Z][A-Za-z0-9]*(?![A-Za-z0-9])"
)


def _looks_like_op(s: str) -> bool:
    return bool(_OP_RE.match(s)) or s in _BARE_VERB_OPS


def _read_version() -> str:
    try:
        with open(PYPROJECT, "r", encoding="utf-8") as f:
            for line in f:
                m = re.match(r'\s*version\s*=\s*"([^"]+)"', line)
                if m:
                    return m.group(1)
    except Exception:
        pass
    return "unknown"


def _extract_ops(filepath: str) -> tuple[set[str], list[str]]:
    """Return (ops, sources) where sources lists which extraction strategies hit."""
    ops: set[str] = set()
    sources: list[str] = []
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            src = f.read()
        tree = ast.parse(src)
    except Exception:
        return ops, sources

    # Strategy 1: any module-level dict whose keys are >=3 AWS-op-shaped strings.
    # Catches _ACTIONS, _HANDLERS, _DISPATCH, _OP_HANDLERS, action_map, etc.
    dict_hits = 0
    for node in ast.walk(tree):
        if isinstance(node, ast.Dict):
            keys = [
                k.value for k in node.keys
                if isinstance(k, ast.Constant) and isinstance(k.value, str)
            ]
            if len(keys) >= 3 and sum(1 for k in keys if _looks_like_op(k)) >= max(3, len(keys) // 2):
                for k in keys:
                    if _looks_like_op(k):
                        ops.add(k)
                        dict_hits += 1
    if dict_hits:
        sources.append(f"dict-keys ({dict_hits})")

    # Strategy 2: equality comparisons against action/target/op/x_amz_target.
    cmp_hits = 0
    cmp_names = {"action", "target", "op", "operation", "x_amz_target", "amz_target", "name"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Compare) and isinstance(node.left, ast.Name):
            if node.left.id.lower() in cmp_names:
                for op_node, comp in zip(node.ops, node.comparators):
                    if isinstance(op_node, ast.Eq) and isinstance(comp, ast.Constant):
                        if isinstance(comp.value, str) and _looks_like_op(comp.value):
                            ops.add(comp.value)
                            cmp_hits += 1
    if cmp_hits:
        sources.append(f"compare ({cmp_hits})")

    # Strategy 3: match/case statements.
    case_hits = 0
    Match = getattr(ast, "Match", None)
    if Match is not None:
        for node in ast.walk(tree):
            if isinstance(node, Match):
                for case in node.cases:
                    pat = case.pattern
                    val = getattr(pat, "value", None)
                    if isinstance(val, ast.Constant) and isinstance(val.value, str):
                        if _looks_like_op(val.value):
                            ops.add(val.value)
                            case_hits += 1
        if case_hits:
            sources.append(f"match-case ({case_hits})")

    # Strategy 4: URL-path dispatch dicts (e.g. batch uses "/v1/createjobqueue").
    # Convert lowercase URL tail back to CamelCase if it matches a known verb.
    path_hits = 0
    for node in ast.walk(tree):
        if isinstance(node, ast.Dict):
            keys = [
                k.value for k in node.keys
                if isinstance(k, ast.Constant) and isinstance(k.value, str)
            ]
            url_keys = [k for k in keys if k.startswith("/") and len(keys) >= 3]
            for url in url_keys:
                tail = url.rstrip("/").rsplit("/", 1)[-1]
                if not tail or not tail.isalpha():
                    continue
                for verb in _AWS_VERBS:
                    vlow = verb.lower()
                    if tail.startswith(vlow) and len(tail) > len(vlow):
                        rest = tail[len(vlow):]
                        cased = verb + rest[0].upper() + rest[1:]
                        if _looks_like_op(cased):
                            ops.add(cased)
                            path_hits += 1
                        break
    if path_hits:
        sources.append(f"url-paths ({path_hits})")

    # Strategy 5: docstring as fallback / supplement.
    doc = ast.get_docstring(tree) or ""
    doc_ops = set(_OP_FIND_RE.findall(doc))
    new_from_doc = doc_ops - ops
    if new_from_doc:
        ops.update(new_from_doc)
        sources.append(f"docstring (+{len(new_from_doc)})")

    return ops, sources


def _extract_env_vars() -> dict[str, dict]:
    """Walk ministack/ for os.environ.get / getenv / os.environ[...] usage."""
    found: dict[str, dict] = {}
    for root, _, files in os.walk(MINISTACK_DIR):
        for name in files:
            if not name.endswith(".py"):
                continue
            path = os.path.join(root, name)
            try:
                with open(path, "r", encoding="utf-8") as f:
                    tree = ast.parse(f.read())
            except Exception:
                continue
            rel = os.path.relpath(path, ROOT)
            for node in ast.walk(tree):
                key, default = None, None

                # os.environ.get("X", default) / os.getenv("X", default)
                if isinstance(node, ast.Call):
                    func = node.func
                    is_environ_get = (
                        isinstance(func, ast.Attribute)
                        and func.attr == "get"
                        and isinstance(func.value, ast.Attribute)
                        and func.value.attr == "environ"
                    )
                    is_getenv = (
                        isinstance(func, ast.Attribute) and func.attr == "getenv"
                    )
                    if is_environ_get or is_getenv:
                        if node.args and isinstance(node.args[0], ast.Constant):
                            if isinstance(node.args[0].value, str):
                                key = node.args[0].value
                                if len(node.args) >= 2 and isinstance(node.args[1], ast.Constant):
                                    default = node.args[1].value

                # os.environ["X"]
                elif isinstance(node, ast.Subscript):
                    val = node.value
                    if (
                        isinstance(val, ast.Attribute)
                        and val.attr == "environ"
                    ):
                        sl = node.slice
                        if isinstance(sl, ast.Constant) and isinstance(sl.value, str):
                            key = sl.value

                if not key:
                    continue
                entry = found.setdefault(key, {"name": key, "files": [], "default": None})
                if rel not in entry["files"]:
                    entry["files"].append(rel)
                if default is not None and entry["default"] is None:
                    try:
                        json.dumps(default)
                        entry["default"] = default
                    except TypeError:
                        entry["default"] = repr(default)
    return found


def build() -> dict:
    global ROOT, SERVICES_DIR, MINISTACK_DIR, PYPROJECT
    paths = _paths()
    ROOT = paths["ROOT"]
    SERVICES_DIR = paths["SERVICES_DIR"]
    MINISTACK_DIR = paths["MINISTACK_DIR"]
    PYPROJECT = paths["PYPROJECT"]
    version = _read_version()
    services: dict[str, dict] = {}
    for path in sorted(glob.glob(os.path.join(SERVICES_DIR, "*.py"))):
        name = os.path.splitext(os.path.basename(path))[0]
        if name.startswith("__"):
            continue
        ops, sources = _extract_ops(path)
        services[name] = {
            "name": name,
            "operations": sorted(ops),
            "operation_count": len(ops),
            "extraction_sources": sources,
        }

    # Services authored as packages (subdirectory with __init__.py): scan every
    # .py file in the package and merge operations into one entry keyed by the
    # package name. Without this, multi-file services like cloudformation are
    # missing from the catalog entirely.
    for entry in sorted(os.listdir(SERVICES_DIR)):
        sub = os.path.join(SERVICES_DIR, entry)
        if not os.path.isdir(sub) or entry.startswith("__"):
            continue
        if not os.path.exists(os.path.join(sub, "__init__.py")):
            continue
        merged_ops: set[str] = set()
        merged_sources: list[str] = []
        for sub_path in sorted(glob.glob(os.path.join(sub, "*.py"))):
            ops, sources = _extract_ops(sub_path)
            merged_ops.update(ops)
            merged_sources.extend(sources)
        services[entry] = {
            "name": entry,
            "operations": sorted(merged_ops),
            "operation_count": len(merged_ops),
            "extraction_sources": merged_sources,
        }

    # Apply authoritative op pins (ops_pins.json). The AST heuristics above are
    # generous by design and mis-scrape struct field names, enum values,
    # service-integration `action ==` tokens, and docstring prose as operations.
    # For every module with a code-verified dispatched-op list, the pin REPLACES
    # the scraped set so the catalog matches the real runtime dispatch. Modules
    # absent from the pins keep their scraped ops.
    pins_path = os.path.join(_HERE, "ops_pins.json")
    if os.path.exists(pins_path):
        with open(pins_path, "r", encoding="utf-8") as f:
            pins = json.load(f)
        for name, ops in pins.items():
            if name == "_comment":
                continue
            entry = services.get(name) or {"name": name}
            entry["operations"] = sorted(ops)
            entry["operation_count"] = len(ops)
            entry["extraction_sources"] = ["pinned"]
            services[name] = entry

    env_vars = _extract_env_vars()
    # Drop noisy non-MiniStack vars (PATH, HOME, etc.) — keep only those with
    # MINISTACK_/AWS_ prefix or that look intentional.
    env_clean = {}
    for k, v in env_vars.items():
        if (
            k.startswith("MINISTACK_")
            or k.startswith("AWS_")
            or k.startswith("OPENSEARCH_")
            or k in {
                "S3_PERSIST", "DOCKER_HOST", "TZ", "PORT", "PYTHONUNBUFFERED",
            }
        ):
            env_clean[k] = v

    return {
        "schema_version": 1,
        "ministack_version": version,
        "generated_at": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "endpoint": {
            "default_url": "http://localhost:4566",
            "default_port": 4566,
            "auth_model": "SigV4 not validated; access key ID is read to derive account",
            "default_account": "000000000000",
            "default_region": "us-east-1",
        },
        "service_count": len(services),
        "services": services,
        "env_vars": dict(sorted(env_clean.items())),
    }


def main(argv: list[str]) -> int:
    catalog = build()
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(catalog, f, indent=2, sort_keys=False)
        f.write("\n")
    total_ops = sum(s["operation_count"] for s in catalog["services"].values())
    empty = [n for n, s in catalog["services"].items() if s["operation_count"] == 0]
    print(f"Wrote {OUT_PATH}")
    print(f"  ministack {catalog['ministack_version']}")
    print(f"  {catalog['service_count']} services, {total_ops} operations, {len(catalog['env_vars'])} env vars")
    if empty:
        print(f"  WARNING: {len(empty)} services with 0 operations: {', '.join(empty)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
