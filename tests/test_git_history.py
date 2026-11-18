import os
os.environ.setdefault("QT_QPA_PLATFORM","offscreen")
import queue
import unittest
from unittest.mock import Mock, patch
from PySide6.QtWidgets import QApplication,QMainWindow,QWidget
from source.stand_management.git_history import GitHistory
from source.stand_management.git_commit_view import GitCommitView
from source.core.config import Config

class GitHistoryTests(unittest.TestCase):
    @classmethod
    def test_parse_commit_fields_and_multiline_body(cls):
        text="\0".join(["a"*40,"abc123","2026-11-10T12:00:00+01:00","OGENCUE","Message <test>","Line one\nLine two",""])+"\n"+"\0".join(["b"*40,"b123","2026-11-09","Other","Older commit","",""])+"\n"
        commits=GitHistory.parse(text)
        assert len(commits)==2
        assert commits[0]["subject"]=="Message <test>"
        assert commits[0]["body"]=="Line one\nLine two"
        assert commits[1]["sha"]=="b"*40

    @classmethod
    def test_snapshot_continues_when_one_submodule_missing(cls):
        from pathlib import Path
        with patch("source.stand_management.git_history.GitBranches.validate",return_value=Path("repo")), patch("source.stand_management.git_history.GitBranches.refs",return_value={"branches":["main","devAGK"]}), patch.object(GitHistory,"commits",side_effect=[{"branch":"devAGK","commits":[]},ValueError("missing"),{"branch":"devAGK","commits":[]},{"branch":"main","commits":[]},{"branch":"main","commits":[]}]):
            data=GitHistory.snapshot("repo")
            assert data["SimFiles"]["branch"]=="devAGK"
            assert data["ECM"]["branch"]=="devAGK"
            assert "error" in data["ICE"]
            assert data["CPC"]["branch"]=="main"

    @classmethod
    def test_five_columns_and_stale_results_ignored(cls):
        app=QApplication.instance() or QApplication([])
        window=QMainWindow()
        workspace=QWidget()
        window.setCentralWidget(workspace)
        GitCommitView.attach(window,workspace)
        assert list(window._commits["panels"])==["SimFiles","ICE","ECM","CPC","DT"]
        data={name:{"branch":"main","commits":[{"sha":"abc","short":"abc","date":"2026-11-10","author":"Test","subject":"Message","body":"PT4_OTTO_27A\n\nSensor-Patch"}]} for name in GitHistory.REPOSITORIES}
        with patch.object(Config,"state",return_value={"GitLocalRepoPath":"repo"}):
            window._commits["queue"].put((0,"repo",data,None))
            GitCommitView.poll(window)
            label,listing=window._commits["panels"]["ECM"]
            assert "main" in label.text()
            assert listing.count()==1
            assert "Sensor-Patch" in listing.item(0).text()
            assert "PT4_OTTO_27A" in listing.item(0).text()
            assert listing.alternatingRowColors()
            assert set(window._commits["branch_controls"])=={"ICE","ECM","CPC","DT"}
            window._commits["request"]=1
            window._commits["queue"].put((0,"repo",None,"stale"))
            GitCommitView.poll(window)
            assert listing.count()==1
        window.close()

    @classmethod
    def test_individual_control_targets_only_selected_module(cls):
        from source.ui.git_licence import GitLicenceFlow
        from source.stand_management.git_window import GitWindow
        app=QApplication.instance() or QApplication([])
        with patch("source.stand_management.git_installation.GitInstallation.start_probe"), patch.object(GitWindow,"start"), patch.object(GitWindow,"load_branches"), patch.object(GitCommitView,"reload"), patch.object(GitLicenceFlow,"allow_git_action",return_value=True), patch("source.stand_management.git_installation.GitInstallation.require",return_value=True), patch("source.stand_management.git_commit_view.threading.Thread") as thread, patch.object(GitWindow,"show_clone_progress"), patch.object(Config,"state",return_value={"GitLocalRepoPath":"repo"}):
            window=GitWindow.open()
            combo,button=window._commits["branch_controls"]["ECM"]
            combo.addItem("devAGK")
            button.setEnabled(True)
            button.click()
            assert thread.call_args.kwargs["target"]==GitCommitView.submodule_worker
            assert thread.call_args.kwargs["args"][1:4]==("repo","ECM","devAGK")
            window._git["busy"]=False
            window.close()
