from pathlib import Path
import os
import sys
import logging
from logging.handlers import RotatingFileHandler

class Runtime:
    @classmethod
    def is_compiled(cls):
        return bool(getattr(sys,"frozen",False) or "__compiled__" in globals())

    @classmethod
    def project_root(cls):
        if getattr(sys, "frozen", False) or "__compiled__" in globals():
            return Path(sys.executable).resolve().parent
        return Path(__file__).resolve().parents[2]

    @classmethod
    def data_root(cls):
        root = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "siLAssistent"
        root.mkdir(parents=True, exist_ok=True)
        return root

    @classmethod
    def configure_logging(cls):
        logger = logging.getLogger("siLAssistent")
        if not logger.handlers:
            handler = RotatingFileHandler(cls.data_root() / "siLAssistent.log", maxBytes=2_000_000,
                                          backupCount=3, encoding="utf-8")
            handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
            logger.addHandler(handler)
            logger.setLevel(logging.INFO)
        return logger
