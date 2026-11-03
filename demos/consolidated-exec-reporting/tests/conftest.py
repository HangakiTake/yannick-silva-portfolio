import json, sys
from pathlib import Path
import pytest
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import pipeline  # noqa: E402

@pytest.fixture(scope="session")
def key():
    return json.loads((ROOT / "data" / "answer_key.json").read_text(encoding="utf-8"))

@pytest.fixture(scope="session")
def runs():
    return {s: pipeline.run(ROOT / "data" / s) for s in ("base", "clean", "messy", "next")}
