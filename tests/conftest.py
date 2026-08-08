import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SKILL = ROOT / "skills" / "precis"
SCRIPTS = SKILL / "scripts"
FIXTURES = SKILL / "assets" / "fixtures"
REFERENCES = SKILL / "references"

sys.path.insert(0, str(SCRIPTS))

FIXTURE_NAMES = ["small", "medium", "monster"]


@pytest.fixture(scope="session")
def fixtures():
    return {name: json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))
            for name in FIXTURE_NAMES}


@pytest.fixture(params=FIXTURE_NAMES)
def fixture_model(request, fixtures):
    return request.param, fixtures[request.param]
