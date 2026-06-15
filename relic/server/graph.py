from pathlib import Path

from tree_sitter import Language, Parser
import tree_sitter_python as tspython

PY_LANGUAGE = Language(tspython.language())


class CallGraph:
    def __init__(self, repo_path: Path):
        self.repo_path = repo_path
        self.parser = Parser(PY_LANGUAGE)
        self.nodes: dict = {}
        self.edges: list = []
        self._all_funcs: dict[str, str] = {}
        self._build()

    def _build(self):
        for py_file in sorted(self.repo_path.rglob("*.py")):
            rel = str(py_file.relative_to(self.repo_path)).replace("\\", "/")
            service = rel.split("/")[0]

            source = py_file.read_text(encoding="utf-8")
            tree = self.parser.parse(source.encode())

            local_funcs: dict[str, str] = {}
            calls: list[tuple[str, str]] = []

            def walk(node, current_func=None):
                if node.type == "function_definition":
                    name_node = node.child_by_field_name("name")
                    if name_node:
                        fname = name_node.text.decode()
                        node_id = f"n_{service}_{fname}"
                        local_funcs[fname] = node_id
                        self._all_funcs[fname] = node_id
                        self.nodes[node_id] = {
                            "node_id": node_id,
                            "name": fname,
                            "file": rel,
                            "service": service,
                            "operation": fname,
                        }
                        for child in node.children:
                            walk(child, fname)
                        return
                if node.type == "call":
                    fn_node = node.child_by_field_name("function")
                    if fn_node:
                        call_name = fn_node.text.decode()
                        if current_func:
                            calls.append((current_func, call_name))
                for child in node.children:
                    walk(child, current_func)

            walk(tree.root_node)

            for caller, callee_name in calls:
                callee_simple = callee_name.split(".")[-1]
                if callee_simple in local_funcs:
                    caller_id = f"n_{service}_{caller}"
                    callee_id = local_funcs[callee_simple]
                    if caller_id in self.nodes:
                        self.edges.append((caller_id, callee_id))

        for caller, callee_name in list(self.edges):
            pass

        cross_calls: list[tuple[str, str]] = []
        for py_file in sorted(self.repo_path.rglob("*.py")):
            rel = str(py_file.relative_to(self.repo_path)).replace("\\", "/")
            service = rel.split("/")[0]
            source = py_file.read_text(encoding="utf-8")
            tree = self.parser.parse(source.encode())

            def find_calls(node, current_func_id=None):
                current = current_func_id
                if node.type == "function_definition":
                    name_node = node.child_by_field_name("name")
                    if name_node:
                        fname = name_node.text.decode()
                        current = f"n_{service}_{fname}"
                    for child in node.children:
                        find_calls(child, current)
                    return
                if node.type == "call":
                    fn_node = node.child_by_field_name("function")
                    if fn_node and current:
                        call_name = fn_node.text.decode()
                        callee_simple = call_name.split(".")[-1]
                        if callee_simple in self._all_funcs:
                            callee_id = self._all_funcs[callee_simple]
                            edge = (current, callee_id)
                            if edge not in self.edges and current != callee_id:
                                cross_calls.append(edge)
                    if fn_node and current:
                        parts = call_name.split(".")
                        if len(parts) >= 2:
                            imported_svc = parts[-2]
                            for nid, ndata in self.nodes.items():
                                if ndata["service"].replace("_service", "") == imported_svc and ndata["operation"] == parts[-1]:
                                    edge = (current, nid)
                                    if edge not in self.edges and current != nid:
                                        cross_calls.append(edge)
                for child in node.children:
                    find_calls(child, current)

            find_calls(tree.root_node)

        for edge in cross_calls:
            if edge not in self.edges:
                self.edges.append(edge)

    def blast_radius(self, node_id: str) -> int:
        if node_id not in self.nodes:
            return 0
        downstream = set()
        stack = [node_id]
        while stack:
            current = stack.pop()
            for caller, callee in self.edges:
                if callee == current and caller not in downstream:
                    downstream.add(caller)
                    stack.append(caller)
        return len(downstream)

    def changed_files_to_nodes(self, changed_files: list) -> list:
        result = []
        for f in changed_files:
            f_norm = f.replace("\\", "/")
            for node_id, data in self.nodes.items():
                if data["file"].replace("\\", "/") == f_norm:
                    result.append(node_id)
        return result
