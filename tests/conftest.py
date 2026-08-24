from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest


@pytest.fixture(scope="session")
def golden_fixture() -> dict[str, Any]:
    path = Path(__file__).parents[1] / "fixtures" / "golden" / "sales-fraud-v1.json"
    return json.loads(path.read_text(encoding="utf-8"))
