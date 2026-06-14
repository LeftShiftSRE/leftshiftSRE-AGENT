from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yaml


@dataclass
class GraphNode:
    id: str
    kind: str
    name: str
    path: str
    start_line: int
    end_line: int
    signature: Optional[str] = None
    parent: Optional[str] = None


@dataclass
class GraphEdge:
    from_node: str
    to_node: str
    edge_type: str


@dataclass
class CtxGraph:
    nodes: dict[str, GraphNode] = field(default_factory=dict)
    edges: list[GraphEdge] = field(default_factory=list)
    interfaces: list[dict] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)
    span_map: dict[str, dict] = field(default_factory=dict)

    _adj_downstream: dict[str, list[GraphEdge]] = field(default_factory=lambda: defaultdict(list))
    _adj_upstream: dict[str, list[GraphEdge]] = field(default_factory=lambda: defaultdict(list))
    _name_index: dict[str, list[str]] = field(default_factory=lambda: defaultdict(list))

    @classmethod
    def load(cls, ctx_path: str | Path) -> "CtxGraph":
        ctx_path = Path(ctx_path)
        with open(ctx_path, encoding="utf-8") as f:
            data = yaml.safe_load(f)

        g = cls()
        g.metadata = data.get("metadata", {})
        g.interfaces = data.get("interfaces", [])
        g.span_map = data.get("span_map", {})

        for n in data.get("nodes", []):
            span = n.get("span", {})
            node = GraphNode(
                id=n["id"],
                kind=n["kind"],
                name=n["name"],
                path=n["path"],
                start_line=span.get("start_line", 0),
                end_line=span.get("end_line", 0),
                signature=n.get("signature"),
                parent=n.get("parent"),
            )
            g.nodes[n["id"]] = node
            g._name_index[node.name.lower()].append(node.id)

        for e in data.get("edges", []):
            edge = GraphEdge(from_node=e["from"], to_node=e["to"], edge_type=e["type"])
            g.edges.append(edge)
            g._adj_downstream[e["from"]].append(edge)
            g._adj_upstream[e["to"]].append(edge)

        return g

    def get_node(self, node_id: str) -> GraphNode | None:
        return self.nodes.get(node_id)

    def search(self, query: str, kind: str | None = None) -> list[GraphNode]:
        query_lower = query.lower()
        results: list[tuple[GraphNode, float]] = []

        for node_id, node in self.nodes.items():
            if kind and node.kind != kind:
                continue
            name_lower = node.name.lower()
            if query_lower == name_lower:
                results.append((node, 1.0))
            elif name_lower.startswith(query_lower):
                results.append((node, 0.8))
            elif query_lower in name_lower:
                results.append((node, 0.5))

        results.sort(key=lambda x: (-x[1], x[0].name))
        return [r[0] for r in results]

    def get_context_summary(self) -> dict:
        kind_counts: dict[str, int] = defaultdict(int)
        packages: set[str] = set()
        for node in self.nodes.values():
            kind_counts[node.kind] += 1
            if node.kind == "file":
                pkg = str(Path(node.path).parent)
                if pkg not in (".", ""):
                    packages.add(pkg)

        return {
            "files": kind_counts.get("file", 0),
            "classes": kind_counts.get("class", 0),
            "functions": kind_counts.get("function", 0),
            "methods": kind_counts.get("method", 0),
            "imports": kind_counts.get("import", 0),
            "interfaces": len(self.interfaces),
            "packages": sorted(packages),
        }

    def traverse(
        self,
        start_node_id: str,
        direction: str = "downstream",
        edge_type: str | None = None,
        max_depth: int = 3,
    ) -> list[GraphNode]:
        results: list[GraphNode] = []
        visited: set[str] = set()
        queue: list[tuple[str, int]] = [(start_node_id, 0)]
        adj = self._adj_downstream if direction == "downstream" else self._adj_upstream

        while queue:
            current_id, depth = queue.pop(0)
            if current_id in visited or depth > max_depth:
                continue
            visited.add(current_id)

            node = self.nodes.get(current_id)
            if node and current_id != start_node_id:
                results.append(node)

            for edge in adj.get(current_id, []):
                if edge_type and edge.edge_type != edge_type:
                    continue
                neighbor_id = edge.to_node if direction == "downstream" else edge.from_node
                if neighbor_id not in visited and depth < max_depth:
                    queue.append((neighbor_id, depth + 1))

        return results

    def get_edges(self, node_id: str, direction: str = "downstream", edge_type: str | None = None) -> list[GraphEdge]:
        adj = self._adj_downstream if direction == "downstream" else self._adj_upstream
        edges = adj.get(node_id, [])
        if edge_type:
            edges = [e for e in edges if e.edge_type == edge_type]
        return edges

    def get_code_span(self, node_id: str) -> dict | None:
        span = self.span_map.get(node_id)
        if not span:
            node = self.nodes.get(node_id)
            if not node:
                return None
            span = {"file": node.path, "start_line": node.start_line, "end_line": node.end_line}
            self.span_map[node_id] = span

        file_path = Path(self.metadata.get("root_path", ".")) / span["file"]
        if file_path.exists():
            with open(file_path, encoding="utf-8") as f:
                lines = f.readlines()
            start = max(0, span["start_line"] - 1)
            end = min(len(lines), span["end_line"])
            code = "".join(lines[start:end])
        else:
            code = f"# (file not found: {span['file']})"

        return {
            "node_id": node_id,
            "file": span["file"],
            "start_line": span["start_line"],
            "end_line": span["end_line"],
            "code": code,
        }

    def find_critical_paths(self) -> list[list[str]]:
        paths: list[list[str]] = []
        entry_nodes = [nid for nid, n in self.nodes.items() if n.kind == "file" and ("gateway" in n.path or "api" in n.path or "main" in n.path)]

        for entry_id in entry_nodes:
            visited: set[str] = set()
            path: list[str] = []

            def dfs(node_id: str, current_path: list[str]):
                current_path = current_path + [node_id]
                node = self.nodes.get(node_id)
                if not node:
                    return
                edges = self.get_edges(node_id, direction="downstream", edge_type="calls")
                if not edges:
                    paths.append(current_path)
                    return
                for edge in edges:
                    if edge.to_node not in visited:
                        visited.add(edge.to_node)
                        dfs(edge.to_node, current_path)
                        visited.discard(edge.to_node)

            dfs(entry_id, [])
        return paths