import os,configparser
os.environ.setdefault("QT_QPA_PLATFORM","offscreen")
from pathlib import Path
from unittest.mock import Mock,patch
from source.ui.support import Support
from source.core.config import Config
from source.core import build_settings


def test_support_draft_has_exact_recipient_subject_and_is_not_sent():
    mail=Mock();outlook=Mock();outlook.CreateItem.return_value=mail
    with patch("win32com.client.Dispatch",return_value=outlook),patch("source.ui.support.QTimer.singleShot") as later:
        Support.compose("help@example.invalid")
    assert later.call_args.args[0]==200
    with patch.object(Support,"foreground") as foreground:
        later.call_args.args[1]()
        foreground.assert_called_once_with(mail.GetInspector)
    assert mail.To=="help@example.invalid"
    assert mail.Subject=="M286-SIL :: "
    mail.Display.assert_called_once_with(False);mail.Send.assert_not_called()
    mail.GetInspector.Activate.assert_called_once_with()
    assert mail.mock_calls.index(("Display", (False,), {})) < mail.mock_calls.index(("GetInspector.Activate", (), {}))


def test_local_application_address_is_used_without_network_lookup(tmp_path):
    path=tmp_path/"local.ini"
    with patch.object(build_settings,"SUPPORT_MAIL",""):
        Config.ensure_state(path)
        parser=Config.parser(path);parser.set("APPLICATION","supportMail","local@example.invalid");Config.write(path,parser)
        with patch.object(Config,"path",return_value=path),patch.object(Config,"load",side_effect=AssertionError("No network lookup")):
            assert Support.recipient()=="local@example.invalid"


def test_update_manifest_syncs_application_address_but_missing_mail_preserves_it(tmp_path):
    path=tmp_path/"local.ini"
    with patch.object(build_settings,"SUPPORT_MAIL","build@example.invalid"):
        Config.ensure_state(path)
        parser=configparser.ConfigParser(interpolation=None);parser.read_string("[UPDATE]\nsupportMail=new@example.invalid\n")
        Config.sync_support_mail(parser,path)
        assert Config.parser(Config.ensure_state(path)).get("APPLICATION","supportMail")=="new@example.invalid"
        empty=configparser.ConfigParser();empty.read_string("[UPDATE]\nlatest_version=1.0.0\n")
        Config.sync_support_mail(empty,path)
        assert Config.parser(path).get("APPLICATION","supportMail")=="new@example.invalid"
    with patch.object(build_settings,"SUPPORT_MAIL","next-release@example.invalid"):
        Config.ensure_state(path)
        assert Config.parser(path).get("APPLICATION","supportMail")=="next-release@example.invalid"


def test_installer_ini_uses_generated_support_mail_instead_of_developer_value(tmp_path):
    source=tmp_path/"local.ini";target=tmp_path/"stage.ini"
    Config.ensure_state(source)
    with patch.object(Config,"path",return_value=source):
        Config.export_installation_config(target,support_mail="release@example.invalid")
    assert Config.parser(target).get("APPLICATION","supportMail")=="release@example.invalid"
    installer=(Path(__file__).parents[1]/"_iss/siLAssistent.iss").read_text(encoding="utf-8")
    assert 'Section: "APPLICATION"; Key: "supportMail"; String: "{#SupportMail}"' in installer


def test_footer_support_button_has_shipped_icon_and_opens_support_action():
    from PySide6.QtWidgets import QApplication,QPushButton
    from source.ui.launcher import Launcher
    app=QApplication.instance() or QApplication([])
    with patch.object(Support,"open") as open:
        window=Launcher.create()
        try:
            button=window.findChild(QPushButton,"supportButton")
            assert button is not None and not button.icon().isNull()
            button.click();open.assert_called_once_with(window)
        finally:
            Launcher._timer.stop();window.deleteLater();app.processEvents()


def test_draft_foreground_uses_exact_handle_and_releases_thread_links():
    inspector=Mock()
    inspector._oleobj_.QueryInterface.return_value.GetWindow.return_value=123
    with patch("win32gui.IsWindow",return_value=True),patch("win32gui.IsIconic",return_value=True),patch("win32gui.GetForegroundWindow",return_value=456),patch("win32api.GetCurrentThreadId",return_value=1),patch("win32process.GetWindowThreadProcessId",side_effect=lambda hwnd:(2 if hwnd==123 else 3,42)),patch("win32process.AttachThreadInput") as attach,patch("win32gui.ShowWindow") as restore,patch("win32gui.BringWindowToTop") as top,patch("win32gui.SetForegroundWindow") as activate:
        Support.foreground(inspector)
    restore.assert_called_once();top.assert_called_once_with(123);activate.assert_called_once_with(123)
    assert sorted(tuple(call.args) for call in attach.call_args_list)==[(1,2,False),(1,2,True),(1,3,False),(1,3,True)]
