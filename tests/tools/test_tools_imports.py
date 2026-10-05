import os
from pathlib import Path
import subprocess
import sys


def test_merge_tool_import_does_not_require_optional_pyarrow():
    code = """
import builtins

original_import = builtins.__import__

def guarded_import(name, *args, **kwargs):
    if name == "pyarrow" or name.startswith("pyarrow."):
        raise AssertionError("merge tool attempted to import optional PyArrow")
    return original_import(name, *args, **kwargs)

builtins.__import__ = guarded_import
import canpy.tools.merge_nhr_csv
"""
    env = dict(os.environ)
    source_root = str(Path(__file__).resolve().parents[2] / "src")
    env["PYTHONPATH"] = os.pathsep.join(
        part for part in (source_root, env.get("PYTHONPATH")) if part
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )

    assert result.returncode == 0, result.stderr
