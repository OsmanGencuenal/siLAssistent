import queue
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
from source.silver.silent import SilverSilent
from source.silver.updates import SilverUpdates
from source.silver.licences import SilverLicences
from source.core.config import Config
from source.core.errors import AssistantError


class SilverSilentTests(unittest.TestCase):
    @classmethod
    def test_explicit_silent_no_profile_or_forced_application_close(cls):
        command = SilverSilent.command("setup.exe", "Y-2026.03-1", {"local_app_data":"C:/Users/Test/AppData/Local"}, "C:/Logs/setup.log")
        assert "/VERYSILENT" in command and "/ACCEPTLICENSES" in command
        assert "/NORESTART" in command and "/TYPE=full" in command
        assert "/TASKS=" + ",".join(SilverSilent.TASKS) in command
        assert "mingw_path" in ",".join(command) and "matlab_path" in ",".join(command)
        assert not any(s in ",".join(command).upper() for s in ("LOADINF", "SAVEINF", "FORCECLOSEAPPLICATIONS", "MERGETASKS", "XIL"))
        assert any(arg.startswith("/DEMOFOLDER=") and "Test" in arg for arg in command)

    @classmethod
    def test_license_environment_replaces_existing_duplicates(cls):
        with patch.dict("os.environ", {"SNPSLMD_LICENSE_FILE":"old;old"}), patch.object(SilverLicences,"environment_value",return_value="27031@new;27031@other"):
            env = SilverSilent.environment()
        assert env["SNPSLMD_LICENSE_FILE"] == "27031@new;27031@other"
        assert env["SNPS_QUEUE"] == "1"

    @classmethod
    def test_path_update_is_idempotent_and_keeps_other_paths(cls):
        existing = r"C:\Tools;%SILVER_HOME%\bin;%SILVER_HOME%\bin"
        result = SilverSilent.merged_path(existing)
        assert result == SilverSilent.merged_path(result)
        assert result.count(r"%SILVER_HOME%\bin") == 1
        assert r"C:\Tools" in result

    @classmethod
    def test_success_verifies_settings_before_completion(cls):
        process = Mock(pid=123, returncode=0)
        process.poll.return_value=0
        with tempfile.TemporaryDirectory() as temp:
            request={"local_app_data":temp,"ini_path":str(Path(temp)/"local.ini"),"sid":"S-1-5-21-123"}
            with patch.object(SilverSilent,"validate_request"), patch.object(SilverSilent,"environment",return_value={}), patch("source.silver.silent.subprocess.Popen",return_value=process) as start, patch.object(SilverSilent,"verify_installation",return_value=Path(temp)) as verify, patch.object(SilverSilent,"configure_user") as configure:
                pids=set(); record=Mock()
                assert SilverSilent.run("setup.exe","Y-2026.03-1",request,queue.Queue(),threading.Event(),pids,record)==request["ini_path"]
                assert pids == {123}
                verify.assert_called_once_with("Y-2026.03-1")
                configure.assert_called_once_with(request,Path(temp))
                assert "/VERYSILENT" in start.call_args.args[0]

    @classmethod
    def test_failed_setup_never_reports_success_or_changes_user_settings(cls):
        process=Mock(pid=123,returncode=2);process.poll.return_value=2
        with tempfile.TemporaryDirectory() as temp:
            with patch.object(SilverSilent,"validate_request"),patch.object(SilverSilent,"environment",return_value={}),patch("source.silver.silent.subprocess.Popen",return_value=process),patch.object(SilverSilent,"verify_installation") as verify,patch.object(SilverSilent,"configure_user") as configure:
                with unittest.TestCase().assertRaises(AssistantError):
                    SilverSilent.run("setup.exe","Y-2026.03-1",{"local_app_data":temp,"sid":"S-1-5-21-123"},queue.Queue(),threading.Event(),set(),Mock())
                verify.assert_not_called();configure.assert_not_called()

    @classmethod
    def test_success_stores_full_actual_version_in_original_ini(cls):
        with patch.object(SilverUpdates,"installed",return_value=[{"version":"Y-2026.03-1.260409"}]),patch.object(Config,"set_state") as save:
            SilverUpdates.record_success("Y-2026.03-1",ini_path="C:/Tool/siLAssistent.ini")
            save.assert_called_once_with("InstalledSilverVersion","Y-2026.03-1.260409",path=Path("C:/Tool/siLAssistent.ini"))

    @classmethod
    def test_wrong_patch_cannot_be_saved_as_success(cls):
        with patch.object(SilverUpdates,"installed",return_value=[{"version":"Y-2026.03-2.260409"}]),patch.object(Config,"set_state") as save:
            with unittest.TestCase().assertRaises(AssistantError):
                SilverUpdates.record_success("Y-2026.03-1")
            save.assert_not_called()

    @classmethod
    def test_utf16_start_notification(cls):
        with tempfile.TemporaryDirectory() as temp:
            log=Path(temp)/"setup.log"
            log.write_text("Starting the installation process.",encoding="utf-16")
            assert SilverSilent.log_has_started(log)

    @classmethod
    def test_offline_share_still_refreshes_local_version(cls):
        with patch.object(SilverUpdates,"release",side_effect=OSError("Offline")),patch.object(SilverUpdates,"refresh_local_version") as refresh:
            with unittest.TestCase().assertRaises(OSError):SilverUpdates.check()
            refresh.assert_called_once_with()
