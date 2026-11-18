import os
os.environ.setdefault("QT_QPA_PLATFORM","offscreen")
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from PySide6.QtWidgets import QApplication, QLabel
from PySide6.QtCore import QTimer
from source.silEinrichten import SilEinrichten
from source.core.runtime import Runtime

class ITShopSupportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app=QApplication.instance() or QApplication([])

    @classmethod
    def test_error_details_are_saved_to_json(cls):
        with tempfile.TemporaryDirectory() as folder, patch.object(Runtime,"data_root",return_value=Path(folder)):
            path=SilEinrichten.save_itshop_error("TimeoutException: technical detail")
            assert json.loads(path.read_text(encoding="utf-8"))["error"]=="TimeoutException: technical detail"

    @classmethod
    def test_log_opens_in_editor_without_shell(cls):
        with patch("subprocess.Popen") as launch:
            SilEinrichten.open_itshop_log(None,Path("C:/Logs/test log.json"))
            args=launch.call_args.args[0]
            assert args[0].endswith("notepad.exe")
            assert args[1]==str(Path("C:/Logs/test log.json"))
            assert launch.call_args.kwargs["shell"] is False

    @classmethod
    def test_dialog_hides_technical_details_and_links_log(cls):
        with tempfile.TemporaryDirectory() as folder, patch.object(Runtime,"data_root",return_value=Path(folder)), patch.object(SilEinrichten,"foreground_dialog"), patch.object(SilEinrichten,"open_itshop_log") as editor:
            QTimer.singleShot(20,cls.check_dialog_and_click)
            SilEinrichten.show_itshop_error("TimeoutException: hidden technical detail")
            editor.assert_called_once()
            assert editor.call_args.args[1].is_file()

    @classmethod
    def check_dialog_and_click(cls):
        dialog=cls.app.activeModalWidget()
        body=dialog.findChild(QLabel,"body")
        assert "Support" in body.text()
        assert "TimeoutException" not in body.text()
        link=dialog.findChild(QLabel,"itshopLogLink")
        assert not link.openExternalLinks()
        link.linkActivated.emit("itshop-log")
        dialog.accept()
