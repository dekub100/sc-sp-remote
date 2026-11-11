"""Log tailing (routes.py) and console stream encoding (log.py)."""

from __future__ import annotations

from typing import Any

import routes


class TestLogTail:
    def test_small_file_is_complete(self, tmp_path: Any) -> None:
        path = tmp_path / "a.log"
        path.write_text("hello", encoding="utf-8")
        text, truncated = routes._read_log_tail(str(path))
        assert text == "hello"
        assert truncated is False

    def test_large_file_is_tailed(self, tmp_path: Any) -> None:
        path = tmp_path / "big.log"
        path.write_text("x" * (routes.LOG_TAIL_BYTES + 100), encoding="utf-8")
        text, truncated = routes._read_log_tail(str(path))
        assert truncated is True
        assert text.startswith("[showing last 256 KB")
        assert text.endswith("x" * 100)


class TestConsoleStream:
    def test_undecodable_character_is_replaced(self) -> None:
        from log import _ConsoleStream

        class _AsciiStream:
            encoding = "ascii"

            def __init__(self) -> None:
                self.written: list[str] = []

            def write(self, msg: str) -> None:
                msg.encode("ascii")  # raises UnicodeEncodeError when needed
                self.written.append(msg)

            def flush(self) -> None:
                pass

        stream = _AsciiStream()
        _ConsoleStream(stream).write("caf\u00e9")
        assert stream.written == ["caf?"]
