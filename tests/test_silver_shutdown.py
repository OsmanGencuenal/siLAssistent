import os
os.environ.setdefault("QT_QPA_PLATFORM","offscreen")
import queue,threading
from unittest.mock import Mock,patch,call
import pytest
from source.silver.connection import SilverConnection as C
from source.silver.methods import Silver
from source.silver.connection_worker import SilverConnectionWorker as Worker
from source.setup_operation.setup_control_window import SetupControlWindow as Window
from source.core.config import Config


@pytest.mark.parametrize("immediate",[False,True])
def test_always_saves_before_normal_or_immediate_exit(immediate):
    events=[]
    with patch.object(C,"_headless",True),patch.object(C,"_silver_pid",None),patch.object(C,"_silver_closed",False),patch.object(Silver,"save",side_effect=lambda *a,**kw:events.append("save")),patch.object(Silver,"exit",side_effect=lambda **kw:events.append(("exit",kw["force"]))) as exit,patch.object(C,"disconnect") as disconnect:
        C.save_and_exit("setup.sil",immediate)
        assert events==["save",("exit",immediate)]
        exit.assert_called_once_with(force=immediate,timeout=None,session="setup-control")
        disconnect.assert_called_once()


def test_failed_save_never_exits_even_with_immediate_selected():
    with patch.object(C,"_headless",True),patch.object(C,"_silver_pid",None),patch.object(C,"_silver_closed",False),patch.object(Silver,"save",return_value=False),patch.object(Silver,"exit") as exit,patch.object(C,"disconnect") as disconnect:
        with pytest.raises(RuntimeError,match="nicht speichern"):C.save_and_exit("setup.sil",True)
        exit.assert_not_called();disconnect.assert_not_called()


def test_gui_editor_is_saved_before_gui_instance_exits():
    from contextlib import nullcontext
    from source.silver.editor_save import SilverEditorSave as Editor
    events=[]
    with patch.object(C,"_headless",False),patch.object(C,"_silver_pid",42),patch.object(C,"_silver_closed",False),patch("psutil.Process",return_value=Mock()),patch.object(Editor,"during_apply",return_value=nullcontext()),patch.object(Editor,"clear_editor",side_effect=lambda pid:events.append("editor")),patch.object(Silver,"save",side_effect=lambda *a,**kw:events.append("save")),patch.object(Silver,"exit",side_effect=lambda **kw:events.append("exit")),patch.object(C,"disconnect"):
        C.save_and_exit("setup.sil")
    assert events==["editor","save","exit"]


def test_worker_forgets_overrides_after_successful_exit():
    target=Mock();target.exit.return_value=None
    with patch.object(Worker,"target",target),patch.object(Worker,"overrides",{"x"}):
        Worker.dispatch({"op":"call","method":"exit","kwargs":{"force":True}})
        assert Worker.target is None and not Worker.overrides


def test_worker_shutdown_only_reattaches_exact_known_pid_and_never_launches():
    commands=queue.Queue();responses=queue.Queue();target={"path":"setup.sil","pid":42,"headless":True}
    commands.put(("shutdown",[target],True));commands.put(None)
    with patch.object(C,"_silver_pid",42),patch.object(C,"_headless",True),patch.object(C,"connect",return_value={"reused":True}) as connect,patch.object(C,"alive",return_value=True),patch.object(C,"save_and_exit") as close,patch.object(C,"disconnect"):
        Window.connection_loop(commands,responses,threading.Event(),threading.Event())
        connect.assert_called_once_with("setup.sil",allow_start=False,gui=False,pid=42)
        close.assert_called_once_with("setup.sil",immediate=True)
    assert responses.get_nowait()==("shutdown",["setup.sil"],None)


def test_exit_now_ini_setting_roundtrips(tmp_path):
    path=tmp_path/"test.ini"
    assert Config.state(path)["SetupExitNow"] is False
    Config.set_state("SetupExitNow",True,path)
    assert Config.state(path)["SetupExitNow"] is True


def test_close_button_sends_save_exit_and_keeps_auto_preference():
    from PySide6.QtWidgets import QApplication
    app=QApplication.instance() or QApplication([])
    with patch("source.setup_operation.setup_control_window.threading.Thread"),patch.object(Config,"state",return_value={}),patch.object(Config,"set_state"):
        window=Window.open();state=window._setup_control
        try:
            target={"path":"setup.sil","pid":42,"headless":True}
            state["selected"]=state["connected_path"]="setup.sil";state["instances"]["setup.sil"]=target
            state["auto"].setChecked(True);state["exit_now"].setChecked(True)
            state["close_setup"].click()
            assert list(state["commands"].queue)[-1]==("shutdown",[target],True)
            assert state["progress"][0].isVisible()
            state["responses"].put(("shutdown",["setup.sil"],None));Window.poll(window)
            assert state["connected_path"] is None and not state["instances"]
            assert state["auto"].isChecked()
        finally:window.close()


def test_window_close_waits_for_headless_shutdown_before_accepting():
    from PySide6.QtWidgets import QApplication
    from PySide6.QtCore import QTimer
    app=QApplication.instance() or QApplication([])
    with patch("source.setup_operation.setup_control_window.threading.Thread"),patch.object(Config,"state",return_value={}),patch.object(Config,"set_state"):
        window=Window.open();state=window._setup_control
        state["instances"]["setup.sil"]={"path":"setup.sil","pid":42,"headless":True}
        def finished():
            state["responses"].put(("shutdown",["setup.sil"],None));Window.poll(window)
        QTimer.singleShot(50,finished)
        assert window.close()
        assert state["stop"].is_set() and state["shutdown_ok"]
        assert not state["instances"]


def test_closing_window_leaves_known_gui_instance_open():
    from PySide6.QtWidgets import QApplication
    app=QApplication.instance() or QApplication([])
    with patch("source.setup_operation.setup_control_window.threading.Thread"),patch.object(Config,"state",return_value={}),patch.object(Config,"set_state"):
        window=Window.open();state=window._setup_control
        state["instances"]["setup.sil"]={"path":"setup.sil","pid":42,"headless":False}
        assert window.close()
        assert not any(isinstance(command,tuple) and command[0]=="shutdown" for command in list(state["commands"].queue))
