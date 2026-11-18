from pathlib import Path
import json
import pytest
from tools.check_distribution import DistributionCheck


def test_distribution_rejects_missing_runtime_and_development_artifacts(tmp_path):
    with pytest.raises(ValueError,match="Missing runtime files"):
        DistributionCheck.inspect(tmp_path)
    for name in DistributionCheck.REQUIRED:
        target=tmp_path/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_text("runtime",encoding="utf-8")
    (tmp_path/"drivers/manifest.json").write_text(json.dumps({"versions":[]}),encoding="utf-8")
    assert DistributionCheck.inspect(tmp_path)["runtime_only"]
    (tmp_path/"icons/proposals").mkdir()
    with pytest.raises(ValueError,match="proposals"):
        DistributionCheck.inspect(tmp_path)
