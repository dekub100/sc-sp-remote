"""Role permissions and error envelope in server/protocol.py."""

from __future__ import annotations

import protocol


class TestProtocolPermissions:
    def test_source_and_controller_permissions_are_disjoint(self) -> None:
        source = protocol.permissions_for("spicetify")
        controller = protocol.permissions_for("streamdeck")
        assert "nowPlaying" in source and "command" not in source
        assert "command" in controller and "nowPlaying" not in controller

    def test_unknown_type_gets_logging_only(self) -> None:
        assert protocol.permissions_for("mystery") == protocol.DEFAULT_PERMISSIONS

    def test_check_and_draw_commands_are_valid(self) -> None:
        for command in ("like", "togglePlay", "next", "setVolume", "volumeUp"):
            assert command in protocol.COMMANDS

    def test_error_envelope_is_versioned(self) -> None:
        message = protocol.error_message("forbidden", "nope")
        assert message["v"] == protocol.PROTOCOL_VERSION
        assert message["type"] == "error"
        assert message["code"] == "forbidden"
