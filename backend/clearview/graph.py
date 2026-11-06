"""Context Studio knowledge graph (JSON-LD) with hybrid retrieval.

Hybrid query = vector similarity (TF-IDF cosine over each node's text) + graph expansion
(one hop over governedBy / routesTo / evidenceFrom edges). This mirrors the
`context-broker-hybrid-query` MCP tool contract so the same ontology file that is imported into
IBM Context Studio can be queried locally and offline.
"""
from __future__ import annotations

import json
import math
import re
from collections import Counter
from functools import lru_cache
from pathlib import Path

from . import config

EDGE_PROPS = ("governedBy", "routesTo", "evidenceFrom", "requiresAuthority", "usesSystem")
_TOKEN = re.compile(r"[a-z0-9£]+")
_STOP = {"the", "a", "an", "of", "and", "or", "to", "in", "is", "are", "for", "on", "be", "by", "at", "as", "it", "with"}


def _tokens(text: str) -> list[str]:
    return [t for t in _TOKEN.findall(text.lower()) if t not in _STOP]


def _flatten(node: dict) -> str:
    parts: list[str] = []
    for key, val in node.items():
        if key.startswith("@") and key != "@type":
            continue
        if isinstance(val, str):
            parts.append(val)
        elif isinstance(val, list):
            parts.extend(v for v in val if isinstance(v, str))
    return " ".join(parts + [str(node.get("@type", ""))])


class KnowledgeGraph:
    def __init__(self, graph: list[dict]):
        self.nodes: dict[str, dict] = {n["@id"]: n for n in graph}
        self._docs = {nid: Counter(_tokens(_flatten(n))) for nid, n in self.nodes.items()}
        df: Counter = Counter()
        for toks in self._docs.values():
            df.update(toks.keys())
        n_docs = len(self._docs)
        self._idf = {t: math.log((1 + n_docs) / (1 + c)) + 1 for t, c in df.items()}
        self._vec = {nid: self._weigh(c) for nid, c in self._docs.items()}

    @classmethod
    def load(cls, path: Path | str | None = None) -> "KnowledgeGraph":
        data = json.loads(Path(path or config.ONTOLOGY_PATH).read_text(encoding="utf-8"))
        return cls(data["@graph"])

    # ---- retrieval -------------------------------------------------------------------------
    def _weigh(self, counts: Counter) -> dict[str, float]:
        vec = {t: (1 + math.log(c)) * self._idf.get(t, 1.0) for t, c in counts.items()}
        norm = math.sqrt(sum(v * v for v in vec.values())) or 1.0
        return {t: v / norm for t, v in vec.items()}

    def _score(self, qvec: dict[str, float], nid: str) -> float:
        dvec = self._vec[nid]
        return sum(w * dvec.get(t, 0.0) for t, w in qvec.items())

    def of_type(self, node_type: str) -> list[dict]:
        return [n for n in self.nodes.values() if n.get("@type") == node_type]

    def get(self, node_id: str) -> dict | None:
        return self.nodes.get(node_id)

    @staticmethod
    def edges(node: dict) -> list[str]:
        out: list[str] = []
        for prop in EDGE_PROPS:
            val = node.get(prop)
            if not val:
                continue
            for item in val if isinstance(val, list) else [val]:
                if isinstance(item, dict) and "@id" in item:
                    out.append(item["@id"])
        return out

    def hybrid_query(self, query: str, node_types: list[str] | None = None, top_k: int = 5,
                     expand: bool = True) -> dict:
        qvec = self._weigh(Counter(_tokens(query)))
        scored = []
        for nid, node in self.nodes.items():
            if node_types and node.get("@type") not in node_types:
                continue
            s = self._score(qvec, nid)
            if s > 0:
                scored.append((s, nid))
        scored.sort(reverse=True)
        hits, graph_nodes = [], {}
        for s, nid in scored[:top_k]:
            node = self.nodes[nid]
            neighbours = self.edges(node) if expand else []
            hits.append({
                "id": nid, "type": node.get("@type"), "name": node.get("name"),
                "description": node.get("description", ""), "score": round(s, 4),
                "neighbours": neighbours,
            })
            for nb in neighbours:
                if nb in self.nodes and nb not in graph_nodes:
                    n = self.nodes[nb]
                    graph_nodes[nb] = {"id": nb, "type": n.get("@type"), "name": n.get("name"),
                                       "description": n.get("description", "")}
        return {"query": query, "hits": hits, "graph_context": list(graph_nodes.values())}


@lru_cache(maxsize=1)
def default_graph() -> KnowledgeGraph:
    return KnowledgeGraph.load()
