from pathlib import Path
import queue
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch
from source.core.config import Config
from source.core.errors import AssistantError
from source.core.update import UpdateManager
from source.silver.updates import SilverUpdates
from source.silEinrichten import SilverInstallation, SilEinrichten
from source.silver.silent import SilverSilent
from source.ui.launcher import Launcher

class SilverUpdateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.diagnostic_patch=patch.object(SilverUpdates,"save_version_diagnostic")
        cls.diagnostic_patch.start()
        local_files = patch.object(SilverUpdates, "installed_files", return_value=[])
        local_files.start()
        cls.addClassCleanup(local_files.stop)
        for name in ("validate_request", "environment", "command"):
            guard = patch.object(SilverSilent, name)
            guard.start()
            cls.addClassCleanup(guard.stop)
        cls.addClassCleanup(cls.diagnostic_patch.stop)

    @classmethod
    def release(cls):
        return {"installer_path": "SilverSetup_Y-2026.03-1.exe", "version": "Y-2026.03-1", "ini_path": "remote.ini"}

    @classmethod
    def entry(cls):
        return {"locator": "machine|-|64|Silver_W-2024.09_is1", "version": "W-2024.09.240830",
                "DisplayName": "Silver W-2024.09.240830", "InstallLocation": "C:/Silver", "UninstallString": "unins000.exe"}

    @classmethod
    def test_remote_ini_canonical_path_is_parsed(cls):
        with tempfile.TemporaryDirectory() as temp:
            ini = Path(temp) / "siLAssistent_Update.ini"
            ini.write_text("[UPDATE]\nsilverInstallerPath = SilverSetup_Y-2026.03-1.exe\n", encoding="utf-8-sig")
            release = SilverUpdates.release(ini)
            assert release["version"] == "Y-2026.03-1"
            assert release["installer_path"] == str(Path(temp) / "SilverSetup_Y-2026.03-1.exe")
            ini.write_text("[UPDATE]\ninstaller_path = unrelated.exe\n", encoding="utf-8")
            with unittest.TestCase().assertRaises(AssistantError):
                SilverUpdates.release(ini)

    @classmethod
    def test_same_version_is_not_offered_again(cls):
        state = {"InstalledSilverVersion": "Y-2026.03-1"}
        entry = {**cls.entry(), "version": "Y-2026.03-1"}
        with patch.object(SilverUpdates, "release", return_value=cls.release()), patch.object(SilverUpdates, "sync_path"), patch.object(SilverUpdates, "installed", return_value=[entry]), patch.object(Config, "state", return_value=state), patch.object(Config, "set_state") as save:
            result = SilverUpdates.check()
            assert not result["available"]
            save.assert_not_called()

    @classmethod
    def test_changed_version_is_offered_but_not_installed(cls):
        with patch.object(SilverUpdates, "release", return_value=cls.release()), patch.object(SilverUpdates, "sync_path"), patch.object(SilverUpdates, "installed", return_value=[cls.entry()]), patch.object(Config, "state", return_value={"InstalledSilverVersion": None}), patch.object(Config, "set_state") as save:
            result = SilverUpdates.check()
            assert result["available"] and result["installed_version"] == "W-2024.09.240830"
            assert result["target_locator"] == cls.entry()["locator"]
            save.assert_called_once_with("InstalledSilverVersion", "W-2024.09.240830")

    @classmethod
    def test_no_installed_silver_does_not_offer_uninstall_update(cls):
        with patch.object(SilverUpdates, "release", return_value=cls.release()), patch.object(SilverUpdates, "sync_path"), patch.object(SilverUpdates, "installed", return_value=[]), patch.object(Config, "state", return_value={"InstalledSilverVersion": None}):
            assert not SilverUpdates.check()["available"]

    @classmethod
    def test_multiple_unidentified_versions_are_not_arbitrarily_removed(cls):
        with unittest.TestCase().assertRaises(AssistantError):
            SilverUpdates.select_installed([cls.entry(), {**cls.entry(), "version": "Y-2026.03"}])

    @classmethod
    def test_no_answer_does_not_start_update(cls):
        release = {**cls.release(), "available": True, "installed_version": "W-2024.09", "target_locator": cls.entry()["locator"]}
        with patch.object(Launcher, "_silver_prompted", False, create=True), patch.object(SilEinrichten, "ask_question", return_value=False), patch.object(SilEinrichten, "launch") as launch:
            Launcher.offer_silver_update(release)
            launch.assert_not_called()

    @classmethod
    def test_yes_routes_confirmed_target_to_separate_update_process(cls):
        release = {**cls.release(), "available": True, "installed_version": "W-2024.09", "target_locator": cls.entry()["locator"]}
        with patch.object(Launcher, "_silver_prompted", False, create=True), patch.object(SilEinrichten, "ask_question", return_value=True), patch.object(SilEinrichten, "launch") as launch:
            Launcher.offer_silver_update(release)
            assert launch.call_args.kwargs["silver_update"] is True
            assert launch.call_args.kwargs["uninstall_target"] == cls.entry()["locator"]
            assert launch.call_args.kwargs["previous_version"] == "W-2024.09"

    @classmethod
    def test_app_update_failure_does_not_skip_silver_check(cls):
        with patch.object(Launcher, "_messages", queue.Queue()), patch.object(Launcher, "_checking", False, create=True), patch.object(Config,"load",return_value={"update_ini_path":"remote.ini"}), patch.object(Launcher,"start_silver_check") as silver, patch("source.ui.launcher.threading.Thread") as thread:
            Launcher.check_updates()
            silver.assert_called_once_with("remote.ini")
            thread.return_value.start.assert_called_once_with()

    @classmethod
    def test_manifest_publication_preserves_silver_path(cls):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "update.ini"
            path.write_text("[UPDATE]\nsilverInstallerPath=SilverSetup_Z-2027.01.exe\n", encoding="utf-8")
            UpdateManager.write_manifest(path, "0.2.0", "new-installer.exe", "a" * 64)
            parser = Config.parser(path)
            assert parser["PATH"]["silverInstallerPath"] == "SilverSetup_Z-2027.01.exe"
            assert parser["UPDATE"]["latest_version"] == "0.2.0"

    @classmethod
    def test_uninstall_requires_confirmed_identity(cls):
        with patch("source.silver.updates.subprocess.Popen") as start:
            with unittest.TestCase().assertRaises(AssistantError):
                SilverUpdates.uninstall(None, None, queue.Queue(), threading.Event())
            start.assert_not_called()

    @classmethod
    def test_registry_target_changed_after_consent_is_rejected(cls):
        with patch.object(SilverUpdates, "registered_entry", return_value=cls.entry()), patch("source.silver.updates.subprocess.Popen") as start:
            with unittest.TestCase().assertRaises(AssistantError):
                SilverUpdates.uninstall(cls.entry()["locator"], "Z-2030.01", queue.Queue(), threading.Event())
            start.assert_not_called()

    @classmethod
    def test_failed_uninstall_never_marks_removal_success(cls):
        process = Mock(); process.poll.return_value = 1; process.returncode = 1
        with patch.object(SilverUpdates, "registered_entry", return_value=cls.entry()), patch.object(SilverUpdates, "ensure_not_running"), patch.object(SilverUpdates, "uninstall_command", return_value=["unins000.exe"]), patch("source.silver.updates.subprocess.Popen", return_value=process), patch.object(Config, "set_state") as save:
            with unittest.TestCase().assertRaises(AssistantError):
                SilverUpdates.uninstall(cls.entry()["locator"], cls.entry()["version"], queue.Queue(), threading.Event())
            save.assert_not_called()

    @classmethod
    def test_successful_uninstall_requires_registry_disappearance(cls):
        process = Mock(); process.poll.return_value = 0; process.returncode = 0
        with patch.object(SilverUpdates, "registered_entry", side_effect=[cls.entry(), None]), patch.object(SilverUpdates, "ensure_not_running"), patch.object(SilverUpdates, "uninstall_command", return_value=["unins000.exe"]), patch("source.silver.updates.subprocess.Popen", return_value=process), patch.object(Config, "set_state") as save:
            SilverUpdates.uninstall(cls.entry()["locator"], cls.entry()["version"], queue.Queue(), threading.Event())
            save.assert_called_once_with("InstalledSilverVersion", None)

    @classmethod
    def test_worker_does_not_launch_new_installer_if_uninstall_failed(cls):
        with tempfile.TemporaryDirectory() as temp:
            installer = Path(temp) / "SilverSetup_Y-2026.03-1.exe"; installer.touch()
            messages = queue.Queue()
            with patch.object(SilverInstallation, "IS_WORKER", True, create=True), patch.object(SilverInstallation, "UPDATE_REQUESTED", True), patch.object(SilverInstallation, "prepare_local_installer", return_value=str(installer)), patch.object(SilverUpdates, "validate_installer"), patch.object(SilverUpdates, "uninstall", side_effect=AssistantError("uninstall failed")), patch.object(SilverInstallation, "shell_launch") as start, patch.object(SilverInstallation, "save_launch_diagnostic", return_value="diagnostic.json"), patch.object(SilverInstallation, "remove_local_installer"):
                SilverInstallation.launch_worker(str(installer), messages, threading.Event())
                start.assert_not_called()
                assert list(messages.queue)[-1][0] == "error"

    @classmethod
    def test_worker_uninstalls_before_new_install_and_records_after_success(cls):
        with tempfile.TemporaryDirectory() as temp:
            installer = Path(temp) / "SilverSetup_Y-2026.03-1.exe"; installer.touch()
            order = []
            with patch.object(SilverInstallation, "IS_WORKER", True, create=True), patch.object(SilverInstallation, "UPDATE_REQUESTED", True), patch.object(SilverInstallation, "TARGET_VERSION", "Y-2026.03-1"), patch.object(SilverInstallation, "prepare_local_installer", return_value=str(installer)), patch.object(SilverUpdates, "validate_installer"), patch.object(SilverUpdates, "uninstall", side_effect=lambda *a, **k:order.append("uninstall")), patch.object(SilverSilent, "run", side_effect=lambda *a, **k:order.append("install") or "local.ini"), patch.object(SilverUpdates, "record_success", side_effect=lambda version, **kwargs:order.append("record")), patch.object(SilverInstallation, "save_launch_diagnostic"), patch.object(SilverInstallation, "remove_local_installer"):
                messages = queue.Queue()
                SilverInstallation.launch_worker(str(installer), messages, threading.Event())
                assert order == ["uninstall", "install", "record"]
                assert list(messages.queue)[-1][0] == "installation_complete"

    @classmethod
    def test_fresh_install_queries_remote_before_preparing_and_elevating(cls):
        order = []
        with patch.object(SilverInstallation, "IS_WORKER", False, create=True), patch.object(SilverInstallation, "UPDATE_REQUESTED", False), patch.object(SilverInstallation, "TARGET_VERSION", None), patch.object(SilverUpdates, "release", side_effect=lambda:order.append("remote") or cls.release()), patch.object(SilverUpdates, "sync_path"), patch.object(SilverInstallation, "prepare_local_installer", side_effect=lambda *a:order.append("stage") or "cached.exe"), patch.object(SilverInstallation, "relay_elevated_worker", side_effect=lambda *a:order.append("elevate")):
            SilverInstallation.launch_worker("stale-local.exe", queue.Queue(), threading.Event())
            assert order == ["remote", "stage", "elevate"]

    @classmethod
    def test_success_marker_only_written_for_registered_target(cls):
        with patch.object(SilverUpdates, "installed", return_value=[{**cls.entry(), "version": "Y-2026.03-1"}]), patch.object(Config, "set_state") as save:
            SilverUpdates.record_success("Y-2026.03-1")
            save.assert_called_once_with("InstalledSilverVersion", "Y-2026.03-1")
        with patch.object(SilverUpdates, "installed", return_value=[]), patch.object(Config, "set_state") as save:
            with unittest.TestCase().assertRaises(AssistantError):
                SilverUpdates.record_success("Y-2026.03-1")
            save.assert_not_called()

    @classmethod
    def test_invalid_new_installer_never_uninstalls_existing_version(cls):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "SilverSetup_Y-2026.03-1.exe"
            path.write_bytes(b"not an executable")
            with patch.object(SilverInstallation, "IS_WORKER", True, create=True), patch.object(SilverInstallation, "UPDATE_REQUESTED", True), patch.object(SilverInstallation, "prepare_local_installer", return_value=str(path)), patch.object(SilverUpdates, "uninstall") as uninstall, patch.object(SilverInstallation, "save_launch_diagnostic"), patch.object(SilverInstallation, "remove_local_installer"):
                messages = queue.Queue()
                SilverInstallation.launch_worker(str(path), messages, threading.Event())
                uninstall.assert_not_called()
                assert list(messages.queue)[-1][0] == "error"

    @classmethod
    def test_only_registered_inno_uninstaller_inside_installation_can_be_used(cls):
        with tempfile.TemporaryDirectory() as temp:
            uninstaller = Path(temp) / "unins000.exe"; uninstaller.touch()
            entry = {**cls.entry(), "InstallLocation": temp, "UninstallString": f'"{uninstaller}" /SILENT'}
            assert SilverUpdates.uninstall_command(entry) == [str(uninstaller.resolve()), "/SILENT", "/NORESTART"]
            unrelated = Path(temp) / "other.exe"; unrelated.touch()
            entry["UninstallString"] = f'"{unrelated}"'
            with unittest.TestCase().assertRaises(AssistantError):
                SilverUpdates.uninstall_command(entry)

    @classmethod
    def test_confirmed_update_flags_survive_worker_handoff(cls):
        with patch.object(SilverInstallation, "UPDATE_REQUESTED", True), patch.object(SilverInstallation, "TARGET_VERSION", "Y-2026.03-1"), patch.object(SilverInstallation, "PREVIOUS_VERSION", "W-2024.09"), patch.object(SilverInstallation, "UNINSTALL_TARGET", cls.entry()["locator"]):
            flags = SilverInstallation.worker_options()
            assert "--silver-update" in flags
            assert flags[flags.index("--silver-target-version") + 1] == "Y-2026.03-1"
            assert flags[flags.index("--silver-uninstall-target") + 1] == cls.entry()["locator"]

    @classmethod
    def test_installed_release_with_build_date_suppresses_update(cls):
        entry={**cls.entry(),"version":"Y-2026.03-1.260409"}
        with patch.object(SilverUpdates,"release",return_value=cls.release()), patch.object(SilverUpdates,"sync_path"), patch.object(SilverUpdates,"installed",return_value=[cls.entry(),entry]), patch.object(SilverUpdates,"installed_files",return_value=[]), patch.object(Config,"state",return_value={"InstalledSilverVersion":"W-2024.09.240830"}), patch.object(Config,"set_state") as save:
            assert not SilverUpdates.check()["available"]
            save.assert_called_once_with("InstalledSilverVersion","Y-2026.03-1.260409")

    @classmethod
    def test_executable_version_detects_installation_missing_from_registry(cls):
        with patch.object(SilverUpdates,"release",return_value=cls.release()), patch.object(SilverUpdates,"sync_path"), patch.object(SilverUpdates,"installed",return_value=[cls.entry()]), patch.object(SilverUpdates,"installed_files",return_value=[{"version":"Y-2026.03-1","path":"Silver.exe"}]), patch.object(Config,"state",return_value={"InstalledSilverVersion":"W-2024.09.240830"}), patch.object(Config,"set_state"):
            assert not SilverUpdates.check()["available"]

    @classmethod
    def test_release_matching_keeps_patch_numbers_distinct(cls):
        assert SilverUpdates.release_matches("Y-2026.03-1.260409","Y-2026.03-1")
        assert not SilverUpdates.release_matches("Y-2026.03-2.260409","Y-2026.03-1")
        assert not SilverUpdates.release_matches("Y-2026.03-10.260409","Y-2026.03-1")

    @classmethod
    def test_remote_silver_home_is_never_detected_as_local(cls):
        with patch.dict("os.environ",{},clear=True),patch.object(Config,"load",return_value={"silver_home":r"\\OtherComputer\c$\Program Files\Synopsys\Silver Y-2026.03-1.260409"}),patch("win32api.GetFileVersionInfo") as read:
            assert SilverUpdates.installed_files()==[]
            read.assert_not_called()
