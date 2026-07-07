"""Graph storage backend: the ONLY place that knows how nodes and edges are
physically persisted.

Two implementations behind one protocol:

  InMemoryGraphStore : dict-backed, models upsert-by-key (MERGE) semantics
                       exactly, so the whole platform is testable with no
                       network and idempotency is a real property, not a mock.
  Neo4jGraphStore    : the same operations compiled to Cypher MERGE. This is the
                       only module in the codebase that emits Cypher.

The store speaks in upsert-by-key terms, never in queries. `GraphClient` builds
the domain API on top. Because both stores honor "upsert on the identity key",
re-running any write is a no-op, which is the idempotency guarantee the spec
requires and which the tests exercise against the in-memory store.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Protocol

from .model import Constraint, ConstraintKind

# Labels and relationship types cannot be parameterized in Cypher, so they are
# interpolated. Everything that reaches interpolation is validated against this
# to make injection impossible; property VALUES always go through parameters.
_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _check_ident(value: str) -> str:
    if not _IDENT.match(value):
        raise ValueError(f"unsafe graph identifier: {value!r}")
    return value


def _key(base_label: str, key_props: dict[str, object]) -> tuple[str, frozenset]:
    """Canonical, order-independent identity for a node: its base label plus the
    frozenset of its constrained key properties."""
    return base_label, frozenset(key_props.items())


class GraphStore(Protocol):
    """The persistence seam. All methods are idempotent on their identity keys."""

    def ensure_constraints(self, constraints: Iterable[Constraint]) -> None: ...

    def upsert_node(
        self,
        base_label: str,
        key_props: dict[str, object],
        set_props: dict[str, object],
        extra_labels: tuple[str, ...] = (),
    ) -> None:
        """MERGE a node on (base_label, key_props); set the rest; union in any
        extra labels (the pack subtype). Re-running with equal input is a no-op."""
        ...

    def upsert_edge(
        self,
        rel_type: str,
        src_label: str,
        src_key: dict[str, object],
        dst_label: str,
        dst_key: dict[str, object],
        key_props: dict[str, object],
        set_props: dict[str, object],
    ) -> None:
        """MERGE an edge on (rel_type, src, dst, key_props); set the rest.
        `key_props` carries identifying props (e.g. role) so distinct-role edges
        coexist; `set_props` carries provenance."""
        ...

    def get_node(self, base_label: str, key_props: dict[str, object]) -> dict | None:
        """Return the node's stored properties (including `_labels`) or None."""
        ...

    def out_neighbors(
        self, src_label: str, src_key: dict[str, object], rel_type: str
    ) -> list[tuple[dict, dict]]:
        """Return [(neighbor_props, edge_props)] for outgoing edges of rel_type."""
        ...

    def nodes_by_label(self, base_label: str) -> list[dict]:
        """Return the stored properties of every node with this base label."""
        ...


class InMemoryGraphStore:
    """Dict-backed reference store. Faithful to MERGE-on-key semantics so tests
    prove real idempotency rather than a mock's behavior."""

    def __init__(self) -> None:
        # (base_label, frozenset(key items)) -> mutable props dict (+ "_labels")
        self._nodes: dict[tuple[str, frozenset], dict] = {}
        # identity tuple -> edge props dict
        self._edges: dict[tuple, dict] = {}

    def ensure_constraints(self, constraints: Iterable[Constraint]) -> None:
        # In memory the identity key IS the constraint, so there is nothing to
        # create. Consuming the iterable keeps the interface honest.
        for _ in constraints:
            pass

    def upsert_node(
        self,
        base_label: str,
        key_props: dict[str, object],
        set_props: dict[str, object],
        extra_labels: tuple[str, ...] = (),
    ) -> None:
        k = _key(base_label, key_props)
        node = self._nodes.get(k)
        if node is None:
            node = {**key_props, "_labels": {base_label}}
            self._nodes[k] = node
        node.update(set_props)
        node["_labels"].update(extra_labels)

    def upsert_edge(
        self,
        rel_type: str,
        src_label: str,
        src_key: dict[str, object],
        dst_label: str,
        dst_key: dict[str, object],
        key_props: dict[str, object],
        set_props: dict[str, object],
    ) -> None:
        ident = (
            rel_type,
            _key(src_label, src_key),
            _key(dst_label, dst_key),
            frozenset(key_props.items()),
        )
        edge = self._edges.get(ident)
        if edge is None:
            edge = {**key_props}
            self._edges[ident] = edge
        edge.update(set_props)

    def get_node(self, base_label: str, key_props: dict[str, object]) -> dict | None:
        node = self._nodes.get(_key(base_label, key_props))
        return dict(node) if node is not None else None

    def out_neighbors(
        self, src_label: str, src_key: dict[str, object], rel_type: str
    ) -> list[tuple[dict, dict]]:
        src = _key(src_label, src_key)
        out: list[tuple[dict, dict]] = []
        for (rtype, s, d, _kp), eprops in self._edges.items():
            if rtype == rel_type and s == src:
                node = self._nodes.get(d)
                if node is not None:
                    out.append((dict(node), dict(eprops)))
        return out

    def nodes_by_label(self, base_label: str) -> list[dict]:
        return [
            dict(props)
            for (label, _k), props in self._nodes.items()
            if label == base_label
        ]


