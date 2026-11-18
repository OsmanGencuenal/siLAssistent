from pathlib import Path
from unittest.mock import patch
import pytest
from source.core.config import Config
from source.core.runtime import Runtime
from source.core.uninstall import Uninstall


def test_uninstall_export_uses_existing_user_configuration_format(tmp_path):
    root=tmp_path/"app";root.mkdir();ini=root/"siLAssistent.ini"
    Config.set_state("GitUserState",True,ini)
    target=tmp_path/"documents/USER.ini"
    with patch.object(Runtime,"project_root",return_value=root):Uninstall.export_user_config(target)
    exported=Config.parser(target)
    assert exported.sections()==["USER"]
    assert exported.getboolean("USER","GitUserState")


def test_uninstall_export_cannot_save_inside_installation(tmp_path):
    with patch.object(Runtime,"project_root",return_value=tmp_path):
        with pytest.raises(ValueError,match="außerhalb"):Uninstall.export_user_config(tmp_path/"backup.ini")


def test_uninstall_starts_only_this_installations_native_uninstaller(tmp_path):
    root=tmp_path/"app";root.mkdir();target=root/"unins001.exe";target.write_bytes(b"MZ")
    with patch.object(Runtime,"project_root",return_value=root),patch("source.core.uninstall.subprocess.Popen") as launch:
        Uninstall.start(target)
        assert launch.call_args.args[0]==[str(target)]
        other=tmp_path/"unins001.exe";other.write_bytes(b"MZ")
        with pytest.raises(ValueError):Uninstall.start(other)
        assert launch.call_count==1


def test_export_command_uses_backend_and_does_not_start_launcher(tmp_path):
    from source.siLAssistent import Application
    root=tmp_path/"application";root.mkdir()
    Config.set_state("GitUserState",True,root/"siLAssistent.ini")
    destination=tmp_path/"documents with spaces"/"USER.ini"
    with patch.object(Runtime,"project_root",return_value=root),patch("source.ui.launcher.Launcher.run",side_effect=AssertionError("No launcher for uninstall export")):
        assert Application.main(["--export-user-config",str(destination)])==0
    assert Config.parser(destination).sections()==["USER"]


def test_uninstall_command_is_dispatched_without_opening_launcher(tmp_path):
    from source.siLAssistent import Application
    with patch.object(Uninstall,"start") as start,patch("source.ui.launcher.Launcher.run",side_effect=AssertionError("No launcher for uninstall")):
        assert Application.main(["--uninstall",str(tmp_path/"unins001.exe")])==0
        start.assert_called_once_with(str(tmp_path/"unins001.exe"))
