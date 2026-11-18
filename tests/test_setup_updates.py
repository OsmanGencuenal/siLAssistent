import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock,patch
from source.core.config import Config
from source.stand_management.setup_updates import SetupUpdates

class SetupUpdateTests(unittest.TestCase):
    @classmethod
    def test_counter_is_state_and_persisted(cls):
        with tempfile.TemporaryDirectory() as temp:
            ini=Path(temp)/"state.ini"
            assert Config.state(ini)["silSetupVersionCounter"]=="0"
            Config.set_state("silSetupVersionCounter","17",ini)
            assert Config.parser(ini).get("STATE","silSetupVersionCounter")=="17"

    @classmethod
    def test_only_newer_counter_offers_update(cls):
        for local,expected in (("0",True),("5",False),("6",False)):
            with patch.object(SetupUpdates,"manifest",return_value={"counter":5,"source":""}),patch.object(Config,"state",return_value={"silSetupVersionCounter":local}):
                assert SetupUpdates.check()["available"]==expected

    @classmethod
    def test_copy_replaces_stale_files_and_preserves_complete_backup(cls):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);source=root/"source"/"SimFiles";target=root/"local"/"SimFiles"
            source.mkdir(parents=True);target.mkdir(parents=True)
            (source/"new.txt").write_text("new")
            (target/"old.txt").write_text("local modifications")
            SetupUpdates.copy_update(source,target)
            assert (target/"new.txt").read_text()=="new"
            assert not (target/"old.txt").exists()
            backups=list(target.parent.glob("SimFiles-backup-*"))
            assert len(backups)==1 and (backups[0]/"old.txt").read_text()=="local modifications"

    @classmethod
    def test_copy_failure_never_replaces_old_setup(cls):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);source=root/"source"/"SimFiles";target=root/"local"/"SimFiles"
            source.mkdir(parents=True);target.mkdir(parents=True)
            (target/"old.txt").write_text("keep")
            with patch("source.stand_management.setup_updates.shutil.copytree",side_effect=OSError("offline")):
                with unittest.TestCase().assertRaises(OSError): SetupUpdates.copy_update(source,target)
            assert (target/"old.txt").read_text()=="keep"

    @classmethod
    def test_failed_update_never_advances_counter(cls):
        release={"counter":4,"source":"source"};pipe=Mock()
        with patch.object(SetupUpdates,"manifest",return_value=release),patch.object(SetupUpdates,"git_update",side_effect=RuntimeError("diverged")),patch.object(Config,"set_state") as save:
            SetupUpdates.worker(pipe,"git",release,"target")
            save.assert_not_called()
            assert pipe.send.call_args.args[0]["error"]=="diverged"

    @classmethod
    def test_success_advances_counter_only_after_verification(cls):
        release={"counter":4,"source":"source"};pipe=Mock()
        with patch.object(SetupUpdates,"manifest",return_value=release),patch.object(SetupUpdates,"copy_update",return_value="done"),patch.object(Config,"set_state") as save:
            SetupUpdates.worker(pipe,"drive",release,"target")
            save.assert_any_call("DriveSetupLocalPath","target")
            save.assert_any_call("silSetupVersionCounter","4")

    @classmethod
    def test_manifest_changed_mid_update_never_advances_counter(cls):
        release={"counter":4,"source":"source"};pipe=Mock()
        with patch.object(SetupUpdates,"manifest",side_effect=[release,{**release,"counter":5}]),patch.object(SetupUpdates,"copy_update",return_value="done"),patch.object(Config,"set_state") as save:
            SetupUpdates.worker(pipe,"drive",release,"target")
            save.assert_not_called()
            assert pipe.send.call_args.args[0]["error"]

    @classmethod
    def test_real_git_dirty_update_preserves_changes_in_stash(cls):
        import subprocess
        import shutil
        from source.stand_management.git_branches import GitBranches
        from source.stand_management.git import GitTool
        from source.stand_management.git_installation import GitInstallation
        git=shutil.which("git") or GitInstallation.executable()
        if not git: raise unittest.SkipTest("Git unavailable")
        with tempfile.TemporaryDirectory() as temp:
            base=Path(temp);remote=base/"remote.git";local=base/"SimFiles";other=base/"other"
            def run(*args):
                return subprocess.run([git,*map(str,args)],check=True,capture_output=True)
            run("init","--bare","--initial-branch=main",remote)
            run("clone",remote,local)
            for repo in (local,):
                run("-C",repo,"config","user.name","Test")
                run("-C",repo,"config","user.email","test@example.invalid")
            (local/"tracked.txt").write_text("original")
            run("-C",local,"add",".");run("-C",local,"commit","-m","initial");run("-C",local,"push","origin","main")
            run("clone",remote,other)
            run("-C",other,"config","user.name","Test");run("-C",other,"config","user.email","test@example.invalid")
            (other/"new.txt").write_text("remote update")
            run("-C",other,"add",".");run("-C",other,"commit","-m","update");run("-C",other,"push","origin","main")
            (local/"tracked.txt").write_text("local work")
            (local/"untracked.txt").write_text("keep untracked")
            with patch.object(GitBranches,"validate",return_value=local),patch.object(Config,"state",return_value={"GitUserLicenceState":True}),patch.object(GitTool,"repository_check",return_value={"allowed":True}),patch.object(GitTool,"windows_user",return_value={"username":"TEST"}):
                message=SetupUpdates.git_update(local)
            assert (local/"new.txt").read_text()=="remote update"
            assert (local/"tracked.txt").read_text()=="original"
            assert "Git-Stash" in message
            assert run("-C",local,"show","stash@{0}:tracked.txt").stdout.decode()=="local work"
            assert run("-C",local,"show","stash@{0}^3:untracked.txt").stdout.decode()=="keep untracked"
