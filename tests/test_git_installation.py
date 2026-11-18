import os
os.environ.setdefault("QT_QPA_PLATFORM","offscreen")
import unittest
import queue
from unittest.mock import Mock,patch
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTimer
from source.stand_management.git_installation import GitInstallation
from source.core.config import Config

class GitInstallationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app=QApplication.instance() or QApplication([])

    @classmethod
    def test_unknown_installation_starts_process_without_gui_detection(cls):
        with patch.object(Config,"state",return_value={"GitInstallationState":False}),patch.object(GitInstallation,"executable") as detect,patch.object(GitInstallation,"start_probe") as probe:
            assert not GitInstallation.require(None)
            probe.assert_called_once_with(None,retry=None,notify=True)
            detect.assert_not_called()

    @classmethod
    def test_missing_git_cancel_does_not_launch_installer(cls):
        from PySide6.QtWidgets import QMainWindow
        window=QMainWindow()
        window._git={"busy":False}
        with patch.object(Config,"state",return_value={"GitInstallationState":False}),patch.object(GitInstallation,"executable",return_value=None),patch.object(Config,"set_state") as save,patch.object(GitInstallation,"start") as start:
            QTimer.singleShot(20,cls.cancel_installation_prompt)
            GitInstallation.missing_prompt(window)
            start.assert_not_called()
            save.assert_not_called()
        window.close()

    @classmethod
    def cancel_installation_prompt(cls):
        dialog=cls.app.activeModalWidget()
        assert "keine Git-Installation" in dialog.text()
        assert any(button.text()=="Git-Installieren" for button in dialog.buttons())
        next(button for button in dialog.buttons() if button.text()=="Abbrechen").click()

    @classmethod
    def test_failed_install_worker_does_not_mark_installed(cls):
        messages=queue.Queue()
        with patch.object(GitInstallation,"install",side_effect=RuntimeError("cancelled")),patch.object(Config,"set_state") as save:
            GitInstallation.worker(messages)
            assert "nicht installiert" in messages.get()
            save.assert_not_called()

    @classmethod
    def test_state_true_only_after_installer_and_git_version_succeed(cls):
        import tempfile
        from pathlib import Path
        from contextlib import ExitStack
        for version_code in (0,1):
            with tempfile.TemporaryDirectory() as folder,ExitStack() as stack:
                installer=Path(folder)/"setup.exe"
                installer.write_bytes(b"test placeholder, never executed")
                stack.enter_context(patch.object(Config,"state",return_value={"GitInstallationPath":str(installer)}))
                save=stack.enter_context(patch.object(Config,"set_state"))
                stack.enter_context(patch("win32com.shell.shell.ShellExecuteEx",return_value={"hProcess":123}))
                stack.enter_context(patch("win32event.WaitForSingleObject"))
                stack.enter_context(patch("win32process.GetExitCodeProcess",return_value=0))
                stack.enter_context(patch("win32api.CloseHandle"))
                stack.enter_context(patch.object(GitInstallation,"executable",return_value="git.exe"))
                stack.enter_context(patch("subprocess.run",return_value=Mock(returncode=version_code)))
                if version_code:
                    with unittest.TestCase().assertRaises(RuntimeError):
                        GitInstallation.install()
                    save.assert_not_called()
                else:
                    GitInstallation.install()
                    save.assert_called_once_with("GitInstallationState",True)

    @classmethod
    def test_recorded_installation_skips_detection_on_every_action(cls):
        with patch.object(Config,"state",return_value={"GitInstallationState":True}),patch.object(GitInstallation,"_resolved_executable","git.exe",create=True),patch("source.stand_management.git_installation.Path.is_file",return_value=True),patch.object(GitInstallation,"executable") as detect,patch.object(Config,"set_state") as save:
            assert GitInstallation.require(None)
            assert GitInstallation.require(None)
            detect.assert_not_called()
            save.assert_not_called()

    @classmethod
    def test_background_repo_check_records_detected_git(cls):
        from source.stand_management.git import GitTool
        with patch.object(Config,"state",return_value={"GitInstallationState":False}),patch.object(Config,"set_state") as save,patch.object(GitTool,"windows_user",return_value={"username":"user"}),patch.object(GitInstallation,"executable",return_value="git.exe"),patch.object(GitTool,"repository_url",return_value="https://mercedes-benz.ghe.com/devM286/SimFiles.git"),patch("subprocess.run",return_value=Mock(returncode=0)):
            GitTool.repository_check("user",persist=False)
            save.assert_called_once_with("GitInstallationState",True)

    @classmethod
    def test_stale_true_with_removed_cached_git_rechecks_in_process(cls):
        with patch.object(Config,"state",return_value={"GitInstallationState":True}),patch.object(GitInstallation,"_resolved_executable","removed/git.exe",create=True),patch("source.stand_management.git_installation.Path.is_file",return_value=False),patch.object(GitInstallation,"start_probe") as probe:
            assert not GitInstallation.require(None)
            probe.assert_called_once_with(None,retry=None,notify=True)
            assert GitInstallation._resolved_executable is None

    @classmethod
    def test_present_broken_git_is_not_reported_as_uninstalled(cls):
        from source.core.git_probe import GitProbe
        connection=Mock()
        with patch.object(GitProbe,"find_executable",return_value="git.exe"),patch("source.core.git_probe.subprocess.run",side_effect=PermissionError("blocked")):
            GitProbe.run(connection)
            result=connection.send.call_args.args[0]
            assert result["path"]=="git.exe"
            assert "installiert" in result["error"] and "starten" in result["error"]

    @classmethod
    def test_missing_git_probe_returns_missing_without_exception(cls):
        from source.core.git_probe import GitProbe
        connection=Mock()
        with patch.object(GitProbe,"find_executable",return_value=None):
            GitProbe.run(connection)
        result=connection.send.call_args.args[0]
        assert result["path"] is None and result["error"] is None

    @classmethod
    def test_missing_probe_resets_stale_true_and_offers_existing_installer(cls):
        from PySide6.QtWidgets import QMainWindow
        window=QMainWindow();window._git={"busy":False}
        process=Mock();process.is_alive.return_value=False
        receiver=Mock();receiver.poll.return_value=True
        receiver.recv.return_value={"path":None,"error":None}
        window._git_probe={"process":process,"receiver":receiver,"timer":Mock(),"result":None,"notify":True,"retry":None}
        with patch.object(Config,"set_state") as save,patch.object(GitInstallation,"missing_prompt") as prompt:
            GitInstallation.poll_probe(window)
            save.assert_called_once_with("GitInstallationState",False)
            prompt.assert_called_once_with(window)
        window.close()
