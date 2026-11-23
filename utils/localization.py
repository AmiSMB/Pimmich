"""Translations for messages emitted outside Flask request handling."""

from functools import lru_cache
from gettext import NullTranslations, translation
from pathlib import Path

from utils.config_manager import load_config


_TRANSLATIONS_DIR = Path(__file__).resolve().parent.parent / "translations"
_SUPPORTED_LANGUAGES = {"fr", "en", "es", "de", "ja"}


def get_global_language() -> str:
    language = load_config().get("ui_language", "fr")
    return language if isinstance(language, str) and language in _SUPPORTED_LANGUAGES else "fr"


@lru_cache(maxsize=len(_SUPPORTED_LANGUAGES))
def _catalog(language: str):
    try:
        return translation(
            "messages",
            localedir=str(_TRANSLATIONS_DIR),
            languages=[language],
            fallback=True,
        )
    except OSError:
        return NullTranslations()


def tr(message: str, **values) -> str:
    """Translate a message using the globally configured language."""
    translated = _catalog(get_global_language()).gettext(message)
    return translated % values if values else translated
