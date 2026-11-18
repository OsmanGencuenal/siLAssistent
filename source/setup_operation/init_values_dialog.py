"""Selection and editable Silver defaults for temperature initialization."""
from PySide6.QtCore import QLocale
from PySide6.QtWidgets import QFrame,QWidget,QGridLayout,QCheckBox,QDoubleSpinBox,QPushButton,QHBoxLayout
from ..ui.dialogs import Dialogs
from ..silver.operation import SilverOperation

class InitValuesDialog:
    @classmethod
    def open(cls,owner,values,submit):
        dialog,footer,body=Dialogs.card("INIT-Werte einstellen","Größen auswählen und die gewünschten INIT-Werte eintragen.",owner)
        grid=QGridLayout();grid.setVerticalSpacing(12);fields={}
        for row,name in enumerate(SilverOperation.INIT_TEMPERATURES):
            card=QFrame();card.setObjectName("initTemperatureCard")
            card.setStyleSheet("QFrame#initTemperatureCard {background:#343440; border:1px solid #6b7280; border-radius:6px;}")
            card_layout=QHBoxLayout(card);card_layout.setContentsMargins(12,10,12,10);card_layout.setSpacing(14)
            selected=QCheckBox(name);selected.setObjectName("initSelect_"+name)
            selected.setMinimumWidth(180)
            selected.setStyleSheet("QCheckBox {color:#e2e8f0; font:700 12pt 'Segoe UI'; background:transparent; padding:6px;} QCheckBox::indicator {width:22px; height:22px; border:2px solid #cbd5e1; border-radius:4px; background:#f8fafc;} QCheckBox::indicator:checked {background:#f59e0b; border-color:#ffedd5;} QCheckBox:checked {color:#ffda9b;}")
            from ..ui.checkboxes import Checkboxes
            Checkboxes.full_click(selected)
            edit=QDoubleSpinBox();edit.setObjectName("initValue_"+name);edit.setLocale(QLocale.c())
            edit.setDecimals(3);edit.setRange(-1000000,1000000);edit.setValue(values[name]);edit.setEnabled(False)
            edit.setStyleSheet("QDoubleSpinBox {background:#ffffff; color:#172554; padding:6px;} QDoubleSpinBox:disabled {background:#30303e; color:#8892a5;}")
            selected.toggled.connect(edit.setEnabled)
            selected.toggled.connect(lambda checked,card=card:cls.highlight(card,checked))
            card_layout.addWidget(selected);card_layout.addWidget(edit,1)
            grid.addWidget(card,row,0,1,2);fields[name]=(selected,edit)
        footer.addLayout(grid)
        row=QHBoxLayout();cancel=QPushButton("Schließen");apply=QPushButton("INIT-Werte setzen")
        apply.setStyleSheet("background:#bbf7d0; color:#172554; font-weight:700;")
        cancel.clicked.connect(dialog.reject)
        apply.clicked.connect(lambda:cls.submit(dialog,fields,submit))
        row.addWidget(cancel);row.addWidget(apply);footer.addLayout(row)
        dialog.setModal(True);dialog.show();Dialogs.foreground(dialog)
        owner._init_values_dialog=dialog
        return dialog

    @classmethod
    def highlight(cls,card,selected):
        background,border=("#594027","#f5b55b") if selected else ("#343440","#6b7280")
        card.setStyleSheet(f"QFrame#initTemperatureCard {{background:{background}; border:2px solid {border}; border-radius:6px;}}")

    @classmethod
    def submit(cls,dialog,fields,submit):
        chosen={name:edit.value() for name,(selected,edit) in fields.items() if selected.isChecked()}
        if not chosen:
            Dialogs.message("INIT-Größe auswählen","Bitte mindestens eine INIT-Größe auswählen.",dialog);return
        dialog.accept();submit(chosen)
