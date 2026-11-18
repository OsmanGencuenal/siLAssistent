import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
from source.stand_management.git import GitTool
from source.core.config import Config

class GitCloneTests(unittest.TestCase):
    @classmethod
    def test_target_adds_simulate_once(cls):
        assert GitTool.clone_target(Path("root")/"work")==Path("root")/"work"/"Simulate"/"SimFiles"
        assert GitTool.clone_target(Path("root")/"Simulate")==Path("root")/"Simulate"/"SimFiles"
        assert GitTool.clone_target(Path("root")/"SIMULATE")==Path("root")/"SIMULATE"/"SimFiles"

    @classmethod
    def test_clone_uses_submodules_and_creates_parent(cls):
        with tempfile.TemporaryDirectory() as temp, patch.object(Config,"state",return_value={"GitUserLicenceState":True}), patch.object(GitTool,"repository_check",return_value={"allowed":True}), patch.object(GitTool,"repository_url",return_value="https://mercedes-benz.ghe.com/devM286/SimFiles.git"), patch("shutil.which",return_value="git.exe"), patch("subprocess.run",return_value=Mock(returncode=0)) as run:
            target=GitTool.clone_target(temp)
            result=GitTool.clone_repository("user",target)
            assert target.parent.is_dir()
            assert "--recurse-submodules" in run.call_args.args[0]
            assert "switch" not in run.call_args.args[0]
            assert "--branch" not in run.call_args.args[0]
            assert "devAGK" not in run.call_args.args[0]
            assert result["path"]==str(target.resolve())

    @classmethod
    def test_failed_recursive_clone_is_not_reported_successful(cls):
        with tempfile.TemporaryDirectory() as temp, patch.object(Config,"state",return_value={"GitUserLicenceState":True}), patch.object(GitTool,"repository_check",return_value={"allowed":True}), patch.object(GitTool,"repository_url",return_value="https://mercedes-benz.ghe.com/devM286/SimFiles.git"), patch("shutil.which",return_value="git.exe"), patch("subprocess.run",return_value=Mock(returncode=1)):
            with unittest.TestCase().assertRaises(RuntimeError):
                GitTool.clone_repository("user",GitTool.clone_target(temp))


def test_clone_failures_distinguish_access_network_and_authentication():
    for error,expected in ((b"fatal: unable to access: 403", "access_denied"),(b"fatal: Could not resolve host", "unavailable"),(b"Authentication failed", "authentication_required")):
        assert GitTool.git_failure(Mock(stderr=error))["status"]==expected
