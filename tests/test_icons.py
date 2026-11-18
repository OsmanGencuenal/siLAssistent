import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QIcon
from source.ui.icons import Icons
from source.core.runtime import Runtime

class IconTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.root = Path(__file__).resolve().parents[1]

    @classmethod
    def test_main_ico_is_used_when_renderable(cls):
        with patch.object(Icons, "file_icon", wraps=Icons.file_icon) as load:
            icon = Icons.application()
            assert not icon.pixmap(64, 64).isNull()
            assert load.call_count == 1
            assert load.call_args.args[0].name == "Main.ico"

    @classmethod
    def test_missing_or_broken_main_uses_robot_file(cls):
        for corrupt in (False, True):
            with tempfile.TemporaryDirectory() as temp:
                folder = Path(temp) / "icons"; folder.mkdir()
                if corrupt:
                    (folder / "Main.ico").write_bytes(b"broken image")
                shutil.copy2(cls.root / "icons/assistant.png", folder / "assistant.png")
                with patch.object(Runtime, "project_root", return_value=Path(temp)), patch.object(Icons, "file_icon", wraps=Icons.file_icon) as load:
                    icon = Icons.application()
                    assert not icon.pixmap(64, 64).isNull()
                    assert load.call_args.args[0].name == "assistant.png"

    @classmethod
    def test_entire_missing_icons_folder_uses_embedded_robot(cls):
        with tempfile.TemporaryDirectory() as temp, patch.object(Runtime, "project_root", return_value=Path(temp)):
            icon = Icons.application()
            for size in (16, 32, 64, 256):
                assert not icon.pixmap(size, size).isNull()

    @classmethod
    def test_icons_folder_is_shipped_recursively(cls):
        build = (cls.root / "tools/build_siLAssistent.ps1").read_text(encoding="utf-8")
        installer = (cls.root / "_iss/siLAssistent.iss").read_text(encoding="utf-8")
        assert "--include-data-files=$Root\\icons\\Main.ico=icons/Main.ico" in build
        assert "--include-data-files=$Root\\icons\\Support.ico=icons/Support.ico" in build
        assert 'Name: "{app}\\icons"' in installer
        assert "recursesubdirs createallsubdirs" in installer
