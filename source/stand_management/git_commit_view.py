"""Five parallel repository history columns with asynchronous refresh."""
import queue
import threading
from pathlib import Path
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QWidget,QVBoxLayout,QHBoxLayout,QLabel,QScrollArea,QListWidget,QListWidgetItem,QPushButton,QAbstractItemView,QComboBox
from ..core.config import Config
from .git_history import GitHistory

class GitCommitView:
    @classmethod
    def attach(cls, window, workspace):
        layout=QVBoxLayout(workspace)
        layout.setContentsMargins(8,8,8,8)
        toolbar=QHBoxLayout()
        caption=QLabel("Commits der aktiven Branches · jeweils die letzten 100")
        caption.setWordWrap(True)
        toolbar.addWidget(caption,1)
        refresh=QPushButton("Aktualisieren")
        refresh.clicked.connect(lambda: cls.refresh_clicked(window))
        toolbar.addWidget(refresh)
        layout.addLayout(toolbar)
        scroll=QScrollArea()
        scroll.setWidgetResizable(True)
        content=QWidget()
        content.setMinimumWidth(1000)
        columns=QHBoxLayout(content)
        columns.setContentsMargins(0,0,0,0)
        columns.setSpacing(8)
        panels={}
        branch_controls={}
        for name in GitHistory.REPOSITORIES:
            panel=QWidget()
            column=QVBoxLayout(panel)
            column.setContentsMargins(0,0,0,0)
            title=QLabel(name)
            title.setStyleSheet("color:#facc15; font:700 14pt 'Segoe UI';")
            branch=QLabel("Kein Repo geladen")
            branch.setWordWrap(True)
            branch.setStyleSheet("color:#40e0d0; font:11pt 'Segoe UI';")
            listing=QListWidget()
            listing.setObjectName("gitCommits"+name)
            listing.setWordWrap(True)
            listing.setTextElideMode(Qt.TextElideMode.ElideNone)
            listing.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            listing.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
            listing.setAlternatingRowColors(True)
            listing.setStyleSheet("QListWidget {background:#1e1e2e; color:#e2e8f0; alternate-background-color:#243047; border:1px solid #334155; font:10pt 'Segoe UI';} QListWidget::item {background:#bbf7d0; color:#172554; padding:10px 6px; border-bottom:1px solid #334155;} QListWidget::item:alternate {background:#243047; color:#e2e8f0;} QListWidget::item:selected {background:#164e63; color:#e2e8f0;}")
            column.addWidget(title)
            column.addWidget(branch)
            if name!="SimFiles":
                row_widget=QWidget()
                row_widget.setFixedHeight(44)
                row=QHBoxLayout(row_widget)
                row.setContentsMargins(0,0,0,0)
                combo=QComboBox()
                combo.setObjectName("gitModuleBranch"+name)
                combo.setMinimumContentsLength(8)
                combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
                button=QPushButton("Aktivieren")
                button.setObjectName("gitModuleActivate"+name)
                button.setStyleSheet("background:#99f6e4; color:#172554; font-weight:700;")
                button.setEnabled(False)
                button.clicked.connect(lambda checked=False,module=name: cls.activate_submodule(window,module))
                row.addWidget(combo,1)
                row.addWidget(button)
                column.addWidget(row_widget)
                branch_controls[name]=(combo,button)
            else:
                spacer=QWidget()
                spacer.setFixedHeight(44)
                column.addWidget(spacer)
            column.addWidget(listing,1)
            columns.addWidget(panel,1)
            panels[name]=(branch,listing)
        scroll.setWidget(content)
        layout.addWidget(scroll,1)
        window._commits={"queue":queue.Queue(),"request":0,"panels":panels,"branch_controls":branch_controls,"module_queue":queue.Queue()}
        timer=QTimer(window)
        timer.timeout.connect(lambda: cls.poll(window))
        timer.start(100)
        window._commits["timer"]=timer

    @classmethod
    def refresh_clicked(cls, window):
        from .git_installation import GitInstallation
        if GitInstallation.require(window,retry=lambda: cls.refresh_clicked(window)):
            cls.reload(window)

    @classmethod
    def reload(cls, window):
        if not hasattr(window,"_commits"):
            return
        if getattr(window,"_git",{}).get("busy",False):
            return
        state=window._commits
        state["request"]+=1
        request=state["request"]
        path=Config.state()["GitLocalRepoPath"]
        for branch,listing in state["panels"].values():
            branch.setText("Commits werden geladen ..." if path else "Bitte lokalen Repo-Pfad wählen")
            listing.clear()
        for combo,button in state["branch_controls"].values():
            combo.clear()
            button.setEnabled(False)
        if not path:
            return
        worker=threading.Thread(target=cls.worker,args=(state["queue"],request,path),daemon=True)
        state["worker"]=worker
        worker.start()

    @classmethod
    def worker(cls, messages, request, path):
        try:
            messages.put((request,path,GitHistory.snapshot(path),None))
        except Exception as error:
            messages.put((request,path,None,str(error)))

    @classmethod
    def poll(cls, window):
        state=window._commits
        cls.poll_submodule(window)
        try:
            request,path,result,error=state["queue"].get_nowait()
        except queue.Empty:
            return
        if request!=state["request"] or path!=Config.state()["GitLocalRepoPath"]:
            return
        for name,(branch,listing) in state["panels"].items():
            listing.clear()
            info=(result or {}).get(name,{})
            if error or info.get("error"):
                branch.setText("Nicht verfügbar")
                listing.addItem(error or info["error"])
                continue
            branch.setText("Branch :: "+info.get("branch",""))
            if name in state["branch_controls"]:
                combo,button=state["branch_controls"][name]
                combo.clear()
                combo.addItems(info.get("branches",[]))
                combo.setCurrentIndex(combo.findText(info.get("branch","")))
                if combo.currentIndex()<0 and combo.count():
                    combo.setCurrentIndex(0)
                button.setEnabled(combo.count()>0)
            for commit in info.get("commits",[]):
                text=commit["short"]+" · "+commit["date"][:10]+"\n"+commit["author"]+"\n\n"+commit["subject"]+("\n\n"+commit["body"] if commit["body"] else "")
                item=QListWidgetItem(cls.wrap_long_tokens(text))
                item.setData(Qt.ItemDataRole.UserRole,commit["sha"])
                item.setToolTip(commit["sha"]+"\n"+commit["date"]+"\n"+commit["author"]+"\n\n"+commit["subject"]+"\n"+commit["body"])
                listing.addItem(item)
            if not info.get("commits"):
                listing.addItem("Keine Commits vorhanden.")

    @classmethod
    def wrap_long_tokens(cls, text):
        import re
        # Add invisible wrap opportunities; raw text remains intact in the tooltip.
        return re.sub(r"\S{24,}",lambda match:"\u200b".join(match.group(0)[i:i+20] for i in range(0,len(match.group(0)),20)),text)

    @classmethod
    def activate_submodule(cls, window, name):
        from .git_installation import GitInstallation
        if not GitInstallation.require(window,retry=lambda: cls.activate_submodule(window,name)):
            return
        from ..ui.git_licence import GitLicenceFlow
        from .git_window import GitWindow
        if window._git["busy"]:
            return
        combo,button=window._commits["branch_controls"][name]
        branch=combo.currentText()
        if not branch or not GitLicenceFlow.allow_git_action(window):
            return
        path=Config.state()["GitLocalRepoPath"]
        state=window._commits
        state["request"]+=1
        window._git["request"]+=1
        window._git["branch_request"]+=1
        window._git["busy"]=True
        GitWindow.show_clone_progress(window,branch+" wird in "+name+" aktiviert","module_progress")
        worker=threading.Thread(target=cls.submodule_worker,args=(state["module_queue"],path,name,branch,window._git["user"].text()),daemon=True)
        state["module_worker"]=worker
        worker.start()

    @classmethod
    def submodule_worker(cls, messages, path, name, branch, user_id):
        from .git_branches import GitBranches
        try:
            result=GitBranches.activate(path,branch,user_id,submodule=name)
            messages.put((name,branch,result,None))
        except Exception as error:
            messages.put((name,branch,None,str(error)))

    @classmethod
    def poll_submodule(cls, window):
        from .git_window import GitWindow
        from ..ui.dialogs import Dialogs
        try:
            name,branch,result,error=window._commits["module_queue"].get_nowait()
        except queue.Empty:
            return
        GitWindow.finish_clone_progress(window,"module_progress")
        window._git["busy"]=False
        cls.reload(window)
        if error:
            Dialogs.message("Submodul-Branch konnte nicht vollständig aktiviert werden",error,window)
        else:
            Dialogs.message(branch+" Branch ist aktiviert.",name+" :: "+result["active"]+"\n\nDer Branch von SimFiles und anderen eigenständigen Submodulen bleibt unverändert.",window)
