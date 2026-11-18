import os
import queue
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
from source.core.config import Config
from source.silver.updates import SilverUpdates
from source.silver.probe import SilverProbe


class SilverProbeTests(unittest.TestCase):
    @classmethod
    def test_persists_local_version_before_failing_network_access(cls):
        order=[]
        connection=Mock()
        with patch.object(SilverUpdates,"refresh_local_version",side_effect=lambda path:order.append("local saved") or "Y-2026.03-1.260409"),patch.object(SilverUpdates,"check",side_effect=lambda path:order.append("network") or (_ for _ in ()).throw(OSError("offline"))):
            SilverProbe.run(connection,"remote.ini")
        assert order==["local saved","network"]
        assert connection.send.call_args_list[0].args[0][0]=="silver_local"
        assert connection.send.call_args_list[1].args[0][0]=="check_error"
        connection.close.assert_called_once_with()

    @classmethod
    def test_refresh_replaces_none_and_old_version_with_latest_detected_local_version(cls):
        with patch.object(SilverUpdates,"installed",return_value=[{"version":"W-2024.09.240830"},{"version":"Y-2026.03-1.260409"}]),patch.object(SilverUpdates,"installed_files",return_value=[]),patch.object(Config,"set_state") as save:
            assert SilverUpdates.refresh_local_version()=="Y-2026.03-1.260409"
            save.assert_called_once_with("InstalledSilverVersion","Y-2026.03-1.260409")

    @classmethod
    def test_actual_spawn_checks_local_machine_and_writes_temporary_ini(cls):
        with tempfile.TemporaryDirectory() as temp:
            ini=Path(temp)/"siLAssistent.ini"
            Config.ensure_state(ini)
            destination=queue.Queue()
            SilverProbe.collect(None,destination,state_ini_path=str(ini),timeout=30)
            messages=list(destination.queue)
            assert len(messages)==1 and messages[0][0]=="silver_local", messages
            result=messages[0][1]
            assert result["pid"]!=os.getpid()
            assert Config.state(ini)["InstalledSilverVersion"]==result["version"]
