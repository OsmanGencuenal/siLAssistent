import unittest
from unittest.mock import patch
from source.stand_management.setup_updates import SetupUpdates
from source.stand_management.git import GitTool
from source.core.config import Config

class SetupGitEligibilityTests(unittest.TestCase):
    @classmethod
    def test_no_licence_never_checks_or_offers_update(cls):
        with patch.object(Config,"state",return_value={"GitUserLicenceState":False}),patch.object(GitTool,"repository_check") as access,patch.object(SetupUpdates,"check") as counter:
            assert not SetupUpdates.check_mode("git")["available"]
            access.assert_not_called();counter.assert_not_called()

    @classmethod
    def test_denied_repo_never_checks_or_offers_update(cls):
        with patch.object(Config,"state",return_value={"GitUserLicenceState":True}),patch.object(Config,"set_state"),patch.object(GitTool,"windows_user",return_value={"username":"USER"}),patch.object(GitTool,"repository_check",return_value={"allowed":False}),patch.object(SetupUpdates,"check") as counter:
            result=SetupUpdates.check_mode("git")
            assert not result["available"] and not result["git_allowed"]
            counter.assert_not_called()

    @classmethod
    def test_licence_and_verified_repo_allow_update_check(cls):
        with patch.object(Config,"state",return_value={"GitUserLicenceState":True}),patch.object(Config,"set_state"),patch.object(GitTool,"windows_user",return_value={"username":"USER"}),patch.object(GitTool,"repository_check",return_value={"allowed":True}) as access,patch.object(SetupUpdates,"check",return_value={"available":True,"counter":7}):
            result=SetupUpdates.check_mode("git","USER")
            assert result["available"] and result["git_allowed"]
            access.assert_called_once_with("USER",persist=False)

    @classmethod
    def test_drive_update_is_independent_of_git_permissions(cls):
        with patch.object(Config,"state",return_value={"GitUserLicenceState":False}),patch.object(GitTool,"repository_check") as access,patch.object(SetupUpdates,"check",return_value={"available":True}):
            assert SetupUpdates.check_mode("drive")["available"]
            access.assert_not_called()

    @classmethod
    def test_pull_and_revert_denial_have_access_request_marker(cls):
        from unittest.mock import Mock
        from source.stand_management.git_branches import GitBranches
        for operation in ("pull","revert"):
            with patch.object(Config,"state",return_value={"GitUserLicenceState":True}),patch.object(GitTool,"windows_user",return_value={"username":"USER"}),patch.object(GitTool,"repository_check",return_value={"allowed":False}),patch.object(GitBranches,"validate") as validate:
                pipe=Mock()
                SetupUpdates.worker(pipe,operation,target="repo")
                result=pipe.send.call_args.args[0]
                assert result["repo_access_required"]
                assert "Zugriffsrechte" in result["error"]
                validate.assert_not_called()

    @classmethod
    def test_denied_action_uses_existing_access_request_dialog(cls):
        from unittest.mock import Mock
        from source.stand_management.git_window import GitWindow
        from source.stand_management.git_commit_view import GitCommitView
        parent=Mock();parent._git={}
        process=Mock();process.is_alive.return_value=False
        receiver=Mock();receiver.poll.return_value=True
        receiver.recv.return_value={"result":None,"error":"Repo-Rechte erforderlich","repo_access_required":True}
        state={"process":process,"receiver":receiver,"timer":Mock(),"parent":parent,"mode":"git","operation":"pull","result":None}
        with patch.object(GitCommitView,"reload"),patch.object(GitWindow,"access_notice") as notice,patch.object(SetupUpdates,"_active",True,create=True):
            SetupUpdates.poll(state)
            notice.assert_called_once_with(parent,"Repo-Rechte erforderlich",force_request=True)

    @classmethod
    def test_request_button_reuses_toolbar_handler(cls):
        from PySide6.QtWidgets import QApplication,QWidget,QLineEdit
        from PySide6.QtCore import QTimer
        from source.stand_management.git_window import GitWindow
        app=QApplication.instance() or QApplication([])
        parent=QWidget();parent._git={"user":QLineEdit("USER")}
        with patch.object(GitTool,"windows_user",return_value={"username":"USER"}),patch.object(GitWindow,"request_repo_access") as request:
            QTimer.singleShot(20,cls.click_request_button)
            GitWindow.access_notice(parent,"Repo-Rechte erforderlich",force_request=True)
            request.assert_called_once_with(parent)
        parent.close()

    @classmethod
    def click_request_button(cls):
        from PySide6.QtWidgets import QApplication
        box=QApplication.activeModalWidget()
        button=next((button for button in box.buttons() if button.text()=="Zugriff auf Setup-Repo beantragen"),None)
        if button:button.click()
        else:box.reject()
