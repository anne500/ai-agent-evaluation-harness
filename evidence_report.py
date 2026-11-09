"""Versioned JSON evidence and atomic per-run checkpoints. Standard library only."""
import hashlib
import importlib.metadata
import json
import os
import platform
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def message_record(message):
    """Capture observable content and metadata; omit additional reasoning fields."""
    return {
        "type": getattr(message, "type", None),
        "id": getattr(message, "id", None),
        "name": getattr(message, "name", None),
        "content": getattr(message, "content", None),
        "tool_calls": getattr(message, "tool_calls", []) or [],
        "invalid_tool_calls": getattr(message, "invalid_tool_calls", []) or [],
        "tool_call_id": getattr(message, "tool_call_id", None),
        "status": getattr(message, "status", None),
        "response_metadata": getattr(message, "response_metadata", {}) or {},
        "usage_metadata": getattr(message, "usage_metadata", None),
    }


def provenance(root):
    root = Path(root)

    def git(*args):
        try:
            result = subprocess.run(
                ["git", *args], cwd=root, capture_output=True, text=True,
                timeout=10, check=False,
            )
            return result.stdout.strip() if result.returncode == 0 else None
        except (OSError, subprocess.TimeoutExpired):
            return None

    versions = {}
    for package in ["langchain", "langchain-core", "langchain-ollama", "langgraph", "ollama"]:
        try:
            versions[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            versions[package] = None

    hashes = {}
    for name in [
        "agent.py", "eval.py", "eval_execution.py", "execution_checks.py",
        "evidence_report.py", "requirements.txt",
    ]:
        path = root / name
        hashes[name] = hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None

    status = git("status", "--porcelain")
    return {
        "git_commit": git("rev-parse", "HEAD"),
        "git_dirty": None if status is None else bool(status),
        "source_sha256": hashes,
        "python": sys.version,
        "platform": platform.platform(),
        "package_versions": versions,
        "timezone_names": list(__import__("time").tzname),
    }


def new_report(output_dir, root, requested_model):
    """Reserve a unique directory; no reuse or overwrite of earlier runs."""
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid4().hex
    directory = Path(output_dir) / run_id
    directory.mkdir(parents=True, exist_ok=False)
    report = {
        "schema_version": 1,
        "run_id": run_id,
        "run_status": "running",
        "started_at_utc": utc_now(),
        "finished_at_utc": None,
        "elapsed_seconds": None,
        "provenance": provenance(root),
        "configuration": {
            "requested_agent_model": requested_model,
            "temperature": 0,
            "agent_reasoning": "model_default",
            "agent_num_predict": "model_default",
            "agent_client_timeout": "default",
            "recursion_limit": 20,
            "judge_invoked": False,
            "storage_tools_present": False,
        },
        "cases": [],
        "summary": {},
        "error": None,
    }
    return directory / "report.json", report


def write_report(path, report):
    """Replace the current run's checkpoint only after complete serialization."""
    text = json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    path = Path(path)
    temporary = path.with_suffix(".tmp")
    try:
        with temporary.open("w", encoding="utf-8", newline="\n") as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def summarize(cases, total):
    counts = {
        status: sum(case["status"] == status for case in cases)
        for status in ("pass", "fail", "error", "interrupted", "running")
    }
    return {
        "total_cases": total,
        "completed_cases": sum(counts[s] for s in ("pass", "fail", "error")),
        **counts,
        "not_started": total - len(cases),
        "judge_invoked": False,
    }
