"""Read-only commit snapshots for the active branch of each setup repository."""
from pathlib import Path
from .git_branches import GitBranches

class GitHistory:
    REPOSITORIES=("SimFiles","ICE","ECM","CPC","DT")

    @classmethod
    def commits(cls, path, limit=100, ref=None):
        path=Path(path).resolve()
        if not (path/".git").exists():
            raise ValueError("Repository nicht vorhanden oder nicht initialisiert.")
        actual=Path(GitBranches.run(path,["rev-parse","--show-toplevel"]).stdout.strip()).resolve()
        if actual!=path:
            raise ValueError("Kein eigenständiges Repository.")
        head=GitBranches.run(path,["rev-parse","--verify",ref or "HEAD"]).stdout.strip()
        branch=GitBranches.run(path,["symbolic-ref","--quiet","--short","HEAD"],required=False).stdout.strip()
        log=GitBranches.run(path,["log", "-n",str(limit),"--format=%H%x00%h%x00%aI%x00%an%x00%s%x00%b%x00",head]).stdout
        return {"branch":branch or "Detached HEAD", "head":head,"commits":cls.parse(log)}

    @classmethod
    def parse(cls, log):
        fields=log.split("\0")
        commits=[]
        for index in range(0,len(fields)-5,6):
            sha,short,date,author,subject,body=fields[index:index+6]
            if not sha.strip():
                continue
            commits.append({"sha":sha.strip(),"short":short,"date":date,"author":author,"subject":subject,"body":body.strip()})
        return commits

    @classmethod
    def snapshot(cls, root, refresh=False, notify=None, cancelled=None):
        root=GitBranches.validate(root)
        result={}
        for name in cls.REPOSITORIES:
            if cancelled is not None and cancelled.is_set():break
            path=root if name=="SimFiles" else root/name
            try:
                info=cls.commits(path)
                result[name]=info
                if refresh:
                    try:GitBranches.run(path,["fetch","--prune","--no-recurse-submodules","origin"],timeout=120)
                    except (RuntimeError,OSError) as error:info["warning"]="Remote-Abruf fehlgeschlagen: "+str(error)
                info["branches"]=GitBranches.refs(path)["branches"]
                # Compare cached refs even offline; only refresh=True contacts origin.
                try:cls.remote_status(path,info)
                except (RuntimeError,ValueError,OSError) as error:info["warning"]="Remote-Vergleich nicht verfügbar: "+str(error)
            except (RuntimeError,ValueError,OSError) as error:
                result[name]={"error":str(error),"branch":"","commits":[]}
            if notify is not None:notify(result)
        return result

    @classmethod
    def remote_status(cls,path,info):
        if info["branch"]=="Detached HEAD":
            # A cloned submodule stays pinned. Compare only a local branch that
            # points exactly at that pinned commit; never check out another state.
            branches=GitBranches.run(path,["for-each-ref","--points-at="+info["head"],"--format=%(refname:short)","refs/heads/"]).stdout.splitlines()
            branch="main" if "main" in branches else branches[0] if len(branches)==1 else None
            if branch is None:
                info["remote_notice"]="Detached HEAD: kein eindeutig zugehöriger Branch für den Remote-Vergleich."
                return
            info["comparison_branch"]=branch
            info["selection_branch"]=branch
            ref="origin/"+branch
        else:
            upstream=GitBranches.run(path,["rev-parse","--abbrev-ref","--symbolic-full-name","@{upstream}"],required=False)
            ref=upstream.stdout.strip() if upstream.returncode==0 else "origin/"+info["branch"]
        if GitBranches.run(path,["rev-parse","--verify",ref],required=False).returncode:
            info["remote_notice"]="Kein zugehöriger Remote-Branch vorhanden."
            return
        info["remote_ref"]=ref
        info["remote_commits"]=cls.commits(path,ref=ref)["commits"]
        info["incoming"]=GitBranches.run(path,["log","-100","--format=%H","HEAD.."+ref]).stdout.splitlines()
        counts=GitBranches.run(path,["rev-list","--left-right","--count","HEAD..."+ref]).stdout.split()
        info["ahead"],info["behind"]=map(int,counts)
        prefix="Zuletzt bekannter Stand: " if info.get("warning") else ""
        info["remote_notice"]=prefix+str(info["behind"])+" neue Remote-Commits · "+str(info["ahead"])+" lokale Commits voraus"
