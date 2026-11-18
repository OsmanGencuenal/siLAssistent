"""Branch discovery and safe switching for the configured SimFiles checkout."""
import os
import shutil
import subprocess
from pathlib import Path
from ..core.config import Config
from ..core.errors import GitMissing
from ..core.git_probe import GitProbe
from .git import GitTool
from .git_installation import GitInstallation

class GitBranches:
    @classmethod
    def run(cls, path, args, timeout=60, required=True):
        git=GitInstallation.executable()
        if not git:
            Config.set_state("GitInstallationState",False)
            raise GitMissing("Git ist nicht installiert oder wurde entfernt.")
        env=dict(os.environ,GIT_TERMINAL_PROMPT="0",GCM_INTERACTIVE="never",GIT_ASKPASS="",SSH_ASKPASS="")
        try:
            result=subprocess.run([git,"-C",str(path),"-c","credential.interactive=never",*args],capture_output=True,text=True,encoding="utf-8",errors="replace",timeout=timeout,env=env,creationflags=getattr(subprocess,"CREATE_NO_WINDOW",0))
        except FileNotFoundError:
            Config.set_state("GitInstallationState",False)
            raise GitMissing("Git wurde entfernt oder ist nicht mehr erreichbar.") from None
        except subprocess.TimeoutExpired:
            raise RuntimeError("Git antwortet nicht rechtzeitig. Bitte Netzwerk und laufende Git-Prozesse prüfen.") from None
        except OSError:
            raise RuntimeError("Git ist vorhanden, kann aber nicht ausgeführt werden. Bitte Installation und Windows-Ausführungsrechte prüfen.") from None
        if required and result.returncode:
            raise RuntimeError(GitProbe.failure_message(result.stderr))
        return result

    @classmethod
    def validate(cls, path):
        path=Path(path).resolve()
        if not path.is_dir():
            raise ValueError("Bitte zuerst einen vorhandenen lokalen SimFiles-Repo-Ordner wählen.")
        root=Path(cls.run(path,["rev-parse","--show-toplevel"]).stdout.strip()).resolve()
        if os.path.normcase(str(root))!=os.path.normcase(str(path)):
            raise ValueError("Der Pfad muss direkt auf den SimFiles-Repo-Ordner zeigen.")
        origin=cls.run(path,["remote","get-url","origin"]).stdout.strip()
        if origin.rstrip("/")!=GitTool.repository_url().rstrip("/"):
            raise ValueError("Der ausgewählte Ordner gehört nicht zum konfigurierten M286-Setup-Repo.")
        return path

    @classmethod
    def list(cls, path, refresh=True):
        path=cls.validate(path)
        warning=""
        if refresh:
            fetch=cls.run(path,["fetch","--prune","--no-recurse-submodules","origin"],required=False)
            if fetch.returncode:
                warning="Remote-Branches konnten nicht aktualisiert werden. Angezeigt werden die lokal bekannten Branches."
        return {**cls.refs(path),"warning":warning}

    @classmethod
    def refs(cls, path):
        refs=cls.run(path,["for-each-ref","--format=%(refname)","refs/heads/","refs/remotes/origin/"]).stdout.splitlines()
        local={ref[len("refs/heads/"):] for ref in refs if ref.startswith("refs/heads/")}
        remote={ref[len("refs/remotes/origin/"):] for ref in refs if ref.startswith("refs/remotes/origin/") and ref!="refs/remotes/origin/HEAD"}
        active=cls.run(path,["symbolic-ref","--quiet","--short","HEAD"],required=False).stdout.strip()
        return {"branches":sorted(local|remote,key=str.casefold),"active":active,"local":local,"remote":remote,"warning":""}

    @classmethod
    def gitlinks(cls, path, ref):
        output=cls.run(path,["ls-tree","-r","-z","--full-tree",ref]).stdout
        return [entry.split("\t",1)[1] for entry in output.split("\0") if entry.startswith("160000 ") and "\t" in entry]

    @classmethod
    def switch_plan(cls, path, branch, root=None, skipped=None, issues=None):
        path=Path(path).resolve()
        root=path if root is None else root
        skipped=[] if skipped is None else skipped
        issues=[] if issues is None else issues
        if not path.is_relative_to(root) or not (path/".git").exists():
            raise RuntimeError("Submodul fehlt oder ist nicht initialisiert: "+str(path)+". Bitte zuerst das Setup vollständig rekursiv klonen.")
        actual=Path(cls.run(path,["rev-parse","--show-toplevel"]).stdout.strip()).resolve()
        if actual!=path:
            raise RuntimeError("Ungültiges Submodul: "+str(path))
        cls.run(path,["fetch","--prune","--no-recurse-submodules","origin"])
        info=cls.refs(path)
        if branch not in info["branches"]:
            if path==root:
                raise RuntimeError("Branch „"+branch+"“ fehlt im Hauptrepo.")
            skipped.append(str(path)+": Zielbranch fehlt; unverändert auf "+(info.get("active") or "bisherigem Commit"))
            plan=[]
            for relative in cls.gitlinks(path,"HEAD"):
                try:
                    plan.extend(cls.switch_plan(path/relative,branch,root,skipped,issues))
                except (RuntimeError,ValueError) as error:
                    issues.append(str(path/relative)+": "+str(error))
            return plan
        # Different submodule commits are expected in development mode. File and
        # staged changes in each individual repository still block switching.
        dirty=cls.run(path,["status","--porcelain","--untracked-files=normal","--ignore-submodules=all"]).stdout.strip()
        staged=cls.run(path,["diff","--cached","--name-only"]).stdout.strip()
        if dirty or staged:
            raise RuntimeError("Branch nicht gewechselt: lokale Änderungen in "+str(path)+". Bitte zuerst sichern bzw. committen.")
        local=branch in info["local"]
        ref=("refs/heads/" if local else "refs/remotes/origin/")+branch
        plan=[(path,local)]
        for relative in cls.gitlinks(path,ref):
            try:
                plan.extend(cls.switch_plan(path/relative,branch,root,skipped,issues))
            except (RuntimeError,ValueError) as error:
                issues.append(str(path/relative)+": "+str(error))
        return plan

    @classmethod
    def submodule_branches(cls, root, path=None):
        root=Path(root).resolve()
        path=root if path is None else path
        result=[]
        for relative in cls.gitlinks(path,"HEAD"):
            child=(path/relative).resolve()
            if not child.is_relative_to(root):
                continue
            name=child.relative_to(root).as_posix()
            if not (child/".git").exists():
                result.append({"name":name,"branch":"Nicht initialisiert"})
                continue
            active=cls.run(child,["symbolic-ref","--quiet","--short","HEAD"],required=False).stdout.strip()
            result.append({"name":name,"branch":active or "Detached HEAD"})
            result.extend(cls.submodule_branches(root,child))
        return result

    @classmethod
    def activate(cls, path, branch, user_id, submodule=None):
        if not Config.state()["GitUserLicenceState"]:
            raise RuntimeError("Bitte zuerst eine gültige Git User Lizenz bestätigen.")
        access=GitTool.repository_check(user_id,persist=False)
        Config.set_state("GitUserState",access["allowed"])
        if not access["allowed"]:
            raise RuntimeError("Der Repo-Zugriff konnte für diese User-ID nicht bestätigt werden.")
        path=cls.validate(path)
        if submodule is not None:
            if submodule not in ("ICE","ECM","CPC","DT") or submodule not in cls.gitlinks(path,"HEAD"):
                raise ValueError("Das ausgewählte Submodul gehört nicht zum Setup.")
            child=(path/submodule).resolve()
            if not child.is_relative_to(path.resolve()):
                raise ValueError("Ungültiger Submodul-Pfad.")
            path=child
        cls.run(path,["check-ref-format","--branch",branch])
        skipped=[]
        issues=[]
        plan=cls.switch_plan(path,branch,skipped=skipped,issues=issues)
        changed=[]
        for repository,local in plan:
            try:
                args=(["switch","--no-recurse-submodules","--no-guess","--",branch] if local else
                      ["switch","--no-recurse-submodules","--track","-c",branch,"origin/"+branch])
                cls.run(repository,args)
                active=cls.run(repository,["symbolic-ref","--quiet","--short","HEAD"]).stdout.strip()
                if active!=branch:
                    raise RuntimeError("Branch-Aktivierung konnte nicht bestätigt werden.")
                changed.append(str(repository))
            except RuntimeError as error:
                issues.append(str(repository)+": "+str(error))
                if repository==path:
                    break
        if issues:
            raise RuntimeError("Branchwechsel nicht vollständig abgeschlossen.\n\nGewechselt:\n"+"\n".join(changed)+"\n\nProbleme:\n"+"\n".join(issues)+("\n\nUnverändert:\n"+"\n".join(skipped) if skipped else ""))
        return {**(cls.refs(path) if submodule else cls.list(path,refresh=False)),"submodule_count":max(0,len(plan)-1),"skipped_submodules":skipped,"submodule_branches":cls.submodule_branches(path)}
