from __future__ import annotations

from PySide6.QtCore import QSettings


SETTINGS_ORGANIZATION = "Ledgerly"
SETTINGS_APPLICATION = "Ledgerly"
LEGACY_SETTINGS_ORGANIZATION = "Finance"
LEGACY_SETTINGS_APPLICATION = "Finance"
OPEN_FULLSCREEN_KEY = "display/open_fullscreen"
SAVE_IMPORTED_FILES_KEY = "imports/save_source_files"
LAST_USER_ID_KEY = "session/last_user_id"


def application_settings() -> QSettings:
    settings = QSettings(SETTINGS_ORGANIZATION, SETTINGS_APPLICATION)
    if not settings.allKeys():
        legacy = QSettings(
            LEGACY_SETTINGS_ORGANIZATION,
            LEGACY_SETTINGS_APPLICATION,
        )
        for key in legacy.allKeys():
            settings.setValue(key, legacy.value(key))
        settings.sync()
    return settings


def _boolean_preference(
    key: str,
    default: bool,
    settings: QSettings | None = None,
) -> bool:
    target = settings if settings is not None else application_settings()
    value = target.value(key, default)
    if isinstance(value, bool):
        return value
    return str(value).strip().casefold() not in {"0", "false", "no", "off"}


def open_fullscreen_enabled(settings: QSettings | None = None) -> bool:
    return _boolean_preference(OPEN_FULLSCREEN_KEY, True, settings)


def set_open_fullscreen(
    enabled: bool,
    settings: QSettings | None = None,
) -> None:
    target = settings if settings is not None else application_settings()
    target.setValue(OPEN_FULLSCREEN_KEY, bool(enabled))
    target.sync()


def save_imported_files_enabled(settings: QSettings | None = None) -> bool:
    return _boolean_preference(SAVE_IMPORTED_FILES_KEY, True, settings)


def set_save_imported_files(
    enabled: bool,
    settings: QSettings | None = None,
) -> None:
    target = settings if settings is not None else application_settings()
    target.setValue(SAVE_IMPORTED_FILES_KEY, bool(enabled))
    target.sync()


def last_user_id(settings: QSettings | None = None) -> str | None:
    target = settings if settings is not None else application_settings()
    value = target.value(LAST_USER_ID_KEY)
    text = str(value).strip() if value is not None else ""
    return text or None


def set_last_user_id(
    user_id: str | None,
    settings: QSettings | None = None,
) -> None:
    target = settings if settings is not None else application_settings()
    if user_id is None:
        target.remove(LAST_USER_ID_KEY)
    else:
        target.setValue(LAST_USER_ID_KEY, str(user_id))
    target.sync()
