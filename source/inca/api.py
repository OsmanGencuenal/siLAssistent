"""INCA COM sessions. Public operations are class methods; handles stay explicit."""
import threading
import logging
from ..core.errors import ConnectionError, ApiCallError, ThreadAffinityError

class Inca:
    _sessions = {}

    @classmethod
    def connect(cls, session="default", prog_id="INCA.INCA", *, attach=False, application=None):
        if session in cls._sessions:
            raise ConnectionError(f"INCA session already exists: {session}")
        initialized = False
        pythoncom = None
        if application is None:
            try:
                import pythoncom
                import win32com.client
                pythoncom.CoInitialize()
                initialized = True
                application = (win32com.client.GetActiveObject(prog_id) if attach
                               else win32com.client.Dispatch(prog_id))
            except Exception as error:
                if initialized:
                    pythoncom.CoUninitialize()
                raise ConnectionError(f"INCA COM connection failed ({prog_id}): {error}") from error
        cls._sessions[session] = {"application": application, "thread": threading.get_ident(),
                                  "com": pythoncom if initialized else None}
        return application

    @classmethod
    def application(cls, session="default"):
        try:
            state = cls._sessions[session]
        except KeyError as error:
            raise ConnectionError(f"INCA is not connected: {session}") from error
        if state["thread"] != threading.get_ident():
            raise ThreadAffinityError("Use INCA COM handles only on their creating thread.")
        return state["application"]

    @classmethod
    def invoke(cls, target, method, *args, session="default", **kwargs):
        cls.application(session)  # validates both connection and COM thread affinity
        if target is None:
            raise ConnectionError(f"INCA target is None for {method}")
        if not method.isidentifier() or method.startswith("_"):
            raise ValueError("Invalid vendor member name")
        try:
            member = getattr(target, method)
            if callable(member):
                return member(*args, **kwargs)
            if args or kwargs:
                raise TypeError(f"{method} is a property, not a method")
            return member
        except Exception as error:
            logging.getLogger("siLAssistent").error("INCA.%s failed: %s", method, error)
            raise ApiCallError(f"INCA.{method}: {error}") from error

    @classmethod
    def call(cls, method, *args, session="default", target=None, **kwargs):
        if target is None:
            target = cls.application(session)
        return cls.invoke(target, method, *args, session=session, **kwargs)

    @classmethod
    def disconnect(cls, session="default"):
        application = cls.application(session)
        state = cls._sessions[session]
        try:
            cls.invoke(application, "DisconnectFromTool", session=session)
        finally:
            del cls._sessions[session]
            if state["com"] is not None:
                state["com"].CoUninitialize()

    @classmethod
    def open_database(cls, path, session="default"):
        return cls.call("OpenDataBase", str(path), session=session)

    @classmethod
    def database(cls, session="default"):
        return cls.call("GetCurrentDataBase", session=session)

    @classmethod
    def open_experiment(cls, name, folder, workspace=None, session="default"):
        database = cls.database(session)
        item = cls.invoke(database, "GetItemInFolder", name, folder, session=session)
        if workspace is not None:
            result = cls.invoke(item, "SetHardwareConfiguration", workspace, session=session)
            if result is False:
                raise ApiCallError("INCA rejected the hardware configuration")
        view = cls.invoke(item, "OpenExperiment", session=session)
        experiment = cls.invoke(view, "GetExperiment", session=session)
        return {"item": item, "view": view, "experiment": experiment}

    @classmethod
    def read_calibration(cls, experiment, name, *, device=None, session="default"):
        element = (cls.invoke(experiment, "GetCalibrationElement", name, session=session) if device is None
                   else cls.invoke(experiment, "GetCalibrationElementInDevice", name, device, session=session))
        value = cls.invoke(element, "GetValue", session=session)
        return cls.invoke(value, "GetDoublePhysValue", session=session)

    @classmethod
    def write_calibration(cls, experiment, name, value, *, device=None, session="default"):
        element = (cls.invoke(experiment, "GetCalibrationElement", name, session=session) if device is None
                   else cls.invoke(experiment, "GetCalibrationElementInDevice", name, device, session=session))
        data = cls.invoke(element, "GetValue", session=session)
        result = cls.invoke(data, "SetDoublePhysValue", value, session=session)
        if result is False:
            raise ApiCallError(f"INCA rejected calibration write: {name}")
        return result
