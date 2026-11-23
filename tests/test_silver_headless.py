import os
os.environ.setdefault("QT_QPA_PLATFORM","offscreen")
import queue
import threading
from unittest.mock import Mock,patch
from source.silver.connection_worker import SilverConnectionWorker as Worker
from source.silver.connection import SilverConnection as Connection
from source.setup_operation.setup_control_window import SetupControlWindow as Window
from source.silver.parameter_files import SilverParameterFiles as Files
from source.core.config import Config


def test_headless_launch_uses_native_api_without_gui():
    target=Mock();target.started_successfully.return_value=True;target._silver_process.pid=123
    remote=Mock();remote.RemoteSilver.return_value=target
    try:
        with patch.object(Worker,"remote",remote):
            result=Worker.connect({"path":"setup.sil","existing":[],"gui":False})
            assert remote.RemoteSilver.call_args.kwargs["gui"] is False
            assert remote.RemoteSilver.call_args.kwargs["stopped"] is False
            assert result["headless"] is True
    finally:Worker.target=None


def test_existing_gui_instance_keeps_actual_mode_and_is_not_restarted():
    api=Mock();grpc=Mock();remote=Mock()
    try:
        with patch.object(Worker,"grpc_api",Mock(SilverApi=Mock(return_value=api)),create=True),patch.object(Worker,"grpc",grpc,create=True),patch.object(Worker,"remote",remote),patch.object(Worker,"existing_ports",return_value=[12345]):
            result=Worker.connect({"path":"setup.sil","gui":False,"existing":[{"pid":42,"ports":[12345],"headless":False}]})
            assert result["reused"] and not result["headless"]
            remote.RemoteSilver.assert_not_called()
    finally:Worker.target=None


def test_manual_start_receives_selected_headless_mode():
    commands=queue.Queue();responses=queue.Queue();stop=threading.Event();cancel=threading.Event()
    for message in (("headless",True),"setup.sil",None):commands.put(message)
    with patch.object(Connection,"connect",return_value={"reused":False}) as connect,patch.object(Connection,"disconnect"):
        Window.connection_loop(commands,responses,stop,cancel)
    connect.assert_called_once_with("setup.sil",cancelled=cancel,gui=False,enforce_mode=True)


def test_headless_flash_never_enters_silver_gui_editor():
    from source.silver.editor_save import SilverEditorSave
    commands=queue.Queue();responses=queue.Queue();stop=threading.Event()
    commands.put(("headless",True));commands.put("setup.sil")
    commands.put(("operation","parameters_save",{},"setup.sil"));commands.put(None)
    with patch.object(Connection,"connect",return_value={"reused":False}),patch.object(Connection,"disconnect"),patch.object(Connection,"alive",return_value=True),patch.object(Connection,"_headless",True),patch.object(Files,"apply_and_reload") as apply,patch.object(Files,"entries",return_value={}),patch.object(SilverEditorSave,"during_apply") as guard,patch.object(SilverEditorSave,"clear_editor") as editor:
        Window.connection_loop(commands,responses,stop,threading.Event())
        apply.assert_called_once();guard.assert_not_called();editor.assert_not_called()


def test_headless_ini_setting_roundtrips_as_boolean(tmp_path):
    path=tmp_path/"test.ini"
    assert Config.state(path)["SetupHeadless"] is False
    Config.set_state("SetupHeadless",True,path)
    assert Config.state(path)["SetupHeadless"] is True
    assert Config.parser(path).get("STATE","SetupHeadless")=="True"
    Config.set_state("SetupHeadless",False,path)
    assert Config.state(path)["SetupHeadless"] is False


def test_unchecking_headless_reconnects_in_visible_mode_even_when_already_connected():
    commands=queue.Queue();responses=queue.Queue();stop=threading.Event()
    for message in (("headless",True),"setup.sil",("headless",False),"setup.sil",None):commands.put(message)
    def connect(*args,**kwargs):
        Connection._headless=not kwargs["gui"]
        return {"reused":False}
    with patch.object(Connection,"_headless",False),patch.object(Connection,"connect",side_effect=connect) as start,patch.object(Connection,"alive",return_value=True),patch.object(Connection,"disconnect"):
        Window.connection_loop(commands,responses,stop,threading.Event())
        assert [call.kwargs["gui"] for call in start.call_args_list]==[False,True]
        assert all(call.kwargs["enforce_mode"] for call in start.call_args_list)


def test_manual_mode_change_saves_before_starting_new_instance():
    events=[]
    with patch.object(Connection,"_headless",True),patch.object(Connection,"save_and_exit",side_effect=lambda path:events.append("save_exit")),patch.object(Connection,"connect",side_effect=lambda *a,**kw:events.append("visible_start") or {"headless":False}) as start:
        assert Connection.match_requested_mode("setup.sil",{"headless":True},True)["headless"] is False
    assert events==["save_exit","visible_start"]
    assert start.call_args.kwargs["gui"] is True


def test_failed_save_never_starts_replacement_instance():
    import pytest
    with patch.object(Connection,"_headless",True),patch.object(Connection,"save_and_exit",side_effect=RuntimeError("save failed")),patch.object(Connection,"connect") as start:
        with pytest.raises(RuntimeError,match="save failed"):Connection.match_requested_mode("setup.sil",{},True)
        start.assert_not_called()
