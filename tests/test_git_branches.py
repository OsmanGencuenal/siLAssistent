import unittest
from pathlib import Path
from unittest.mock import Mock, patch
from source.stand_management.git_branches import GitBranches
from source.stand_management.git import GitTool
from source.core.config import Config

class GitBranchTests(unittest.TestCase):
    @classmethod
    def test_local_and_origin_branches_deduplicated(cls):
        refs="refs/heads/main\nrefs/remotes/origin/main\nrefs/remotes/origin/topic/test\nrefs/remotes/origin/HEAD\n"
        with patch.object(GitBranches,"validate",return_value=Path("repo")), patch.object(GitBranches,"run",side_effect=[Mock(stdout=refs),Mock(stdout="main\n")]):
            result=GitBranches.list("repo",refresh=False)
            assert result["branches"]==["main","topic/test"]
            assert result["active"]=="main"


    @classmethod
    def test_dirty_tree_blocks_switch(cls):
        with patch.object(Config,"state",return_value={"GitUserLicenceState":True}), patch.object(Config,"set_state"), patch.object(GitTool,"repository_check",return_value={"allowed":True}), patch.object(GitBranches,"validate",return_value=Path("repo")), patch.object(GitBranches,"switch_plan",side_effect=RuntimeError("lokale Änderungen")), patch.object(GitBranches,"run") as run:
            with unittest.TestCase().assertRaisesRegex(RuntimeError,"lokale Änderungen"):
                GitBranches.activate("repo","main","user")
            assert not any("switch" in call.args[1] for call in run.call_args_list)

    @classmethod
    def test_switches_main_and_submodules_to_named_branches(cls):
        root=Path("repo")
        final={"active":"devAGK","branches":["devAGK"],"warning":""}
        with patch.object(Config,"state",return_value={"GitUserLicenceState":True}), patch.object(Config,"set_state"), patch.object(GitTool,"repository_check",return_value={"allowed":True}), patch.object(GitBranches,"validate",return_value=root), patch.object(GitBranches,"switch_plan",return_value=[(root,True),(root/"ECM",False),(root/"ECM"/"nested",True)]), patch.object(GitBranches,"list",return_value=final), patch.object(GitBranches,"run",return_value=Mock(stdout="devAGK\n")) as run:
            result=GitBranches.activate(root,"devAGK","user")
            commands=[call.args[1] for call in run.call_args_list]
            assert commands.count(["switch","--no-recurse-submodules","--no-overwrite-ignore","--no-guess","--","devAGK"])==2
            assert ["switch","--no-recurse-submodules","--no-overwrite-ignore","--track","-c","devAGK","origin/devAGK"] in commands
            assert not any("push" in command for command in commands)
            assert not any("update" in command or "--force" in command for command in commands)
            assert result["submodule_count"]==2

    @classmethod
    def test_missing_license_never_switches(cls):
        with patch.object(Config,"state",return_value={"GitUserLicenceState":False}), patch.object(GitBranches,"run") as run:
            with unittest.TestCase().assertRaises(RuntimeError):
                GitBranches.activate("repo","main","user")
            run.assert_not_called()

    @classmethod
    def test_partial_switch_is_not_reported_successful(cls):
        root=Path("repo")
        with patch.object(Config,"state",return_value={"GitUserLicenceState":True}), patch.object(Config,"set_state"), patch.object(GitTool,"repository_check",return_value={"allowed":True}), patch.object(GitBranches,"validate",return_value=root), patch.object(GitBranches,"switch_plan",return_value=[(root,True),(root/"ECM",True)]), patch.object(GitBranches,"run",side_effect=[Mock(stdout=""),Mock(stdout=""),RuntimeError("failure")]):
            with unittest.TestCase().assertRaisesRegex(RuntimeError,"nicht vollständig"):
                GitBranches.activate(root,"devAGK","user")

    @classmethod
    def test_missing_branch_in_submodule_is_skipped(cls):
        import tempfile
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder).resolve()
            (root/".git").mkdir()
            (root/"ECM"/".git").mkdir(parents=True)
            refs={"branches":["devAGK"],"local":{"devAGK"}}
            with patch.object(GitBranches,"refs",side_effect=[refs,{"branches":["main"],"local":{"main"}}]), patch.object(GitBranches,"gitlinks",side_effect=[["ECM"],[]]), patch.object(GitBranches,"run",side_effect=[Mock(stdout=str(root)),Mock(stdout=""),Mock(stdout=""),Mock(stdout=""),Mock(stdout=str(root/"ECM")),Mock(stdout="")]) as run:
                skipped=[]
                plan=GitBranches.switch_plan(root,"devAGK",skipped=skipped)
                assert plan==[(root,True)]
                assert len(skipped)==1 and "Zielbranch fehlt" in skipped[0]
                assert not any("switch" in call.args[1] for call in run.call_args_list)

    @classmethod
    def test_gitlinks_handles_paths_with_spaces(cls):
        tree="160000 commit abc\tmodule with spaces\0"+"100644 blob def\treadme.txt\0"
        with patch.object(GitBranches,"run",return_value=Mock(stdout=tree)):
            assert GitBranches.gitlinks("repo","refs/heads/devAGK")==["module with spaces"]

    @classmethod
    def test_real_local_git_switches_submodule_from_detached_to_branch(cls):
        import tempfile
        import subprocess
        import shutil
        if not shutil.which("git"):
            raise unittest.SkipTest("Git not available")
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as folder:
            base=Path(folder)
            child=base/"child"
            root=base/"SimFiles"
            cls.local_git(base,["init","-b","main",str(child)])
            cls.local_git(child,["commit","--allow-empty","-m","initial"])
            cls.local_git(child,["switch","-c","devAGK"])
            cls.local_git(child,["commit","--allow-empty","-m","development"])
            cls.local_git(child,["branch","feature/setup"])
            cls.local_git(child,["switch","main"])
            cls.local_git(base,["init","-b","main",str(root)])
            cls.local_git(root,["submodule","add",str(child),"ECM"])
            cpc=base/"cpc-source"
            cls.local_git(base,["init","-b","main",str(cpc)])
            cls.local_git(cpc,["commit","--allow-empty","-m","main only"])
            cls.local_git(root,["submodule","add",str(cpc),"CPC"])
            cls.local_git(root,["commit","-m","submodule"])
            cls.local_git(root,["branch","devAGK"])
            cls.local_git(root,["branch","feature/setup"])
            cls.local_git(root,["remote","add","origin",str(root)])
            cls.local_git(root/"ECM",["checkout","--detach"])
            with patch.object(Config,"state",return_value={"GitUserLicenceState":True}), patch.object(Config,"set_state"), patch.object(GitTool,"repository_check",return_value={"allowed":True}), patch.object(GitBranches,"validate",return_value=root.resolve()):
                for selected in ("devAGK","main","feature/setup","devAGK"):
                    result=GitBranches.activate(root,selected,"user")
                    assert result["active"]==selected
                    assert cls.local_git(root/"ECM",["branch","--show-current"]).strip()==selected
                    assert cls.local_git(root/"CPC",["branch","--show-current"]).strip()=="main"
                    assert bool(result["skipped_submodules"])==(selected!="main")
                    states={entry["name"]:entry["branch"] for entry in result["submodule_branches"]}
                    assert states=={"CPC":"main","ECM":selected}
            from source.stand_management.git_history import GitHistory
            history=GitHistory.commits(root/"ECM")
            assert history["branch"]=="devAGK"
            assert history["commits"][0]["subject"]=="development"
            assert len(history["commits"][0]["sha"])==40
            assert result["active"]=="devAGK"
            assert cls.local_git(root/"ECM",["branch","--show-current"]).strip()=="devAGK"
            assert cls.local_git(root/"ECM",["rev-parse","@{upstream}"]).strip()==cls.local_git(child,["rev-parse","devAGK"]).strip()
            assert result["submodule_count"]==1
            with patch.object(Config,"state",return_value={"GitUserLicenceState":True}), patch.object(Config,"set_state"), patch.object(GitTool,"repository_check",return_value={"allowed":True}), patch.object(GitBranches,"validate",return_value=root.resolve()):
                GitBranches.activate(root,"main","user",submodule="ECM")
                assert cls.local_git(root,["branch","--show-current"]).strip()=="devAGK"
                assert cls.local_git(root/"ECM",["branch","--show-current"]).strip()=="main"
                assert cls.local_git(root/"CPC",["branch","--show-current"]).strip()=="main"
                GitBranches.activate(root,"devAGK","user")
                assert cls.local_git(root/"ECM",["branch","--show-current"]).strip()=="devAGK"

    @classmethod
    def local_git(cls, folder, args):
        import subprocess
        result=subprocess.run(["git","-c","user.name=Test","-c","user.email=test@example.invalid","-c","protocol.file.allow=always","-C",str(folder),*args],capture_output=True,text=True,encoding="utf-8",errors="replace",timeout=30)
        assert result.returncode==0,result.stderr
        return result.stdout


    @classmethod
    def test_remote_only_branch_is_planned_as_local_tracking_checkout(cls):
        import tempfile
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder).resolve()
            (path/".git").mkdir()
            with patch.object(GitBranches,"refs",return_value={"branches":["devAGK"],"local":set()}), patch.object(GitBranches,"gitlinks",return_value=[]), patch.object(GitBranches,"run",side_effect=[Mock(stdout=str(path)),Mock(stdout=""),Mock(stdout=""),Mock(stdout="")]) as run:
                assert GitBranches.switch_plan(path,"devAGK")==[(path,False)]
                assert not any("push" in call.args[1] for call in run.call_args_list)

    @classmethod
    def test_summary_marks_only_target_branches_yellow(cls):
        from source.ui.dialogs import Dialogs
        entries=[{"name":"CPC","branch":"main"},{"name":"ECM","branch":"devAGK"}]
        dev=Dialogs.branch_summary_html("Branches",entries,"devAGK")
        assert '<span style="color:#facc15; font-weight:700;">• ECM :: devAGK</span>' in dev
        assert '<span style="color:#facc15; font-weight:700;">• CPC :: main</span>' not in dev
        main=Dialogs.branch_summary_html("Branches",entries,"main")
        assert '<span style="color:#facc15; font-weight:700;">• CPC :: main</span>' in main
        assert '<span style="color:#facc15; font-weight:700;">• ECM :: devAGK</span>' not in main
