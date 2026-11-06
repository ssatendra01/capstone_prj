"""Runtime configuration (environment variables only – no secrets in the repo)."""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parent
DB_PATH = Path(os.environ.get("CLEARVIEW_DB", ROOT / "data" / "clearview.db"))
SCHEMA_PATH = REPO / "db" / "schema.sqlite.sql"
ONTOLOGY_PATH = Path(os.environ.get("CLEARVIEW_ONTOLOGY", REPO / "context-studio" / "ontology.jsonld"))
STP_CONFIDENCE = 0.90
HITL_REDRESS_LIMIT = 150.0
