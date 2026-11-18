import os,subprocess
from contextlib import nullcontext
from unittest.mock import Mock,patch
from source.silver.connection_worker import SilverConnectionWorker as Worker


def test_silver_launcher_hides_console_and_sanitizes_external_environment(tmp_path):
    env={"LOCALAPPDATA":str(tmp_path),"SILVER_HOME":"C:/Silver","QT_PLUGIN_PATH":"C:/Package/PySide6","PYTHONPATH":"C:/Package"}
    with patch.dict(os.environ,env,clear=True),patch.object(Worker,"external_dll_search",return_value=nullcontext()),patch("source.silver.connection_worker.subprocess.Popen") as popen:
        Worker.launch_silver(["C:/Silver/bin/silver.com","setup.sil"],creationflags=subprocess.CREATE_NEW_PROCESS_GROUP)
        options=popen.call_args.kwargs
        assert options["creationflags"] & subprocess.CREATE_NO_WINDOW
        assert options["creationflags"] & subprocess.CREATE_NEW_PROCESS_GROUP
        assert options["env"]["SILVER_HOME"]=="C:/Silver"
        assert "QT_PLUGIN_PATH" not in options["env"] and "PYTHONPATH" not in options["env"]
        assert options["stdout"].name.endswith("silver_start.log")
        assert options["stderr"] is options["stdout"]


def test_vendor_launcher_override_leaves_global_popen_untouched():
    module=Mock();original=subprocess.Popen
    Worker.configure_launcher(module)
    assert module.subprocess.Popen==Worker.launch_silver
    assert subprocess.Popen is original


def test_release_before_connection_is_harmless():
    with patch.object(Worker,"target",None),patch.object(Worker,"overrides",set()):
        assert Worker.dispatch({"op":"release"}) is True


def test_dll_directory_is_restored_after_launch_failure():
    import pytest
    kernel=Mock();kernel.SetDllDirectoryW.return_value=True
    kernel.GetDllDirectoryW.side_effect=lambda size,buffer:setattr(buffer,"value","C:/Package") or 10
    with patch("ctypes.WinDLL",return_value=kernel):
        with pytest.raises(RuntimeError,match="failed"):
            with Worker.external_dll_search():raise RuntimeError("failed")
    assert [call.args[0] for call in kernel.SetDllDirectoryW.call_args_list]==[None,"C:/Package"]
