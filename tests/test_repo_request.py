import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
from source.stand_management.repo_request import RepoRequest
from source.ui.git_licence import GitLicenceFlow
from source.core.config import Config

class RepoRequestTests(unittest.TestCase):
    @classmethod
    def test_support_address_must_be_unambiguous(cls):
        with tempfile.TemporaryDirectory() as temp:
            ini=Path(temp)/"update.ini"
            ini.write_text("[UPDATE]\nsupportMail = support@example.invalid\n",encoding="utf-8")
            assert RepoRequest.read_support_mail(ini)=="support@example.invalid"
            ini.write_text("[UPDATE]\nsupportMail = invalid\n",encoding="utf-8")
            with unittest.TestCase().assertRaises(ValueError):
                RepoRequest.read_support_mail(ini)

    @classmethod
    def test_outlook_opens_draft_and_never_sends(cls):
        mail=Mock()
        outlook=Mock()
        outlook.CreateItem.return_value=mail
        with patch("win32com.client.Dispatch",return_value=outlook):
            RepoRequest.compose("support@example.invalid",[("Anwender (User)",True),("Entwickler (Developer)",False),("Admin",False)])
            assert mail.To=="support@example.invalid"
            assert mail.Subject=="Antrag auf M286-SiL-Setup"
            assert "[x] Anwender (User)" in mail.Body
            from source.stand_management.git import GitTool
            assert mail.Body.startswith("M286-SiL-Setup Zugriff für ::\r\nUser-ID :: " + GitTool.windows_user()["username"].upper() + "\r\n\r\n")
            mail.Display.assert_called_once_with(False)
            mail.Send.assert_not_called()

    @classmethod
    def test_existing_license_shows_message_and_records_state(cls):
        import queue
        parent=Mock()
        messages=queue.Queue()
        browser=Mock()
        messages.put(({"license":"present","_browser":browser},None))
        parent._license_request=(messages,Mock())
        with patch.object(Config,"set_state") as save, patch("source.ui.dialogs.Dialogs.message") as message:
            GitLicenceFlow.poll_license_request(parent)
            save.assert_called_once_with("GitUserLicenceState",True)
            assert "bereits" in message.call_args.args[1]
            browser.quit.assert_called_once()

    @classmethod
    def test_request_without_role_keeps_dialog_open(cls):
        dialog=Mock()
        roles=[Mock(isChecked=Mock(return_value=False)) for _ in range(3)]
        with patch("source.stand_management.repo_request.QMessageBox.warning") as warning:
            assert not RepoRequest.validate_roles(dialog,roles)
            warning.assert_called_once()
            assert "mindestens eine Rolle" in warning.call_args.args[2]
            dialog.accept.assert_not_called()

    @classmethod
    def test_selected_role_allows_request(cls):
        dialog=Mock()
        assert RepoRequest.validate_roles(dialog,[Mock(isChecked=Mock(return_value=True))])
        dialog.accept.assert_called_once()

    @classmethod
    def test_empty_roles_never_open_outlook(cls):
        with patch("win32com.client.Dispatch") as outlook:
            with unittest.TestCase().assertRaises(ValueError):
                RepoRequest.compose("support@example.invalid",[("Admin",False)])
            outlook.assert_not_called()
