import hashlib
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import tree_sitter_python as tspython
from tree_sitter import Language, Parser


@dataclass
class CtxNode:
    id: str
    kind: str
    name: str
    path: str
    start_line: int
    end_line: int
    signature: Optional[str] = None
    parent: Optional[str] = None

    def to_dict(self) -> dict:
        d = {
            "id": self.id,
            "kind": self.kind,
            "name": self.name,
            "path": self.path,
            "span": {"start_line": self.start_line, "end_line": self.end_line},
        }
        if self.signature:
            d["signature"] = self.signature
        if self.parent:
            d["parent"] = self.parent
        return d


@dataclass
class CtxEdge:
    from_node: str
    to_node: str
    edge_type: str

    def to_dict(self) -> dict:
        return {"from": self.from_node, "to": self.to_node, "type": self.edge_type}


@dataclass
class CtxInterface:
    name: str
    members: list[str]

    def to_dict(self) -> dict:
        return {"name": self.name, "members": self.members}


@dataclass
class CtxDocument:
    metadata: dict
    nodes: list[dict]
    edges: list[dict]
    interfaces: list[dict]
    span_map: dict[str, dict]

    def to_dict(self) -> dict:
        return {
            "metadata": self.metadata,
            "nodes": self.nodes,
            "edges": self.edges,
            "interfaces": self.interfaces,
            "span_map": self.span_map,
        }


def _make_node_id(kind: str, path: str, name: str) -> str:
    raw = f"{path}:{name}:{kind}"
    h = hashlib.sha256(raw.encode()).hexdigest()[:12]
    prefix = kind[0].lower()
    safe_name = name.lower().replace("_", "")
    return f"n_{prefix}_{safe_name}_{h}"


def _get_text(node, source: bytes) -> str:
    return source[node.start_byte : node.end_byte].decode("utf-8", errors="replace")


