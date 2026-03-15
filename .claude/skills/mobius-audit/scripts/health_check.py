"""Quick health check: imports, DB, CLI, and tests.

Exit code 0 = all green, 1 = issues found.
Prints a structured report for the skill to interpret.
"""

import importlib
import json
import subprocess
import sys

sys.path.insert(0, "src")


def check_imports():
    """Verify all core modules import without error."""
    modules = [
        "mobius.config", "mobius.db", "mobius.models", "mobius.registry",
        "mobius.tournament", "mobius.memory", "mobius.selector", "mobius.swarm",
        "mobius.judge", "mobius.orchestrator", "mobius.runner", "mobius.ui",
        "mobius.providers.base", "mobius.providers.anthropic",
        "mobius.providers.google", "mobius.providers.openai",
        "mobius.providers.openrouter", "mobius.providers.tools",
    ]
    results = {}
    for mod in modules:
        try:
            importlib.import_module(mod)
            results[mod] = "ok"
        except Exception as e:
            results[mod] = f"FAIL: {e}"
    return results


def check_db():
    """Verify DB opens and has expected tables."""
    try:
        from mobius.config import get_config
        from mobius.db import init_db

        config = get_config()
        conn, vec = init_db(config)
        tables = [
            r[0] for r in
            conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        ]
        agents = conn.execute("SELECT COUNT(*) FROM agents").fetchone()[0]
        matches = conn.execute("SELECT COUNT(*) FROM matches").fetchone()[0]
        conn.close()
        return {
            "status": "ok",
            "vec_available": vec,
            "tables": tables,
            "agents": agents,
            "matches": matches,
        }
    except Exception as e:
        return {"status": f"FAIL: {e}"}


def check_cli():
    """Verify CLI entry point responds."""
    try:
        result = subprocess.run(
            [sys.executable, "-m", "mobius.cli", "--help"],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode != 0:
            return {"status": f"FAIL: exit code {result.returncode}", "stderr": result.stderr.strip()}
        commands = []
        for line in result.stdout.splitlines():
            stripped = line.strip()
            if stripped and not stripped.startswith(("-", "+", "|", "Usage", "Adversarial")):
                parts = stripped.split()
                if parts and parts[0].isalpha() and len(parts[0]) > 1:
                    commands.append(parts[0])
        return {"status": "ok", "commands": commands}
    except Exception as e:
        return {"status": f"FAIL: {e}"}


def check_env():
    """Check which API keys are available."""
    import os
    from mobius.config import get_config

    get_config()  # triggers .env loading
    keys = {
        "ANTHROPIC_API_KEY": bool(os.environ.get("ANTHROPIC_API_KEY")),
        "GOOGLE_API_KEY": bool(os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY")),
        "OPENAI_API_KEY": bool(os.environ.get("OPENAI_API_KEY")),
        "OPENROUTER_API_KEY": bool(os.environ.get("OPENROUTER_API_KEY")),
    }
    return keys


def check_tests():
    """Run pytest and return pass/fail counts."""
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pytest", "tests/", "-v", "--tb=line", "-q"],
            capture_output=True, text=True, timeout=60,
        )
        return {
            "status": "ok" if result.returncode == 0 else "FAIL",
            "returncode": result.returncode,
            "output": result.stdout[-500:] if result.stdout else "",
            "errors": result.stderr[-300:] if result.stderr else "",
        }
    except Exception as e:
        return {"status": f"FAIL: {e}"}


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "quick"

    report = {
        "imports": check_imports(),
        "db": check_db(),
        "cli": check_cli(),
        "env": check_env(),
    }

    if mode == "full":
        report["tests"] = check_tests()

    # Print as JSON for the skill to parse
    print(json.dumps(report, indent=2, default=str))

    # Exit code
    has_fail = any(
        "FAIL" in str(v) for v in report.values()
    )
    sys.exit(1 if has_fail else 0)


if __name__ == "__main__":
    main()
