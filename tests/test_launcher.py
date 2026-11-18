import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from pathlib import Path
import unittest
from unittest.mock import patch
from PySide6.QtWidgets import QApplication, QPushButton, QToolButton, QTabWidget, QListWidget, QLabel, QWidget
from PySide6.QtGui import QIcon
from source.ui.launcher import Launcher

class LauncherTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setStyle("Fusion")

    @classmethod
    def test_requested_structure_and_backend_separation(cls):
        window = Launcher.create()
        window.show()
        cls.app.processEvents()
        left = window.findChild(QToolButton, "standHeader")
        right = window.findChild(QToolButton, "operationHeader")
        assert left.text() == "Stand-Management" and right.text() == "Setup-Betrieb"
        assert left.mapTo(window, left.rect().center()).x() < right.mapTo(window, right.rect().center()).x()
        assert window.findChild(QPushButton, "setupButton").text() == "SiL-Einrichten"
        assert not window.findChildren(QTabWidget) and not window.findChildren(QListWidget)
        assert not window.windowIcon().isNull()
        window.close()

    @classmethod
    def test_section_headers_expand_and_collapse(cls):
        window = Launcher.create()
        window.show()
        cls.app.processEvents()
        hints = [window.findChild(QWidget, name) for name in ("standHeaderContent", "operationHeaderContent")]
        assert all(hint is not None and not hint.isVisible() for hint in hints)
        for name in ("standHeader", "operationHeader"):
            window.findChild(QToolButton, name).click()
        cls.app.processEvents()
        assert all(hint.isVisible() for hint in hints)
        for name in ("standHeader", "operationHeader"):
            window.findChild(QToolButton, name).click()
        assert all(not hint.isVisible() for hint in hints)
        window.close()

    @classmethod
    def test_setup_button_opens_setup_dialog(cls):
        window = Launcher.create()
        with patch.object(Launcher, "show_setup") as open_setup:
            # Signals bind their callback during construction.
            window.close()
            window = Launcher.create()
            window.findChild(QPushButton, "setupButton").click()
            open_setup.assert_called_once()
        window.close()

    @classmethod
    def test_footer_remains_visible_on_compact_windows(cls):
        for width, height in ((480, 360), (600, 480), (800, 600)):
            window = Launcher.create()
            window.resize(width, height)
            window.show()
            cls.app.processEvents()
            assert window.findChild(QPushButton, "updateButton") is None
            assert window.findChild(QLabel, "versionLabel") is None
            footer = window.findChild(QLabel, "suiteLabel")
            assert footer.text() == "siLAssistent Suite\nTeam-Merkle RD/EIC"
            position = footer.mapTo(window, footer.rect().bottomRight())
            assert footer.isVisible() and position.y() < window.height()
            bottom_bar = footer.parentWidget()
            bottom = bottom_bar.mapTo(window, bottom_bar.rect().bottomRight()).y()
            assert window.height() - 14 <= bottom < window.height(), (window.height(), bottom)
            window.close()

    @classmethod
    def test_setup_starts_dedicated_script_process(cls):
        window = Launcher.create()
        from source.silEinrichten import SilEinrichten
        with patch.object(SilEinrichten, "launch") as launch:
            Launcher.show_setup()
            launch.assert_called_once()
        window.close()

    @classmethod
    def test_git_and_jira_buttons_are_in_stand_management(cls):
        window = Launcher.create()
        window.show()
        window.findChild(QToolButton, "standHeader").click()
        cls.app.processEvents()
        git = window.findChild(QPushButton, "gitTool")
        jira = window.findChild(QPushButton, "jiraTool")
        assert git.text() == "Git" and jira.text() == "Jira"
        assert git.isVisible() and jira.isVisible()
        window.close()

    @classmethod
    def test_icon_assets_are_in_build_and_installer(cls):
        root = Path(__file__).resolve().parents[1]
        assert not QIcon(str(root / "icons/Main.ico")).isNull()
        pipeline = (root / "tools/build_siLAssistent.ps1").read_text(encoding="utf-8")
        assert "--windows-icon-from-ico=$Root\\icons\\Main.ico" in pipeline
        assert "--include-data-files=$Root\\icons\\Main.ico=icons/Main.ico" in pipeline
        assert "--include-data-files=$Root\\icons\\Support.ico=icons/Support.ico" in pipeline
        assert "SetupIconFile=..\\icons\\Support.ico" in (root / "_iss/siLAssistent.iss").read_text(encoding="utf-8")
        launcher = (root / "source/ui/launcher.py").read_text(encoding="utf-8")
        assert "Icons.application()" in launcher

    @classmethod
    def test_unavailable_update_share_does_not_change_launcher_layout(cls):
        import queue
        from PySide6.QtWidgets import QStatusBar, QFrame
        window = Launcher.create()
        window.show()
        cls.app.processEvents()
        footer = window.findChild(QFrame, "bottomBar")
        initial = footer.geometry()
        with patch.object(Launcher, "_messages", queue.Queue()), patch("source.ui.launcher.QMessageBox.warning") as warning:
            Launcher._messages.put(("check_error", "Missing update share: " + "very long path/" * 100))
            Launcher.poll()
            cls.app.processEvents()
            assert footer.geometry() == initial
            assert not window.findChildren(QStatusBar)
            warning.assert_not_called()
        window.close()

    @classmethod
    def test_update_check_is_scheduled_automatically_on_start(cls):
        from PySide6.QtCore import QTimer
        with patch.object(cls.app, "exec", return_value=0), patch.object(QTimer, "singleShot") as schedule:
            assert Launcher.run() == 0
            schedule.assert_called_once_with(700, Launcher.startup)
            Launcher._window.hide()
            Launcher._window.deleteLater()

    @classmethod
    def test_launcher_brand_colors(cls):
        window = Launcher.create()
        window.show()
        cls.app.processEvents()
        assert window.findChild(QLabel, "title").palette().color(window.findChild(QLabel, "title").foregroundRole()).name() == "#facc15"
        stand = window.findChild(QToolButton, "standHeader")
        assert stand.palette().color(stand.foregroundRole()).name() == "#f59e0b"
        window.close()

    @classmethod
    def test_close_confirmation_accepts_only_yes(cls):
        from PySide6.QtCore import QTimer, Qt
        from PySide6.QtWidgets import QMessageBox
        for answer, remains_visible in (("Nein", True), ("Ja", False)):
            window = Launcher.create()
            window.closeEvent = lambda event: Launcher.close_event(window, event)
            window.show()
            def choose():
                box = window._close_prompt
                assert box.windowModality() == Qt.WindowModality.ApplicationModal
                assert box.windowFlags() & Qt.WindowType.WindowStaysOnTopHint
                assert box.defaultButton().text() == "Nein"
                next(button for button in box.buttons() if button.text() == answer).click()
            with patch.object(Launcher, "foreground_close_prompt"):
                QTimer.singleShot(20, choose)
                window.close()
            assert window.isVisible() == remains_visible
            window.hide()
            window.deleteLater()
