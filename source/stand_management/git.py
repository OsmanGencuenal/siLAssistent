"""Git backend: Windows identity and authenticated GitHub access checks."""
import json
from .git_installation import GitInstallation
from urllib.request import Request, build_opener, HTTPRedirectHandler
from urllib.error import HTTPError, URLError


class GitApiRedirectHandler(HTTPRedirectHandler):
    @classmethod
    def redirect_request(cls, req, fp, code, msg, headers, newurl):
        raise HTTPError(req.full_url, code, "Unexpected API redirect", headers, fp)


class GitTool:
    API_URL = "https://api.mercedes-benz.ghe.com"

    @classmethod
    def open(cls, parent=None):
        from .git_window import GitWindow
        return GitWindow.open(parent)

    @classmethod
    def windows_user(cls):
        """Read the current Windows security context, not editable environment variables."""
        import win32api
        import win32con
        account = win32api.GetUserNameEx(win32con.NameSamCompatible)
        domain, separator, username = account.rpartition("\\")
        return {"domain": domain if separator else "", "username": username,
                "account": account}

    @classmethod
    def api_get(cls, endpoint, token, timeout=10):
        # Fixed enterprise host; no arbitrary URLs or credentials in diagnostics.
        request = Request(cls.API_URL + endpoint, headers={
            "Authorization": "Bearer " + token,
            "Accept": "application/vnd.github+json",
            "User-Agent": "siLAssistent"})
        with build_opener(GitApiRedirectHandler()).open(request, timeout=timeout) as response:
            if response.geturl().split("/", 3)[:3] != cls.API_URL.split("/"):
                raise ValueError("Unexpected GitHub API response host")
            return json.load(response)

    @classmethod
    def check_access(cls, token=None, repository="devM286/SimFiles", timeout=10):
        """Read-only; call from a worker. Windows and GitHub identities are separate.

        A token must belong to the user being checked. Never persist it in the INI.
        No authentication UI or credential lookup is triggered by this method.
        """
        identity = cls.windows_user()
        result = {"windows_user": identity, "github_user": None,
                  "account_access": None, "repository_access": None,
                  "status": "authentication_required"}
        if not token:
            return result
        if not isinstance(token, str) or any(c in token for c in "\r\n"):
            raise ValueError("Invalid authentication value")
        import re
        if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository):
            raise ValueError("Repository must be owner/name")
        try:
            user = cls.api_get("/user", token, timeout)
            if not isinstance(user, dict) or not user.get("login"):
                result["status"] = "invalid_response"
                return result
            result.update(github_user=user["login"], account_access=True)
            repo = cls.api_get("/repos/" + repository, token, timeout)
            if not isinstance(repo, dict) or str(repo.get("full_name", "")).lower() != repository.lower():
                result["status"] = "invalid_response"
                return result
            result.update(repository_access=True, status="accessible")
        except HTTPError as error:
            # 403 may mean policy/SSO/rate limiting; 404 can hide a private repo.
            result["status"] = {401: "authentication_required", 403: "restricted_or_rate_limited",
                                404: "not_visible_or_missing"}.get(error.code, "service_error")
            result["http_status"] = error.code
        except (URLError, TimeoutError, OSError):
            result["status"] = "network_error"
        except (ValueError, TypeError):
            result["status"] = "invalid_response"
        return result

    @classmethod
    def repository_check(cls, user_id, persist=True):
        import os
        import shutil
        import subprocess
        from ..core.config import Config
        if persist:
            Config.set_state("GitUserState", False)
        actual = cls.windows_user()["username"]
        if user_id.strip().casefold() != actual.casefold():
            return {"allowed": False, "status": "identity_mismatch"}
        git = GitInstallation.executable()
        if not git:
            Config.set_state("GitInstallationState",False)
            return {"allowed": False, "status": "git_missing"}
        if not Config.state().get("GitInstallationState",False):
            Config.set_state("GitInstallationState",True)
        repo = cls.repository_url()
        env = dict(os.environ, GIT_TERMINAL_PROMPT="0", GCM_INTERACTIVE="never", GIT_ASKPASS="", SSH_ASKPASS="")
        try:
            result = subprocess.run([git, "-c", "credential.interactive=never", "ls-remote", repo],
                                    capture_output=True, timeout=40, env=env,
                                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        except FileNotFoundError:
            Config.set_state("GitInstallationState",False)
            return {"allowed":False,"status":"git_missing"}
        except subprocess.TimeoutExpired:
            return {"allowed":False,"status":"unavailable","reason":"Git antwortet bei der Repo-Prüfung nicht rechtzeitig. Bitte Netzwerk, VPN und laufende Git-Prozesse prüfen."}
        except OSError:
            return {"allowed":False,"status":"git_error","reason":"Git ist vorhanden, kann aber nicht ausgeführt werden. Bitte Git-Installation und Windows-Ausführungsrechte prüfen."}
        allowed = result.returncode == 0
        if persist:
            Config.set_state("GitUserState", allowed)
        return {"allowed":True,"status":"accessible"} if allowed else cls.git_failure(result)

    @classmethod
    def repository_url(cls):
        from ..core.config import Config
        repo = Config.state()["GitSetupRepo"]
        from ..core.release_paths import ReleasePaths
        return ReleasePaths.validate_repository(repo)

    @classmethod
    def clone_target(cls, selected_folder):
        from pathlib import Path
        folder=Path(selected_folder)
        base=folder if folder.name.casefold()=="simulate" else folder/"Simulate"
        return base/"SimFiles"

    @classmethod
    def clone_repository(cls, user_id, destination):
        import os
        import shutil
        import subprocess
        from pathlib import Path
        from ..core.config import Config
        if not Config.state()["GitUserLicenceState"]:
            return {"allowed":False,"status":"license_required"}
        # Recheck immediately before execution, even if an INI flag was edited.
        access = cls.repository_check(user_id, persist=False)
        if not access["allowed"]:
            return access
        target = Path(destination)
        if target.exists():
            raise ValueError("Der Zielordner existiert bereits. Bitte einen neuen Ordner wählen.")
        env = dict(os.environ, GIT_TERMINAL_PROMPT="0", GCM_INTERACTIVE="never", GIT_ASKPASS="", SSH_ASKPASS="")
        try:
            target.parent.mkdir(parents=True,exist_ok=True)
            result = subprocess.run([GitInstallation.executable(), "-c", "credential.interactive=never", "clone", "--recurse-submodules", "--", cls.repository_url(), str(target)],
                                    capture_output=True, timeout=1800, env=env,
                                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        except subprocess.TimeoutExpired:
            raise RuntimeError("Das Klonen hat zu lange gedauert. Bitte Netzwerk und Zugriff auf die Submodule prüfen. Ein unvollständiger Zielordner kann vorhanden sein.") from None
        except OSError:
            raise RuntimeError("Der Zielordner konnte nicht angelegt oder Git nicht gestartet werden. Bitte Schreibrechte, Speicherplatz und Git-Installation prüfen.") from None
        if result.returncode != 0:
            failure=cls.git_failure(result)
            if failure["status"]!="unverified":return failure
            raise RuntimeError("Klonen fehlgeschlagen. Anmeldung, Netzwerk und Zielordner prüfen. Ein unvollständiger Ordner kann vorhanden sein.")
        return {"allowed": True, "status": "cloned", "path": str(target.resolve())}

    @classmethod
    def git_failure(cls,result):
        output=getattr(result,"stderr","")
        output=output.decode("utf-8",errors="replace") if isinstance(output,bytes) else output if isinstance(output,str) else ""
        text=output.casefold()
        if any(word in text for word in ("could not resolve", "failed to connect", "timed out", "ssl certificate", "connection reset", "network is unreachable")):
            return {"allowed":False,"status":"unavailable","reason":"Git erreicht den Server nicht. Bitte Netzwerk, VPN, Proxy und Zertifikate prüfen. Das ist kein Nachweis fehlender Repo-Rechte."}
        if any(word in text for word in ("authentication failed", "could not read username", "terminal prompts disabled", "invalid username or password")):
            return {"allowed":False,"status":"authentication_required","reason":"Git konnte die Anmeldung nicht bestätigen. Bitte die GitHub-Anmeldung für das verwendete Konto prüfen. Eine neue Lizenz ist dafür nicht automatisch erforderlich."}
        if any(word in text for word in ("403", "access denied", "permission to ", "not authorized", "you are not allowed")):
            return {"allowed":False,"status":"access_denied","reason":"Der Server verweigert den Repository- oder Submodul-Zugriff. Bitte Repo-Berechtigung und gegebenenfalls SSO-Freigabe prüfen."}
        return {"allowed":False,"status":"unverified"}
