import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch,Mock
from source.stand_management.git_actions import GitActions
from source.stand_management.git_branches import GitBranches
from source.stand_management.git_installation import GitInstallation
from source.stand_management.setup_updates import SetupUpdates
from source.core.config import Config

class GitActionTests(unittest.TestCase):
    @classmethod
    def test_real_recursive_main_pull_and_revert(cls):
        git=shutil.which("git") or GitInstallation.executable()
        if not git:raise unittest.SkipTest("Git unavailable")
        with tempfile.TemporaryDirectory() as temp,patch.dict(os.environ,{"GIT_ALLOW_PROTOCOL":"file"}):
            base=Path(temp);remote=base/"module.git";seed=base/"seed";root=base/"SimFiles";origin=base/"root.git"
            def run(*args):return subprocess.run([git,*map(str,args)],check=True,capture_output=True).stdout.decode().strip()
            def identity(repo):
                run("-C",repo,"config","user.name","Test")
                run("-C",repo,"config","user.email","test@example.invalid")
            run("init","--bare","--initial-branch=main",remote)
            run("clone",remote,seed);identity(seed)
            (seed/"file.txt").write_text("initial")
            run("-C",seed,"add",".");run("-C",seed,"commit","-m","initial");run("-C",seed,"push","origin","main")
            run("init","--bare","--initial-branch=main",origin)
            run("clone",origin,root);identity(root)
            run("-C",root,"submodule","add",remote,"ECM")
            (root/"root.txt").write_text("original")
            run("-C",root,"add",".");run("-C",root,"commit","-m","root");run("-C",root,"push","origin","main")
            run("-C",root,"switch","-c","devAGK")
            run("-C",root/"ECM","switch","-c","devAGK")
            (seed/"file.txt").write_text("latest main")
            run("-C",seed,"add",".");run("-C",seed,"commit","-m","new main");run("-C",seed,"push","origin","main")
            (root/"ECM"/"file.txt").write_text("local changes")
            (root/"root.txt").write_text("local root changes")
            with patch.object(GitActions,"authorize",return_value=root):
                message=GitActions.pull(root,"main")
                assert run("-C",root,"branch","--show-current")=="main"
                assert run("-C",root/"ECM","branch","--show-current")=="main"
                assert (root/"ECM"/"file.txt").read_text()=="latest main"
                assert run("-C",root/"ECM","show","stash@{0}:file.txt")=="local changes"
                assert "ECM :: main" in message
                (root/"root.txt").write_text("discard")
                run("-C",root,"add","root.txt")
                (root/"ECM"/"file.txt").write_text("discard module")
                (root/"new.txt").write_text("keep")
                GitActions.revert(root)
                assert (root/"root.txt").read_text()=="original"
                assert (root/"ECM"/"file.txt").read_text()=="latest main"
                assert (root/"new.txt").read_text()=="keep"
                assert run("-C",root/"ECM","show","stash@{0}:file.txt")=="local changes"

    @classmethod
    def test_manual_pull_and_revert_do_not_advance_release_counter(cls):
        for operation in ("pull","revert"):
            with patch.object(GitActions,operation,return_value="done"),patch.object(Config,"set_state") as save,patch.object(SetupUpdates,"manifest",side_effect=AssertionError("No manifest for manual Git actions")):
                pipe=Mock();SetupUpdates.worker(pipe,operation,target="repo")
                save.assert_not_called()
                assert pipe.send.call_args.args[0]["error"] is None
