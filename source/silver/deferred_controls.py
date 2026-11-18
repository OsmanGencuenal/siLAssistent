"""Defer control confirmation and pulse cleanup until simulation time advances."""
import time
from .operation import SilverOperation as Op
from .methods import Silver

class SilverDeferredControls:
    ACTIONS=frozenset(("ignition","engine","ignition_engine","start_stop","clear_errors"))
    values={}
    pending={}
    active=False
    deadline=None
    pulse_until=None

    @classmethod
    def reset(cls):
        cls.values={};cls.pending={};cls.active=False;cls.deadline=None;cls.pulse_until=None

    @classmethod
    def current(cls,name,default):
        if name in cls.values:return cls.values[name]
        try:return Op.read(name)
        except (TypeError,ValueError):return default

    @classmethod
    def stage(cls,action):
        if action not in cls.ACTIONS:raise ValueError("Aktion kann nicht vorgemerkt werden.")
        if action in ("ignition","ignition_engine"):
            key=Op.PREFIX+"pos_IgnitionSwitch_const"
            value=1 if action=="ignition_engine" else (0 if cls.current(key,0)>0.5 else 1)
            cls.values[Op.PREFIX+"pos_IgnitionSwitch_mode"]=0
            cls.values[key]=value;cls.pending["ignition"]=value
        if action in ("engine","ignition_engine"):
            cls.values[Op.PREFIX+"pos_Starter_const"]=1;cls.pending["engine"]=True
        if action=="start_stop":
            key="Parameters_SSA_Enbl_Rq_TCM"
            value=1 if cls.current(key,1)==2 else 2
            cls.values[key]=value;cls.pending["start_stop"]=value
        if action=="clear_errors":
            for key in ("Master_DSMAUX_xClearTrg_C","Slave_DSMAUX_xClearTrg_C"):cls.values[key]=255
            cls.pending["clear_errors"]=True
        cls.active=False;cls.deadline=None;cls.pulse_until=None
        # An unloaded setup can reset/ignore overrides; retain them for the first running step.
        if Silver.started_successfully(session=Op.SESSION):cls.write_values()
        return list(cls.pending)

    @classmethod
    def write_values(cls):
        for name,value in cls.values.items():Op.write(name,value)

    @classmethod
    def tick(cls,running):
        if not cls.pending:return []
        if running is not True:
            cls.active=False;cls.deadline=None;cls.pulse_until=None
            return list(cls.pending)
        if not cls.active:
            cls.write_values();cls.active=True;cls.deadline=time.monotonic()+30
            if "clear_errors" in cls.pending:cls.pulse_until=float(Silver.get_time(session=Op.SESSION))+1
            # Readback before the next simulation step could still contain old outputs.
            return list(cls.pending)
        if "ignition" in cls.pending:
            if (Op.read(Op.PREFIX+"pos_IgnitionSwitch_const")>0.5)==bool(cls.pending["ignition"]):
                cls.pending.pop("ignition")
        if "start_stop" in cls.pending:
            if Op.read("Parameters_SSA_Enbl_Rq_TCM")==cls.pending["start_stop"]:cls.pending.pop("start_stop")
        if "engine" in cls.pending and Op.read("n_EngineSpeed")>300:
            Op.write(Op.PREFIX+"pos_Starter_const",0)
            cls.values.pop(Op.PREFIX+"pos_Starter_const",None);cls.pending.pop("engine")
        if "clear_errors" in cls.pending and float(Silver.get_time(session=Op.SESSION))>=cls.pulse_until:
            cls.clear_pulses(errors_only=True);cls.pending.pop("clear_errors")
        if cls.pending and time.monotonic()>=cls.deadline:
            pending=set(cls.pending)
            try:cls.clear_pulses()
            finally:cls.reset()
            if "engine" in pending:raise RuntimeError("Motor ist nicht gestartet.")
            raise RuntimeError("Die vorgemerkten Werte wurden von der laufenden Simulation nicht bestätigt.")
        if not cls.pending:cls.reset()
        return list(cls.pending)

    @classmethod
    def clear_pulses(cls,errors_only=False):
        names=[]
        if not errors_only and "engine" in cls.pending:names.append(Op.PREFIX+"pos_Starter_const")
        if "clear_errors" in cls.pending:names.extend(("Master_DSMAUX_xClearTrg_C","Slave_DSMAUX_xClearTrg_C"))
        failures=[]
        for name in names:
            try:Op.write(name,0);cls.values.pop(name,None)
            except Exception as error:failures.append(str(error))
        if failures:raise RuntimeError("Vorgemerkte Impulse konnten nicht zurückgesetzt werden: "+"; ".join(failures))
