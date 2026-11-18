import os
os.environ.setdefault("QT_QPA_PLATFORM","offscreen")
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch, Mock
from PySide6.QtWidgets import QApplication
from source.stand_management.git import GitTool
from source.stand_management.git_window import GitWindow
from source.core.config import Config

class GitWindowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app=QApplication.instance() or QApplication([])
        cls.branch_loading_patch=patch.object(GitWindow,"load_branches")
        cls.branch_loading_patch.start()
        cls.addClassCleanup(cls.branch_loading_patch.stop)
        cls.history_patch=patch("source.stand_management.git_window.GitCommitView.reload")
        cls.history_patch.start()
        cls.addClassCleanup(cls.history_patch.stop)
        cls.git_requirement_patch=patch("source.stand_management.git_window.GitInstallation.require",return_value=True)
        cls.git_requirement_patch.start()
        cls.addClassCleanup(cls.git_requirement_patch.stop)
        cls.probe_patch=patch("source.stand_management.git_window.GitInstallation.start_probe")
        cls.probe_patch.start()
        cls.addClassCleanup(cls.probe_patch.stop)

    @classmethod
    def test_empty_path_and_editable_user(cls):
        with patch.object(Config,"state",return_value={"GitLocalRepoPath":""}), patch.object(GitTool,"windows_user",return_value={"username":"ogencue"}), patch.object(GitWindow,"start"), patch.object(Config,"set_state"):
            window=GitWindow.open()
            cls.app.processEvents()
            assert window._git["user"].text()=="OGENCUE"
            assert not window._git["user"].isReadOnly()
            assert window._git["path"].text()==""
            assert window._git["clone"].isEnabled()
            window.close()

    @classmethod
    def test_verified_repo_sets_local_flag(cls):
        with patch.object(Config,"set_state") as state, patch.object(GitTool,"windows_user",return_value={"username":"ogencue"}), patch.object(GitTool,"repository_url",return_value="https://mercedes-benz.ghe.com/devM286/SimFiles.git"), patch("shutil.which",return_value="git.exe"), patch("subprocess.run",return_value=Mock(returncode=0)) as run:
            assert GitTool.repository_check("OGENCUE")["allowed"]
            assert state.call_args.args==("GitUserState",True)
            assert "ls-remote" in run.call_args.args[0]

    @classmethod
    def test_changed_identity_cannot_gain_access(cls):
        with patch.object(Config,"set_state") as state, patch.object(GitTool,"windows_user",return_value={"username":"ogencue"}), patch("subprocess.run") as run:
            assert not GitTool.repository_check("OTHER")["allowed"]
            state.assert_called_with("GitUserState",False)
            run.assert_not_called()

    @classmethod
    def test_clone_requires_fresh_access(cls):
        with patch.object(Config,"state",return_value={"GitUserLicenceState":True}), patch.object(GitTool,"repository_check",return_value={"allowed":False,"status":"unverified"}), patch("subprocess.run") as run:
            assert not GitTool.clone_repository("user","unused")["allowed"]
            run.assert_not_called()

    @classmethod
    @patch("source.ui.dialogs.Dialogs.message")
    def test_successful_clone_fills_path_only_after_completion(cls, message):
        with patch.object(GitTool,"windows_user",return_value={"username":"ogencue"}), patch.object(GitWindow,"start"), patch.object(Config,"set_state"):
            window=GitWindow.open()
            cls.app.processEvents()
            window._git["queue"].put((0,window._git["user"].text(),"clone",{"allowed":True,"status":"cloned","path":"D:/SimFiles"},None))
            GitWindow.poll(window)
            assert window._git["path"].text()=="D:/SimFiles"
            assert window._git["clone"].isEnabled()
            window.close()

    @classmethod
    def test_launcher_button_restores_launcher(cls):
        from source.ui.launcher import Launcher
        from source.silEinrichten import SilverInstallation
        from PySide6.QtWidgets import QPushButton
        from PySide6.QtCore import Qt
        launcher=Mock()
        launcher.winId.return_value=123
        launcher.windowState.return_value=Qt.WindowState.WindowNoState
        with patch.object(GitWindow,"start"), patch.object(Launcher,"_window",launcher), patch.object(SilverInstallation,"show_wizard"):
            from PySide6.QtWidgets import QWidget
            parent=QWidget()
            window=GitWindow.open(parent)
            cls.app.processEvents()
            assert window.parentWidget() is None
            assert window.isMaximized()
            window.findChild(QPushButton,"gitLauncher").click()
            launcher.showNormal.assert_called_once()
            launcher.raise_.assert_called_once()
            launcher.activateWindow.assert_called_once()
            window.close()

    @classmethod
    def test_stale_check_cannot_authorize_changed_user(cls):
        with patch.object(GitWindow,"start"), patch.object(Config,"set_state") as save:
            window=GitWindow.open()
            cls.app.processEvents()
            old=window._git["user"].text()
            window._git["user"].setText(old[:-1])
            window._git["queue"].put((0,old,"check",{"allowed":True,"status":"accessible"},None))
            GitWindow.poll(window)
            assert not window._git["allowed"]
            assert save.call_args.args==("GitUserState",False)
            window.close()

    @classmethod
    def test_denied_preclone_never_opens_folder_or_clones(cls):
        with patch.object(GitWindow,"start"), patch.object(Config,"set_state"), patch.object(GitWindow,"access_notice") as notice, patch("source.stand_management.git_window.QFileDialog.getExistingDirectory") as folder:
            window=GitWindow.open()
            cls.app.processEvents()
            window._git["queue"].put((0,window._git["user"].text(),"preclone",{"allowed":False,"status":"identity_mismatch"},None))
            GitWindow.poll(window)
            folder.assert_not_called()
            notice.assert_called_once()
            assert "nicht geprüft" in window._git["status"].text()
            window.close()

    @classmethod
    def test_startup_check_leaves_controls_available(cls):
        with patch.object(GitWindow,"start"):
            window=GitWindow.open()
            cls.app.processEvents()
        with patch("source.stand_management.git_window.threading.Thread"):
            GitWindow.start(window,"check")
            assert not window._git["busy"]
            assert window._git["clone"].isEnabled()
            assert window._git["user"].isEnabled()
            window.close()

    @classmethod
    def test_launcher_closes_tool_windows(cls):
        from source.ui.launcher import Launcher
        with patch.object(GitWindow,"start"):
            window=GitWindow.open()
            cls.app.processEvents()
            assert Launcher.close_tools()
            assert not window.isVisible()

    @classmethod
    def test_notice_restores_actual_windows_user(cls):
        from PySide6.QtCore import QTimer
        with patch.object(GitWindow,"start") as start, patch.object(Config,"set_state"), patch.object(GitTool,"windows_user",return_value={"username":"ogencue"}):
            window=GitWindow.open()
            cls.app.processEvents()
            window._git["user"].setText("SVMERKL")
            start.reset_mock()
            QTimer.singleShot(20, cls.click_current_user_button)
            GitWindow.access_notice(window,"Test")
            assert window._git["user"].text()=="OGENCUE"
            start.assert_called_once_with(window,"check")
            window.close()

    @classmethod
    def click_current_user_button(cls):
        box=cls.app.activeModalWidget()
        next(button for button in box.buttons() if button.text()=="User-ID des aktuellen Users").click()

    @classmethod
    def test_license_toolbar_button_runs_license_flow(cls):
        from source.ui.git_licence import GitLicenceFlow
        from PySide6.QtWidgets import QPushButton
        with patch.object(GitWindow,"start") as start, patch.object(GitLicenceFlow,"question",return_value=True):
            window=GitWindow.open()
            cls.app.processEvents()
            start.reset_mock()
            window.findChild(QPushButton,"gitRequestLicense").click()
            start.assert_called_once_with(window,"license_order")
            window.close()

    @classmethod
    def test_open_checks_and_updates_status_without_click(cls):
        import threading
        import time
        started=threading.Event()
        finished=threading.Event()
        with patch.object(Config,"state",return_value={**Config.state(),"GitInstallationState":True}), patch.object(Config,"set_state"), patch.object(GitTool,"repository_check",side_effect=lambda *a,**kw: (started.set(),{"allowed":True,"status":"accessible"})[1]):
            window=GitWindow.open()
            deadline=time.monotonic()+3
            while time.monotonic()<deadline and not window._git["allowed"]:
                cls.app.processEvents()
            assert started.is_set()
            assert window._git["allowed"]
            assert "vorhanden" in window._git["status"].text()
            assert window._git["poll_timer"].isActive()
            assert window._git["clone"].isEnabled()
            window.close()

    @classmethod
    def test_branch_activation_progress_ends_after_result(cls):
        from source.ui.git_licence import GitLicenceFlow
        from PySide6.QtWidgets import QLabel
        with patch.object(GitWindow,"start"), patch.object(Config,"state",return_value={"GitLocalRepoPath":"D:/SimFiles"}), patch.object(GitLicenceFlow,"allow_git_action",return_value=True), patch("source.stand_management.git_window.threading.Thread"), patch("source.silEinrichten.SilEinrichten.foreground_dialog"), patch("source.ui.dialogs.Dialogs.message"):
            window=GitWindow.open()
            window._git["branches"].addItems(["main","develop"])
            window._git["branches"].setCurrentIndex(1)
            GitWindow.activate_branch(window)
            dialog,animation=window._git["branch_progress"]
            assert dialog.findChild(QLabel,"heading").text()=="develop wird aktiviert"
            assert any(label.text()=="Bitte warten ..." for label in dialog.findChildren(QLabel))
            result={"branches":["main","develop"],"active":"develop","warning":""}
            window._git["branch_queue"].put((window._git["branch_request"],"D:/SimFiles","develop",result,None))
            GitWindow.poll_branches(window)
            assert "branch_progress" not in window._git
            assert not window._git["busy"]
            assert window._git["branches"].currentText()=="develop"
            window.close()

    @classmethod
    def test_loading_branches_never_activates_them(cls):
        from source.stand_management.git_branches import GitBranches
        import queue
        messages=queue.Queue()
        with patch.object(GitBranches,"list",return_value={"branches":["main","devAGK"]}) as listing, patch.object(GitBranches,"activate") as activate:
            GitWindow.branch_worker(messages,1,"repo",None,None)
            listing.assert_called_once_with("repo")
            activate.assert_not_called()

    @classmethod
    def test_long_branch_error_stays_within_sidebar(cls):
        from PySide6.QtWidgets import QScrollArea
        with patch.object(GitWindow,"start"):
            window=GitWindow.open()
            window.showNormal()
            window.resize(700,500)
            path=Config.state()["GitLocalRepoPath"]
            error="Branch fehlt in C:\\"+"VeryLongPathSegment\\"*15
            window._git["branch_queue"].put((0,path,None,None,error))
            GitWindow.poll_branches(window)
            cls.app.processEvents()
            label=window._git["branch_note"]
            sidebar=window.findChild(QScrollArea)
            assert label.wordWrap()
            assert label.width() <= sidebar.viewport().width()
            assert "\u200b" in label.text()
            window.close()

    @classmethod
    def test_access_warning_links_request_and_has_cancel(cls):
        from PySide6.QtCore import QTimer
        with patch.object(GitWindow,"start"), patch.object(GitWindow,"request_repo_access") as request:
            window=GitWindow.open()
            QTimer.singleShot(20,cls.click_repo_request_warning)
            GitWindow.access_notice(window,"Zugriff nicht bestätigt")
            request.assert_called_once_with(window)
            window.close()

    @classmethod
    def click_repo_request_warning(cls):
        box=cls.app.activeModalWidget()
        assert "#f59e0b" in box.text()
        assert "Zugriffsrechte" in box.text()
        assert any(button.text()=="Abbrechen" for button in box.buttons())
        assert box.defaultButton().text()=="Abbrechen"
        next(button for button in box.buttons() if button.text()=="Zugriff auf Setup-Repo beantragen").click()

    @classmethod
    def test_open_unknown_git_starts_probe_before_repo_check(cls):
        from source.stand_management.git_installation import GitInstallation
        with patch.object(Config,"state",return_value={"GitLocalRepoPath":"","GitInstallationState":False}), patch.object(GitWindow,"start") as repo, patch.object(GitInstallation,"start_probe") as probe:
            window=GitWindow.open()
            probe.assert_called_once()
            repo.assert_not_called()
            probe.call_args.kwargs["retry"]()
            repo.assert_called_once_with(window,"check")
            window.close()
