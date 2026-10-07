from __future__ import annotations

from dataclasses import dataclass

from database.profiles import ProfileContext


@dataclass
class CurrentSession:
    """Keep operator identity separate from the financial profile being viewed."""

    current_user_id: str | None = None
    active_profile: ProfileContext | None = None

    @property
    def active_profile_key(self) -> str | None:
        return self.active_profile.key if self.active_profile is not None else None

    def set_active_profile(self, profile_key: str | None) -> None:
        self.active_profile = (
            ProfileContext.from_key(profile_key) if profile_key is not None else None
        )
