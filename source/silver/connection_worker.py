"""Silver API worker: packaged EXE or the vendor runtime during development."""
import json
import subprocess
import time
from contextlib import contextmanager
import os
from pathlib import Path
import sys

class SilverConnectionWorker:
    target=None
    overrides=set()
    remote=None
    DISCOVERY_TIMEOUT=120
    READY_TIMEOUT=180
    _pedal_names=None
    _pedal_target=None
    PEDAL_NAMES=("pos_BrakePedal_const","pos_AcceleratorPedal_const")

    @classmethod
    def load(cls,home):
        home=Path(home);os.environ['SILVER_HOME']=str(home)
        sys.path.insert(0,str(home/'lib/Pyro4.zip'))
        sys.path.insert(0,str(home/'common/ext-tools/python3/Lib/site-packages/synopsys/silver/remotescripting'))
        import silver_grpc,grpc
        cls.grpc_api=silver_grpc;cls.grpc=grpc

    @classmethod
    def connect(cls,request):
        path=str(Path(request['path']).resolve())
        candidates=request.get('existing',[])
        if candidates:
            return cls.reuse_existing(path,candidates)
        if not request.get('allow_start',True):raise RuntimeError('Das ausgewählte Setup ist nicht geöffnet.')
        if cls.remote is None:
            import remotesilverapi
            cls.remote=remotesilverapi
            cls.configure_launcher(cls.remote)
        target=cls.remote.RemoteSilver(sil=path,timeout=cls.DISCOVERY_TIMEOUT,stopped=False,gui=bool(request.get("gui",True)),silent=True)
        cls.target=target
        cls.wait_for_ready(target)
        return {'path':path,'reused':False,'pid':target._silver_process.pid,'headless':not bool(request.get('gui',True))}

    @classmethod
    def existing_ports(cls,candidate):
        try:import psutil
        except ModuleNotFoundError:
            # The vendor Python used in development does not ship psutil.
            # The parent already obtained these process-scoped listener ports.
            return candidate.get('ports',[])
        process=psutil.Process(candidate['pid'])
        created=candidate.get('created')
        if created is not None and abs(process.create_time()-created)>.01:
            raise RuntimeError("Der erkannte Silver-Prozess wurde inzwischen ersetzt. Bitte erneut verbinden.")
        return sorted({item.laddr.port for item in process.net_connections('tcp')
                       if item.status=='LISTEN' and item.laddr.ip in ('127.0.0.1','::1','0.0.0.0','::')})

    @classmethod
    def reuse_existing(cls,path,candidates):
        # Ports captured by the GUI may predate the scripting server. Refresh
        # only the identified Silver processes; never launch/close user setups.
        started=time.monotonic()
        retry=any(item.get('api_expected',False) for item in candidates)
        deadline=started+(min(cls.DISCOVERY_TIMEOUT,30) if retry else 0)
        last_error=None
        while True:
            for candidate in candidates:
                try:ports=cls.existing_ports(candidate)
                except Exception as error:
                    last_error=str(error);ports=[]
                cls.diagnostic(f"Attach: pid={candidate['pid']}, api_expected={candidate.get('api_expected')}, ports={ports}")
                for port in ports:
                    api=None
                    try:
                        api=cls.grpc_api.SilverApi(int(port))
                        cls.grpc.channel_ready_future(api.channel).result(timeout=1)
                        # A TCP/HTTP2 listener alone does not prove this is the
                        # scripting API. Read-only RPC, with a hard deadline.
                        api._simulation_control.StartedSuccessfully(cls.grpc_api.Empty(),timeout=2)
                        cls.target=api
                        cls.diagnostic(f"Attached: pid={candidate['pid']}, port={port}, elapsed={time.monotonic()-started:.1f}s")
                        return {'path':path,'reused':True,'pid':candidate['pid'],'headless':bool(candidate.get('headless',False))}
                    except Exception as error:
                        last_error=f"Port {port}: {type(error).__name__}: {error}"
                        if api is not None:api.channel.close()
            if time.monotonic()>=deadline:break
            time.sleep(.25)
        cls.diagnostic("Attach failed: "+str(last_error))
        if all(item.get('api_expected') is False for item in candidates):
            raise RuntimeError("Das Setup ist bereits in Silver geöffnet, wurde aber ohne aktivierte Remote-API gestartet. "
                               "Diese Instanz kann das Tool deshalb nicht steuern. Bitte den aktuellen Stand in Silver speichern, "
                               "diese Silver-Instanz schließen und im Tool Setup :: Verbinden/Starten anklicken. "
                               "Dabei wird die Remote-API automatisch aktiviert. Es wurde keine zweite Instanz gestartet.")
        raise RuntimeError("Das Setup ist bereits geöffnet, seine Remote-API wurde aber auch nach erneuter Prüfung nicht erreichbar. "
                           "Bitte Lade- oder Lizenzmeldungen in Silver prüfen und erneut verbinden. Details: silver_connection_worker.log. "
                           "Es wurde keine zweite Instanz gestartet.")

    @classmethod
    def wait_for_ready(cls,target):
        started=time.monotonic();deadline=started+cls.READY_TIMEOUT
        process=getattr(target,"_silver_process",None)
        pid=getattr(process,"pid",None)
        cls.diagnostic(f"Module readiness started: pid={pid}, timeout={cls.READY_TIMEOUT}s")
        last_error=None
        while True:
            try:
                if target.started_successfully():
                    cls.diagnostic(f"Modules ready: pid={pid}, elapsed={time.monotonic()-started:.1f}s")
                    return
            except (ConnectionError,TimeoutError) as error:
                if str(error)!=last_error:cls.diagnostic("Waiting for scripting API: "+str(error))
                last_error=str(error)
            if process is not None and process.poll() is not None:
                raise RuntimeError(f"Silver wurde während des Ladens beendet (Exitcode {process.returncode}). Details: silver_start.log und silver_connection_worker.log.")
            if time.monotonic()>=deadline:
                cls.diagnostic(f"Module readiness timed out: pid={pid}")
                raise RuntimeError(f"Silver hat das Laden der Module innerhalb von {cls.READY_TIMEOUT} Sekunden nicht bestätigt. Es wurde keine zweite Instanz gestartet. Bitte die Silver-Ladefehler prüfen; Details stehen in silver_start.log und silver_connection_worker.log."+(" Letzte API-Meldung: "+last_error if last_error else ""))
            time.sleep(0.25)

    @classmethod
    def diagnostic(cls,message):
        from datetime import datetime
        print(datetime.now().isoformat(timespec="seconds")+" "+message,file=sys.stderr,flush=True)

    @classmethod
    def configure_launcher(cls,module):
        from types import SimpleNamespace
        api={name:getattr(subprocess,name) for name in dir(subprocess) if not name.startswith("_")}
        api["Popen"]=cls.launch_silver
        # Isolate the vendor launcher; never replace subprocess.Popen globally.
        module.subprocess=SimpleNamespace(**api)

    @classmethod
    def external_environment(cls):
        env=dict(os.environ)
        for key in ("QT_PLUGIN_PATH","QT_QPA_PLATFORM_PLUGIN_PATH","QT_QPA_PLATFORM","QML2_IMPORT_PATH","QML_IMPORT_PATH","PYTHONHOME","PYTHONPATH"):
            env.pop(key,None)
        if getattr(sys,"frozen",False) or "__compiled__" in globals():
            bundle=Path(sys.executable).resolve().parent
            env["PATH"]=os.pathsep.join(value for value in env.get("PATH","").split(os.pathsep) if value and not Path(value.strip('"')).is_relative_to(bundle))
        return env

    @classmethod
    @contextmanager
    def external_dll_search(cls):
        if os.name!="nt":
            yield;return
        import ctypes
        from ctypes import wintypes
        kernel=ctypes.WinDLL("kernel32",use_last_error=True)
        kernel.GetDllDirectoryW.argtypes=[wintypes.DWORD,wintypes.LPWSTR]
        kernel.GetDllDirectoryW.restype=wintypes.DWORD
        kernel.SetDllDirectoryW.argtypes=[wintypes.LPCWSTR]
        kernel.SetDllDirectoryW.restype=wintypes.BOOL
        previous=ctypes.create_unicode_buffer(32768)
        kernel.GetDllDirectoryW(len(previous),previous)
        if not kernel.SetDllDirectoryW(None):raise ctypes.WinError(ctypes.get_last_error())
        try:yield
        finally:kernel.SetDllDirectoryW(previous.value or None)

    @classmethod
    def launch_silver(cls,command,*args,**kwargs):
        log_root=Path(os.environ.get("LOCALAPPDATA") or Path.home())/"siLAssistent"/"Logs"
        log_root.mkdir(parents=True,exist_ok=True)
        kwargs["creationflags"]=kwargs.get("creationflags",0)|getattr(subprocess,"CREATE_NO_WINDOW",0)
        kwargs["env"]=cls.external_environment()
        kwargs["stdin"]=subprocess.DEVNULL
        with (log_root/"silver_start.log").open("a",encoding="utf-8") as log:
            kwargs["stdout"]=log;kwargs["stderr"]=log
            # Nuitka's DLL directory must not be inherited by another Qt application.
            with cls.external_dll_search():return subprocess.Popen(command,*args,**kwargs)

    @classmethod
    def pedal_name(cls,name):
        prefix="mapping.mdl."
        short=name.removeprefix(prefix)
        if short not in cls.PEDAL_NAMES:return name
        if cls._pedal_target is not cls.target:
            cls._pedal_target=cls.target;cls._pedal_names=None
        if cls._pedal_names is None:
            # _const names may carry either variable or parameter flags.
            # Inspect names instead of probing values: zero/None is not absence.
            names=set(cls.target.get_variable_names())|set(cls.target.get_parameter_names())
            resolved={key:key if key in names else prefix+key for key in cls.PEDAL_NAMES}
            if names:cls._pedal_names=resolved
            return resolved[short]
        return cls._pedal_names[short]

    @classmethod
    def dispatch(cls,request):
        operation=request['op']
        if operation=='connect':return cls.connect(request)
        if operation=='release':return cls.release_overrides()
        if cls.target is None:raise RuntimeError('Keine Silver-Verbindung vorhanden.')
        if operation=='ping':
            api=getattr(cls.target,'target',cls.target)
            # API reachability is independent of stopped/unloaded simulation modules.
            cls.grpc.channel_ready_future(api.channel).result(timeout=3)
            return True
        if operation=='call':
            method=request['method']
            if not method.isidentifier() or method.startswith('_'):raise ValueError('Ungültige API-Methode.')
            args=list(request.get('args',[]));kwargs=dict(request.get('kwargs',{}))
            if method in ('reload','open','clear','stop'):
                cls._pedal_names=None
            if method in ('get_variable_value','set_variable_value'):
                if args:args[0]=cls.pedal_name(args[0])
                elif 'variable_name' in kwargs:kwargs['variable_name']=cls.pedal_name(kwargs['variable_name'])
            if method=='set_variable_value':
                name=args[0] if args else kwargs['variable_name']
                value=args[1] if len(args)>1 else kwargs.get('value')
                # Record before sending: the server might apply a write even if its reply is lost.
                if value is not None:cls.overrides.add(name)
            result=getattr(cls.target,method)(*args,**kwargs)
            if method=='set_variable_value' and value is None:cls.overrides.discard(name)
            if method=='reload':cls.overrides.clear()
            if method=='exit' and result is not False:
                cls.overrides.clear();cls.target=None
            return result
        raise ValueError('Unbekannter API-Auftrag.')

    @classmethod
    def release_overrides(cls):
        failures=[]
        if cls.target is None:return True
        for name in list(cls.overrides):
            try:
                cls.target.set_variable_value(name,None)
                cls.overrides.discard(name)
            except Exception:failures.append(name)
        if failures:raise RuntimeError("API-Vorgaben konnten nicht vollständig freigegeben werden: "+", ".join(failures)+". Bitte das Setup in Silver neu laden.")
        return True

    @classmethod
    def main(cls,home=None):
        cls.load(home or sys.argv[1])
        # GUI executables still receive redirected pipe handles from their parent.
        if sys.stdin is None:sys.stdin=open(0,"r",encoding="utf-8",closefd=False)
        if sys.stdout is None:sys.stdout=open(1,"w",encoding="utf-8",closefd=False)
        try:
            for line in sys.stdin:
                request=json.loads(line)
                if request['op']=='disconnect':break
                try:reply={'id':request['id'],'result':cls.dispatch(request),'error':None}
                except Exception as error:
                    import traceback
                    traceback.print_exc(file=sys.stderr)
                    reply={'id':request['id'],'result':None,'error':str(error)}
                print('SILASSISTENT_RPC '+json.dumps(reply,ensure_ascii=True),flush=True)
        finally:
            # Detach only. Never close an open user setup on disconnect or tool exit.
            if cls.target is not None:
                try:cls.release_overrides()
                except Exception as error:print(str(error),file=sys.stderr,flush=True)
                api=getattr(cls.target,'target',cls.target)
                try:api.channel.close()
                except Exception:pass

    @classmethod
    def self_test(cls,destination):
        import grpc
        import google.protobuf
        import os
        report={"pid":os.getpid(),"executable":sys.executable,"grpc":grpc.__version__,"protobuf":google.protobuf.__version__}
        if os.name=="nt":
            command=os.environ.get("COMSPEC") or str(Path(os.environ["WINDIR"])/"System32/cmd.exe")
            child=cls.launch_silver([command,"/d","/c","exit","0"])
            if child.wait(timeout=10)!=0:raise RuntimeError("External process launch failed")
        report["external_process"]=True
        # Exercise the same redirected stdin/stdout channel as the real worker.
        if sys.stdin is None:sys.stdin=open(0,"r",encoding="utf-8",closefd=False)
        if sys.stdout is None:sys.stdout=open(1,"w",encoding="utf-8",closefd=False)
        request=json.loads(sys.stdin.readline())
        if request!={"op":"self_test"}:raise RuntimeError("Worker input pipe failed")
        print("SILASSISTENT_RPC "+json.dumps({"result":"worker_ok"}),flush=True)
        Path(destination).write_text(json.dumps(report),encoding="utf-8")
        return 0

if __name__=='__main__':SilverConnectionWorker.main()
