import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class NodeConfig:
    name: str
    role: str
    host: str
    ssh_user: str
    ssh_port: int = 22
    project_dir: str = "~/image-pipeline"


@dataclass(frozen=True)
class ClusterConfig:
    name: str
    api_url: str
    nodes: list[NodeConfig]


def load_cluster_config(path: Path) -> ClusterConfig:
    if not path.exists():
        raise FileNotFoundError(f"Cluster config not found: {path}")

    raw = json.loads(path.read_text(encoding="utf-8"))

    name = require_non_empty_string(raw, "name")
    api_url = require_non_empty_string(raw, "api_url")

    raw_nodes = raw.get("nodes")

    if not isinstance(raw_nodes, list) or not raw_nodes:
        raise ValueError("'nodes' must be a non-empty list")

    nodes = [parse_node(node, index) for index, node in enumerate(raw_nodes)]

    node_names = [node.name for node in nodes]

    if len(node_names) != len(set(node_names)):
        raise ValueError("Every node must have a unique name")

    main_nodes = [node for node in nodes if node.role == "main"]

    if len(main_nodes) != 1:
        raise ValueError(
            "Cluster config must contain exactly one node with role='main'"
        )

    return ClusterConfig(
        name=name,
        api_url=api_url,
        nodes=nodes,
    )


def parse_node(raw: dict, index: int) -> NodeConfig:
    if not isinstance(raw, dict):
        raise ValueError(f"Node at index {index} must be an object")

    name = require_non_empty_string(raw, "name", context=f"node {index}")
    role = require_non_empty_string(raw, "role", context=f"node {index}")
    host = require_non_empty_string(raw, "host", context=f"node {index}")
    ssh_user = require_non_empty_string(raw, "ssh_user", context=f"node {index}")

    if role not in {"main", "worker"}:
        raise ValueError(
            f"'role' for node '{name}' must be either 'main' or 'worker'"
        )

    ssh_port = raw.get("ssh_port", 22)
    project_dir = raw.get("project_dir", "~/image-pipeline")

    if not isinstance(ssh_port, int) or ssh_port <= 0:
        raise ValueError(f"'ssh_port' for node '{name}' must be a positive integer")

    if not isinstance(project_dir, str) or not project_dir.strip():
        raise ValueError(f"'project_dir' for node '{name}' must be a non-empty string")

    return NodeConfig(
        name=name,
        role=role,
        host=host,
        ssh_user=ssh_user,
        ssh_port=ssh_port,
        project_dir=project_dir,
    )


def require_non_empty_string(
    raw: dict,
    key: str,
    context: str = "cluster config",
) -> str:
    value = raw.get(key)

    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"'{key}' in {context} must be a non-empty string")

    return value.strip()
