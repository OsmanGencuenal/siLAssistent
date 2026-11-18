"""PySide6 range settings for map sweeps."""
from PySide6.QtCore import QLocale
from PySide6.QtWidgets import QWidget,QVBoxLayout,QGridLayout,QGroupBox,QLabel,QDoubleSpinBox,QPushButton,QHBoxLayout

class MapSweepPanel:
    @classmethod
    def create(cls):
        panel=QWidget();layout=QVBoxLayout(panel);layout.setContentsMargins(0,0,0,0)
        from ..ui.field_colors import FieldColors
        panel.fields={}
        for title,prefix,unit,defaults,maximum in (("Drehzahlbereich","rpm","rpm",(1000,6000,500),30000),("Pedalposition","pedal","",(0,1,0.1),1)):
            group=FieldColors.group(title,"rpm" if prefix=="rpm" else "pedal")
            grid=QGridLayout(group)
            for index,(key,label,value) in enumerate(zip(("from","to","step"),("Von","Bis","Schrittweite"),defaults)):
                spin=QDoubleSpinBox();spin.setLocale(QLocale.c());spin.setDecimals(2);spin.setRange(0 if key!="step" else 0.01,maximum);spin.setValue(value);spin.setSuffix(" "+unit if unit else "")
                spin.setStyleSheet(FieldColors.field("rpm" if prefix=="rpm" else "pedal","QDoubleSpinBox"))
                panel.fields[prefix+"_"+key]=spin
                grid.addWidget(QLabel(label+(" ["+unit+"]" if unit else "")+":"),index//2,(index%2)*2)
                grid.addWidget(spin,index//2,(index%2)*2+1)
            layout.addWidget(group)
        times=QHBoxLayout()
        for key,title,default,minimum in (("settle","Einregelzeit",1.5,0),("dwell","Wartezeit je Messpunkt",10,0.01)):
            group=FieldColors.group(title,"time");box=QVBoxLayout(group)
            box.addWidget(QLabel("Simulationssekunden:"))
            spin=QDoubleSpinBox();spin.setLocale(QLocale.c());spin.setRange(minimum,3600);spin.setValue(default);spin.setSuffix(" s")
            spin.setStyleSheet(FieldColors.field("time","QDoubleSpinBox"));panel.fields[key]=spin;box.addWidget(spin);times.addWidget(group,1)
        layout.addLayout(times)
        panel.cancel=QPushButton("Rasterung abbrechen");panel.cancel.setStyleSheet("background:#fecaca; color:#172554; font-weight:700;");panel.cancel.setEnabled(False);layout.addWidget(panel.cancel)
        return panel

    @classmethod
    def values(cls,panel):return {key:field.value() for key,field in panel.fields.items()}
