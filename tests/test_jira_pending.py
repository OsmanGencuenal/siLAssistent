import os
os.environ.setdefault("QT_QPA_PLATFORM","offscreen")
import queue
import unittest
from unittest.mock import Mock,patch
from source.stand_management.jira import JiraTool
from source.stand_management.jira_access import JiraAccess
from source.core.config import Config

class JiraPendingTests(unittest.TestCase):
    @classmethod
    def monitor(cls,snapshots):
        clock={"now":0}
        stop=Mock();stop.is_set.return_value=False
        stop.wait.side_effect=lambda seconds:clock.update(now=clock["now"]+seconds)
        results=queue.Queue()
        with patch.object(JiraTool,"_commands",queue.Queue()),patch.object(JiraTool,"_results",results),patch.object(JiraTool,"_stopping",stop),patch("source.stand_management.jira.time.monotonic",side_effect=lambda:clock["now"]),patch.object(JiraAccess,"snapshot",side_effect=snapshots) as snapshot,patch.object(Config,"set_state") as save:
            JiraTool.check_board(Mock(),"Allgemein")
            return list(results.queue),clock["now"],save.call_args_list,snapshot.call_count

    @classmethod
    def test_persistent_access_gate_notifies_at_30_seconds_without_changing_ini(cls):
        events,elapsed,writes,calls=cls.monitor(["site_access_pending"]*7)
        assert elapsed==30 and calls==7
        assert events==[("Allgemein","site_access_pending"),("Allgemein","access_unconfirmed")]
        assert not writes

    @classmethod
    def test_access_before_30_seconds_does_not_show_pending_warning(cls):
        events,elapsed,writes,calls=cls.monitor(["joining"]*5+["allowed"])
        assert elapsed==25
        assert not any(state=="access_unconfirmed" for name,state in events)
        assert writes[0].args==("JiraUserState",True)

    @classmethod
    def test_login_does_not_count_toward_30_seconds_joining(cls):
        events,elapsed,writes,calls=cls.monitor(["login_required"]*8+["joining"]*7)
        assert elapsed==70
        assert events[-1][1]=="access_unconfirmed" and not writes

    @classmethod
    def test_leaving_joining_resets_continuous_wait_timer(cls):
        events,elapsed,writes,calls=cls.monitor(["joining"]*4+["login_required"]+["site_access_pending"]*7)
        assert elapsed==55 and not writes

    @classmethod
    def test_only_explicit_denial_sets_false(cls):
        events,elapsed,writes,calls=cls.monitor(["denied"])
        assert writes[0].args==("JiraUserState",False)

    @classmethod
    def test_retry_keeps_existing_page(cls):
        with patch.object(JiraTool,"submit") as submit:
            JiraTool.retry("Allgemein")
            submit.assert_called_once_with("Allgemein",navigate=False)

    @classmethod
    def test_three_pending_buttons_call_correct_actions(cls):
        from PySide6.QtWidgets import QApplication
        from PySide6.QtCore import QTimer
        app=QApplication.instance() or QApplication([])
        for action in ("Erneut prüfen","Jira-Zugriff beantragen","Abbrechen"):
            cls._action=action
            with patch.object(JiraTool,"retry") as retry,patch.object(JiraTool,"request_access") as request,patch("source.ui.dialogs.Dialogs.foreground"):
                QTimer.singleShot(20,cls.click_pending_action)
                JiraTool.pending_dialog(None,"Allgemein")
                assert cls._buttons==["Erneut prüfen","Jira-Zugriff beantragen","Abbrechen"]
                if action=="Erneut prüfen":retry.assert_called_once_with("Allgemein")
                else:retry.assert_not_called()
                if action=="Jira-Zugriff beantragen":request.assert_called_once_with(None)
                else:request.assert_not_called()

    @classmethod
    def click_pending_action(cls):
        from PySide6.QtWidgets import QApplication,QPushButton
        dialog=QApplication.activeModalWidget()
        buttons=dialog.findChildren(QPushButton)
        cls._buttons=[button.text() for button in buttons]
        match=next((button for button in buttons if button.text()==cls._action),None)
        if match:match.click()
        else:dialog.reject()
