from pathlib import Path
import hashlib
import tempfile
import unittest
from unittest.mock import Mock
from source.core.update import UpdateManager
from source.core.errors import AssistantError

class UpdateTests(unittest.TestCase):
    @classmethod
    def test_version_comparison_handles_different_lengths(cls):
        assert UpdateManager.version_tuple("1.2") == UpdateManager.version_tuple("1.2.0")
        assert UpdateManager.version_tuple("1.10.0") > UpdateManager.version_tuple("1.9.9")
        with unittest.TestCase().assertRaises(ValueError):
            UpdateManager.version_tuple("1.0-beta")

    @classmethod
    def test_unconfigured_update_does_not_touch_share(cls):
        assert UpdateManager.check("", "0.1.0") == {"available": False, "configured": False}

    @classmethod
    def test_ini_parsing_preserves_percent_and_relative_paths(cls):
        with tempfile.TemporaryDirectory() as temp:
            ini = Path(temp) / "update.ini"
            ini.write_text("[UPDATE]\nlatest_version=1.2.0\ninstaller_path=setup.exe\nforce_update=1\nmessage=100% verfügbar\n", encoding="utf-8-sig")
            release = UpdateManager.check(ini, "1.1.9")
            assert release["available"] and release["force_update"]
            assert release["message"] == "100% verfügbar"
            assert release["installer_path"] == str(Path(temp) / "setup.exe")

    @classmethod
    def test_same_version_never_updates(cls):
        with tempfile.TemporaryDirectory() as temp:
            ini = Path(temp) / "update.ini"
            ini.write_text("[UPDATE]\nlatest_version=1.2.0\n", encoding="utf-8")
            assert not UpdateManager.check(ini, "1.2.0")["available"]

    @classmethod
    def test_stage_copy_is_verified_and_original_unchanged(cls):
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / "published.exe"; source.write_bytes(b"installer-test")
            release = {"installer_path": str(source), "sha256": hashlib.sha256(source.read_bytes()).hexdigest()}
            target = UpdateManager.stage(release, Path(temp) / "local")
            assert target.read_bytes() == source.read_bytes() == b"installer-test"
            launch = Mock(); UpdateManager.launch(target, launch)
            launch.assert_called_once_with(str(target.resolve()))

    @classmethod
    def test_hash_mismatch_never_replaces_staged_installer(cls):
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / "published.exe"; source.write_bytes(b"modified")
            target = Path(temp) / "local"; target.mkdir()
            (target / "siLAssistent_Installer.exe").write_bytes(b"previous-valid")
            release = {"installer_path": str(source), "sha256": "a" * 64}
            with unittest.TestCase().assertRaises(AssistantError):
                UpdateManager.stage(release, target)
            assert (target / "siLAssistent_Installer.exe").read_bytes() == b"previous-valid"
            assert not list(target.glob("*.partial"))

    @classmethod
    def test_missing_hash_cannot_launch_update(cls):
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / "published.exe"; source.write_bytes(b"test")
            with unittest.TestCase().assertRaises(AssistantError):
                UpdateManager.stage({"installer_path": str(source)}, Path(temp) / "local")


def test_stage_reports_real_copy_and_hash_progress(tmp_path):
    source=tmp_path/"published.exe";source.write_bytes(b"installer"*300000)
    release={"installer_path":str(source),"sha256":hashlib.sha256(source.read_bytes()).hexdigest()}
    progress=[]
    target=UpdateManager.stage(release,tmp_path/"stage",progress=lambda text,value:progress.append((text,value)))
    assert target.read_bytes()==source.read_bytes()
    assert progress[0][1] is None and progress[-1][1]==100
    measured=[value for _,value in progress if value is not None]
    assert measured==sorted(measured)
    assert any("MB übertragen" in text for text,_ in progress)
    assert any("Prüfsumme" in text for text,_ in progress)


def test_update_installer_waits_for_exact_parent_to_exit():
    from unittest.mock import patch
    events=[];parent=Mock();parent.create_time.return_value=42
    parent.wait.side_effect=lambda **kwargs:events.append("parent exited")
    with patch("psutil.Process",return_value=parent),patch.object(UpdateManager,"launch",side_effect=lambda path,**kwargs:events.append("installer started")):
        assert UpdateManager.apply_after_exit("installer.exe",123,42)==0
    assert events==["parent exited","installer started"]


def test_update_does_not_start_if_parent_does_not_exit():
    import psutil,pytest
    from unittest.mock import patch
    parent=Mock();parent.create_time.return_value=42;parent.wait.side_effect=psutil.TimeoutExpired(120)
    with patch("psutil.Process",return_value=parent),patch.object(UpdateManager,"launch") as launch:
        with pytest.raises(AssistantError):UpdateManager.apply_after_exit("installer.exe",123,42)
        launch.assert_not_called()


def test_update_dialog_has_orange_bar_and_actual_percentage():
    from PySide6.QtWidgets import QApplication
    from source.ui.launcher import Launcher
    app=QApplication.instance() or QApplication([])
    with __import__('unittest.mock',fromlist=['patch']).patch.object(Launcher,"_window",None):
        try:
            Launcher.update_progress("Installer wird vorbereitet …",53)
            dialog=Launcher._update_progress
            assert dialog._bar.value()==53 and dialog._percent.text()=="53 %"
            assert "#f59e0b" in dialog.styleSheet()
            Launcher.update_progress("Anwendung wird beendet …",None)
            assert dialog._bar.maximum()==0
        finally:Launcher.finish_update_progress();app.processEvents()


def test_initial_status_is_reported_before_potentially_slow_network_access(tmp_path):
    from unittest.mock import patch
    source=tmp_path/"published.exe";source.write_bytes(b"installer")
    release=dict(installer_path=str(source),sha256=hashlib.sha256(source.read_bytes()).hexdigest())
    events=[];original=Path.stat
    def check(path,*args,**kwargs):
        if path==source:
            assert events and events[0][1] is None
            assert "Laufwerk" in events[0][0]
        return original(path,*args,**kwargs)
    with patch.object(Path,"stat",check):
        UpdateManager.stage(release,tmp_path/"stage",progress=lambda text,value:events.append((text,value)))
    assert events[-1][1]==100
