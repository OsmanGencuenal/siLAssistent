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
    events=[];app=Mock();messages=queue.Queue();messages.put(("installer","staged.exe"))
    with patch.object(Launcher,"_messages",messages),patch.object(Launcher,"update_progress"),patch.object(Launcher,"finish_update_progress"),patch.object(Launcher,"close_tools",side_effect=lambda:events.append("tools closed") or True),patch.object(JiraTool,"shutdown",side_effect=lambda:events.append("jira stopped")),patch.object(UpdateManager,"launch_after_exit",side_effect=lambda path:events.append("helper started")),patch.object(Launcher,"_timer",Mock(),create=True),patch("source.ui.launcher.QApplication.instance",return_value=app):
        app.quit.side_effect=lambda:events.append("quit")
        Launcher.poll()
    assert events==["tools closed","jira stopped","helper started","quit"]


def test_busy_tool_prevents_installer_and_quit():
    import queue
    from source.core.update import UpdateManager
    messages=queue.Queue();messages.put(("installer","staged.exe"));app=Mock()
    with patch.object(Launcher,"_messages",messages),patch.object(Launcher,"update_progress"),patch.object(Launcher,"finish_update_progress"),patch.object(Launcher,"close_tools",return_value=False),patch.object(UpdateManager,"launch_after_exit") as launch,patch("source.ui.launcher.QApplication.instance",return_value=app),patch("source.ui.launcher.QMessageBox.warning"):
        Launcher.poll()
        launch.assert_not_called();app.quit.assert_not_called()
