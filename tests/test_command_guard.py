"""Unit tests for McdrCommandGuard."""

import pytest
from queqiao_mcdr.command_guard import McdrCommandGuard


def test_command_guard_policy_and_audit():
    guard = McdrCommandGuard()

    # Safe command
    allowed, reason = guard.check_and_audit("10001", "list")
    assert allowed is True
    assert reason == "Authorized"

    # Blocked command
    allowed, reason = guard.check_and_audit("10001", "/stop")
    assert allowed is False
    assert "violates MCDR security policy" in reason

    # Audit history
    audits = guard.get_recent_audits()
    assert len(audits) == 2
    assert audits[0].command == "list"
    assert audits[1].is_blocked is True
