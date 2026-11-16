"""Command-line interface for the AeroRoute backend."""
from __future__ import annotations

import base64
import binascii
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any

# Support both ``python backend/cli.py`` and importing as a package.
try:
    from .planner import plan, validate_scenario
except ImportError:  # pragma: no cover - direct script execution
    from planner import plan, validate_scenario

APP_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = APP_ROOT / "user-data"
SCENARIO_PATH = DATA_DIR / "scenario.json"


def _reject_constant(value: str) -> Any:
    raise ValueError(f"invalid JSON constant: {value}")


def decode_scenario(argument: str) -> dict[str, Any]:
    try:
        raw = base64.b64decode(argument.encode("ascii"), validate=True)
    except (ValueError, UnicodeEncodeError, binascii.Error) as exc:
        raise ValueError("scenario argument is not valid base64") from exc
    try:
        text = raw.decode("utf-8")
        value = json.loads(text, parse_constant=_reject_constant)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise ValueError("scenario argument is not valid UTF-8 JSON") from exc
    return validate_scenario(value)


def _write_scenario(scenario: dict[str, Any]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix="scenario.", suffix=".tmp", dir=str(DATA_DIR))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(scenario, stream, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, SCENARIO_PATH)
    except Exception:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise


def load_scenario() -> dict[str, Any] | None:
    if not SCENARIO_PATH.exists():
        return None
    try:
        with SCENARIO_PATH.open("r", encoding="utf-8") as stream:
            value = json.load(stream, parse_constant=_reject_constant)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise ValueError("stored scenario is invalid") from exc
    return validate_scenario(value)


def _emit(value: Any) -> None:
    print(json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False))


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    try:
        if not args or args[0] not in {"plan", "save", "load"}:
            raise ValueError("usage: cli.py plan BASE64_UTF8_JSON | save BASE64_UTF8_JSON | load")
        command = args[0]
        if command == "load":
            if len(args) != 1:
                raise ValueError("usage: cli.py load")
            _emit(load_scenario())
        else:
            if len(args) != 2:
                raise ValueError(f"usage: cli.py {command} BASE64_UTF8_JSON")
            scenario = decode_scenario(args[1])
            if command == "plan":
                _emit(plan(scenario))
            else:
                _write_scenario(scenario)
                _emit({"ok": True})
        return 0
    except Exception as exc:
        _emit({"error": str(exc) or "request failed"})
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
