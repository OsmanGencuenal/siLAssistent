"""Read-only commit snapshots for the active branch of each setup repository."""
from pathlib import Path
from .git_branches import GitBranches

class GitHistory:
    REPOSITORIES=("SimFiles","ICE","ECM","CPC","DT")

    @classmethod
    def commits(cls, path, limit=100):
        path=Path(path).resolve()
        if not (path/".git").exists():
            raise ValueError("Repository nicht vorhanden oder nicht initialisiert.")
        actual=Path(GitBranches.run(path,["rev-parse","--show-toplevel"]).stdout.strip()).resolve()
        if actual!=path:
            raise ValueError("Kein eigenständiges Repository.")
        head=GitBranches.run(path,["rev-parse","--verify","HEAD"]).stdout.strip()
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
    def snapshot(cls, root):
        root=GitBranches.validate(root)
        result={}
        for name in cls.REPOSITORIES:
            path=root if name=="SimFiles" else root/name
            try:
                result[name]=cls.commits(path)
                result[name]["branches"]=GitBranches.refs(path)["branches"]
            except (RuntimeError,ValueError,OSError) as error:
                result[name]={"error":str(error),"branch":"","commits":[]}
        return result
