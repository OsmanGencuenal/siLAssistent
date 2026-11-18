"""Read supportMail and silverLicences once at build time and bake it into the source snapshot."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from source.core.config import Config
from source.core.release_paths import ReleasePaths
from source.stand_management.repo_request import RepoRequest
from source.silver.licences import SilverLicences
from source.core.runtime import Runtime

class EmbedBuildSettings:
    @classmethod
    def write(cls, destination, ini=None):
        source=Path(ini) if ini else Runtime.project_root()/"siLAssistent_Update.ini"
        paths=ReleasePaths.read(ini or Config.load()["update_ini_path"])
        mail=RepoRequest.read_support_mail(ini or Config.load()["update_ini_path"])
        servers=SilverLicences.read(source)
        Path(destination).write_text("# Generated at build time.\nSUPPORT_MAIL = "+repr(mail)+"\nSILVER_LICENCE_SERVERS = "+repr(servers)+"\nRELEASE_PATHS = "+repr(paths)+"\n",encoding="utf-8")

if __name__=="__main__":
    EmbedBuildSettings.write(sys.argv[1])