class Neo4jGraphStore:
    """Neo4j-backed store. Compiles the same upsert operations to Cypher MERGE.
    The only Cypher in the codebase lives here. The driver is imported lazily so
    the in-memory path (and its tests) run without the neo4j package present."""

    def __init__(self, uri: str, auth: tuple[str, str], database: str = "neo4j") -> None:
        from neo4j import GraphDatabase  # lazy: keeps offline tests dependency-free

        self._driver = GraphDatabase.driver(uri, auth=auth)
        self._database = database

    def close(self) -> None:
        self._driver.close()

    def ensure_constraints(self, constraints: Iterable[Constraint]) -> None:
        stmts: list[str] = []
        for c in constraints:
            label = _check_ident(c.label.value)
            props = ", ".join(f"n.{_check_ident(p)}" for p in c.properties)
            name = f"{label.lower()}_{'_'.join(c.properties)}"
            if c.kind is ConstraintKind.NODE_KEY:
                clause = f"({props}) IS NODE KEY"
            else:
                clause = f"({props}) IS UNIQUE"
            stmts.append(
                f"CREATE CONSTRAINT {name} IF NOT EXISTS "
                f"FOR (n:{label}) REQUIRE {clause}"
            )
        with self._driver.session(database=self._database) as s:
            for stmt in stmts:
                s.run(stmt)

    def upsert_node(
        self,
        base_label: str,
        key_props: dict[str, object],
        set_props: dict[str, object],
        extra_labels: tuple[str, ...] = (),
    ) -> None:
        label = _check_ident(base_label)
        key_pattern = ", ".join(f"{_check_ident(k)}: ${k}" for k in key_props)
        cypher = f"MERGE (n:{label} {{{key_pattern}}}) SET n += $set_props"
        for extra in extra_labels:
            cypher += f" SET n:{_check_ident(extra)}"
        params = {**key_props, "set_props": set_props}
        with self._driver.session(database=self._database) as s:
            s.run(cypher, **params)

    def upsert_edge(
        self,
        rel_type: str,
        src_label: str,
        src_key: dict[str, object],
        dst_label: str,
        dst_key: dict[str, object],
        key_props: dict[str, object],
        set_props: dict[str, object],
    ) -> None:
        rel = _check_ident(rel_type)
        sl, dl = _check_ident(src_label), _check_ident(dst_label)
        s_pat = ", ".join(f"{_check_ident(k)}: $s_{k}" for k in src_key)
        d_pat = ", ".join(f"{_check_ident(k)}: $d_{k}" for k in dst_key)
        r_pat = ", ".join(f"{_check_ident(k)}: $r_{k}" for k in key_props)
        r_pat = f" {{{r_pat}}}" if key_props else ""
        cypher = (
            f"MATCH (s:{sl} {{{s_pat}}}) MATCH (d:{dl} {{{d_pat}}}) "
            f"MERGE (s)-[r:{rel}{r_pat}]->(d) SET r += $set_props"
        )
        params: dict[str, object] = {"set_props": set_props}
        params.update({f"s_{k}": v for k, v in src_key.items()})
        params.update({f"d_{k}": v for k, v in dst_key.items()})
        params.update({f"r_{k}": v for k, v in key_props.items()})
        with self._driver.session(database=self._database) as s:
            s.run(cypher, **params)

    def get_node(self, base_label: str, key_props: dict[str, object]) -> dict | None:
        label = _check_ident(base_label)
        key_pattern = ", ".join(f"{_check_ident(k)}: ${k}" for k in key_props)
        cypher = f"MATCH (n:{label} {{{key_pattern}}}) RETURN n, labels(n) AS labels"
        with self._driver.session(database=self._database) as s:
            rec = s.run(cypher, **key_props).single()
            if rec is None:
                return None
            props = dict(rec["n"])
            props["_labels"] = set(rec["labels"])
            return props

    def out_neighbors(
        self, src_label: str, src_key: dict[str, object], rel_type: str
    ) -> list[tuple[dict, dict]]:
        sl = _check_ident(src_label)
        rel = _check_ident(rel_type)
        key_pattern = ", ".join(f"{_check_ident(k)}: ${k}" for k in src_key)
        cypher = (
            f"MATCH (s:{sl} {{{key_pattern}}})-[r:{rel}]->(d) "
            f"RETURN d, labels(d) AS labels, r"
        )
        out: list[tuple[dict, dict]] = []
        with self._driver.session(database=self._database) as s:
            for rec in s.run(cypher, **src_key):
                node = dict(rec["d"])
                node["_labels"] = set(rec["labels"])
                out.append((node, dict(rec["r"])))
        return out

    def nodes_by_label(self, base_label: str) -> list[dict]:
        label = _check_ident(base_label)
        cypher = f"MATCH (n:{label}) RETURN n, labels(n) AS labels"
        out: list[dict] = []
        with self._driver.session(database=self._database) as s:
            for rec in s.run(cypher):
                props = dict(rec["n"])
                props["_labels"] = set(rec["labels"])
                out.append(props)
        return out
