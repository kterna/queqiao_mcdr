"""MCDR command execution audit logger and permission guard."""

import time
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class AuditRecord:
    source_qq: str
    command: str
    is_blocked: bool
    reason: str
    timestamp: datetime = field(default_factory=datetime.utcnow)


class McdrCommandGuard:
    """Enforces MCDR execution policy and maintains audit trails."""

    DEFAULT_BLOCKED_COMMANDS = {
        "stop", "restart", "reload", "kill", "ban", "op", "deop",
        "whitelist off", "execute"
    }

    def __init__(self, blocked_commands: Optional[set] = None):
        self.blocked_commands = (
            set(blocked_commands) if blocked_commands is not None
            else set(self.DEFAULT_BLOCKED_COMMANDS)
        )
        self.audit_log: List[AuditRecord] = []

    def check_and_audit(self, source_qq: str, command: str) -> Tuple[bool, str]:
        cmd_clean = command.strip()
        if cmd_clean.startswith("/"):
            cmd_clean = cmd_clean[1:].strip()

        root = cmd_clean.split()[0].lower() if cmd_clean else ""

        if root in self.blocked_commands:
            record = AuditRecord(
                source_qq=source_qq,
                command=command,
                is_blocked=True,
                reason=f"Command '{root}' violates MCDR security policy (P0)"
            )
            self.audit_log.append(record)
            return False, record.reason

        record = AuditRecord(
            source_qq=source_qq,
            command=command,
            is_blocked=False,
            reason="Authorized"
        )
        self.audit_log.append(record)
        return True, "Authorized"

    def get_recent_audits(self, limit: int = 50) -> List[AuditRecord]:
        return self.audit_log[-limit:]
