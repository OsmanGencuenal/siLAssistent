import queue
import threading
import unittest
from unittest.mock import Mock,patch
from selenium.common.exceptions import InvalidSessionIdException
from source.stand_management.jira import JiraTool
from source.stand_management.jira_access import JiraAccess
from source.stand_management.jira_alice import JiraAlice

class JiraBrowserRecoveryTests(unittest.TestCase):
    @classmethod
    def test_all_jira_buttons_and_retry_recover_closed_browser(cls):
        for name in (*JiraAccess.BOARD_IDS,JiraTool.REQUEST_ACCESS):
            for navigate in (True,False):
                commands=queue.Queue()
                commands.put((JiraTool.REQUEST_ACCESS,True))
                commands.put((name,navigate))
                results=queue.Queue();stop=threading.Event()
                old=Mock();old.window_handles=[]
                new=Mock()
                def prepare(driver,*args,**kwargs):
                    if driver is new:stop.set()
                with patch.object(JiraTool,"_commands",commands),patch.object(JiraTool,"_results",results),patch.object(JiraTool,"_stopping",stop),patch.object(JiraAccess,"browser",side_effect=[old,new]) as browser,patch.object(JiraAlice,"prepare",side_effect=prepare) as alice,patch.object(JiraTool,"check_board",side_effect=lambda *a:stop.set()) as check:
                    JiraTool.worker()
                    assert browser.call_count==2,(name,navigate)
                    if name==JiraTool.REQUEST_ACCESS:
                        assert alice.call_count==2
                        assert alice.call_args.args[0] is new
                        check.assert_not_called()
                    else:
                        check.assert_called_once_with(new,name)
                        new.get.assert_called_once_with(JiraAccess.url(name))
                    old.quit.assert_called_once_with()
                    assert results.empty(),(name,navigate)

    @classmethod
    def test_healthy_session_is_reused(cls):
        driver=Mock();driver.window_handles=["tab"];driver.current_window_handle="tab"
        with patch.object(JiraAccess,"browser") as browser:
            assert JiraTool.ensure_browser(driver)==(driver,False)
            browser.assert_not_called();driver.quit.assert_not_called()

    @classmethod
    def test_closed_session_during_navigation_is_retried_once(cls):
        commands=queue.Queue();commands.put(("Allgemein",True))
        results=queue.Queue();stop=threading.Event()
        old=Mock();old.get.side_effect=InvalidSessionIdException("browser closed")
        new=Mock()
        with patch.object(JiraTool,"_commands",commands),patch.object(JiraTool,"_results",results),patch.object(JiraTool,"_stopping",stop),patch.object(JiraAccess,"browser",side_effect=[old,new]) as browser,patch.object(JiraTool,"check_board",side_effect=lambda *a:stop.set()):
            JiraTool.worker()
            assert browser.call_count==2 and results.empty()
            new.get.assert_called_once_with(JiraAccess.url("Allgemein"))

    @classmethod
    def test_real_errors_are_not_retried_as_browser_closure(cls):
        assert not JiraTool.session_lost(ValueError("unknown page structure"))
        assert JiraTool.session_lost(InvalidSessionIdException())
