"""Cancellable rpm/pedal sweep using the existing Silver API session."""
import math,time
from .methods import Silver
from .operation import SilverOperation as Op

class MapSweepCancelled(RuntimeError):
    pass

class MapSweep:
    @classmethod
    def axis(cls,start,end,step):
        from decimal import Decimal,ROUND_CEILING
        first,last,increment=(Decimal(str(value)) for value in (start,end,step))
        count=int(((last-first)/increment).to_integral_value(rounding=ROUND_CEILING))
        return [float(min(first+i*increment,last)) for i in range(count+1)]

    @classmethod
    def validate(cls,settings):
        keys=("rpm_from","rpm_to","rpm_step","pedal_from","pedal_to","pedal_step","dwell")
        values={key:float(settings[key]) for key in keys}
        values["settle"]=float(settings.get("settle",1.5))
        if not all(math.isfinite(v) for v in values.values()):raise ValueError("Bitte endliche Zahlen eingeben.")
        if not 300<values["rpm_from"]<=values["rpm_to"]:raise ValueError("Drehzahl: Von muss über 300 liegen und darf Bis nicht überschreiten.")
        if not 0<=values["pedal_from"]<=values["pedal_to"]<=1:raise ValueError("Pedalbereich muss zwischen 0 und 1 liegen.")
        if values["rpm_step"]<=0 or values["pedal_step"]<=0 or values["dwell"]<=0:raise ValueError("Schrittweiten und Wartezeit müssen größer als 0 sein.")
        if values["settle"]<0:raise ValueError("Die Einregelzeit darf nicht negativ sein.")
        count=(math.ceil((values["rpm_to"]-values["rpm_from"])/values["rpm_step"])+1)*(math.ceil((values["pedal_to"]-values["pedal_from"])/values["pedal_step"])+1)
        if count>100000:raise ValueError("Das Raster ist zu groß. Bitte größere Schrittweiten wählen.")
        return values

    @classmethod
    def check_cancel(cls,cancelled,closing):
        if any(event is not None and event.is_set() for event in (cancelled,closing)):
            raise MapSweepCancelled("Kennfeld-Rasterung abgebrochen.")

    @classmethod
    def wait_simulation(cls,seconds,cancelled=None,closing=None,control=None):
        previous=float(Silver.get_time(session=Op.SESSION));target=previous+seconds
        stalled=time.monotonic()
        while previous<target:
            cls.check_cancel(cancelled,closing)
            if control is not None and control():
                stalled=time.monotonic();time.sleep(0.05);continue
            current=float(Silver.get_time(session=Op.SESSION))
            if not math.isfinite(current) or current<previous:raise RuntimeError("Simulationszeit wurde zurückgesetzt oder ist ungültig.")
            if current>previous:stalled=time.monotonic()
            elif time.monotonic()-stalled>15:raise RuntimeError("Die Simulationszeit steht. Bitte pausierte Simulation oder Silver prüfen.")
            previous=current
            time.sleep(0.05)

    @classmethod
    def run(cls,settings,log,cancelled=None,closing=None,control=None):
        values=cls.validate(settings)
        rpms=cls.axis(values["rpm_from"],values["rpm_to"],values["rpm_step"])
        pedals=cls.axis(values["pedal_from"],values["pedal_to"],values["pedal_step"])
        cls.check_cancel(cancelled,closing)
        initialized=False
        try:
            Op.write("Parameters_SSA_Enbl_Rq_TCM",1)
            Op.start_mode("Test-Bench",closing);initialized=True
            point=0
            for rpm in rpms:
                for pedal in pedals:
                    cls.check_cancel(cancelled,closing)
                    Op.set_inputs({"rpm":rpm,"accelerator":pedal})
                    point+=1
                    log(f"Drehzahl: {rpm:g} rpm | Pedal: {pedal:g}")
                    for seconds in (values["settle"],values["dwell"]):
                        if control is None:cls.wait_simulation(seconds,cancelled,closing)
                        else:cls.wait_simulation(seconds,cancelled,closing,control)
                    cls.check_cancel(cancelled,closing)
                    torque=Op.read("HW__ICE__CrkShftTq_M")
                    log(f"Drehzahl: {rpm:g} rpm | Pedal: {pedal:g} | HW__ICE__CrkShftTq_M: {torque:g}")
        finally:
            if initialized:Op.write(Op.PREFIX+"pos_AcceleratorPedal_const",0)
