from pathlib import Path
import sys
import argparse
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from source.core.update import UpdateManager

class ReleaseManifest:
    @classmethod
    def main(cls):
        parser = argparse.ArgumentParser()
        parser.add_argument("--output", required=True)
        parser.add_argument("--version", required=True)
        parser.add_argument("--installer", required=True)
        parser.add_argument("--sha256", required=True)
        args = parser.parse_args()
        UpdateManager.write_manifest(args.output, args.version, args.installer, args.sha256)

if __name__ == "__main__":
    ReleaseManifest.main()
