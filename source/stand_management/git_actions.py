"""Recursive branch pulls and explicit restoration of tracked modifications."""
from pathlib import Path
import time
from .git_branches import GitBranches
from .git import GitTool
from ..core.config import Config
from ..core.errors import RepoAccessRequired,GitMissing

class GitActions:
    @classmethod
    def repositories(cls,root):
        lines=GitBranches.run(root,["submodule","foreach","--quiet","--recursive","git rev-parse --show-toplevel"]).stdout.splitlines()
        children=[Path(line).resolve() for line in lines if line.strip()]
        if any(not path.is_relative_to(root) for path in children):
            raise RuntimeError("Submodul liegt außerhalb des Setup-Ordners.")
        return [root]+children

    @classmethod
    def authorize(cls,path):
        if not Config.state()["GitUserLicenceState"]:
            raise RuntimeError("Bitte zuerst eine gültige Git User Lizenz bestätigen.")
        access=GitTool.repository_check(GitTool.windows_user()["username"])
        if access.get("status")=="git_missing":raise GitMissing("Git ist nicht mehr installiert.")
        if access.get("status") in ("git_error","unavailable"):
            raise RuntimeError(access.get("reason","Git konnte den Server nicht erreichen. Bitte Netzwerk und Git-Anmeldung prüfen."))
        if not access["allowed"]:
            raise RepoAccessRequired("Zum Klonen, Pullen oder Zurücksetzen benötigen Sie Zugriffsrechte auf das M286-Setup-Repo.")
        return GitBranches.validate(path)

    @classmethod
    def stash(cls,repos):
        run=GitBranches.run;saved=[]
        for repo in sorted(repos,key=lambda p:len(p.parts),reverse=True):
            if run(repo,["status","--porcelain","--untracked-files=all","--ignore-submodules=all"]).stdout.strip():
                before=run(repo,["rev-parse","--verify","refs/stash"],required=False).stdout.strip()
                run(repo,["stash","push","--include-untracked","-m","siLAssistent vor Pull "+time.strftime("%Y-%m-%d %H:%M:%S")])
                after=run(repo,["rev-parse","--verify","refs/stash"],required=False).stdout.strip()
                if after and after!=before:saved.append(repo.name+" :: "+after[:10])
        return saved

    @classmethod
    def choose_branch(cls,repo,target,strict=False):
        run=GitBranches.run
        run(repo,["fetch","--no-recurse-submodules","origin"],timeout=600)
        refs=GitBranches.refs(repo)
        branch=target if target in refs["branches"] else (refs.get("active") or ("main" if "main" in refs["branches"] else None))
        if strict and branch!=target or not branch or branch not in refs["branches"]:
            raise RuntimeError("Branch „"+target+"“ ist nicht vorhanden in "+repo.name)
        return branch

    @classmethod
    def switch(cls,repo,branch):
        run=GitBranches.run
        local=run(repo,["show-ref","--verify","--quiet","refs/heads/"+branch],required=False).returncode==0
        run(repo,["switch","--no-recurse-submodules","--no-overwrite-ignore",branch] if local else ["switch","--no-recurse-submodules","--no-overwrite-ignore","--track","origin/"+branch])

    @classmethod
    def pull(cls,path,branch=None,progress=None):
        root=cls.authorize(path);run=GitBranches.run
        target=branch or run(root,["symbolic-ref","--quiet","--short","HEAD"]).stdout.strip()
        if not target:raise RuntimeError("Bitte zuerst einen Branch aktivieren.")
        if progress:progress(target)
        repos=cls.repositories(root)
        saved=cls.stash(repos)
        try:
            # Preflight all existing repos before switching or pulling any of them.
            choices={repo:cls.choose_branch(repo,target,strict=(repo==root or target=="main")) for repo in repos}
            for repo,selected in choices.items():cls.switch(repo,selected)
            run(root,["pull","--ff-only","--no-recurse-submodules","origin",target],timeout=1200)
            run(root,["submodule","sync","--recursive"])
            run(root,["submodule","update","--init","--recursive"],timeout=3600)
            results=["SimFiles :: "+target]
            for repo in cls.repositories(root)[1:]:
                selected=choices.get(repo) or cls.choose_branch(repo,target,strict=target=="main")
                cls.switch(repo,selected)
                run(repo,["pull","--ff-only","--no-recurse-submodules","origin",selected],timeout=1200)
                results.append(repo.relative_to(root).as_posix()+" :: "+selected)
        except GitMissing:
            raise
        except Exception as error:
            raise RuntimeError(str(error)+"\n\nBereits gesicherte Änderungen bleiben im Git-Stash erhalten:\n"+"\n".join(saved)) from error
        return "Branches wurden aktualisiert:\n"+"\n".join(results)+( "\n\nLokale Änderungen im Git-Stash gesichert (nicht wieder angewendet):\n"+"\n".join(saved) if saved else "")

    @classmethod
    def revert(cls,path):
        root=cls.authorize(path)
        repos=cls.repositories(root)
        for repo in sorted(repos,key=lambda p:len(p.parts),reverse=True):
            GitBranches.run(repo,["restore","--source=HEAD","--staged","--worktree","--","."])
        return "Änderungen an versionierten Dateien wurden in SimFiles und allen initialisierten Submodulen auf den jeweiligen lokalen HEAD zurückgesetzt.\n\nBranches, Commits, unversionierte Dateien und Git-Stashes bleiben erhalten."
