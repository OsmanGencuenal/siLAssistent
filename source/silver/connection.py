"""Thread-owned connection to the exact selected setup through Silver's bundled runtime."""
import functools
import json
import os
from pathlib import Path
import queue
import subprocess
import sys
import threading
import time
import uuid
from types import SimpleNamespace
from ..core.runtime import Runtime
from ..core.config import Config
from .api import Silver as SilverApi

class SilverStartCancelled(RuntimeError):
    pass

class SilverConnection:
    _process=None
    _messages=None
    _session='setup-control'
    _silver_pid=None
    _headless=False
    _silver_closed=False
    _setup_path=None
    _detach=threading.Event()

    @classmethod
    def running_setups(cls):
        import psutil
        matches=[]
        owner=psutil.Process().username().casefold()
        for process in psutil.process_iter(['pid','name']):
            if (process.info['name'] or '').casefold() not in ('silver.exe','silver.com','silver2.exe','silver2.com','silver3.exe','silver3.com','silversim.exe','silversim.com'):continue
            try:
                if process.username().casefold()!=owner:continue
                exe=Path(process.exe());cwd=Path(process.cwd());args=process.cmdline()
                setup=None
                for arg in args[1:]:
                    item=Path(arg.strip('"'))
                    if item.suffix.casefold()=='.sil':
                        setup=(item if item.is_absolute() else cwd/item).resolve()
                        break
                ports=sorted({c.laddr.port for c in process.net_connections('tcp') if c.status=='LISTEN' and c.laddr.ip in ('127.0.0.1','::1','0.0.0.0','::')})
                if setup is not None:matches.append({'pid':process.pid,'path':str(setup),'ports':ports,'home':str(exe.parent.parent),'headless':any(arg.casefold()=='--nogui' for arg in args) or exe.stem.casefold().startswith('silversim')})
            except (psutil.NoSuchProcess,psutil.AccessDenied,OSError):continue
        return matches

    @classmethod
    def home(cls,existing):
        if existing:return Path(existing[0]['home'])
        homes=SilverApi.installations()
        if not homes:raise RuntimeError('Silver ist nicht lokal installiert oder seine Installation wurde nicht gefunden.')
        # Prefer the newest installed release, not an inherited SILVER_HOME pointing at an old one.
        from .updates import SilverUpdates
        import re
        return max((Path(home) for home in homes),key=lambda home:tuple(int(v) for v in re.findall(r'\d+',SilverUpdates.version_label(home.name) or '0')))

    @classmethod
    def read_output(cls,stream,messages):
        for line in stream:
            if line.startswith('SILASSISTENT_RPC '):
                try:messages.put(json.loads(line[len('SILASSISTENT_RPC '):]))
                except ValueError:pass
            elif line.strip():
                from datetime import datetime
                with (Runtime.data_root()/"silver_connection_worker.log").open("a",encoding="utf-8") as log:
                    log.write(datetime.now().isoformat(timespec="seconds")+" [Silver start] "+line)
        messages.put({'error':'Die Silver-API-Verbindung wurde beendet.','id':None})

    @classmethod
    def rpc(cls,operation,timeout=10,cancelled=None,**values):
        if cls._process is None or cls._process.poll() is not None:raise RuntimeError('Die Silver-API-Verbindung ist nicht aktiv.')
        identifier=uuid.uuid4().hex
        cls._process.stdin.write(json.dumps({'id':identifier,'op':operation,**values})+'\n')
        cls._process.stdin.flush()
        deadline=time.monotonic()+timeout
        while time.monotonic()<deadline:
            if cls._detach.is_set() and operation!="release":raise RuntimeError("Die Silver-API-Verbindung wurde getrennt.")
            if cancelled is not None and cancelled.is_set():
                cls.abort_start()
                raise SilverStartCancelled("Der Setup-Start wurde abgebrochen.")
            try:reply=cls._messages.get(timeout=min(0.1,max(0.01,deadline-time.monotonic())))
            except queue.Empty:continue
            if reply.get('id') not in (None,identifier):continue
            if reply.get('error'):raise RuntimeError(reply['error'])
            return reply.get('result')
        raise RuntimeError('Silver antwortet nicht rechtzeitig. Bitte Lizenzmeldungen und das geöffnete Setup prüfen.')

    @classmethod
    def connect(cls,path,cancelled=None,allow_start=True,gui=True,pid=None,enforce_mode=False):
        cls._detach.clear()
        requested_path=str(path)
        path=Path(path).resolve()
        if not path.is_file() or path.suffix.casefold()!='.sil':raise ValueError('Bitte eine vorhandene .sil-Datei auswählen.')
        if cancelled is not None and cancelled.is_set():raise SilverStartCancelled("Der Setup-Start wurde abgebrochen.")
        existing=[entry for entry in cls.running_setups() if os.path.normcase(entry['path'])==os.path.normcase(str(path)) and (pid is None or entry['pid']==pid)]
        if not existing and not allow_start:return None
        cls.disconnect()
        home=cls.home(existing)
        command=cls.worker_launch_command(home)
        log=Runtime.data_root()/'silver_connection_worker.log'
        with log.open('a',encoding='utf-8') as errors:
            cls._process=subprocess.Popen(command,cwd=str(path.parent),stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=errors,text=True,encoding='utf-8',errors='replace',creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        cls._messages=queue.Queue()
        threading.Thread(target=cls.read_output,args=(cls._process.stdout,cls._messages),daemon=True).start()
        try:
            result=cls.rpc('connect',timeout=330,cancelled=cancelled,path=str(path),existing=existing,allow_start=allow_start,gui=bool(gui))
            if cancelled is not None and cancelled.is_set():
                cls.abort_start()
                raise SilverStartCancelled("Der Setup-Start wurde abgebrochen.")
            cls._silver_closed=False;cls._setup_path=requested_path
            cls._silver_pid=result.get('pid')
            cls._headless=bool(result.get('headless',False))
            from .operation import SilverOperation
            from .deferred_controls import SilverDeferredControls
            SilverDeferredControls.reset()
            SilverOperation._requested_pause=None
            SilverOperation._last_sim_time=None;SilverOperation._last_sim_change=None
            # Existing OOP API methods remain usable on this same worker thread.
            from ..core.catalog import Catalog
            target=SimpleNamespace(**{entry['name']:functools.partial(cls.call,entry['name']) for entry in Catalog.load('silver')['methods']})
            SilverApi.attach(target,session=cls._session)
            return cls.match_requested_mode(requested_path,result,gui,cancelled) if enforce_mode and allow_start else result
        except Exception as original:
            try:cls.disconnect()
            except Exception as cleanup:
                raise RuntimeError(str(original)+"\nZusätzlich beim Trennen: "+str(cleanup)) from original
            raise

    @classmethod
    def match_requested_mode(cls,path,result,gui,cancelled=None):
        if cls._headless!=bool(gui):return result
        # Silver cannot change its GUI mode in-place. A failed save must prevent restart.
        cls.save_and_exit(path)
        return cls.connect(path,cancelled=cancelled,allow_start=True,gui=gui)

    @classmethod
    def worker_launch_command(cls,home):
        if Runtime.is_compiled():return [sys.executable,"--silver-api-worker",str(home)]
        python=Path(home)/"common/ext-tools/python3/python.exe"
        source=Path(__file__).with_name("connection_worker.py")
        if not python.is_file() or not source.is_file():
            raise RuntimeError("Die Silver-API-Laufzeit fehlt. Bitte Silver vollständig installieren.")
        return [str(python),"-u",str(source),str(home)]

    @classmethod
    def abort_start(cls):
        """Stop only our helper and its newly launched descendants, never matched user instances."""
        import psutil
        helper=cls._process
        if helper is None or helper.poll() is not None:return
        try:root=psutil.Process(helper.pid)
        except psutil.NoSuchProcess:return
        # Freeze the spawning parent before enumerating children to close the launch race.
        suspended=False
        try:
            root.suspend();suspended=True
            children=root.children(recursive=True)
            for child in reversed(children):
                try:child.kill()
                except psutil.NoSuchProcess:pass
            root.kill();suspended=False
            _,alive=psutil.wait_procs(children+[root],timeout=3)
            if alive:raise RuntimeError("Der Setup-Start konnte nicht vollständig abgebrochen werden. Bitte Silver prüfen.")
        finally:
            if suspended:
                try:root.resume()
                except psutil.NoSuchProcess:pass

    @classmethod
    def request_detach(cls):
        # Only signal here; the owning API thread performs the actual cleanup.
        cls._detach.set()

    @classmethod
    def call(cls,method,*args,**kwargs):
        return cls.rpc('call',timeout=300 if method in ('stop','exit') else (180 if method in ('reload','run','open','save','set_sfu_property') else 10),method=method,args=args,kwargs=kwargs)

    @classmethod
    def save_and_exit(cls,path,immediate=False):
        from .methods import Silver
        cls._detach.clear()
        def save_exit():
            import psutil
            process=None
            if cls._silver_pid is not None:
                try:process=psutil.Process(cls._silver_pid)
                except psutil.NoSuchProcess:pass
            if Silver.save(str(path),session=cls._session) is False:
                raise RuntimeError("Silver konnte den aktuellen Projektstand nicht speichern. Das Setup wurde nicht geschlossen.")
            try:Silver.exit(force=bool(immediate),timeout=None,session=cls._session)
            except Exception:
                # Exit Now may close gRPC before its reply arrives; only accept
                # that case if the exact Silver process has actually terminated.
                if process is None:raise
                try:process.wait(timeout=2)
                except psutil.TimeoutExpired:raise
            cls._silver_closed=True
            if process is not None:
                try:process.wait(timeout=15 if immediate else 300)
                except psutil.TimeoutExpired as error:raise RuntimeError("Silver hat die Beendigung noch nicht abgeschlossen.") from error
        try:
            if cls._headless:save_exit()
            else:
                from .editor_save import SilverEditorSave
                with SilverEditorSave.during_apply(cls._silver_pid):
                    SilverEditorSave.clear_editor(cls._silver_pid)
                    save_exit()
        finally:
            if cls._silver_closed:cls.disconnect()

    @classmethod
    def alive(cls):
        try:return bool(cls.rpc('ping',timeout=5))
        except Exception:return False

    @classmethod
    def disconnect(cls):
        from .deferred_controls import SilverDeferredControls
        SilverDeferredControls.reset()
        cls._silver_pid=None;cls._headless=False;cls._setup_path=None
        if cls._session in SilverApi._sessions:SilverApi.release(cls._session)
        process=cls._process
        release_error=None
        if process is not None and process.poll() is None and not cls._silver_closed:
            try:cls.rpc('release',timeout=15)
            except Exception as error:release_error=error
        cls._process=None
        if process is not None:
            try:
                if process.poll() is None:
                    process.stdin.write(json.dumps({'op':'disconnect'})+'\n');process.stdin.flush()
                    process.wait(timeout=2)
            except Exception:
                if process.poll() is None:process.terminate()
            finally:
                try:process.stdin.close()
                except Exception:pass
                try:process.stdout.close()
                except Exception:pass
        cls._silver_closed=False
        if release_error is not None:
            raise RuntimeError("API-Verbindung getrennt, aber die Freigabe der Vorgaben konnte nicht bestätigt werden. Bitte das Setup in Silver neu laden.") from release_error
