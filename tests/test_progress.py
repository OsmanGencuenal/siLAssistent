import os
os.environ.setdefault("QT_QPA_PLATFORM","offscreen")
from unittest.mock import Mock,patch
from PySide6.QtWidgets import QApplication
from source.ui.progress import ProgressWindow
from source.ui.launcher import Launcher
from source.siLAssistent import Application
from source.core.config import Config
from source.core.runtime import Runtime


def test_startup_shows_actual_stages_before_launcher():
    app=QApplication.instance() or QApplication([])
    dialog=ProgressWindow.create("startup")
    with patch.object(ProgressWindow,"create",return_value=dialog),patch.object(ProgressWindow,"stage",wraps=ProgressWindow.stage) as stage,patch.object(Config,"ensure_state"),patch.object(Runtime,"configure_logging"),patch.object(Launcher,"run",return_value=0) as run:
        assert Application.main(["--no-update"])==0
        assert [call.args[2] for call in stage.call_args_list]==[0,25,50,75]
        assert run.call_args.kwargs["progress"] is dialog
        assert "#60a5fa" in dialog.styleSheet()
    ProgressWindow.finish(dialog);app.processEvents()


def test_update_closes_tools_then_launches_helper_then_quits():
    import queue
    from source.core.update import UpdateManager
    from source.stand_management.jira import JiraTool
    events=[];app=Mock();window=Mock();messages=queue.Queue();messages.put(("installer","staged.exe"))
    with patch.object(Launcher,"_window",window),patch.object(Launcher,"_messages",messages),patch.object(Launcher,"update_progress"),patch.object(Launcher,"finish_update_progress"),patch.object(Launcher,"close_tools",side_effect=lambda:events.append("tools closed") or True),patch.object(JiraTool,"shutdown",side_effect=lambda:events.append("jira stopped")),patch.object(UpdateManager,"launch_after_exit",side_effect=lambda path:events.append("helper started")),patch.object(Launcher,"_timer",Mock(),create=True),patch("source.ui.launcher.QApplication.instance",return_value=app):
        app.quit.side_effect=lambda:events.append("quit")
        Launcher.poll()
    assert events==["tools closed","jira stopped","helper started","quit"]
    assert window._update_exit is True


def test_busy_tool_prevents_installer_and_quit():
    import queue
    from source.core.update import UpdateManager
    messages=queue.Queue();messages.put(("installer","staged.exe"));app=Mock()
    with patch.object(Launcher,"_messages",messages),patch.object(Launcher,"update_progress"),patch.object(Launcher,"finish_update_progress"),patch.object(Launcher,"close_tools",return_value=False),patch.object(UpdateManager,"launch_after_exit") as launch,patch("source.ui.launcher.QApplication.instance",return_value=app),patch("source.ui.update_recovery.UpdateRecovery.notice"):
        Launcher.poll()
        launch.assert_not_called();app.quit.assert_not_called()


def test_update_exit_skips_normal_close_confirmation():
    window=Mock();window._update_exit=True;event=Mock()
    with patch("source.ui.launcher.QMessageBox") as question,patch.object(Launcher,"close_tools") as close:
        Launcher.close_event(window,event)
        event.accept.assert_called_once();event.ignore.assert_not_called()
        question.assert_not_called();close.assert_not_called()


def test_real_qt_update_exit_has_no_second_question(tmp_path):
    import subprocess,sys,textwrap
    from pathlib import Path
    script=textwrap.dedent("""
        import queue,sys
        from unittest.mock import patch
        from PySide6.QtCore import QTimer
        from PySide6.QtWidgets import QApplication,QMessageBox
        from source.ui.launcher import Launcher
        from source.core.update import UpdateManager
        from source.stand_management.jira import JiraTool
        app=QApplication([])
        errors=[]
        sys.excepthook=lambda *args:errors.append(str(args[1]))
        window=Launcher.create()
        window.closeEvent=lambda event:Launcher.close_event(window,event)
        window.show()
        messages=queue.Queue();messages.put(("installer","staged.exe"))
        launched=[]
        def unexpected_question(*args):raise AssertionError("Unexpected exit confirmation")
        with patch.object(Launcher,"_messages",messages),patch.object(Launcher,"_manual_update",False,create=True),patch.object(Launcher,"close_tools",return_value=True),patch.object(JiraTool,"shutdown"),patch.object(UpdateManager,"launch_after_exit",side_effect=lambda path:launched.append(path)),patch.object(QMessageBox,"exec",side_effect=unexpected_question):
            QTimer.singleShot(0,Launcher.poll)
            QTimer.singleShot(1500,lambda:app.exit(9))
            result=app.exec()
        assert result==0,(result,errors)
        assert errors==[],errors
        assert launched==["staged.exe"]
        assert window._update_exit is True
        print("QT_UPDATE_EXIT_WITHOUT_CONFIRMATION_OK")
    """)
    env=dict(os.environ,QT_QPA_PLATFORM="offscreen",QT_QPA_FONTDIR="C:/Windows/Fonts")
    result=subprocess.run([sys.executable,"-c",script],cwd=Path(__file__).resolve().parents[1],env=env,capture_output=True,text=True,timeout=15)
    assert result.returncode==0,result.stdout+result.stderr
    assert "QT_UPDATE_EXIT_WITHOUT_CONFIRMATION_OK" in result.stdout


def test_wait_phase_animates_without_seconds_or_fake_percentage():
    app=QApplication.instance() or QApplication([])
    dialog=ProgressWindow.create("update")
    ProgressWindow.stage(dialog,"Verbindung zum Laufwerk wird hergestellt …",None)
    assert dialog._bar.minimum()==0 and dialog._bar.maximum()==0
    assert dialog._percent.isHidden() and dialog._percent.text()==""
    ProgressWindow.stage(dialog,"Update ... 1.0 von 122.0 MB übertragen",.7)
    assert dialog._bar.maximum()==100 and dialog._percent.text()=="0,7 %"
    assert not dialog._percent.isHidden()
    ProgressWindow.finish(dialog);app.processEvents()


def test_accept_update_immediately_uses_activity_instead_of_zero_percent():
    import queue
    from PySide6.QtWidgets import QMessageBox
    from source.ui.update_recovery import UpdateRecovery
    messages=queue.Queue();messages.put(("release",dict(available=True,latest_version="0.0.9",force_update=False)))
    with patch.object(Launcher,"_messages",messages),patch.object(Launcher,"_update_started",False),patch.object(UpdateRecovery,"offer",return_value=QMessageBox.StandardButton.Yes),patch.object(Launcher,"update_progress") as stage,patch("source.ui.launcher.threading.Thread"):
        Launcher.poll()
        assert stage.call_args.args[1] is None
        assert "Laufwerk" in stage.call_args.args[0]
