"""LW-Setup einrichten und den gespeicherten lokalen Zielpfad anzeigen."""
from pathlib import Path
from ..core.config import Config


class DriveSetup:
    @classmethod
    def target(cls,selected):
        folder=Path(selected)
        simulate=folder if folder.name.casefold()=="simulate" else folder/"Simulate"
        return simulate/"SimFiles"

    @classmethod
    def open(cls,parent):
        from .setup_updates import SetupUpdates
        from ..ui.dialogs import Dialogs
        from ..ui.button_gradients import ButtonGradients
        from PySide6.QtWidgets import QPushButton,QApplication,QDialog
        from PySide6.QtCore import QTimer,Qt
        current=Config.state()["DriveSetupLocalPath"]
        dialog,footer,body=Dialogs.card("Setup vom Laufwerk", "Lokales Setup ::\n"+(current or "Noch kein lokales Setup eingerichtet."),parent)
        body.setStyleSheet("color:#f59e0b; font:12pt 'Segoe UI';")
        new=QPushButton("Neu Einrichten")
        ButtonGradients.apply(new,"#99f6e4",padding="10px 16px",font="700 14pt 'Segoe UI'")
        existing=QPushButton("Bestehenden SimFiles-Ordner definieren")
        ButtonGradients.apply(existing,"#172554",padding="10px 16px",font="700 14pt 'Segoe UI'")
        existing.clicked.connect(lambda:cls.choose_existing(dialog))
        close=QPushButton("Schließen")
        ButtonGradients.apply(close,"#fca5a5",padding="10px 16px",font="700 14pt 'Segoe UI'")
        for button in (new,existing,close):button.setMinimumHeight(44)
        new.clicked.connect(lambda:cls.choose(dialog))
        close.clicked.connect(dialog.reject)
        footer.addWidget(new);footer.addWidget(existing);footer.addWidget(close)
        available=QApplication.primaryScreen().availableGeometry()
        width=min(560,available.width()-24)
        body_height=max(0,body.heightForWidth(max(180,width-90)))
        height=min(max(500,body_height+380),available.height()-48)
        dialog.resize(width,height)
        dialog._drive_controls=(body,new,existing)
        dialog._drive_was_busy=None
        dialog.keyPressEvent=lambda event:event.ignore() if event.key()==Qt.Key.Key_Escape else QDialog.keyPressEvent(dialog,event)
        timer=QTimer(dialog)
        timer.timeout.connect(lambda:cls.refresh(dialog))
        timer.start(150)
        cls.refresh(dialog)
        QTimer.singleShot(0,lambda:SetupUpdates.watch(dialog,"drive"))
        dialog.exec()
        timer.stop()

    @classmethod
    def refresh(cls,dialog):
        from .setup_updates import SetupUpdates
        busy=bool(getattr(SetupUpdates,"_active",False))
        if dialog._drive_was_busy==busy:return
        dialog._drive_was_busy=busy
        body,new,existing=dialog._drive_controls
        new.setEnabled(not busy);existing.setEnabled(not busy)
        if not busy:
            current=Config.state()["DriveSetupLocalPath"]
            body.setText("Lokales Setup ::\n"+(current or "Noch kein lokales Setup eingerichtet."))
    
    @classmethod
    def choose(cls,parent):
        from .setup_updates import SetupUpdates
        from PySide6.QtWidgets import QFileDialog
        if getattr(SetupUpdates,"_active",False):return
        selected=QFileDialog.getExistingDirectory(parent,"Zielordner wählen – Setup wird unter Simulate/SimFiles eingerichtet")
        if not selected:return
        target=str(cls.target(selected))
        SetupUpdates._active=True
        SetupUpdates.spawn(parent,"drive","configure_drive",target=target)

    @classmethod
    def choose_existing(cls,parent):
        from .setup_updates import SetupUpdates
        from ..ui.dialogs import Dialogs
        from PySide6.QtWidgets import QDialog
        if getattr(SetupUpdates,"_active",False):return
        picker=cls.existing_picker(parent,Config.state()["DriveSetupLocalPath"])
        try:
            if picker.exec()!=QDialog.DialogCode.Accepted:return
            selected=next(iter(picker.selectedFiles()),"")
        finally:picker.deleteLater()
        if not selected:return
        try:
            cls.use_existing(selected)
        except ValueError as error:
            Dialogs.message("SimFiles-Ordner nicht übernommen",str(error),parent)
            return
        parent._drive_was_busy=None
        cls.refresh(parent)

    @classmethod
    def use_existing(cls,selected):
        folder=Path(selected).resolve()
        if str(folder).startswith("\\\\") or not folder.is_dir() or folder.name.casefold()!="simfiles":
            raise ValueError("Bitte einen vorhandenen lokalen SimFiles-Ordner auswählen.")
        if not any(folder.glob("*.sil")):
            raise ValueError("Im gewählten SimFiles-Ordner ist keine Setup-Datei (*.sil) vorhanden.")
        Config.set_state("DriveSetupLocalPath",str(folder))
        from ..setup_operation.setup_control_window import SetupControlWindow
        SetupControlWindow.manual_path_changed(str(folder))
        return folder

    @classmethod
    def existing_picker(cls,parent,current=""):
        from PySide6.QtWidgets import QApplication,QFileDialog,QToolButton,QTreeView,QHeaderView,QSplitter
        from PySide6.QtCore import QDir,QSortFilterProxyModel,Qt
        dialog=QFileDialog(parent,"Bestehenden lokalen SimFiles-Ordner wählen",current)
        flags=dialog.windowFlags()|Qt.WindowType.WindowMinMaxButtonsHint
        flags&=~(Qt.WindowType.WindowContextHelpButtonHint|Qt.WindowType.MSWindowsFixedSizeDialogHint)
        dialog.setWindowFlags(flags)
        dialog.setSizeGripEnabled(True)
        dialog.setOption(QFileDialog.Option.DontUseNativeDialog,True)
        dialog.setOption(QFileDialog.Option.ShowDirsOnly,True)
        dialog.setFileMode(QFileDialog.FileMode.Directory)
        dialog.setLabelText(QFileDialog.DialogLabel.Accept,"Ordner wählen")
        dialog.setFilter(QDir.Filter.AllDirs|QDir.Filter.NoDotAndDotDot)
        proxy=QSortFilterProxyModel(dialog)
        proxy.filterAcceptsRow=lambda row,parent:cls.folder_visible(proxy,row,parent)
        dialog.setProxyModel(proxy)
        dialog._simfiles_proxy=proxy
        dialog.setViewMode(QFileDialog.ViewMode.Detail)
        for name in ("backButton","forwardButton","toParentButton","newFolderButton","listModeButton","detailModeButton"):
            button=dialog.findChild(QToolButton,name)
            if button is not None:button.hide()
        dialog.setLabelText(QFileDialog.DialogLabel.LookIn,"Ordner:")
        dialog.setLabelText(QFileDialog.DialogLabel.FileName,"Gewählter Ordner:")
        dialog.setLabelText(QFileDialog.DialogLabel.FileType,"Ordnerfilter:")
        dialog.setLabelText(QFileDialog.DialogLabel.Reject,"Abbrechen")
        available=(parent.screen() if parent else QApplication.primaryScreen()).availableGeometry()
        width=min(1180,max(320,available.width()-48));height=min(760,max(300,available.height()-72))
        dialog.setMinimumSize(min(720,width),min(480,height));dialog.resize(width,height)
        splitter=dialog.findChild(QSplitter,"splitter")
        if splitter is not None:splitter.setSizes([min(220,width//4),max(1,width-220)])
        tree=dialog.findChild(QTreeView,"treeView")
        if tree is not None:
            header=tree.header();header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
            header.setSectionResizeMode(0,QHeaderView.ResizeMode.Stretch)
        return dialog

    @classmethod
    def folder_visible(cls,proxy,row,parent):
        model=proxy.sourceModel()
        return not parent.isValid() or Path(model.filePath(parent)).name.casefold()!="simfiles"
