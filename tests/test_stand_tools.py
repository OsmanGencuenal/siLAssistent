import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import unittest
from unittest.mock import patch
from PySide6.QtWidgets import QApplication, QPushButton
from source.stand_management import GitTool, JiraTool
from source.ui.launcher import Launcher
from source.core.config import Config

class StandToolTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    @classmethod
    def test_tool_entries_do_not_read_or_modify_state(cls):
        from PySide6.QtCore import QTimer
        with patch.object(Config, "state") as read, patch.object(Config, "set_state") as write,patch("source.stand_management.jira_access.JiraAccess.browser") as browser:
            QTimer.singleShot(20,lambda:cls.app.activeModalWidget().reject())
            JiraTool.open()
            browser.assert_not_called()
            read.assert_not_called()
            write.assert_not_called()
        assert not hasattr(GitTool, "open_repository")

    @classmethod
    def test_launcher_tool_clicks_have_no_external_action(cls):
        window = Launcher.create()
        with patch("PySide6.QtGui.QDesktopServices.openUrl") as browser, patch.object(Config, "state") as read, patch.object(GitTool, "open") as git_open,patch.object(JiraTool,"open") as jira_open,patch("source.stand_management.setup_updates.SetupUpdates.watch"):
            window.findChild(QPushButton, "gitTool").click()
            window.findChild(QPushButton, "jiraTool").click()
            browser.assert_not_called()
            read.assert_not_called()
        window.close()
