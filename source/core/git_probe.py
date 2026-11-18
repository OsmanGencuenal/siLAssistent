"""Spawn-safe Git detector: no Qt, configuration writes or application startup."""
import os
import shutil
import subprocess
from pathlib import Path

class GitProbe:
    @classmethod
    def find_executable(cls):
        found=shutil.which("git")
        if found:
            return found
        candidates=[]
        for key in ("ProgramFiles","ProgramW6432","ProgramFiles(x86)"):
            if os.environ.get(key):
                candidates.append(Path(os.environ[key])/"Git/cmd/git.exe")
        if os.environ.get("LOCALAPPDATA"):
            candidates.append(Path(os.environ["LOCALAPPDATA"])/"Programs/Git/cmd/git.exe")
        import winreg
        for hive in (winreg.HKEY_CURRENT_USER,winreg.HKEY_LOCAL_MACHINE):
            for view in (winreg.KEY_WOW64_64KEY,winreg.KEY_WOW64_32KEY):
                try:
                    with winreg.OpenKey(hive,r"SOFTWARE\GitForWindows",0,winreg.KEY_READ|view) as key:
                        folder=winreg.QueryValueEx(key,"InstallPath")[0]
                        candidates.append(Path(folder)/"cmd/git.exe")
                except OSError:
                    pass
        return next((str(path) for path in candidates if path.is_file()),None)

    @classmethod
    def failure_message(cls,detail):
        text=str(detail).casefold()
        if any(word in text for word in ("not possible to fast-forward","non-fast-forward","divergent branches")):
            return "Lokale und entfernte Commits sind auseinander gelaufen. Bitte die Änderungen zusammenführen; lokale Commits werden nicht überschrieben."
        if any(word in text for word in ("could not resolve host","unable to access","timed out","failed to connect","ssl certificate")):
            return "Git erreicht den Server nicht. Bitte Firmennetz/VPN, Proxy und Zertifikate prüfen."
        if any(word in text for word in ("authentication failed","permission denied","repository not found","403","401")):
            return "Git konnte die Anmeldung oder Repo-Berechtigung nicht bestätigen. Bitte Anmeldung und Zugriff prüfen."
        if any(word in text for word in ("index.lock","another git process")):
            return "Das Repository ist durch einen anderen Git-Vorgang gesperrt. Bitte dessen Abschluss abwarten."
        if "not a git repository" in text:
            return "Der ausgewählte Ordner ist kein gültiges Git-Repository. Bitte den lokalen SimFiles-Ordner prüfen."
        if any(word in text for word in ("local changes","would be overwritten","untracked working tree")):
            return "Lokale Änderungen verhindern diesen Git-Schritt. Die Daten bleiben erhalten; bitte die betroffenen Änderungen prüfen."
        return "Git konnte den Befehl nicht abschließen. Bitte Repo-Zustand, Schreibrechte und Speicherplatz prüfen."

    @classmethod
    def run(cls, connection):
        path=None
        try:
            path=cls.find_executable()
            if path:
                try:
                    result=subprocess.run([path,"--version"],capture_output=True,timeout=10,
                                          creationflags=getattr(subprocess,"CREATE_NO_WINDOW",0))
                    if result.returncode:
                        raise RuntimeError("Git --version fehlgeschlagen.")
                except FileNotFoundError:
                    path=None
                except (OSError,subprocess.TimeoutExpired,RuntimeError):
                    connection.send({"path":path,"error":"Git ist installiert, lässt sich aber nicht korrekt starten. Bitte Git reparieren und Sicherheits-/Ausführungsrechte prüfen.","pid":os.getpid()})
                    return
            connection.send({"path":path,"error":None,"pid":os.getpid()})
        except Exception:
            connection.send({"path":path,"error":"Git-Installation konnte nicht geprüft werden.","pid":os.getpid()})
        finally:
            connection.close()
