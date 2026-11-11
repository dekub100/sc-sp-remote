"""manage.py CLI helpers."""

from __future__ import annotations


class TestManageProcessWait:
    def test_wait_returns_when_child_exits(self) -> None:
        import subprocess
        import sys

        import manage

        proc = subprocess.Popen([sys.executable, "-c", "pass"])
        manage._wait_for_process(proc)
        assert proc.returncode == 0
