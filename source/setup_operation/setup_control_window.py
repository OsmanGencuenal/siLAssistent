"""Setup-Ansteuerung: source dropdown and exclusive, vertically listed SIL files."""
import queue
import threading
from pathlib import Path
from PySide6.QtCore import Qt,QTimer,QEventLoop
from PySide6.QtWidgets import (QMainWindow,QWidget,QVBoxLayout,QLabel,QComboBox,
                              QScrollArea,QRadioButton,QButtonGroup,QToolBar,QPushButton,QSplitter,QFrame,QHBoxLayout,QCheckBox,QLineEdit,QPlainTextEdit,QToolButton)
from .setup_control import SetupControl
from ..ui.dialogs import Dialogs
from ..ui.button_gradients import ButtonGradients
from ..ui.launcher import Launcher

class SetupControlWindow:
    _window=None
    _connection_lock=threading.Lock()

    @classmethod
    def open(cls,parent=None):
        if cls._window is not None and cls._window.isVisible():
            Dialogs.foreground(cls._window)
            cls._window.showMaximized()
            cls.reload(cls._window)
            return cls._window
        window=QMainWindow();cls._window=window
        window.setProperty("siLAssistentTool",True)
        window.setProperty("buttonFramePolicy","navy")
        window.setWindowTitle("siLAssistent - Setup-Ansteuerung")
        window.setWindowIcon(Launcher.icon())
        window.setStyleSheet(Dialogs.style()+"""
            QComboBox {background:#0f172a; color:#e2e8f0; padding:8px; border:1px solid #475569; border-radius:4px; font:12pt 'Segoe UI';}
            QComboBox QAbstractItemView {background:#1e1e2e; color:#e2e8f0; selection-background-color:#bbf7d0; selection-color:#172554;}
            QComboBox QAbstractItemView::item:hover, QComboBox QAbstractItemView::item:selected {background:#bbf7d0; color:#172554;}
            QComboBox:disabled, QLineEdit:disabled {color:#64748b; background:#2a2a3e; border:1px solid #475569;}
            QLabel#manualInputHeading {color:#facc15; font:700 13pt 'Segoe UI';}
            QLabel#manualInputHeading:disabled {color:#64748b;}
            QRadioButton {color:#e2e8f0; font:12pt 'Segoe UI'; padding:8px;}
            QRadioButton::indicator {width:18px; height:18px; border:2px solid #94a3b8; border-radius:10px; background:#1e1e2e;}
            QRadioButton::indicator:checked {background:#4ade80; border-color:#86efac;}
            QToolBar {background:#2a2a3e; spacing:8px; padding:5px;}
        """)
        toolbar=QToolBar("Setup-Ansteuerung",window);toolbar.setMovable(False);window.addToolBar(toolbar)
        toolbar.addWidget(QLabel("Setup-Ansteuerung"))
        from PySide6.QtWidgets import QSizePolicy
        spacer=QWidget();spacer.setSizePolicy(QSizePolicy.Policy.Expanding,QSizePolicy.Policy.Preferred);toolbar.addWidget(spacer)
        launcher=QPushButton("Launcher");ButtonGradients.launcher(launcher)
        launcher.clicked.connect(cls.show_launcher);toolbar.addWidget(launcher)
        central=QSplitter(Qt.Orientation.Horizontal)
        central.setChildrenCollapsible(False)
        sidebar=QWidget();sidebar.setObjectName("setupSidebar")
        sidebar.setMinimumWidth(260)
        layout=QVBoxLayout(sidebar);layout.setContentsMargins(14,18,14,14);layout.setSpacing(12)
        heading=QLabel("Setup-Auswahl ::");heading.setStyleSheet("color:#facc15; font:700 14pt 'Segoe UI';");layout.addWidget(heading)
        sources=QComboBox();sources.setObjectName("setupSource");sources.addItems(list(SetupControl.SOURCES))
        sources.setMinimumContentsLength(12);sources.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        layout.addWidget(sources)
        path=QLabel();path.setWordWrap(True);path.setStyleSheet("color:#f59e0b; font:11pt 'Segoe UI';");layout.addWidget(path)
        path.setMinimumWidth(0);path.setSizePolicy(QSizePolicy.Policy.Ignored,QSizePolicy.Policy.Preferred)
        connection_row=QHBoxLayout()
        connect=QPushButton("Setup :: Verbinden/Starten");connect.setObjectName("setupConnect")
        ButtonGradients.apply(connect,"#99f6e4",padding="8px")
        connection=QLabel("Nicht verbunden");connection.setObjectName("setupConnection")
        connection.setAlignment(Qt.AlignmentFlag.AlignCenter);connection.setWordWrap(True)
        connection_row.addWidget(connect,1);connection_row.addWidget(connection,1);layout.addLayout(connection_row)
        detach=QPushButton("Silver :: API-Verbindung Trennen");detach.setObjectName("setupDisconnect")
        ButtonGradients.apply(detach,"#fca5a5")
        layout.addWidget(detach)
        reload_setup=QPushButton("Setup-Reload");reload_setup.setObjectName("setupReload")
        ButtonGradients.apply(reload_setup,"#172554")
        layout.addWidget(reload_setup)
        close_setup=QPushButton("Setup-Schließen");close_setup.setObjectName("setupClose")
        ButtonGradients.apply(close_setup,"#dc2626",padding="8px 4px")
        exit_now=QCheckBox("SOFORT SCHLIESSEN");exit_now.setObjectName("setupExitNow")
        ButtonGradients.apply(exit_now,"#2a2a3e",padding="8px",checked="#fed7aa")
        from ..ui.checkboxes import Checkboxes
        Checkboxes.full_click(exit_now)
        close_row=QHBoxLayout();close_row.addWidget(close_setup,1);close_row.addWidget(exit_now,1);layout.addLayout(close_row)
        auto=QCheckBox("Automatisch Verbinden");auto.setObjectName("setupAutoConnect")
        ButtonGradients.apply(auto,"#fed7aa",padding="8px 12px",checked="#99f6e4")
        from ..ui.checkboxes import Checkboxes
        Checkboxes.full_click(auto)
        layout.addWidget(auto)
        headless=QCheckBox("Ohne GUI");headless.setObjectName("setupHeadless")
        ButtonGradients.apply(headless,"#fed7aa",padding="12px",font="700 14pt 'Segoe UI'",checked="#99f6e4")
        headless.setToolTip("Neue Silver-Instanzen ohne sichtbare Silver-Oberfläche starten. Verbinden/Starten übernimmt diesen Modus. Für einen Moduswechsel wird das laufende Setup zuerst gespeichert und neu gestartet.")
        Checkboxes.full_click(headless);layout.addWidget(headless)
        available_setups=QLabel("Verfügbare Setups ::")
        available_setups.setObjectName("availableSetupsHeading")
        available_setups.setWordWrap(True)
        available_setups.setStyleSheet("color:#f59e0b; font:700 16pt 'Segoe UI';")
        layout.addWidget(available_setups)
        status=QLabel();status.setWordWrap(True);status.setMinimumWidth(0)
        status.setSizePolicy(QSizePolicy.Policy.Ignored,QSizePolicy.Policy.Preferred);layout.addWidget(status)
        scroll=QScrollArea();scroll.setWidgetResizable(True)
        content=QWidget();items=QVBoxLayout(content);items.setAlignment(Qt.AlignmentFlag.AlignTop)
        scroll.setWidget(content);layout.addWidget(scroll,1)
        workspace=QFrame();workspace.setObjectName("setupWorkspace")
        workspace.setStyleSheet("QFrame#setupWorkspace {border:1px solid #334155;}")
        workspace_layout=QHBoxLayout(workspace)
        workspace_layout.setSpacing(8)
        controls=QWidget();controls_layout=QVBoxLayout(controls)
        controls_layout.setContentsMargins(12,12,12,12);controls_layout.setSpacing(10)
        control_heading=QLabel("Setup-Ansteuerung ::")
        control_heading.setStyleSheet("color:#facc15; font:700 16pt 'Segoe UI';")
        controls_layout.addWidget(control_heading)
        mode_label=QLabel("Betriebsmode ::");mode_label.setStyleSheet("color:#facc15; font:700 14pt 'Segoe UI';")

        mode=QComboBox();mode.addItems(["IMO","Test-Bench","Zyklus","Kennfeld-Rasterung"]);mode.setCurrentText("IMO")
        mode_row=QHBoxLayout();mode_row.addWidget(mode,1)
        mode_start=QPushButton("Start")
        start_column=QVBoxLayout();start_column.addWidget(mode_start)
        pause=QPushButton("Pause");pause.setObjectName("cyclePause")
        ButtonGradients.apply(pause,"#f59e0b")
        start_column.addWidget(pause);mode_row.addLayout(start_column)
        cycle=QComboBox();cycle.setObjectName("driveCycle");cycle.addItems(["NEDC","FTP75","US06","WLTP"])
        mode_row.addWidget(cycle,1);cycle.setVisible(False)
        mode.currentTextChanged.connect(lambda value:cycle.setVisible(value=="Zyklus"))
        ignition=QPushButton("Klemme 15");engine=QPushButton("Motor-Start");start_stop=QPushButton("Start-Stop")
        for button in (mode_start,ignition,engine,start_stop):
            ButtonGradients.apply(button,"#bbf7d0")
        ignition_state=QLabel();engine_state=QLabel();start_stop_state=QLabel()
        for button,label in ((ignition,ignition_state),(engine,engine_state),(start_stop,start_stop_state)):
            row=QHBoxLayout();row.addWidget(button,1);row.addWidget(label,1)
            label.setAlignment(Qt.AlignmentFlag.AlignCenter);label.setWordWrap(True)
            label.setSizePolicy(QSizePolicy.Policy.Expanding,QSizePolicy.Policy.Fixed)
            row_height=max(36,button.sizeHint().height())
            button.setMinimumHeight(row_height);label.setMinimumHeight(row_height)
            controls_layout.addLayout(row)
        clear_errors=QPushButton("Fehler Löschen");clear_errors.setObjectName("clearErrors")
        ButtonGradients.apply(clear_errors,"#fecaca")
        clear_row=QHBoxLayout();clear_row.addWidget(clear_errors,1);clear_row.addStretch(1)
        controls_layout.addLayout(clear_row)
        simulation=QPushButton("Simulation-Starten");simulation.setObjectName("simulationToggle")
        simulation.setMinimumHeight(48)
        controls_layout.addWidget(simulation)
        init_values=QPushButton("INIT-Werte");init_values.setObjectName("initValues")
        ButtonGradients.apply(init_values,"#f59e0b",padding="10px 16px")
        init_row=QHBoxLayout();init_row.addWidget(init_values);init_row.addStretch(1);controls_layout.addLayout(init_row)
        controls_layout.addSpacing(22)
        controls_layout.addWidget(mode_label);controls_layout.addLayout(mode_row)
        operation_status=QLabel();operation_status.setWordWrap(True);controls_layout.addWidget(operation_status)
        manual_area=QWidget();manual_layout=QVBoxLayout(manual_area);manual_layout.setContentsMargins(0,0,0,0)
        manual_layout.addSpacing(12)
        from ..ui.field_colors import FieldColors
        inputs={};input_labels={};input_cards={}
        pedal_row=QHBoxLayout()
        for key,title in (("rpm","Drehzahl"),("accelerator","Gas-Pedal"),("brake","Brems-Pedal")):
            card=FieldColors.card(key);input_cards[key]=card;box=QVBoxLayout(card)
            label=QLabel(title);label.setObjectName("manualInputHeading");label.setStyleSheet(FieldColors.heading(key));input_labels[key]=label
            edit=QLineEdit();edit.setObjectName("manual_"+key);edit.setPlaceholderText("Wert mit Enter setzen");edit.setStyleSheet(FieldColors.field(key))
            edit.setToolTip("Drehzahl in rpm" if key=="rpm" else "Pedalstellung: 0 bis 100 (unverändert an Silver)")
            if key!="rpm":
                from PySide6.QtGui import QDoubleValidator
                from PySide6.QtCore import QLocale
                validator=QDoubleValidator(0,100,6,edit);validator.setLocale(QLocale.c())
                validator.setNotation(QDoubleValidator.Notation.StandardNotation);edit.setValidator(validator)
            box.addWidget(label);inputs[key]=edit
            if key=="rpm":
                rpm_row=QHBoxLayout();rpm_row.addWidget(edit,1);rpm_row.addStretch(1);box.addLayout(rpm_row);manual_layout.addWidget(card)
            else:box.addWidget(edit);pedal_row.addWidget(card,1)
        gear_card=FieldColors.card("gear");input_cards["gear"]=gear_card;gear_box=QVBoxLayout(gear_card)
        gear_label=QLabel("Gang");gear_label.setObjectName("manualInputHeading");gear_label.setStyleSheet(FieldColors.heading("gear"))
        gear=QComboBox();gear.setObjectName("manualGear");gear.addItems(["P","R","N","D"]);gear.setStyleSheet(FieldColors.field("gear","QComboBox"))
        gear_box.addWidget(gear_label);gear_box.addWidget(gear);pedal_row.addWidget(gear_card,1)
        manual_layout.addLayout(pedal_row)
        controls_layout.addWidget(manual_area)
        from .map_sweep_panel import MapSweepPanel
        sweep_panel=MapSweepPanel.create();controls_layout.addWidget(sweep_panel);sweep_panel.hide()
        log_heading=QLabel("Log-Verlauf ::");log_heading.setStyleSheet("color:#facc15; font:700 14pt 'Segoe UI';");controls_layout.addWidget(log_heading)
        log_view=QPlainTextEdit();log_view.setReadOnly(True);log_view.setMaximumBlockCount(3000);log_view.setMinimumHeight(120)
        log_view.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        log_view.setStyleSheet("background:#171724; color:#e2e8f0; font:10pt 'Consolas'; border:1px solid #475569;")
        from PySide6.QtWidgets import QSizePolicy
        log_view.setSizePolicy(QSizePolicy.Policy.Expanding,QSizePolicy.Policy.Ignored)
        log_view.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        controls_layout.addWidget(log_view,1)
        controls_bottom=QWidget();controls_bottom.setSizePolicy(QSizePolicy.Policy.Preferred,QSizePolicy.Policy.Expanding)
        controls_layout.addWidget(controls_bottom,1)
        controls.setMinimumSize(600,520)
        controls_scroll=QScrollArea();controls_scroll.setObjectName("operationScroll")
        controls_scroll.setWidgetResizable(True);controls_scroll.setWidget(controls)
        controls_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        controls_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        controls_scroll.setMinimumSize(0,0)
        neighbor=QFrame();neighbor.setObjectName("operationNeighbor")
        neighbor.setStyleSheet("QFrame#operationNeighbor {background:#252536; border:1px solid #334155;}")
        from .parameter_files_panel import ParameterFilesPanel
        parameter_panel=ParameterFilesPanel.create(window,lambda action,data:cls.run_operation(window,action,data))
        neighbor_layout=QVBoxLayout(neighbor);neighbor_layout.addWidget(parameter_panel)
        workspace_layout.addWidget(controls_scroll,2);workspace_layout.addWidget(neighbor,3)
        sidebar_scroll=QScrollArea();sidebar_scroll.setObjectName("setupSelectionScroll")
        sidebar_scroll.setWidgetResizable(True);sidebar_scroll.setWidget(sidebar)
        sidebar_scroll.setMinimumSize(0,0)
        sidebar_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        sidebar_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        empty_sections=QLabel("Bereiche oben wieder einblenden.")
        empty_sections.setAlignment(Qt.AlignmentFlag.AlignCenter);empty_sections.hide()
        empty_sections.setStyleSheet("color:#94a3b8; font:12pt 'Segoe UI';")
        workspace_layout.addWidget(empty_sections,1)
        central.addWidget(sidebar_scroll);central.addWidget(workspace)
        central.setStretchFactor(0,0);central.setStretchFactor(1,1)
        window.setCentralWidget(central)
        group=QButtonGroup(window);group.setExclusive(False)
        state={"sources":sources,"path":path,"status":status,"items":items,"group":group,"queue":queue.Queue(),"request":0,"selected":None}
        state.update(sidebar=sidebar,workspace=workspace,splitter=central,
                     connect=connect,connection=connection,commands=queue.Queue(),responses=queue.Queue(),
                     connected_path=None,connecting=False,stop=threading.Event(),cancelled=threading.Event(),progress=None)
        state.update(controls_bottom=controls_bottom,log_heading=log_heading,manual_area=manual_area,sweep_panel=sweep_panel,sweep_cancel=threading.Event(),sweep_commands=queue.Queue(),log_view=log_view,mode=mode,operation_buttons=(mode_start,ignition,engine,start_stop,clear_errors,simulation,pause,init_values,close_setup),operation_status=operation_status,operating=False)
        state.update(simulation=simulation,parameter_panel=parameter_panel,pause=pause,paused=False,pending_action=None,last_inputs={},pending_input=None,pending_inputs=None,inputs=inputs,input_cards=input_cards,input_labels=input_labels,gear_label=gear_label,gear=gear,cycle=cycle,controls_scroll=controls_scroll)
        state.update(instances={},shutdown_pending=False,shutdown_ok=False,shutdown_loop=None,close_setup=close_setup,exit_now=exit_now,deferred_controls=set(),headless=headless,clear_errors=clear_errors,reload_setup=reload_setup,detach=detach,detaching=False,auto=auto,start_stop_state=start_stop_state,ignition_state=ignition_state,engine_state=engine_state)
        state.update(sidebar_scroll=sidebar_scroll,flash_container=neighbor,empty_sections=empty_sections,section_toggles={},connection_row=connection_row,close_row=close_row)
        window._setup_control=state
        from ..ui.responsive_setup import ResponsiveSetup
        ResponsiveSetup.install(window)
        window.addToolBarBreak()
        sections_bar=QToolBar("Bereiche",window);sections_bar.setObjectName("setupSectionsToolbar")
        sections_bar.setMovable(False)
        sections_bar.setStyleSheet("QToolButton {background:#2a2a3e; color:#94a3b8; border:1px solid #475569; border-radius:4px; padding:7px 10px; font-weight:700;} QToolButton:checked {background:#334155; color:#facc15;} QToolButton:hover {border-color:#99f6e4;}")
        window.addToolBar(sections_bar)
        for key,title in (("selection","Setup-Auswahl"),("controls","Setup-Ansteuerung"),("flash","Flashen")):
            button=QToolButton();button.setObjectName("toggleSection_"+key)
            button.setText(title);button.setCheckable(True);button.setChecked(True)
            ButtonGradients.apply(button,"#2a2a3e",padding="7px 10px",checked="#99f6e4")
            button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
            button.setArrowType(Qt.ArrowType.DownArrow)
            button.setToolTip(title+" ein-/ausklappen")
            state["section_toggles"][key]=button;sections_bar.addWidget(button)
            button.toggled.connect(lambda checked,key=key:cls.toggle_section(window,key,checked))
        from ..ui.comboboxes import ComboBoxes
        for combo in (sources,mode,cycle,gear):ComboBoxes.configure(combo)
        cls.display_states(window,None)
        cls.show_simulation_state(window,False)
        init_values.clicked.connect(lambda:cls.run_operation(window,"init_read"))
        simulation.clicked.connect(lambda:cls.run_operation(window,"simulation_toggle",simulation.text()=="Simulation-Pausieren"))
        mode.currentTextChanged.connect(lambda value:cls.mode_controls(window))
        mode.currentTextChanged.connect(lambda value:cls.append_log(window,"Betriebsmode ausgewählt: "+value))
        cls.mode_controls(window)
        headless.toggled.connect(lambda checked:state["commands"].put(("headless",checked)))
        auto.toggled.connect(lambda checked:state["commands"].put(("automatic",checked,state["selected"])))
        pause.clicked.connect(lambda:cls.run_operation(window,"pause",not state["paused"]))
        mode_start.clicked.connect(lambda:cls.start_selected_mode(window))
        sweep_panel.cancel.clicked.connect(lambda:state["sweep_cancel"].set())
        for key,edit in inputs.items():
            edit.returnPressed.connect(lambda:cls.submit_inputs(window))
        gear.activated.connect(lambda index:cls.run_operation(window,"gear",gear.currentText()))
        cycle.activated.connect(lambda index:cls.cycle_selected(window))
        ignition.clicked.connect(lambda:cls.run_operation(window,"ignition"))
        engine.clicked.connect(lambda:cls.run_operation(window,"engine"))
        start_stop.clicked.connect(lambda:cls.run_operation(window,"start_stop"))
        clear_errors.clicked.connect(lambda:cls.run_operation(window,"clear_errors"))
        cls.connection_status(window)
        connect.clicked.connect(lambda:cls.connect_selected(window))
        detach.clicked.connect(lambda:cls.disconnect_selected(window))
        reload_setup.clicked.connect(lambda:cls.run_operation(window,"reload"))
        close_setup.clicked.connect(lambda:cls.close_selected_setup(window))
        threading.Thread(target=cls.connection_worker,args=(state["commands"],state["responses"],state["stop"],state["cancelled"],state["sweep_cancel"],state["sweep_commands"]),daemon=True).start()
        timer=QTimer(window);timer.timeout.connect(lambda:cls.poll(window));timer.start(100);state["timer"]=timer
        sources.currentIndexChanged.connect(lambda index:cls.reload(window))
        window.closeEvent=lambda event:cls.close(window,event)
        from PySide6.QtWidgets import QApplication
        area=QApplication.primaryScreen().availableGeometry()
        window.resize(min(1000,area.width()-24),min(700,area.height()-48))
        window.showMaximized()
        QTimer.singleShot(0,lambda:cls.size_panels(window))
        cls.reload(window)
        from ..core.config import Config
        preferences=Config.state()
        exit_now.setChecked(preferences.get("SetupExitNow",False))
        headless.setChecked(preferences.get("SetupHeadless",False))
        auto.setChecked(preferences.get("SetupAutoConnect",False))
        # Start grouped every time; users can disable grouping for this session.
        parameter_panel._grouped.setChecked(True)
        return window

    @classmethod
    def reload(cls,window):
        state=window._setup_control;state["request"]+=1;state["selected"]=None
        for button in state["group"].buttons():
            state["group"].removeButton(button);state["items"].removeWidget(button);button.deleteLater()
        cls.connection_status(window)
        cls.watch_selection(window)
        state["path"].clear();state["status"].setText("Setup-Dateien werden geladen ...")
        source=state["sources"].currentText()
        threading.Thread(target=cls.worker,args=(state["queue"],state["request"],source),daemon=True).start()

    @classmethod
    def manual_path_changed(cls,path):
        window=cls._window
        if window is None:return
        from shiboken6 import isValid
        if not isValid(window):return
        state=window._setup_control
        if state["sources"].currentText()!="Lokale manuelle Kopie":return
        if state["path"].text()==path:return
        state["pending_manual_path"]=path
        cls.refresh_manual_path(window)

    @classmethod
    def refresh_manual_path(cls,window):
        state=window._setup_control
        if not state.get("pending_manual_path"):return
        if state["sources"].currentText()!="Lokale manuelle Kopie":
            state.pop("pending_manual_path",None);return
        if any(state.get(key,False) for key in ("connecting","operating","detaching","shutdown_pending")):return
        state.pop("pending_manual_path",None)
        cls.reload(window)

    @classmethod
    def worker(cls,messages,request,source):
        try:messages.put((request,SetupControl.list_setups(source),None))
        except Exception as error:messages.put((request,None,str(error)))

    @classmethod
    def poll(cls,window):
        cls.refresh_manual_path(window)
        state=window._setup_control
        try:
            while True:
                request,result,error=state["queue"].get_nowait()
                if request!=state["request"]:continue
                state["path"].setText((result or {}).get("path",""))
                state["status"].setText(error or result["message"])
                state["status"].setStyleSheet("color:#f59e0b;" if error or result["message"] else "color:#94a3b8;")
                for value in (result or {}).get("files",[]):
                    button=QRadioButton(Path(value).name)
                    button.setAutoExclusive(False)
                    button.setToolTip(value);button.setProperty("silPath",value)
                    button.toggled.connect(lambda checked,value=value:cls.select(window,value,checked))
                    state["group"].addButton(button);state["items"].addWidget(button)
        except queue.Empty:pass
        try:
            while True:
                kind,path,error=state["responses"].get_nowait()
                if kind=="shutdown":
                    cls.finish_progress(window)
                    state["shutdown_pending"]=False;state["shutdown_ok"]=not bool(error)
                    for closed in path:state["instances"].pop(closed,None)
                    if state["connected_path"] in path:state["connected_path"]=None
                    if not error:
                        state["connected_path"]=None;state["deferred_controls"]=set()
                        cls.connection_status(window)
                        state["operation_status"].setText("Setup gespeichert und geschlossen.")
                    for button in state["operation_buttons"]:button.setEnabled(True)
                    state["connect"].setEnabled(True);state["sources"].setEnabled(True)
                    if state["shutdown_loop"]:state["shutdown_loop"].quit()
                    if error:Dialogs.message("Setup konnte nicht geschlossen werden",error,window)
                    continue
                if kind=="disconnected":
                    state["detaching"]=False;state["connecting"]=False;state["operating"]=False
                    state["deferred_controls"]=set();state["connected_path"]=None;cls.finish_progress(window)
                    state["connect"].setEnabled(True);state["sources"].setEnabled(True)
                    for button in state["group"].buttons():button.setEnabled(True)
                    for button in state["operation_buttons"]:button.setEnabled(True)
                    state["status"].clear();state["operation_status"].clear();cls.connection_status(window)
                    cls.append_log(window,"Silver-API-Verbindung getrennt.")
                    if error:Dialogs.message("Silver-Vorgaben nicht vollständig freigegeben",error,window)
                    continue
                if state["detaching"]:continue
                if kind in ("connected","cancelled"):
                    if kind=="connected" and state["cancelled"].is_set():continue
                    cls.finish_progress(window)
                    state["connecting"]=False
                    state["connected_path"]=None if error or kind=="cancelled" else path
                    state["sources"].setEnabled(True)
                    for button in state["group"].buttons():button.setEnabled(True)
                    state["connect"].setEnabled(True)
                    cls.connection_status(window)
                    if kind=="connected" and not error:state["commands"].put(("operation","parameters_read",None,path))
                    if error and kind!="cancelled":Dialogs.message("Silver-Verbindung nicht hergestellt",error,window)
                elif kind=="cancel_failed":
                    cls.finish_progress(window);state["connecting"]=False
                    state["connect"].setEnabled(True);state["sources"].setEnabled(True)
                    for button in state["group"].buttons():button.setEnabled(True)
                    state["deferred_controls"]=set();state["connected_path"]=None;cls.connection_status(window)
                    Dialogs.message("Abbruch nicht vollständig",error,window)
                elif kind=="auto":
                    if state["auto"].isChecked() and state["selected"]==path:
                        state["connected_path"]=path if not error else None
                        cls.connection_status(window)
                        state["status"].clear()
                        if not error:state["commands"].put(("operation","parameters_read",None,path))
                elif kind=="parameter_files":
                    if state["selected"]==path and state["connected_path"]==path:
                        from .parameter_files_panel import ParameterFilesPanel
                        ParameterFilesPanel.populate(state["parameter_panel"],error)
                elif kind=="inputs":
                    if state["selected"]==path and state["connected_path"]==path and error:
                        for key,value in error.items():
                            if key=="gear":
                                selected={-2:"P",-1:"R",0:"N",5:"D"}.get(value)
                                if selected and not state["gear"].view().isVisible():
                                    blocked=state["gear"].blockSignals(True)
                                    state["gear"].setCurrentText(selected)
                                    state["gear"].blockSignals(blocked)
                                continue
                            state["last_inputs"][key]=format(value,"g")
                            edit=state["inputs"][key]
                            text=format(value,"g")
                            editing=edit.hasSelectedText() or (edit.hasFocus() and edit.cursorPosition()<len(edit.text()))
                            # Reassigning even identical text destroys the selection/cursor.
                            if edit.text()!=text and not edit.isModified() and not editing:edit.setText(text)
                elif kind=="signals":
                    if state["selected"]==path and state["connected_path"]==path:
                        cls.display_states(window,error)
                elif kind=="simulation_start_required":
                    action,mode,selected=path
                    if cls.ask_simulation_start(window):
                        state["commands"].put(("operation",action,mode,selected,True))
                    else:
                        state["operating"]=False
                        for button in state["operation_buttons"]:button.setEnabled(True)
                        state["operation_status"].clear()
                elif kind=="initial_rpm":
                    if state["selected"]==path:
                        edit=state["inputs"]["rpm"];text=format(error,"g")
                        edit.setText(text);edit.setModified(False);state["last_inputs"]["rpm"]=text
                elif kind=="simulation_state":
                    if state["selected"]==path and error is not None:cls.show_simulation_state(window,error is True)
                elif kind=="pause_state":
                    if state["selected"]==path:
                        state["paused"]=bool(error)
                        state["pause"].setText("Weiter" if state["paused"] else "Pause")
                        cls.show_simulation_state(window,not state["paused"])
                elif kind=="pending_controls":
                    state["deferred_controls"]=set(error)
                elif kind=="deferred":
                    state["operation_status"].setText(error)
                    Dialogs.message("Simulation läuft nicht",error,window)
                elif kind=="deferred_error":
                    state["deferred_controls"]=set()
                    Dialogs.message("Vorgemerkte Aktion nicht ausgeführt",error,window)
                elif kind=="init_values":
                    from .init_values_dialog import InitValuesDialog
                    InitValuesDialog.open(window,error,lambda values:cls.run_operation(window,"init_apply",values))
                elif kind=="flash_progress":
                    if state["progress"]:state["progress"][1].setText(error)
                elif kind=="log":
                    cls.append_log(window,error,measurement=True)
                elif kind=="sweep_control_error":
                    Dialogs.message("Setup-Aktion nicht ausgeführt",error,window)
                elif kind in ("operation","sweep_cancelled"):
                    if state["pending_action"]=="sweep":
                        state["mode"].setEnabled(True);state["sweep_panel"].cancel.setEnabled(False)
                        for field in state["sweep_panel"].fields.values():field.setEnabled(True)
                        state["connect"].setEnabled(True);state["sources"].setEnabled(True)
                        state["parameter_panel"].setEnabled(True)
                    state["parameter_panel"].setEnabled(True)
                    if not state["shutdown_pending"]:cls.finish_progress(window)
                    state["operating"]=False
                    state["connect"].setEnabled(True);state["sources"].setEnabled(True)
                    for button in state["group"].buttons():button.setEnabled(True)
                    if path and not error:state["connected_path"]=path
                    cls.connection_status(window)
                    for button in state["operation_buttons"]:button.setEnabled(True)
                    if not error and state["pending_action"]=="mode":
                        state["paused"]=False;state["pause"].setText("Pause")
                    state["pending_action"]=None
                    pending=state["pending_input"];state["pending_input"]=None
                    if pending:
                        key,previous,submitted=pending
                        edit=state["inputs"][key]
                        if error:edit.setText(previous)
                        else:state["last_inputs"][key]=submitted
                        edit.setModified(False)
                    pending_batch=state["pending_inputs"];state["pending_inputs"]=None
                    if pending_batch:
                        for key,(previous,submitted) in pending_batch.items():
                            edit=state["inputs"][key]
                            if error:edit.setText(previous)
                            else:state["last_inputs"][key]=submitted
                            edit.setModified(False)
                    cls.append_log(window,error or "Aktion erfolgreich ausgeführt.")
                    state["operation_status"].setText(error or "Aktion erfolgreich ausgeführt.")
                    if error:
                        if kind=="sweep_cancelled":
                            Dialogs.message("Kennfeld-Rasterung abgebrochen","Die Rasterung wurde auf Ihren Wunsch beendet.",window)
                        elif error=="Zündung ist nicht AN! Motor kann nicht gestartet werden":
                            if cls.ask_ignition_start(window):cls.run_operation(window,"ignition_engine")
                        else:Dialogs.message("Setup-Aktion nicht ausgeführt",error,window)
                elif kind=="lost":
                    state["deferred_controls"]=set();state["connected_path"]=None;cls.connection_status(window)
        except queue.Empty:pass

    @classmethod
    def select(cls,window,value,checked):
        state=window._setup_control
        if checked:
            for button in state["group"].buttons():
                if button.property("silPath")!=value:
                    blocked=button.blockSignals(True)
                    button.setChecked(False)
                    button.blockSignals(blocked)
            state["selected"]=value
        elif state["selected"]==value:
            state["selected"]=None
        cls.connection_status(window)
        cls.watch_selection(window)

    @classmethod
    def watch_selection(cls,window):
        state=window._setup_control
        cls.display_states(window,None)
        state["last_inputs"].clear()
        from .parameter_files_panel import ParameterFilesPanel
        ParameterFilesPanel.populate(state["parameter_panel"],{})
        state["commands"].put(("watch",state["selected"],state["auto"].isChecked()))

    @classmethod
    def display_states(cls,window,values):
        state=window._setup_control
        for key,on,off in (("ignition","AN","AUS"),("engine","Motor läuft","Motor steht"),("start_stop","Aktiv","Nicht aktiv")):
            label=state[key+"_state"]
            known=values is not None and values.get(key) is not None
            active=known and values[key]
            label.setText((on if active else off) if known else "—")
            bg,fg=("#4ade80","#172554") if active else (("#dc2626","#ffffff") if known else ("#2a2a3e","#94a3b8"))
            if key in state.get("deferred_controls",set()):
                label.setText("Vorgemerkt");bg,fg="#fed7aa","#172554"
            label.setStyleSheet(f"background:{bg}; color:{fg}; border-radius:4px; padding:8px; font-weight:700;")

    @classmethod
    def ask_ignition_start(cls,window):
        dialog,footer,body=Dialogs.card("Zündung ist nicht AN!","Motor kann nicht gestartet werden",window)
        row=QHBoxLayout();row.addStretch()
        close=QPushButton("Schließen");start=QPushButton("Zündung An + Motor Starten")
        ButtonGradients.apply(start,"#bbf7d0")
        close.clicked.connect(dialog.reject);start.clicked.connect(dialog.accept)
        row.addWidget(close);row.addWidget(start);footer.addLayout(row)
        from PySide6.QtWidgets import QDialog
        return dialog.exec()==QDialog.DialogCode.Accepted

    @classmethod
    def ask_simulation_start(cls,window):
        dialog,footer,body=Dialogs.card("Simulation starten?","Silver-Simulation ist nicht gestartet. Wollen Sie die Simulation starten?",window)
        row=QHBoxLayout()
        no=QPushButton("Nein");yes=QPushButton("Ja")
        no.clicked.connect(dialog.reject);yes.clicked.connect(dialog.accept)
        row.addWidget(no);row.addWidget(yes);footer.addLayout(row)
        from PySide6.QtWidgets import QDialog
        return dialog.exec()==QDialog.DialogCode.Accepted

    @classmethod
    def show_simulation_state(cls,window,running):
        button=window._setup_control["simulation"]
        button.setText("Simulation-Pausieren" if running else "Simulation-Starten")
        ButtonGradients.apply(button,"#fde68a" if running else "#172554",padding="10px 16px",font="700 12pt 'Segoe UI'")

    @classmethod
    def mode_controls(cls,window):
        state=window._setup_control
        sweep=state["mode"].currentText()=="Kennfeld-Rasterung"
        state["manual_area"].setVisible(not sweep);state["sweep_panel"].setVisible(sweep)
        state["controls_bottom"].setVisible(not sweep)
        state["log_heading"].setVisible(sweep)
        state["log_view"].setVisible(sweep);state["log_view"].setEnabled(sweep)
        current_mode=state["mode"].currentText()
        for key,active in {"rpm":current_mode=="Test-Bench","accelerator":current_mode!="Zyklus","brake":current_mode=="IMO","gear":current_mode!="Test-Bench"}.items():
            state["input_cards"][key].setEnabled(active)
        enabled=current_mode!="Test-Bench"
        state["gear"].setEnabled(enabled)
        brake_enabled=state["mode"].currentText()=="IMO"
        state["inputs"]["brake"].setEnabled(brake_enabled)
        state["input_labels"]["brake"].setEnabled(brake_enabled)
        accelerator_enabled=state["mode"].currentText()!="Zyklus"
        state["inputs"]["accelerator"].setEnabled(accelerator_enabled)
        state["input_labels"]["accelerator"].setEnabled(accelerator_enabled)
        state["pause"].setVisible(state["mode"].currentText()=="Zyklus")
        state["gear_label"].setEnabled(enabled)
        state["inputs"]["rpm"].setEnabled(not enabled)
        state["input_labels"]["rpm"].setEnabled(not enabled)

    @classmethod
    def cycle_selected(cls,window):
        state=window._setup_control
        if state["selected"] and state["selected"]==state["connected_path"]:
            cls.run_operation(window,"cycle",state["cycle"].currentText())

    @classmethod
    def submit_inputs(cls,window):
        state=window._setup_control
        values={key:edit.text() for key,edit in state["inputs"].items() if edit.isEnabled()}
        cls.run_operation(window,"inputs",values)

    @classmethod
    def append_log(cls,window,message,measurement=False):
        from datetime import datetime
        state=window._setup_control
        if not measurement or state["mode"].currentText()!="Kennfeld-Rasterung":return
        state["log_view"].appendPlainText(datetime.now().strftime("%H:%M:%S")+"  "+str(message))

    @classmethod
    def start_selected_mode(cls,window):
        state=window._setup_control
        if state["mode"].currentText()=="Kennfeld-Rasterung":
            from .map_sweep_panel import MapSweepPanel
            cls.run_operation(window,"sweep",MapSweepPanel.values(state["sweep_panel"]))
        else:cls.run_operation(window,"mode",(state["mode"].currentText(),state["cycle"].currentText()))

    @classmethod
    def run_operation(cls,window,action,mode=None):
        state=window._setup_control
        if state["operating"] and state["pending_action"]=="sweep" and action in ("clear_errors","simulation_toggle"):
            state["sweep_commands"].put(action)
            return
        if state["connecting"] or state["operating"]:return
        if state["mode"].currentText()=="Test-Bench" and (action=="gear" or (action=="input" and mode[0]=="brake")):return
        if action=="input" and not state["inputs"][mode[0]].isEnabled():return
        if action=="pause" and state["mode"].currentText()!="Zyklus":return
        if not state["selected"]:
            Dialogs.message("Setup auswählen","Bitte wählen Sie zuerst ein Setup aus.",window)
            return
        if action not in ("mode","sweep") and state["selected"]!=state["connected_path"]:
            Dialogs.message("Silver-Verbindung erforderlich","Bitte zuerst das ausgewählte Setup mit Silver verbinden.",window)
            return
        if action=="sweep":
            from ..silver.map_sweep import MapSweep
            try:mode=MapSweep.validate(mode)
            except Exception as error:Dialogs.message("Raster-Einstellungen prüfen",str(error),window);return
            while not state["sweep_commands"].empty():state["sweep_commands"].get_nowait()
            state["sweep_cancel"].clear();state["mode"].setEnabled(False)
            state["sweep_panel"].cancel.setEnabled(True)
            for field in state["sweep_panel"].fields.values():field.setEnabled(False)
            state["connect"].setEnabled(False);state["sources"].setEnabled(False);state["parameter_panel"].setEnabled(False)
        labels={"ignition":"Klemme 15 umschalten","engine":"Motor starten","ignition_engine":"Zündung einschalten und Motor starten","start_stop":"Start-Stop umschalten","clear_errors":"Fehler löschen","inputs":"Eingabewerte übernehmen","input":"Eingabewert übernehmen","gear":"Gang wählen","mode":"Betriebsmode starten","reload":"Setup neu laden","parameters_save":"Varianten-Kodierung und Datenstand übernehmen","parameters_read":"Flashkonfiguration lesen","simulation_toggle":"Simulation starten/pausieren","pause":"Simulation pausieren/fortsetzen","sweep":"Kennfeld-Rasterung starten","cycle":"Fahrzyklus wählen"}
        cls.append_log(window,labels.get(action,action))
        state["operating"]=True;state["pending_action"]=action
        if action=="inputs":
            state["pending_inputs"]={key:(state["last_inputs"].get(key,""),value) for key,value in mode.items()}
        if action.startswith("parameters_"):state["parameter_panel"].setEnabled(False)
        if action=="input":
            key,submitted=mode
            state["pending_input"]=(key,state["last_inputs"].get(key,""),submitted)
        if action in ("mode","parameters_save","reload","init_apply"):
            from ..silEinrichten import SilEinrichten
            title="Datenstand / Variantenkodierung flashen" if action=="parameters_save" else ("Setup wird gestartet" if action=="mode" else "Setup wird geladen")
            if action=="init_apply":title="INIT-Werte werden eingestellt"
            progress,body,animation=SilEinrichten.create_progress_card(title,"Änderungen werden vorbereitet …" if action=="parameters_save" else "")
            progress.setParent(window,Qt.WindowType.Dialog)
            progress.setWindowModality(Qt.WindowModality.WindowModal)
            # Loading RPCs must finish before another operation can be submitted.
            for button in progress.findChildren(QPushButton):button.hide()
            progress.reject=lambda:None
            progress.closeEvent=lambda event:event.ignore()
            state["progress"]=(progress,body,animation)
            animation.start();progress.show();Dialogs.foreground(progress);progress.repaint()
            state["connect"].setEnabled(False);state["sources"].setEnabled(False)
            for button in state["group"].buttons():button.setEnabled(False)
        for button in state["operation_buttons"]:button.setEnabled(False)
        if action=="sweep":
            state["clear_errors"].setEnabled(True);state["simulation"].setEnabled(True)
        state["operation_status"].setText("Bitte warten ...")
        state["commands"].put(("operation",action,mode,state["selected"]))

    @classmethod
    def connection_status(cls,window):
        state=window._setup_control
        from ..silver.connection import SilverConnection
        if state["connected_path"] and SilverConnection._silver_pid is not None and SilverConnection._setup_path==state["connected_path"]:
            state["instances"][state["connected_path"]]={"path":state["connected_path"],"pid":SilverConnection._silver_pid,"headless":SilverConnection._headless}
        if state["selected"]!=state["connected_path"]:cls.display_states(window,None)
        if state["connecting"]:text,bg,fg="Verbinden ...","#bfdbfe","#172554"
        elif state["selected"] and state["selected"]==state["connected_path"]:text,bg,fg="Verbunden","#4ade80","#172554"
        else:text,bg,fg="Nicht verbunden","#dc2626","#ffffff"
        state["connection"].setText(text)
        state["connection"].setStyleSheet(f"background:{bg}; color:{fg}; border-radius:4px; padding:8px; font-weight:700;")

    @classmethod
    def connect_selected(cls,window):
        state=window._setup_control
        if not state["selected"]:
            Dialogs.message("Setup auswählen","Bitte wählen Sie zuerst ein Setup aus.",window)
            return
        if state["connecting"]:return
        state["cancelled"].clear()
        state["connecting"]=True;cls.connection_status(window)
        from ..silEinrichten import SilEinrichten
        progress,body,animation=SilEinrichten.create_progress_card(Path(state["selected"]).name+" wird ausgeführt.","")
        progress.setParent(window,Qt.WindowType.Dialog)
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.reject=lambda:cls.cancel_start(window)
        progress.closeEvent=lambda event:(event.ignore(),cls.cancel_start(window))
        from PySide6.QtWidgets import QDialog
        progress.keyPressEvent=lambda event:cls.cancel_start(window) if event.key()==Qt.Key.Key_Escape else QDialog.keyPressEvent(progress,event)
        for button in progress.findChildren(QPushButton):
            button.clicked.disconnect()
            button.clicked.connect(lambda checked=False:cls.cancel_start(window))
        state["progress"]=(progress,body,animation)
        animation.start();progress.show();Dialogs.foreground(progress)
        state["connect"].setEnabled(False);state["sources"].setEnabled(False)
        for button in state["group"].buttons():button.setEnabled(False)
        state["commands"].put(state["selected"])

    @classmethod
    def disconnect_selected(cls,window):
        from ..silver.connection import SilverConnection
        state=window._setup_control
        state["auto"].setChecked(False)
        from .parameter_files_panel import ParameterFilesPanel
        ParameterFilesPanel.populate(state["parameter_panel"],{})
        state["detaching"]=True
        state["connected_path"]=None;cls.connection_status(window)
        state["connect"].setEnabled(False)
        SilverConnection.request_detach()
        state["commands"].put(("disconnect",))

    @classmethod
    def sweep_control(cls,commands,responses,selected,stop):
        from ..silver.operation import SilverOperation as Op
        while commands is not None:
            try:action=commands.get_nowait()
            except queue.Empty:break
            try:
                if action=="clear_errors":Op.clear_errors(stop)
                elif action=="simulation_toggle":
                    paused=not bool(Op._requested_pause)
                    Op.set_paused(paused)
                    responses.put(("pause_state",selected,paused))
            except Exception as error:responses.put(("sweep_control_error",selected,str(error)))
        return bool(Op._requested_pause)

    @classmethod
    def connection_worker(cls,commands,responses,stop,cancelled,sweep_cancel=None,sweep_commands=None):
        while not stop.is_set():
            if cls._connection_lock.acquire(timeout=0.1):break
        else:return
        try:cls.connection_loop(commands,responses,stop,cancelled,sweep_cancel,sweep_commands)
        finally:cls._connection_lock.release()

    @classmethod
    def connection_loop(cls,commands,responses,stop,cancelled,sweep_cancel=None,sweep_commands=None):
        # Keep every vendor API call on one owning thread, away from the GUI.
        from ..silver.connection import SilverConnection,SilverStartCancelled
        SilverConnection._detach.clear()
        from ..silver.operation import SilverOperation
        SilverOperation._log_messages=None
        from ..silver.deferred_controls import SilverDeferredControls as Deferred
        Deferred.reset()
        path=None;owned_start=False;watch=None;automatic=False;headless=False
        try:
            while not stop.is_set():
                try:requested=commands.get(timeout=1)
                except queue.Empty:
                    if path and not SilverConnection.alive():
                        path=None;responses.put(("lost",None,None))
                    if automatic and watch and path!=watch:
                        try:
                            result=SilverConnection.connect(watch,allow_start=False,gui=not headless)
                            if result is not None:
                                path=watch;responses.put(("auto",path,None))
                        except Exception as error:responses.put(("auto",watch,str(error)))
                    if path:
                        try:
                            from ..silver.operation import SilverOperation
                            running=SilverOperation.sample_simulation_state()
                            try:responses.put(("pending_controls",path,Deferred.tick(running)))
                            except Exception as error:
                                try:Deferred.clear_pulses()
                                except Exception as cleanup:error=RuntimeError(str(error)+" / "+str(cleanup))
                                Deferred.reset();responses.put(("deferred_error",path,str(error)))
                            responses.put(("signals",path,SilverOperation.states()))
                            responses.put(("inputs",path,SilverOperation.input_values()))
                            responses.put(("simulation_state",path,running))
                        except Exception:responses.put(("signals",path,None))
                    continue
                if requested is None:break
                if isinstance(requested,tuple) and requested[0]=="shutdown":
                    _,targets,immediate=requested
                    closed=[];failure=None
                    try:
                        for target in targets:
                            if path!=target["path"] or SilverConnection._silver_pid!=target["pid"] or not SilverConnection.alive():
                                result=SilverConnection.connect(target["path"],allow_start=False,gui=not target["headless"],pid=target["pid"])
                                if result is None:
                                    closed.append(target["path"]);continue
                                path=target["path"]
                            if target["headless"] and not SilverConnection._headless:
                                raise RuntimeError("Die zu schließende kopflose Instanz stimmt nicht mehr überein.")
                            SilverConnection.save_and_exit(target["path"],immediate=immediate)
                            closed.append(target["path"]);path=None
                        watch=None;automatic=False;owned_start=False
                    except Exception as error:failure=str(error)
                    responses.put(("shutdown",closed,failure));continue
                if requested==("disconnect",):
                    release_error=None
                    try:SilverConnection.disconnect()
                    except Exception as error:release_error=str(error)
                    path=None;watch=None;automatic=False;owned_start=False
                    responses.put(("disconnected",None,release_error))
                    continue
                if isinstance(requested,tuple) and requested[0]=="headless":
                    headless=bool(requested[1]);continue
                if isinstance(requested,tuple) and requested[0]=="automatic":
                    automatic=requested[1]
                    if len(requested)>2:watch=requested[2]
                    continue
                if isinstance(requested,tuple) and requested[0]=="watch":
                    _,watch,automatic=requested
                    if watch and watch==path and SilverConnection.alive():
                        try:
                            from ..silver.parameter_files import SilverParameterFiles
                            responses.put(("parameter_files",path,SilverParameterFiles.entries()))
                        except Exception as error:responses.put(("operation",path,str(error)))
                    continue
                if isinstance(requested,tuple) and requested[0]=="operation":
                    try:
                        from ..silver.operation import SilverOperation
                        _,action,mode,selected,*options=requested
                        SilverOperation._log_messages=None
                        if path!=selected or not SilverConnection.alive():
                            if action not in ("mode","sweep"):raise RuntimeError("Die Verbindung zum ausgewählten Setup ist nicht mehr aktiv.")
                            try:
                                SilverConnection.connect(selected,gui=not headless)
                                path=selected
                            except Exception as error:raise RuntimeError("Setup ist nicht erfolgreich geladen. Bitte Silver und die Setup-Konfiguration prüfen.") from error
                        if action in Deferred.ACTIONS:
                            running=SilverOperation.simulation_running()
                            if running is not True:
                                if running is None:running=SilverOperation.sample_simulation_state()
                                if running is not True:
                                    names=Deferred.stage(action)
                                    responses.put(("operation",selected,None))
                                    responses.put(("pending_controls",selected,names))
                                    responses.put(("deferred",selected,"Die Simulation läuft nicht. Die Werte sind vorgemerkt und werden beim Simulationsstart angewendet und erst dann überwacht."))
                                    continue
                        if action=="sweep":
                            from ..silver.map_sweep import MapSweep
                            MapSweep.run(mode,lambda message:responses.put(("log",selected,message)),sweep_cancel,stop,
                                         lambda:cls.sweep_control(sweep_commands,responses,selected,stop))
                        elif action=="mode":
                            chosen,cycle_name=mode if isinstance(mode,tuple) else (mode,"NEDC")
                            SilverOperation.start_mode(chosen,stop,cycle=cycle_name if chosen=="Zyklus" else None)
                            if chosen=="Test-Bench":responses.put(("initial_rpm",selected,SilverOperation.read("n_EngineSpeed")))
                        elif action in ("parameters_read","parameters_save"):
                            from ..silver.parameter_files import SilverParameterFiles
                            if action=="parameters_save":
                                if SilverConnection._headless:
                                    SilverParameterFiles.apply_and_reload(mode,selected,progress=lambda message:responses.put(("flash_progress",selected,message)))
                                else:
                                    from ..silver.editor_save import SilverEditorSave
                                    with SilverEditorSave.during_apply(SilverConnection._silver_pid):
                                        responses.put(("flash_progress",selected,"Aktiver Silver-SFU-Editor wird abgeschlossen …"))
                                        SilverEditorSave.clear_editor(SilverConnection._silver_pid)
                                        SilverParameterFiles.apply_and_reload(mode,selected,progress=lambda message:responses.put(("flash_progress",selected,message)))
                            responses.put(("parameter_files",selected,SilverParameterFiles.entries()))
                        elif action=="reload":SilverOperation.reload_setup(stop)
                        elif action=="simulation_toggle":
                            running=SilverOperation.simulation_running()
                            paused=running if running is not None else mode
                            SilverOperation.set_paused(paused)
                            responses.put(("pause_state",selected,paused))
                        elif action=="pause":
                            SilverOperation.set_paused(mode)
                            responses.put(("pause_state",selected,mode))
                        elif action=="init_read":responses.put(("init_values",selected,SilverOperation.init_defaults()))
                        elif action=="init_apply":
                            SilverOperation.set_init_values(mode,stop)
                            responses.put(("pause_state",selected,SilverOperation._requested_pause is True))
                        elif action=="input":SilverOperation.set_input(*mode)
                        elif action=="inputs":SilverOperation.set_inputs(mode)
                        elif action=="gear":SilverOperation.switchGear(mode,stop)
                        elif action=="cycle":SilverOperation.set_cycle(mode)
                        elif action=="clear_errors":SilverOperation.clear_errors(stop)
                        elif action=="start_stop":SilverOperation.toggle_start_stop()
                        elif action=="ignition":SilverOperation.toggle_ignition()
                        elif action=="engine":
                            SilverOperation.motor_start(stop)
                        elif action=="ignition_engine":SilverOperation.ignition_and_motor_start(stop)
                        responses.put(("operation",selected,None))
                    except Exception as error:
                        from ..silver.map_sweep import MapSweepCancelled
                        kind="sweep_cancelled" if isinstance(error,MapSweepCancelled) else "operation"
                        responses.put((kind,None,str(error)))
                    continue
                if requested==("cancel",):
                    try:
                        if owned_start:SilverConnection.abort_start()
                        SilverConnection.disconnect();path=None;owned_start=False
                        responses.put(("cancelled",None,None))
                    except Exception as error:
                        responses.put(("cancel_failed",None,str(error)))
                    continue
                try:
                    owned_start=False
                    if path!=requested or SilverConnection._headless!=headless or not SilverConnection.alive():
                        result=SilverConnection.connect(requested,cancelled=cancelled,gui=not headless,enforce_mode=True)
                        owned_start=not result["reused"]
                    path=requested
                    responses.put(("connected",path,None))
                except SilverStartCancelled:
                    path=None;responses.put(("cancelled",requested,None))
                except Exception as error:
                    path=None;responses.put(("connected",requested,str(error)))
        finally:
            SilverOperation._log_messages=None
            SilverConnection.disconnect()

    @classmethod
    def cancel_start(cls,window):
        state=window._setup_control
        if not state["connecting"]:return
        if not state["cancelled"].is_set():state["commands"].put(("cancel",))
        state["cancelled"].set()
        if state["progress"]:
            progress,body,animation=state["progress"]
            body.setText("Start wird abgebrochen ...")
            for button in progress.findChildren(QPushButton):button.setEnabled(False)

    @classmethod
    def finish_progress(cls,window):
        state=window._setup_control
        if state["progress"]:
            progress,body,animation=state["progress"]
            animation.stop();progress.accept();progress.deleteLater()
            state["progress"]=None

    @classmethod
    def toggle_section(cls,window,key,expanded):
        state=window._setup_control
        state["section_toggles"][key].setArrowType(Qt.ArrowType.DownArrow if expanded else Qt.ArrowType.RightArrow)
        shown={name:button.isChecked() for name,button in state["section_toggles"].items()}
        state["sidebar_scroll"].setVisible(shown["selection"])
        state["controls_scroll"].setVisible(shown["controls"])
        state["flash_container"].setVisible(shown["flash"])
        all_closed=not any(shown.values())
        state["empty_sections"].setVisible(all_closed)
        state["workspace"].setVisible(shown["controls"] or shown["flash"] or all_closed)
        cls.size_panels(window)

    @classmethod
    def size_panels(cls,window):
        splitter=window._setup_control["splitter"]
        left=min(480,max(280,splitter.width()//4))
        splitter.setSizes([left,max(0,splitter.width()-left)])

    @classmethod
    def show_launcher(cls):
        if Launcher._window is not None:Dialogs.foreground(Launcher._window)

    @classmethod
    def request_shutdown(cls,window,targets):
        state=window._setup_control
        if state["shutdown_pending"]:return
        from ..silEinrichten import SilEinrichten
        cls.finish_progress(window)
        progress,body,animation=SilEinrichten.create_progress_card("Setup wird gespeichert und geschlossen","Bitte warten …")
        progress.setParent(window,Qt.WindowType.Dialog);progress.setWindowModality(Qt.WindowModality.WindowModal)
        for button in progress.findChildren(QPushButton):button.hide()
        progress.reject=lambda:None;progress.closeEvent=lambda event:event.ignore()
        state["progress"]=(progress,body,animation)
        state["shutdown_pending"]=True;state["shutdown_ok"]=False
        state["sweep_cancel"].set()
        animation.start();progress.show();Dialogs.foreground(progress)
        for button in state["operation_buttons"]:button.setEnabled(False)
        state["connect"].setEnabled(False);state["sources"].setEnabled(False)
        state["commands"].put(("shutdown",targets,state["exit_now"].isChecked()))

    @classmethod
    def close_selected_setup(cls,window):
        state=window._setup_control
        if state["operating"] or state["connecting"] or state["shutdown_pending"]:return
        target=state["instances"].get(state["selected"])
        if target is None:
            Dialogs.message("Silver-Verbindung erforderlich","Bitte das ausgewählte Setup zuerst verbinden.",window);return
        cls.request_shutdown(window,[target])

    @classmethod
    def close(cls,window,event):
        from ..silver.connection import SilverConnection
        from ..core.config import Config
        state=window._setup_control
        if state["shutdown_pending"]:
            event.ignore();return
        targets=[target for target in state["instances"].values() if target["headless"]]
        if targets:
            loop=QEventLoop(window);state["shutdown_loop"]=loop
            cls.request_shutdown(window,targets)
            if state["shutdown_pending"]:loop.exec()
            state["shutdown_loop"]=None;loop.deleteLater()
            if not state["shutdown_ok"]:
                event.ignore();return
        state["sweep_cancel"].set()
        try:
            Config.set_state("SetupExitNow",state["exit_now"].isChecked())
            Config.set_state("SetupHeadless",state["headless"].isChecked())
            Config.set_state("SetupAutoConnect",state["auto"].isChecked())
            Config.set_state("FlashFilesGrouped",state["parameter_panel"]._grouped.isChecked())
        except Exception as error:
            Dialogs.message("Einstellungen nicht gespeichert",str(error),window)
        window._setup_control["stop"].set()
        SilverConnection.request_detach()
        cls.finish_progress(window)
        window._setup_control["commands"].put(None)
        window._setup_control["request"]+=1
        window._setup_control["timer"].stop()
        cls._window=None
        event.accept()
