"""Main entry point for the Retail Chatbot application.

This module configures the PyQt6 environment and launches the chatbot GUI.
It handles Qt plugin path configuration for cross-platform compatibility
and sets up logging for the application.

Usage:
    python main.py
"""
import os
import sys
from pathlib import Path

# Ensure Qt can find the platform plugins (e.g., 'cocoa') bundled with PyQt6
try:
    import PyQt6  # type: ignore
    plugins_dir = Path(PyQt6.__file__).parent / "Qt6" / "plugins"
    if plugins_dir.exists():
        os.environ["QT_QPA_PLATFORM_PLUGIN_PATH"] = str(plugins_dir)
    # In case a global QT_PLUGIN_PATH is set and wrong, unset it to avoid conflicts
    if os.environ.get("QT_PLUGIN_PATH"):
        os.environ.pop("QT_PLUGIN_PATH", None)
except Exception:
    # Best-effort: continue; PyQt6 will try its defaults
    pass

import logging
import app as app_module

if __name__ == "__main__":
    # Configure logging so recommendation INFO logs are visible when summary appears
    logging.basicConfig(level=logging.INFO, format='[%(levelname)s] %(message)s', force=True)
    logging.info("App starting (via main.py)")
    qapp = app_module.QApplication(sys.argv)
    ui = app_module.ChatBotUI()
    ui.showMaximized()
    sys.exit(qapp.exec())
