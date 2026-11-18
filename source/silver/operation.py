"""Setup operation sequences using our central Silver classmethod API."""
import time
from .methods import Silver

class SilverOperation:
    SESSION="setup-control"
    PREFIX="mapping.mdl."
    _requested_pause=None
    _log_messages=None
    _last_sim_time=None
    _last_sim_change=None

    @classmethod
    def read(cls,name):
        return float(Silver.get_variable_value(name,session=cls.SESSION))

    @classmethod
    def write(cls,name,value):
        result=Silver.set_variable_value(name,value,session=cls.SESSION)
        if result is False:raise RuntimeError("Silver konnte den Wert nicht setzen: "+name)
        cls.log(cls.describe_write(name,value))

    @classmethod
    def log(cls,message):
        if cls._log_messages is not None:cls._log_messages.put(("log",None,message))

    @classmethod
    def describe_write(cls,name,value):
        key=name.removeprefix(cls.PREFIX)
        labels={"pos_IgnitionSwitch_const":"Klemme 15","pos_Starter_const":"Starter","n_EngineSpeed_const":"Drehzahlvorgabe","pos_AcceleratorPedal_const":"Gas-Pedal","pos_BrakePedal_const":"Brems-Pedal","pos_Selector_const":"Gang","Parameters_SSA_Enbl_Rq_TCM":"Start-Stop","DriveCycleIdxGui":"Fahrzyklus"}
        label=labels.get(key,key)
        if value is None:return label+": API-Vorgabe freigegeben."
        if key in ("pos_IgnitionSwitch_const","pos_Starter_const"):shown="AN" if value>0.5 else "AUS"
        elif key in ("pos_AcceleratorPedal_const","pos_BrakePedal_const"):shown=f"{value*100:g} %"
        elif key=="n_EngineSpeed_const":shown=f"{value:g} rpm"
        elif key=="pos_Selector_const":shown={-2:"P",-1:"R",0:"N",5:"D"}.get(value,str(value))
        elif key=="Parameters_SSA_Enbl_Rq_TCM":shown={1:"Nicht aktiv",2:"Aktiv"}.get(value,str(value))
        elif key.endswith("_mode"):
            label={"n_EngineSpeed_mode":"Drehzahl-Modus","pos_IgnitionSwitch_mode":"Zündungs-Modus","pos_AcceleratorPedal_mode":"Gas-Pedal-Modus","pos_BrakePedal_mode":"Brems-Pedal-Modus","pos_Selector_mode":"Gangwahl-Modus","pos_GearShift_mode":"Gang-Modus"}.get(key,key)
            shown=("Manuell" if value==0 else "Modell" if key=="n_EngineSpeed_mode" and value==2 else "Wert "+str(value))+f" ({value:g})"
        else:shown=str(value)
        return label+": "+shown

    @classmethod
    def wait_above(cls,name,threshold,cancelled=None,timeout=30):
        deadline=time.monotonic()+timeout
        while True:
            if cancelled is not None and cancelled.is_set():raise RuntimeError("Aktion wurde abgebrochen.")
            if cls.read(name)>threshold:return
            if time.monotonic()>=deadline:
                if name in ("n_EngineSpeed",cls.PREFIX+"n_EngineSpeed_const") and threshold==300:
                    raise RuntimeError("Motor ist nicht gestartet.")
                raise RuntimeError(f"Zeitüberschreitung: {name} erreicht nicht den erforderlichen Wert > {threshold}.")
            time.sleep(0.1)

    @classmethod
    def ignition(cls,cancelled=None):
        name=cls.PREFIX+"pos_IgnitionSwitch_const"
        if cls.read(name)<=0.5:cls.write(name,1)
        cls.wait_above(name,0.5,cancelled)

    @classmethod
    def simulation_running(cls):
        # No advancing time is inconclusive (slow/busy simulation), not proof
        # that Silver is stopped. Only ask to start for a confirmed stopped state.
        if not Silver.started_successfully(session=cls.SESSION):return False
        previous=float(Silver.get_time(session=cls.SESSION))
        deadline=time.monotonic()+1
        while time.monotonic()<deadline:
            time.sleep(0.1)
            current=float(Silver.get_time(session=cls.SESSION))
            if current!=previous:
                cls._requested_pause=False
                return True
        return False if cls._requested_pause is True else None

    @classmethod
    def sample_simulation_state(cls):
        # One API sample per idle update; never sleep on the command-owning thread.
        current=float(Silver.get_time(session=cls.SESSION));now=time.monotonic()
        if cls._last_sim_time is None or current<cls._last_sim_time:
            cls._last_sim_time=current;cls._last_sim_change=now
            return None if cls._requested_pause is None else not cls._requested_pause
        if current>cls._last_sim_time:
            cls._last_sim_time=current;cls._last_sim_change=now;cls._requested_pause=False
            return True
        if cls._requested_pause is True:return False
        if cls._last_sim_change is not None and now-cls._last_sim_change>=2:
            return False if cls._requested_pause is None else None
        return None if cls._requested_pause is None else not cls._requested_pause

    @classmethod
    def needs_simulation_start_check(cls,action):
        if action=="ignition":return cls.read(cls.PREFIX+"pos_IgnitionSwitch_const")<=0.5
        return action in ("engine","ignition_engine")

    @classmethod
    def toggle_ignition(cls):
        name=cls.PREFIX+"pos_IgnitionSwitch_const"
        cls.write(name,0 if cls.read(name)>0.5 else 1)

    @classmethod
    def ignition_and_motor_start(cls,cancelled=None):
        cls.ignition(cancelled)
        cls.motor_start(cancelled)

    @classmethod
    def motor_start(cls,cancelled=None):
        if cls.read(cls.PREFIX+"pos_IgnitionSwitch_const")<=0.5:
            raise RuntimeError("Zündung ist nicht AN! Motor kann nicht gestartet werden")
        name="n_EngineSpeed"
        try:
            if cls.read(name)<=300:
                cls.write(cls.PREFIX+"pos_Starter_const",1)
                cls.wait_above(name,300,cancelled)
        finally:cls.write(cls.PREFIX+"pos_Starter_const",0)

    @classmethod
    def clear_errors(cls,cancelled=None,pulse_seconds=1.0):
        master="Master_DSMAUX_xClearTrg_C"
        slave="Slave_DSMAUX_xClearTrg_C"
        try:
            cls.write(master,255)
            cls.write(slave,255)
            if cancelled is None:time.sleep(pulse_seconds)
            else:cancelled.wait(pulse_seconds)
        finally:
            try:cls.write(master,0)
            finally:cls.write(slave,0)

    @classmethod
    def toggle_start_stop(cls):
        name="Parameters_SSA_Enbl_Rq_TCM"
        value=cls.read(name)
        if value not in (1,2):raise RuntimeError("Unbekannter Start-Stop-Zustand: "+str(value))
        cls.write(name,1 if value==2 else 2)

    @classmethod
    def states(cls):
        values={"ignition":cls.read(cls.PREFIX+"pos_IgnitionSwitch_const")>0.5,
                "engine":cls.read("n_EngineSpeed")>300}
        try:
            value=cls.read("Parameters_SSA_Enbl_Rq_TCM")
            values["start_stop"]=value==2 if value in (1,2) else None
        except Exception:values["start_stop"]=None
        return values

    @classmethod
    def startEngine(cls,cancelled=None):
        cls.ignition(cancelled)
        if cls.read("n_EngineSpeed")<=300:
            try:
                cls.write(cls.PREFIX+"pos_Starter_const",1)
                cls.wait_above("n_EngineSpeed",300,cancelled)
            finally:cls.write(cls.PREFIX+"pos_Starter_const",0)
        else:cls.write(cls.PREFIX+"pos_Starter_const",0)
        return cls.read(cls.PREFIX+"pos_IgnitionSwitch_const")>0.5 and cls.read("n_EngineSpeed")>300

    @classmethod
    def wait_equal(cls,name,value,cancelled=None,timeout=10):
        deadline=time.monotonic()+timeout
        while True:
            if cancelled is not None and cancelled.is_set():raise RuntimeError("Aktion wurde abgebrochen.")
            if abs(cls.read(name)-value)<0.01:return
            if time.monotonic()>=deadline:raise RuntimeError("Initialisierung wurde nicht bestätigt: "+name)
            time.sleep(0.1)

    @classmethod
    def initialize_imo(cls,cancelled=None):
        # Leave the user's ignition, SSA and engine state unchanged.
        cls.write(cls.PREFIX+"pos_AcceleratorPedal_const",0)
        cls.switchGear("P",cancelled)
        cls.wait_equal(cls.PREFIX+"pos_Selector_const",-2,cancelled)

    @classmethod
    def switchGear(cls,gear,cancelled=None):
        gears={"R":-1,"N":0,"D":5,"P":-2}
        if gear not in gears:raise ValueError("Gang muss R, N, D oder P sein.")
        cls.write(cls.PREFIX+"pos_BrakePedal_const",100)
        cls.wait_above(cls.PREFIX+"pos_BrakePedal_const",0.4,cancelled)
        cls.write(cls.PREFIX+"pos_Selector_const",gears[gear])

    CYCLES={"NEDC":13,"FTP75":5,"US06":10,"WLTP":8}
    INPUTS={"rpm":"n_EngineSpeed_const","accelerator":"pos_AcceleratorPedal_const","brake":"pos_BrakePedal_const"}

    @classmethod
    def input_values(cls):
        values={key:cls.read(cls.PREFIX+name) for key,name in cls.INPUTS.items()}
        values["gear"]=cls.read(cls.PREFIX+"pos_Selector_const")
        return values

    @classmethod
    def parse_input(cls,name,value):
        import math
        if name not in cls.INPUTS:raise ValueError("Unbekanntes Eingabefeld.")
        value=float(str(value).replace(",","."))
        if not math.isfinite(value) or value<0 or (name!="rpm" and value>100):
            raise ValueError("Bitte einen gültigen Wert eingeben: Drehzahl ≥ 0, Pedalstellung zwischen 0 und 100.")
        return value

    @classmethod
    def set_input(cls,name,value):
        cls.write(cls.PREFIX+cls.INPUTS[name],cls.parse_input(name,value))

    @classmethod
    def set_inputs(cls,values):
        validated={key:cls.parse_input(key,value) for key,value in values.items()}
        for key,value in validated.items():cls.write(cls.PREFIX+cls.INPUTS[key],value)

    @classmethod
    def set_paused(cls,paused):
        result=Silver.pause(session=cls.SESSION) if paused else Silver.run(session=cls.SESSION)
        if result is False:raise RuntimeError("Silver hat den Simulationswechsel nicht bestätigt.")
        cls._requested_pause=paused
        # The next sample must not compare against a time recorded before pause/run.
        cls._last_sim_time=None;cls._last_sim_change=time.monotonic()
        cls.log("Simulation pausiert." if paused else "Simulation gestartet/fortgesetzt.")

    @classmethod
    def set_cycle(cls,name):
        if name not in cls.CYCLES:raise ValueError("Unbekannter Fahrzyklus.")
        cls.write("DriveCycleIdxGui",cls.CYCLES[name])

    @classmethod
    def reload_setup(cls,cancelled=None):
        cls.log("Setup wird neu geladen.")
        try:
            Silver.reload(session=cls.SESSION)
            deadline=time.monotonic()+180
            while not Silver.started_successfully(session=cls.SESSION):
                if cancelled is not None and cancelled.is_set():raise RuntimeError("Aktion wurde abgebrochen.")
                if time.monotonic()>=deadline:raise RuntimeError("Ladezeit überschritten.")
                time.sleep(0.2)
        except Exception as error:raise RuntimeError("Setup ist nicht erfolgreich geladen.") from error

    @classmethod
    def start_mode(cls,mode,cancelled=None,cycle=None):
        if mode not in ("Test-Bench","IMO","Zyklus"):raise ValueError("Unbekannter Betriebsmode.")
        try:
            # Readiness is separate from advancing simulation time: a loaded,
            # paused setup must resume directly without rebuilding modules.
            if not Silver.started_successfully(session=cls.SESSION):
                Silver.reload(session=cls.SESSION)
            if mode=="Zyklus" and cycle is not None:cls.set_cycle(cycle)
            Silver.run(session=cls.SESSION)
            cls._requested_pause=False
            deadline=time.monotonic()+180
            while not Silver.started_successfully(session=cls.SESSION):
                if cancelled is not None and cancelled.is_set():raise RuntimeError("Aktion wurde abgebrochen.")
                if time.monotonic()>=deadline:raise RuntimeError("Zeitüberschreitung beim Laden.")
                time.sleep(0.2)
        except Exception as error:
            raise RuntimeError("Setup ist nicht erfolgreich geladen. Bitte Silver und die Setup-Konfiguration prüfen.") from error
        cls.log("Betriebsmode wird aktiviert: "+mode)
        if mode=="Test-Bench":
            # Test-bench rpm is imposed externally. Leaving IMO's Model mode
            # selected can keep the standstill engine at zero despite the starter.
            try:
                current_rpm=cls.read("n_EngineSpeed")
                import math
                if not math.isfinite(current_rpm):raise RuntimeError("Die aktuelle Motordrehzahl konnte nicht gelesen werden.")
                initial_rpm=current_rpm if current_rpm>300 else 750
                cls.write(cls.PREFIX+"pos_IgnitionSwitch_mode",0)
                cls.write(cls.PREFIX+"pos_AcceleratorPedal_mode",0)
                cls.write(cls.PREFIX+"pos_BrakePedal_mode",0)
                cls.write(cls.PREFIX+"pos_Selector_mode",0)
                cls.write(cls.PREFIX+"n_EngineSpeed_const",initial_rpm)
                cls.write(cls.PREFIX+"n_EngineSpeed_mode",0)
                if not cls.startEngine(cancelled):raise RuntimeError("Der Motorstart konnte nicht bestätigt werden.")
                cls.switchGear("D",cancelled)
                cls.wait_above(cls.PREFIX+"pos_Selector_const",4,cancelled)
                cls.write(cls.PREFIX+"pos_BrakePedal_const",0)
            except Exception:
                try:cls.write(cls.PREFIX+"n_EngineSpeed_const",None)
                finally:cls.write(cls.PREFIX+"n_EngineSpeed_mode",None)
                raise
        elif mode=="IMO":
            cls.write("Parameters.v_TargetSpeed_mode_GUI",0)
            for name,value in (("pos_IgnitionSwitch_mode",0),("pos_AcceleratorPedal_mode",0),("pos_BrakePedal_mode",0),("pos_Selector_mode",0),("n_EngineSpeed_mode",2),("pos_GearShift_mode",2)):
                cls.write(cls.PREFIX+name,value)
            cls.initialize_imo(cancelled)
        else:cls.write("Parameters.v_TargetSpeed_mode_GUI",100)
        cls.log("Betriebsmode aktiv: "+mode)

    INIT_TEMPERATURES=("T_Engine","T_Oil","T_WaterEngine")

    @classmethod
    def init_defaults(cls):
        return {name:cls.read(cls.PREFIX+name+"_const") for name in cls.INIT_TEMPERATURES}

    @classmethod
    def set_init_values(cls,values,cancelled=None,timeout=60):
        import math
        if not values:raise ValueError("Bitte mindestens eine INIT-Größe auswählen.")
        targets={}
        for name,value in values.items():
            if name not in cls.INIT_TEMPERATURES:raise ValueError("Unbekannte INIT-Größe: "+name)
            value=float(value)
            if not math.isfinite(value):raise ValueError("Bitte gültige INIT-Werte eingeben.")
            targets[name]=value
        running=cls.simulation_running()
        if running is None:
            # Confirm an externally paused setup using a second observation window.
            previous=float(Silver.get_time(session=cls.SESSION));deadline=time.monotonic()+2
            running=False
            while time.monotonic()<deadline:
                if cancelled is not None and cancelled.is_set():raise RuntimeError("INIT-Vorgabe abgebrochen.")
                time.sleep(0.1)
                if float(Silver.get_time(session=cls.SESSION))>previous:running=True;break
        manual=[];started_here=False
        try:
            for name,value in targets.items():cls.write(cls.PREFIX+name+"_const",value)
            if not running:
                started_here=True;cls.set_paused(False)
            for name in targets:
                manual.append(name);cls.write(cls.PREFIX+name+"_mode",0)
            pending=set(targets);deadline=time.monotonic()+timeout
            while pending:
                if cancelled is not None and cancelled.is_set():raise RuntimeError("INIT-Vorgabe abgebrochen.")
                for name in tuple(pending):
                    actual=cls.read(name);tolerance=max(abs(targets[name])*0.01,1e-6)
                    if math.isfinite(actual) and abs(actual-targets[name])<=tolerance:
                        cls.write(cls.PREFIX+name+"_mode",2);manual.remove(name);pending.remove(name)
                if not pending:break
                if time.monotonic()>=deadline:raise RuntimeError("INIT-Zielwert wurde nicht innerhalb ±1 % erreicht: "+", ".join(sorted(pending)))
                time.sleep(0.1)
        finally:
            try:
                failures=[]
                for name in manual:
                    try:cls.write(cls.PREFIX+name+"_mode",2)
                    except Exception as error:failures.append(str(error))
                if failures:raise RuntimeError("INIT-Modus konnte nicht zurückgesetzt werden: "+"; ".join(failures))
            finally:
                if started_here:cls.set_paused(True)
