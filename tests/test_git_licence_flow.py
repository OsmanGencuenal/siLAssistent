import unittest
from unittest.mock import patch
from source.ui.git_licence import GitLicenceFlow
from source.core.config import Config

class GitLicenceFlowTests(unittest.TestCase):
    @classmethod
    def test_license_true_does_not_check_or_prompt(cls):
        with patch.object(Config,"state",return_value={"GitUserLicenceState":True}), patch.object(GitLicenceFlow,"question") as question:
            assert GitLicenceFlow.allow_git_action(None)
            question.assert_not_called()

    @classmethod
    def test_unconfirmed_license_can_be_cancelled(cls):
        with patch.object(Config,"state",return_value={"GitUserLicenceState":False}), patch.object(GitLicenceFlow,"license_choice",return_value=None) as question:
            assert not GitLicenceFlow.allow_git_action(None)
            assert not GitLicenceFlow.allow_git_action(None)
            assert question.call_count==2
            assert "monatliche Kosten" in GitLicenceFlow.COST_WARNING

    @classmethod
    def test_request_checks_before_ordering(cls):
        from source.stand_management.git_license import GitLicense
        with patch.object(GitLicense,"check",return_value={"license":"present"}), patch.object(GitLicense,"prepare_order") as order:
            assert GitLicenceFlow.request_license()["license"]=="present"
            order.assert_not_called()
        with patch.object(GitLicense,"check",return_value={"license":"absent"}), patch.object(GitLicense,"prepare_order",return_value={"license":"review"}) as order:
            assert GitLicenceFlow.request_license()["license"]=="review"
            order.assert_called_once()


    @classmethod
    def test_existing_license_message_is_foreground_and_topmost(cls):
        from PySide6.QtWidgets import QApplication
        from PySide6.QtCore import Qt
        from source.ui.dialogs import Dialogs
        app=QApplication.instance() or QApplication([])
        with patch.object(Dialogs,"foreground",side_effect=cls.inspect_and_close_license_message) as foreground:
            Dialogs.message("Git User Lizenz vorhanden","Lizenz vorhanden")
            foreground.assert_called_once()

    @classmethod
    def inspect_and_close_license_message(cls, dialog):
        from PySide6.QtCore import Qt
        assert dialog.windowFlags() & Qt.WindowType.WindowStaysOnTopHint
        assert dialog.windowModality()==Qt.WindowModality.ApplicationModal
        dialog.accept()


def test_existing_license_confirmation_persists_and_allows_real_git_attempt():
    with patch.object(Config,"state",return_value={"GitUserLicenceState":False}),patch.object(Config,"set_state") as save,patch.object(GitLicenceFlow,"license_choice",return_value="present"):
        assert GitLicenceFlow.allow_git_action(None)
        save.assert_called_once_with("GitUserLicenceState",True)


def test_new_license_request_remains_an_explicit_choice():
    from source.stand_management.git_window import GitWindow
    with patch.object(Config,"state",return_value={"GitUserLicenceState":False}),patch.object(GitLicenceFlow,"license_choice",return_value="request"),patch.object(GitWindow,"start") as start:
        assert not GitLicenceFlow.allow_git_action(None)
        start.assert_called_once_with(None,"license_order")
