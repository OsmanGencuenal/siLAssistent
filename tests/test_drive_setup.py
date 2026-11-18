import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock,patch
from source.stand_management.drive_setup import DriveSetup
from source.stand_management.setup_updates import SetupUpdates
from source.core.config import Config

class DriveSetupTests(unittest.TestCase):
    @classmethod
    def test_selected_parent_and_simulate_produce_same_target(cls):
        assert DriveSetup.target(Path("Work"))==Path("Work/Simulate/SimFiles")
        assert DriveSetup.target(Path("Work/Simulate"))==Path("Work/Simulate/SimFiles")

    @classmethod
    def test_initial_copy_runs_even_with_equal_counter_and_persists_only_after_success(cls):
        with tempfile.TemporaryDirectory() as temp:
            source=Path(temp)/"LW"/"SimFiles";source.mkdir(parents=True)
            (source/"new.txt").write_text("new")
            target=DriveSetup.target(Path(temp)/"local")
            release={"counter":0,"source":str(source)}
            with patch.object(SetupUpdates,"manifest",return_value=release),patch.object(Config,"set_state") as save:
                pipe=Mock();SetupUpdates.worker(pipe,"configure_drive",target=str(target))
                assert pipe.send.call_args.args[0]["error"] is None
                assert (target/"new.txt").read_text()=="new"
                save.assert_any_call("DriveSetupLocalPath",str(target))
                save.assert_any_call("silSetupVersionCounter","0")

    @classmethod
    def test_failed_new_setup_keeps_previous_saved_path(cls):
        with patch.object(SetupUpdates,"manifest",return_value={"counter":1,"source":"missing"}),patch.object(SetupUpdates,"copy_update",side_effect=OSError("offline")),patch.object(Config,"set_state") as save:
            pipe=Mock();SetupUpdates.worker(pipe,"configure_drive",target="new target")
            save.assert_not_called()
            assert pipe.send.call_args.args[0]["error"]

    @classmethod
    def test_cancelled_copy_keeps_old_target_and_cleans_staging(cls):
        import threading
        from source.stand_management.setup_updates import SetupCancelled
        with tempfile.TemporaryDirectory() as temp:
            source=Path(temp)/"LW"/"SimFiles";source.mkdir(parents=True)
            (source/"new.txt").write_text("new")
            target=Path(temp)/"local"/"SimFiles";target.mkdir(parents=True)
            (target/"old.txt").write_text("keep")
            cancelled=threading.Event()
            original=SetupUpdates.copy_file
            def interrupt(source,target,event):
                original(source,target,event)
                event.set()
                return target
            with patch.object(SetupUpdates,"copy_file",side_effect=interrupt):
                with unittest.TestCase().assertRaises(SetupCancelled):
                    SetupUpdates.copy_update(source,target,cancelled)
            assert (target/"old.txt").read_text()=="keep"
            assert not (target/"new.txt").exists()
            assert not list(target.parent.glob(".silassistent-stage-*"))

    @classmethod
    def test_cancelled_worker_never_persists_target_or_counter(cls):
        import threading
        cancelled=threading.Event();cancelled.set()
        with patch.object(SetupUpdates,"manifest",return_value={"counter":1,"source":"unused"}),patch.object(Config,"set_state") as save:
            pipe=Mock();SetupUpdates.worker(pipe,"configure_drive",target="unused",cancelled=cancelled)
            save.assert_not_called()
            assert pipe.send.call_args.args[0]["cancelled"]
