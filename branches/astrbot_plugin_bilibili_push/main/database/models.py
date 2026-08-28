from __future__ import annotations

from typing import List


class Subscription:
    def __init__(
        self,
        uid: str,
        username: str,
        sub_type: str,
        target_id: str,
        categories: List[int],
        tags: List[str],
        enabled: bool = True,
    ):
        self.uid = str(uid)
        self.username = username
        self.sub_type = sub_type
        self.target_id = target_id
        self.categories = categories
        self.tags = tags
        self.enabled = enabled


class Target:
    def __init__(
        self,
        target_id: str,
        channel: str,
        title: str = "",
        enabled: bool = True,
        created_at: int = 0,
        updated_at: int = 0,
    ):
        self.target_id = target_id
        self.channel = channel
        self.title = title
        self.enabled = enabled
        self.created_at = created_at
        self.updated_at = updated_at