class CtxParser:
    def __init__(self, repo_path: str, language: str = "python"):
        self.repo_path = Path(repo_path).resolve()
        self.language = language
        self._parser = Parser()
        self._parser.language = Language(tspython.language())
        self._source_cache: dict[str, bytes] = {}

    def _load_source(self, file_path: Path) -> bytes:
        path_str = str(file_path)
        if path_str not in self._source_cache:
            with open(file_path, "rb") as f:
                self._source_cache[path_str] = f.read()
        return self._source_cache[path_str]

    def parse_file(self, file_path: Path) -> tuple[list[CtxNode], list[CtxEdge], list[CtxInterface]]:
        rel_path = str(file_path.relative_to(self.repo_path))
        source = self._load_source(file_path)
        tree = self._parser.parse(source)

        nodes: list[CtxNode] = []
        edges: list[CtxEdge] = []

        total_lines = len(source.decode("utf-8", errors="replace").splitlines())
        file_node_id = _make_node_id("file", rel_path, file_path.stem)
        file_node = CtxNode(
            id=file_node_id,
            kind="file",
            name=file_path.name,
            path=rel_path,
            start_line=1,
            end_line=total_lines,
        )
        nodes.append(file_node)

        class_stack: list[CtxNode] = []
        func_stack: list[tuple[str, str]] = []

        def add_func_node(def_node, name: str, kind: str, signature: str, parent_id: Optional[str] = None) -> str:
            start = def_node.start_point[0] + 1
            end = def_node.end_point[0] + 1
            node_id = _make_node_id(kind, rel_path, name)
            node = CtxNode(
                id=node_id,
                kind=kind,
                name=name,
                path=rel_path,
                start_line=start,
                end_line=end,
                signature=signature,
                parent=parent_id or file_node_id,
            )
            nodes.append(node)
            edges.append(CtxEdge(from_node=file_node_id, to_node=node_id, edge_type="contains"))
            if class_stack:
                edges.append(CtxEdge(from_node=class_stack[-1].id, to_node=node_id, edge_type="contains"))
            func_stack.append((node_id, name))
            return node_id

        def on_call(node):
            if not func_stack:
                return
            try:
                func_text = _get_text(node, source)
                call_name = func_text.split("(")[0].strip().split(".")[-1]
                if call_name and call_name.isidentifier():
                    called_id = _make_node_id("function", rel_path, call_name)
                    edges.append(CtxEdge(from_node=func_stack[-1][0], to_node=called_id, edge_type="calls"))
            except Exception:
                pass

        cursor = tree.walk()

        def walk(node):
            nt = node.type

            if nt == "function_definition":
                name_bytes = node.child_by_field_name("name")
                name = name_bytes.text.decode() if name_bytes else "unknown"
                try:
                    sig = _get_text(node, source).split("\n")[0].strip()
                except Exception:
                    sig = f"def {name}(...)"
                parent_id = class_stack[-1].id if class_stack else None
                add_func_node(node, name, "function", sig, parent_id)

            elif nt == "class_definition":
                name_bytes = node.child_by_field_name("name")
                name = name_bytes.text.decode() if name_bytes else "UnknownClass"
                node_id = _make_node_id("class", rel_path, name)
                start = node.start_point[0] + 1
                end = node.end_point[0] + 1
                class_node = CtxNode(
                    id=node_id, kind="class", name=name, path=rel_path, start_line=start, end_line=end, parent=file_node_id
                )
                nodes.append(class_node)
                edges.append(CtxEdge(from_node=file_node_id, to_node=node_id, edge_type="contains"))
                class_stack.append(class_node)

                try:
                    bases = node.child_by_field_name("base_types")
                    if bases:
                        for base in bases.children:
                            if base.type == "identifier":
                                base_name = base.text.decode()
                                base_id = _make_node_id("class", rel_path, base_name)
                                edges.append(CtxEdge(from_node=node_id, to_node=base_id, edge_type="inherits"))
                except Exception:
                    pass

            elif nt == "import_statement":
                try:
                    for child in node.children:
                        if child.type == "dotted_name":
                            import_name = child.text.decode()
                            imp_id = _make_node_id("import", rel_path, import_name)
                            imp_node = CtxNode(
                                id=imp_id,
                                kind="import",
                                name=import_name,
                                path=rel_path,
                                start_line=node.start_point[0] + 1,
                                end_line=node.end_point[0] + 1,
                            )
                            nodes.append(imp_node)
                            edges.append(CtxEdge(from_node=file_node_id, to_node=imp_id, edge_type="imports"))
                except Exception:
                    pass

            elif nt == "import_from_statement":
                try:
                    module_node = node.child_by_field_name("module_name")
                    module_name = module_node.text.decode() if module_node else "unknown"
                    import_id = _make_node_id("import", rel_path, module_name)
                    import_node = CtxNode(
                        id=import_id,
                        kind="import",
                        name=module_name,
                        path=rel_path,
                        start_line=node.start_point[0] + 1,
                        end_line=node.end_point[0] + 1,
                    )
                    nodes.append(import_node)
                    edges.append(CtxEdge(from_node=file_node_id, to_node=import_id, edge_type="imports"))
                except Exception:
                    pass

            elif nt == "call":
                on_call(node)

            for child in node.children:
                walk(child)

            if nt == "class_definition" and class_stack:
                class_stack.pop()
            if nt == "function_definition" and func_stack:
                func_stack.pop()

        walk(tree.root_node)
        return nodes, edges, []

    def parse_repo(self) -> CtxDocument:
        start = time.time()
        all_nodes: list[CtxNode] = []
        all_edges: list[CtxEdge] = []
        all_interfaces: list[CtxInterface] = []
        span_map: dict[str, dict] = {}

        for root, dirs, files in os.walk(self.repo_path):
            dirs[:] = [d for d in dirs if d not in (".git", "__pycache__", ".venv", "venv", "node_modules", ".pytest_cache", ".ctx")]
            for file in sorted(files):
                if not file.endswith(".py"):
                    continue
                file_path = Path(root) / file
                nodes, edges, interfaces = self.parse_file(file_path)
                all_nodes.extend(nodes)
                all_edges.extend(edges)
                all_interfaces.extend(interfaces)

        for node in all_nodes:
            span_map[node.id] = {
                "file": node.path,
                "start_line": node.start_line,
                "end_line": node.end_line,
            }

        elapsed = time.time() - start

        deduped_nodes: dict[str, CtxNode] = {}
        for n in all_nodes:
            if n.id not in deduped_nodes:
                deduped_nodes[n.id] = n

        deduped_edges: list[CtxEdge] = []
        seen_edges: set[tuple[str, str, str]] = set()
        for e in all_edges:
            key = (e.from_node, e.to_node, e.edge_type)
            if key not in seen_edges:
                seen_edges.add(key)
                deduped_edges.append(e)

        return CtxDocument(
            metadata={
                "repo_id": self.repo_path.name,
                "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "language": self.language,
                "version": "1.0",
                "parser": "tree-sitter-python@0.25.0",
                "parse_time_seconds": round(elapsed, 3),
            },
            nodes=[n.to_dict() for n in sorted(deduped_nodes.values(), key=lambda x: (x.path, x.start_line))],
            edges=[e.to_dict() for e in deduped_edges],
            interfaces=[i.to_dict() for i in all_interfaces],
            span_map=span_map,
        )

    def save(self, document: CtxDocument, output_path: str | Path | None = None) -> str:
        import yaml

        output_path = output_path or self.repo_path / ".ctx" / "repo.ctx"
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        def str_representer(dumper, data):
            style = "|" if "\n" in data else None
            return dumper.represent_scalar("tag:yaml.org,2002:str", data, style=style)

        yaml.add_representer(str, str_representer)
        content = yaml.dump(document.to_dict(), sort_keys=False, allow_unicode=True)

        with open(output_path, "w", encoding="utf-8") as f:
            f.write(content)

        return str(output_path)