"""Five parallel repository history columns with asynchronous refresh."""
import queue
import threading
from pathlib import Path
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor,QBrush
from PySide6.QtWidgets import QWidget,QVBoxLayout,QHBoxLayout,QLabel,QScrollArea,QListWidget,QListWidgetItem,QPushButton,QAbstractItemView,QComboBox
from ..core.config import Config
from .git_history import GitHistory

class GitCommitView:
    @classmethod
    def attach(cls, window, workspace):
        layout=QVBoxLayout(workspace)
        layout.setContentsMargins(8,8,8,8)
        toolbar=QHBoxLayout()
        caption=QLabel("Lokale Commits · neue Remote-Commits in Pink · jeweils die letzten 100")
        caption.setWordWrap(True)
        toolbar.addWidget(caption,1)
        refresh=QPushButton("Aktualisieren")
        refresh.setToolTip("Lokalen Verlauf und Remote-Stand aktualisieren. Pink: noch nicht per Pull übernommen.")
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
            from ..ui.commit_delegate import CommitDelegate
            CommitDelegate.install(listing)
            listing.setStyleSheet("QListWidget {background:#1e1e2e; color:#e2e8f0; alternate-background-color:#243047; border:1px solid #334155; font:10pt 'Segoe UI';} QListWidget::item { padding:10px 6px; border-bottom:1px solid #334155;}  QListWidget::item:selected {background:#164e63; color:#e2e8f0;}")
            column.addWidget(title)
            column.addWidget(branch)
            if name!="SimFiles":
                row_widget=QWidget()
                row_widget.setMinimumHeight(44)
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
        window._commits={"queue":queue.Queue(),"request":0,"panels":panels,"branch_controls":branch_controls,"module_queue":queue.Queue(),"remote_loading":False,"refresh":refresh,"result":None,"error":None}
        timer=QTimer(window)
        timer.timeout.connect(lambda: cls.poll(window))
        timer.start(100)
        window._commits["timer"]=timer

    @classmethod
    def refresh_clicked(cls, window):
        from .git_installation import GitInstallation
        if GitInstallation.require(window,retry=lambda: cls.refresh_clicked(window)):
            cls.reload(window,refresh=True)

    @classmethod
    def reload(cls, window, refresh=False):
        if not hasattr(window,"_commits"):
            return
        state=window._commits
        if state.get("loading",False) and not refresh:
            cancelled=state.get("cancelled")
            if cancelled is not None:cancelled.set()
            state["loading"]=False
        if getattr(window,"_git",{}).get("busy",False) or state.get("loading",False):
            state["pending_reload"]=refresh
            if state.get("loading",False):state["request"]+=1
            return
        state.pop("pending_reload",None)
        state["request"]+=1
        request=state["request"]
        path=Config.state()["GitLocalRepoPath"]
        if not path:
            state["refresh"].setEnabled(True);state["refresh"].setText("Aktualisieren")
            return
        state["loading"]=True;state["loading_request"]=request
        state["cancelled"]=threading.Event()
        state["refresh"].setEnabled(False);state["refresh"].setText("Wird aktualisiert …" if refresh else "Wird geladen …")
        if refresh:
            from .git_incoming_updates import GitIncomingUpdates
            GitIncomingUpdates.check(window)
        worker=threading.Thread(target=cls.worker,args=(state["queue"],request,path,state["cancelled"]),daemon=True)
        state["worker"]=worker
        try:worker.start()
        except Exception as error:state["queue"].put((request,path,None,str(error),True))

    @classmethod
    def worker(cls, messages, request, path, cancelled=None):
        try:
            result=GitHistory.snapshot(path,cancelled=cancelled)
            messages.put((request,path,result,None,True))
        except Exception as error:
            messages.put((request,path,None,str(error),True))

    @classmethod
    def refresh_status(cls,window):
        state=window._commits
        button=state.get("refresh")
        if button is None:return
        loading=state.get("loading",False) or state.get("remote_loading",False)
        button.setEnabled(not loading)
        button.setText("Wird aktualisiert …" if loading else "Aktualisieren")

    @classmethod
    def resume_pending(cls,window):
        state=window._commits
        if "pending_reload" in state and not state.get("loading",False) and not getattr(window,"_git",{}).get("busy",False):
            refresh=state.pop("pending_reload")
            cls.reload(window,refresh=refresh)

    @classmethod
    def poll(cls, window):
        state=window._commits
        cls.poll_submodule(window)
        try:message=state["queue"].get_nowait()
        except queue.Empty:
            cls.resume_pending(window)
            return
        request,path,result,error=message[:4]
        final=message[4] if len(message)>4 else True
        if final and state.get("loading_request",request)==request:
            state["loading"]=False
            cls.refresh_status(window)
        if request==state["request"] and path==Config.state()["GitLocalRepoPath"]:
            if getattr(window,"_git",{}).get("busy",False):
                return
            previous=state.get("result") or {}
            if result is not None:
                # Keep completed local columns while other remote repositories are being fetched.
                existing=state.get("result") or {}
                state["result"]={**existing,**result}
            state["error"]=error
            cls.render(window)
            main=(result or {}).get("SimFiles",{})
            git=getattr(window,"_git",{})
            if main.get("branches") is not None and "branches" in git:
                combo=git["branches"]
                selected=combo.currentText()
                old_active=previous.get("SimFiles",{}).get("branch","")
                target=selected if selected and selected!=old_active else main.get("branch","")
                combo.blockSignals(True);combo.clear();combo.addItems(main["branches"])
                combo.setCurrentIndex(combo.findText(target));combo.blockSignals(False)
                git["activate_branch"].setEnabled(combo.count()>0 and not git.get("busy",False))
                import html
                git["branch_note"].setTextFormat(Qt.TextFormat.RichText)
                git["branch_note"].setText('Aktiver Branch: <span style="color:#22c55e; font-weight:700;">'+html.escape(main.get("branch",""))+"</span>")
        cls.resume_pending(window)

    @classmethod
    def render(cls,window):
        if not hasattr(window,"_commits") or getattr(window,"_git",{}).get("busy",False):return
        state=window._commits
        result=state.get("result");error=state.get("error")
        if result is None and error is None:return
        for name,(branch,listing) in state["panels"].items():
            listing.clear()
            info=(result or {}).get(name,{})
            if error or info.get("error"):
                branch.setText("Nicht verfügbar")
                listing.addItem(error or info["error"])
                continue
            notice="Branch lokal :: "+info.get("branch","")
            if info.get("remote_notice"):notice+="\n"+info["remote_notice"]
            if info.get("warning"):notice+="\n"+info["warning"]
            branch.setText(notice)
            if name in state["branch_controls"]:
                combo,button=state["branch_controls"][name]
                selected=combo.currentText();old_active=combo.property("gitActiveBranch")
                active=info.get("selection_branch",info.get("branch",""))
                target=selected if selected and old_active is not None and selected!=old_active else active
                combo.blockSignals(True);combo.clear()
                combo.addItems(info.get("branches",[]))
                combo.setCurrentIndex(combo.findText(target))
                combo.setProperty("gitActiveBranch",active)
                combo.blockSignals(False)
                if combo.currentIndex()<0 and combo.count():
                    combo.setCurrentIndex(0)
                button.setEnabled(combo.count()>0)
            local=info.get("commits",[])
            local_shas={commit["sha"] for commit in local}
            incoming=set(info.get("incoming",[]))-local_shas
            added=[];seen=set(local_shas)
            for commit in info.get("remote_commits",[]):
                if commit["sha"] in incoming and commit["sha"] not in seen:
                    added.append(commit);seen.add(commit["sha"])
            commits=added+local
            local_index=0
            for commit in commits:
                text=commit["short"]+" · "+commit["date"][:10]+"\n"+commit["author"]+"\n\n"+commit["subject"]+("\n\n"+commit["body"] if commit["body"] else "")
                item=QListWidgetItem(cls.wrap_long_tokens(text))
                item.setData(Qt.ItemDataRole.UserRole,commit["sha"])
                item.setBackground(QBrush(QColor("#99f6e4" if local_index%2==0 else "#243047")))
                item.setForeground(QBrush(QColor("#172554" if local_index%2==0 else "#e2e8f0")))
                if commit["sha"] in incoming:
                    item.setBackground(QBrush(QColor("#f9a8d4")))
                    item.setForeground(QBrush(QColor("#172554")))
                    item.setText(item.text()+"\n\nNOCH NICHT PER PULL ÜBERNOMMEN")
                else:local_index+=1
                item.setToolTip(commit["sha"]+"\n"+commit["date"]+"\n"+commit["author"]+"\n\n"+commit["subject"]+"\n"+commit["body"])
                listing.addItem(item)
            if not commits:
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
            from .git_incoming_updates import GitIncomingUpdates
            GitIncomingUpdates.check(window,restart=True)
            Dialogs.message(branch+" Branch ist aktiviert.",name+" :: "+result["active"]+"\n\nDer Branch von SimFiles und anderen eigenständigen Submodulen bleibt unverändert.",window)

    @classmethod
    def preview_updates(cls,parent=None):
        from .git_installation import GitInstallation
        from .git_window import GitWindow
        path=Config.state().get("GitLocalRepoPath","")
        if not path or not (Path(path)/".git").exists() or not GitInstallation.executable():return
        window=GitWindow.open(parent)
        cls.preview_when_idle(window,60)

    @classmethod
    def preview_when_idle(cls,window,remaining):
        import shiboken6
        if not shiboken6.isValid(window) or not window.isVisible():return
        worker=window._commits.get("worker")
        if window._git.get("busy") or (worker is not None and worker.is_alive()):
            if remaining:QTimer.singleShot(500,lambda:cls.preview_when_idle(window,remaining-1))
            return
        cls.reload(window,refresh=True)
