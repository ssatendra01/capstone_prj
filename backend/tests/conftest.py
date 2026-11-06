from __future__ import annotations

import shutil
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from clearview import db  # noqa: E402
from clearview.seed import ANCHOR, seed  # noqa: E402


@pytest.fixture(scope="session")
def template_db(tmp_path_factory):
    p = tmp_path_factory.mktemp("tpl") / "t.db"
    conn = db.connect(p)
    seed(conn)
    conn.close()
    return p


@pytest.fixture()
def conn(template_db, tmp_path):
    p = tmp_path / "w.db"
    shutil.copy(template_db, p)
    c = db.connect(p)
    yield c
    c.close()


@pytest.fixture()
def as_of():
    return ANCHOR
