from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class UserIdentity:
    platform: str
    platform_user_id: str
    nickname: str
    role: str = "user"

    @property
    def global_user_id(self) -> str:
        return f"{self.platform}:{self.platform_user_id}"


@dataclass(slots=True)
class SessionStream:
    unified_msg_origin: str
    platform: str
    message_type: str
    session_id: str
    group_id: str | None = None
