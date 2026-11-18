from pathlib import Path
from .api import Silver

class SilverSetup:
    @classmethod
    def load(cls, path, session="default"):
        path = Path(path).resolve()
        if not path.is_file() or path.suffix.lower() != ".sil":
            raise ValueError("An existing .sil setup file is required")
        return Silver.call("open", str(path), session=session)

    @classmethod
    def save_as(cls, path, session="default"):
        return Silver.call("save", str(Path(path).resolve()), session=session)

    @classmethod
    def snapshot(cls, session="default"):
        return {"project": Silver.call("get_project_properties", session=session),
                "config_parameters": Silver.call("get_config_parameters", session=session),
                "modules": {uid: Silver.call("get_module_properties", uid, session=session)
                            for uid in Silver.call("get_module_uuids", session=session)},
                "sfus": {uid: Silver.call("get_sfu_properties", uid, session=session)
                         for uid in Silver.call("get_top_level_sfu_uuids", session=session)}}

    @classmethod
    def set_parameter(cls, name, value, session="default"):
        return Silver.call("set_config_parameter", name, value, session=session)

    @classmethod
    def set_module_property(cls, uuid, name, value, session="default"):
        return Silver.call("set_module_property", uuid, name, value, session=session)

    @classmethod
    def set_sfu_property(cls, uuid, name, value, session="default"):
        return Silver.call("set_sfu_property", uuid, name, value, session=session)
