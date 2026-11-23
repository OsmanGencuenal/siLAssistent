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
        from .git_credential_manager import GitCredentialManager
        try:
            result=subprocess.run([git,*GitCredentialManager.options(git),"-C",str(path),"-c","credential.interactive=never",*args],capture_output=True,text=True,encoding="utf-8",errors="replace",timeout=timeout,env=env,creationflags=getattr(subprocess,"CREATE_NO_WINDOW",0))
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
    def switch_plan(cls, path, branch, root=None, skipped=None, issues=None, dirty_repos=None, context=None):
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
        if path==root and context is not None:context["active"]=info.get("active") or "Detached HEAD"
        if branch not in info["branches"]:
            if path==root:
                raise RuntimeError("Branch „"+branch+"“ fehlt im Hauptrepo.")
            skipped.append(str(path)+": Zielbranch fehlt; unverändert auf "+(info.get("active") or "bisherigem Commit"))
            plan=[]
            for relative in cls.gitlinks(path,"HEAD"):
                try:
                    plan.extend(cls.switch_plan(path/relative,branch,root,skipped,issues,dirty_repos,context))
                except (RuntimeError,ValueError) as error:
                    issues.append(str(path/relative)+": "+str(error))
            return plan
        # Different submodule commits are expected in development mode. File and
        # staged changes in each individual repository still block switching.
        dirty=cls.run(path,["status","--porcelain","--untracked-files=normal","--ignore-submodules=all"]).stdout.strip()
        staged=cls.run(path,["diff","--cached","--name-only"]).stdout.strip()
        if dirty or staged:
            if dirty_repos is None:
                raise RuntimeError("Branch nicht gewechselt: lokale Änderungen in "+str(path)+". Bitte zuerst sichern bzw. committen.")
            import hashlib
            delta=cls.run(path,["diff","--binary","HEAD"]).stdout
            untracked=cls.run(path,["ls-files","--others","--exclude-standard","-z"]).stdout
            untracked_state=[]
            for relative in untracked.split("\0"):
                if not relative:continue
                item=path/relative
                if not item.resolve().is_relative_to(root):
                    untracked_state.append([relative,"outside-root"]);continue
                metadata=item.lstat()
                untracked_state.append([relative,metadata.st_size,metadata.st_mtime_ns,metadata.st_mode])
            dirty_repos.append({"path":str(path),"branch":info.get("active") or "Detached HEAD",
                                "status":dirty,"staged":staged,"head":cls.run(path,["rev-parse","HEAD"]).stdout.strip(),
                                "diff":hashlib.sha256(delta.encode("utf-8")).hexdigest(),"untracked":untracked,"untracked_state":untracked_state})
        local=branch in info["local"]
        ref=("refs/heads/" if local else "refs/remotes/origin/")+branch
        plan=[(path,local)]
        for relative in cls.gitlinks(path,ref):
            try:
                plan.extend(cls.switch_plan(path/relative,branch,root,skipped,issues,dirty_repos,context))
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
    def activate(cls, path, branch, user_id, submodule=None, discard=None):
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
        dirty=[];context={}
        plan=cls.switch_plan(path,branch,skipped=skipped,issues=issues,dirty_repos=dirty,context=context)
        if issues:raise RuntimeError("Branchwechsel wurde vor Änderungen abgebrochen.\n\n"+"\n".join(issues))
        approval={"root":str(path),"target":branch,"active":context.get("active","Detached HEAD"),
                  "repositories":dirty,"plan":[[str(repo),local] for repo,local in plan]}
        if dirty:
            if discard!=approval:
                return {"confirmation_required":True,"active":approval["active"],"target":branch,"approval":approval}
            cls.discard_changes(path,dirty)
        changed=[]
        for repository,local in plan:
            try:
                args=(["switch","--no-recurse-submodules","--no-overwrite-ignore","--no-guess","--",branch] if local else
                      ["switch","--no-recurse-submodules","--no-overwrite-ignore","--track","-c",branch,"origin/"+branch])
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

    @classmethod
    def discard_changes(cls,root,repositories):
        # Only the freshly rechecked, explicitly approved repositories are touched.
        root=Path(root).resolve()
        for item in sorted(repositories,key=lambda value:len(Path(value["path"]).parts),reverse=True):
            folder=Path(item["path"]).resolve()
            if not folder.is_relative_to(root) or not (folder/".git").exists():
                raise RuntimeError("Bestätigter Repo-Pfad ist nicht mehr gültig. Bitte Branchwechsel erneut starten.")
            actual=Path(cls.run(folder,["rev-parse","--show-toplevel"]).stdout.strip()).resolve()
            if actual!=folder:raise RuntimeError("Repo-Zuordnung hat sich geändert. Bitte Branchwechsel erneut starten.")
            for relative in item.get("untracked","").split("\0"):
                if relative and not (folder/relative).resolve().is_relative_to(root):
                    raise RuntimeError("Nicht versionierter Pfad führt außerhalb des Setup-Repositories. Es wurden dort keine Änderungen verworfen.")
            cls.run(folder,["reset","--hard","HEAD"])
            # Keep ignored files and nested, unrelated Git repositories.
            cls.run(folder,["clean","-fd"])
