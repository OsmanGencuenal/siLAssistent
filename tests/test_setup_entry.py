import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from pathlib import Path
import json
import queue
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch
from PySide6.QtWidgets import QApplication, QLabel
from source.core.config import Config
from source.siLAssistent import Application
from source.silEinrichten import SilEinrichten, SilverInstallation
from source.ui.dialogs import Dialogs

class SetupEntryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    @classmethod
    def test_setup_entry_routes_to_own_module(cls):
        with patch.object(Config, "ensure_state"), patch("source.core.runtime.Runtime.configure_logging"), patch.object(SilEinrichten, "run", return_value=0) as run:
            assert Application.main(["--sil-einrichten", "--silver-installer", "custom.exe"]) == 0
            assert run.call_args.kwargs["silver_installer"] == "custom.exe"

    @classmethod
    def test_both_worker_flags_reach_helper(cls):
        for flag in ("--Assistent-Worker-result", "--silver-worker-result"):
            with patch.object(SilverInstallation, "helper_main", return_value=0) as helper:
                assert Application.main([flag, "worker.json", "--silver-installer", "setup.exe"]) == 0
                helper.assert_called_once_with("worker.json", "setup.exe")

    @classmethod
    def test_source_launch_uses_host_entry_without_running_installer(cls):
        process = Mock(); process.poll.return_value = None
        with tempfile.TemporaryDirectory() as temp, patch.object(SilEinrichten, "_process", None, create=True), patch("source.silEinrichten.Runtime.data_root", return_value=Path(temp)), patch("source.silEinrichten.subprocess.Popen", return_value=process) as launch:
            assert SilEinrichten.launch() is process
            assert SilEinrichten.launch() is process
            launch.assert_called_once()
            command = launch.call_args.args[0]
            assert command[-1] == "--sil-einrichten" and command[-2].endswith("siLAssistent.py")

    @classmethod
    def test_compiled_launch_restarts_same_executable(cls):
        process = Mock()
        with tempfile.TemporaryDirectory() as temp, patch.object(SilEinrichten, "_process", None, create=True), patch("source.silEinrichten.Runtime.data_root", return_value=Path(temp)), patch("source.silEinrichten.sys.frozen", True, create=True), patch("source.silEinrichten.subprocess.Popen", return_value=process) as launch:
            SilEinrichten.launch()
            assert launch.call_args.args[0] == [__import__('sys').executable, "--sil-einrichten"]

    @classmethod
    def test_ini_path_overrides_legacy_installer_path(cls):
        state = dict(Config.STATE_DEFAULTS); state["silverInstallerPath"] = "new-release.exe"
        with patch.object(Config, "state", return_value=state), patch.object(SilEinrichten, "ask_question", return_value=True), patch.object(SilverInstallation, "run", return_value=0) as install:
            assert SilEinrichten.run() == 0
            assert install.call_args.kwargs["installer"] == "new-release.exe"

    @classmethod
    def test_dialogs_share_launcher_theme_and_keep_footer_visible(cls):
        from source.ui.launcher import Launcher
        dialog, footer, body = SilEinrichten.create_card("SiL-Einrichten", "Lange Meldung " * 100)
        assert Launcher.STYLE in dialog.styleSheet()
        assert body.textFormat() == __import__('PySide6.QtCore',fromlist=['Qt']).Qt.TextFormat.PlainText
        assert not dialog.windowIcon().isNull()
        assert any(label.text() == "siLAssistent" for label in dialog.findChildren(QLabel))
        dialog.close()

    @classmethod
    def test_background_helper_continues_after_installation_started(cls):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "worker.json"
            from source.silver.silent import SilverSilent
            path.with_name("request.json").write_text(json.dumps(SilverSilent.request()), encoding="utf-8")
            with patch.object(SilverInstallation, "is_administrator", return_value=True), patch.object(SilverInstallation, "IS_WORKER", False, create=True), patch.object(SilverInstallation, "launch_worker", side_effect=cls.simulated_worker):
                assert SilverInstallation.helper_main(path, "test.exe") == 0
            events = json.loads(path.read_text(encoding="utf-8"))
            assert [event[0] for event in events] == ["installation_started", "installation_complete"]

    @classmethod
    def simulated_worker(cls, installer, messages, cancelled):
        messages.put(("installation_started", "started"))
        messages.put(("installation_complete", "cleaned"))

    @classmethod
    def test_infosim_question_has_requested_text_colors_and_emphasis(cls):
        from PySide6.QtCore import Qt
        dialog, footer, body = SilEinrichten.create_card(SilEinrichten.INFOSIM_QUESTION, "old description")
        dialog.show()
        cls.app.processEvents()
        heading = dialog.findChild(QLabel, "heading")
        assert heading.textFormat() == Qt.TextFormat.RichText
        assert '<span style="color:#facc15;">InfoSim</span>' in heading.text()
        assert '<span style="color:#facc15;">Ziel-Rechner</span>' in heading.text()
        assert body.textFormat()==Qt.TextFormat.RichText
        assert '<b>InfoSim ist ein Rechner-gebundener Dienst!</b>' in body.text()
        assert 'color:#fca5a5;' in body.text()
        assert "Wenn Sie mit SiL" in body.text()
        assert body.palette().color(body.foregroundRole()).name() == "#40e0d0"
        assert body.font().pointSize() == 12
        redirect = dialog.findChild(QLabel, "itshopRedirect")
        assert redirect.text() == "mit Nein werden Sie zu IT-Shop weitergeleitet"
        assert redirect.palette().color(redirect.foregroundRole()).name() == "#f59e0b"
        assert redirect.font().pointSize() == 14 and redirect.font().bold()
        dialog.close()

    @classmethod
    def test_silver_question_remains_plain_and_without_itshop_notice(cls):
        from PySide6.QtCore import Qt
        dialog, footer, body = SilEinrichten.create_card("Wollen Sie Silver installieren?", "SilverSetup_Y-2026.03-1.exe")
        assert dialog.findChild(QLabel, "heading").textFormat() == Qt.TextFormat.PlainText
        assert body.text() == "SilverSetup_Y-2026.03-1.exe"
        body.ensurePolished()
        assert body.font().pointSize() == 18
        assert body.palette().color(body.foregroundRole()).name() == "#facc15"
        assert dialog.findChild(QLabel, "silverInstallAction").text() == "wird installiert"
        assert dialog.findChild(QLabel, "itshopRedirect") is None
        dialog.close()

    @classmethod
    def cancel_open_question(cls):
        from PySide6.QtWidgets import QPushButton
        dialog = QApplication.activeModalWidget()
        buttons = sorted(dialog.findChildren(QPushButton), key=lambda b:b.mapTo(dialog,b.rect().center()).x())
        assert [button.text() for button in buttons] == ["Abbrechen", "Nein", "Ja"]
        assert "<p>" in dialog.findChild(QLabel, "body").text()
        buttons[0].click()

    @classmethod
    def test_infosim_cancel_stops_before_browser_and_silver_start(cls):
        from PySide6.QtCore import QTimer
        with patch.object(SilEinrichten, "foreground_dialog"), patch.object(Config, "state", return_value=dict(Config.STATE_DEFAULTS)), patch.object(SilverInstallation, "run") as silver, patch.object(SilEinrichten, "browser_worker") as browser:
            QTimer.singleShot(50, cls.cancel_open_question)
            assert SilEinrichten.run() == 0
            assert SilEinrichten.QUESTION_CANCELLED
            silver.assert_not_called()
            browser.assert_not_called()

    @classmethod
    def test_silver_update_colors_and_larger_prompts(cls):
        text="Rechner: TEST\nInstalliert :: W-2024.09\nVerfügbar :: Y-2026.03-1\n\nMöchten Sie Silver aktualisieren?\nMit Ja wird zuerst die vorhandene Silver-Version deinstalliert und anschließend die neue Version installiert."
        dialog,footer,body=SilEinrichten.create_card("Silver-Update vorhanden",text)
        markup=body.text()
        assert 'color:#f59e0b; font-size:14pt;">Installiert ::' in markup
        assert 'color:#22c55e; font-size:14pt;">Verfügbar ::' in markup
        assert 'color:#facc15; font-size:16pt' in markup
        assert 'color:#f59e0b; font-size:12pt' in markup
        dialog.close()

    @classmethod
    def test_packaged_admin_worker_uses_exe_without_python_or_bootstrap(cls):
        with patch("source.silEinrichten.sys.frozen",True,create=True),patch("source.silEinrichten.sys.executable","C:/Package/siLAssistent.exe"):
            executable,args=SilverInstallation.worker_launch_command("start_worker.py","worker.json","SilverSetup.exe")
            assert executable.name=="siLAssistent.exe"
            assert "--Assistent-Worker-result" in args
            assert "start_worker.py" not in args
            assert "python.exe" not in args
            assert "pythonw.exe" not in args

    @classmethod
    def test_packaged_worker_refuses_python_uac_target(cls):
        with patch("source.silEinrichten.sys.frozen",True,create=True),patch("source.silEinrichten.sys.executable","C:/Python/pythonw.exe"):
            with unittest.TestCase().assertRaisesRegex(RuntimeError,"siLAssistent.exe"):
                SilverInstallation.worker_launch_command("bootstrap.py","result.json","SilverSetup.exe")

    @classmethod
    def test_simulation_reminder_is_large_and_in_footer(cls):
        reminder="Bitte laufende Silver-Simulationen vorher schließen."
        dialog,footer,body=SilEinrichten.create_card("Silver-Update vorhanden","Neue Version installieren. "+reminder)
        hint=dialog.findChild(QLabel,"silverSimulationReminder")
        assert hint.text()==reminder
        assert reminder not in body.text()
        assert footer.indexOf(hint)>=0
        hint.ensurePolished()
        assert hint.font().pointSize()==16 and hint.font().bold()
        dialog.close()
