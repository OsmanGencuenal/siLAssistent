from pathlib import Path
import json

class Catalog:
    @classmethod
    def load(cls, product):
        if product not in ("inca", "silver"):
            raise ValueError("Unknown API catalog")
        path = Path(__file__).resolve().parents[1] / product / "catalog.json"
        return json.loads(path.read_text(encoding="utf-8"))

    @classmethod
    def search(cls, product, query=""):
        term = query.casefold()
        return [entry for entry in cls.load(product)["methods"]
                if term in (entry["name"] + " " + entry.get("description", "") + " " +
                            " / ".join(entry.get("path", []))).casefold()]
