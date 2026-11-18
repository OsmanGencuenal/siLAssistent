"""Version-aware adapter to the locally installed vendor RemoteSilver library."""
from pathlib import Path
import os
import sys
import importlib.util
import inspect
import threading
from ..core.errors import ConnectionError, ApiCallError, ThreadAffinityError

class Silver:
    _sessions = {}
    _vendor_home = None
    _vendor_module = None

    @classmethod
    def installations(cls):
        candidates = []
        if os.environ.get("SILVER_HOME"):
            candidates.append(Path(os.environ["SILVER_HOME"]))
        for variable in ("ProgramFiles", "ProgramFiles(x86)"):
            base = Path(os.environ.get(variable, "C:/Program Files")) / "Synopsys"
            if base.is_dir():
                candidates.extend(sorted(base.glob("Silver*"), reverse=True))
        return list(dict.fromkeys(str(p.resolve()) for p in candidates if p.is_dir()))

    @classmethod
    def vendor_module(cls, home=None):
        homes = [str(Path(home).resolve())] if home else cls.installations()
        for candidate in homes:
            folder = Path(candidate) / "common/ext-tools/python3/Lib/site-packages/synopsys/silver/remotescripting"
            module_path = folder / "remotesilverapi.py"
            if not module_path.is_file():
                continue
            if cls._vendor_module is not None:
                if cls._vendor_home != candidate:
                    raise ConnectionError("Changing Silver installations requires a fresh Python process.")
                return cls._vendor_module
            pyro_path = str(Path(candidate) / "lib/Pyro4.zip")
            if pyro_path not in sys.path:
                sys.path.insert(0, pyro_path)
            os.environ["SILVER_HOME"] = candidate
            spec = importlib.util.spec_from_file_location("_silassistent_vendor_remote", module_path)
            module = importlib.util.module_from_spec(spec)
            try:
                spec.loader.exec_module(module)
            except Exception as error:
                raise ConnectionError(f"Cannot load Silver's own Remote API: {error}") from error
            cls._vendor_home = candidate
            cls._vendor_module = module
            return module
        raise ConnectionError("Silver Remote API not found. Configure SILVER_HOME or pass home= explicitly.")

    @classmethod
    def start(cls, sil=None, *, session="default", home=None, timeout=60, stopped=True,
              speedup=False, gui=True, args=(), silent=False, host=None, port=None,
              backend="native", version=None, factory=None):
        if session in cls._sessions:
            raise ConnectionError(f"Silver session already exists: {session}")
        if isinstance(args, str):
            raise TypeError("args must be a sequence of separate arguments")
        if (host is None) != (port is None):
            raise ValueError("host and port must be provided together")
        if backend != "native":
            raise ValueError("Use backend='native'; runner requires Silver's own embedded Python.")
        factory = factory or cls.vendor_module(home).RemoteSilver
        keywords = dict(sil=None if sil is None else str(Path(sil).resolve()), timeout=timeout,
                        stopped=stopped, speedup=speedup, gui=gui, args=list(args), silent=silent,
                        host=host, port=port, backend=backend)
        parameters = inspect.signature(factory).parameters
        supports_version = "version" in parameters or any(p.kind == p.VAR_KEYWORD for p in parameters.values())
        if version is not None:
            if not supports_version:
                raise ConnectionError("This Silver release does not support the version argument.")
            if version not in (2, 3):
                raise ValueError("Silver version must be 2 or 3")
            keywords["version"] = version
        try:
            target = factory(**keywords)
            check = getattr(target, "silverStartedSuccessfully", None) or getattr(target, "started_successfully", None)
            if check is None or not check():
                raise ConnectionError("Silver did not report a successful startup")
        except Exception as error:
            raise ConnectionError(f"Silver startup failed: {error}") from error
        return cls.attach(target, session=session)

    @classmethod
    def attach(cls, target, session="default"):
        if session in cls._sessions:
            raise ConnectionError(f"Silver session already exists: {session}")
        cls._sessions[session] = {"target": target, "thread": threading.get_ident()}
        return target

    @classmethod
    def target(cls, session="default"):
        try:
            state = cls._sessions[session]
        except KeyError as error:
            raise ConnectionError(f"Silver session not found: {session}") from error
        if state["thread"] != threading.get_ident():
            raise ThreadAffinityError("RemoteSilver proxies must stay on their creating thread.")
        return state["target"]

    @classmethod
    def call(cls, method, *args, session="default", **kwargs):
        if not method.isidentifier() or method.startswith("_"):
            raise ValueError("Invalid vendor method name")
        try:
            return getattr(cls.target(session), method)(*args, **kwargs)
        except (ConnectionError, ThreadAffinityError):
            raise
        except Exception as error:
            raise ApiCallError(f"Silver.{method}: {error}") from error

    @classmethod
    def close(cls, session="default", *, force=False, timeout=30):
        result = cls.call("exit", force=force, timeout=timeout, session=session)
        if result is False:
            raise ApiCallError("Silver did not confirm shutdown; session remains connected.")
        del cls._sessions[session]
        return result

    @classmethod
    def release(cls, session="default"):
        """Forget our reference; do not stop a Silver instance controlled elsewhere."""
        cls.target(session)
        del cls._sessions[session]

    @classmethod
    def capabilities(cls, session="default"):
        from ..core.catalog import Catalog
        cls.target(session)
        return {"documented_methods": [entry["name"] for entry in Catalog.load("silver")["methods"]],
                "runtime_validation": "per-call; dynamic vendor proxies cannot prove availability by getattr"}
