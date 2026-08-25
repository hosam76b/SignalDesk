"""Compatibility exports for application configuration.

The project historically imports settings from the repository-root ``config``
module. This module exposes the same settings through ``app.core.config``.
"""

from config import Settings, get_settings, settings

__all__ = ["Settings", "get_settings", "settings"]
