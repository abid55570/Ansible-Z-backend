import yaml

from app.ir.blocks import BLOCKS


class IRError(Exception):
    """Raised when an IR graph is invalid. Carries a list of human-readable messages."""

    def __init__(self, errors):
        self.errors = errors if isinstance(errors, list) else [errors]
        super().__init__("; ".join(self.errors))


def validate(ir: dict) -> None:
    if not isinstance(ir, dict):
        raise IRError("IR must be an object")

    errors: list[str] = []
    for key in ("region", "name"):
        if not ir.get(key):
            errors.append(f"missing '{key}'")

    nodes = ir.get("nodes")
    if not isinstance(nodes, list) or not nodes:
        errors.append("'nodes' must be a non-empty list")
        raise IRError(errors)

    ids = [n.get("id") for n in nodes]
    if len(ids) != len(set(ids)):
        errors.append("duplicate node ids")
    id_to_type = {n["id"]: n.get("type") for n in nodes if n.get("id")}

    for node in nodes:
        nid = node.get("id")
        if not nid:
            errors.append("a node is missing 'id'")
            continue
        ntype = node.get("type")
        if ntype not in BLOCKS:
            errors.append(f"{nid}: unknown type '{ntype}'")
            continue
        spec = BLOCKS[ntype]
        props = node.get("props", {})
        for req in spec["required"]:
            if req not in props:
                errors.append(f"{nid}: missing required prop '{req}'")
        inputs = node.get("inputs", {})
        for port, pspec in spec["inputs"].items():
            if port not in inputs:
                errors.append(f"{nid}: missing input '{port}'")
                continue
            refs = inputs[port] if isinstance(inputs[port], list) else [inputs[port]]
            for ref in refs:
                if ref not in id_to_type:
                    errors.append(f"{nid}: input '{port}' references unknown node '{ref}'")
                elif id_to_type[ref] != pspec["type"]:
                    errors.append(f"{nid}: input '{port}' must be a {pspec['type']}, got '{id_to_type[ref]}'")

    if errors:
        raise IRError(errors)


def _topo_sort(nodes: list[dict]) -> list[str]:
    deps: dict[str, set] = {}
    for node in nodes:
        deps.setdefault(node["id"], set())
        for value in (node.get("inputs") or {}).values():
            for ref in (value if isinstance(value, list) else [value]):
                deps[node["id"]].add(ref)

    order: list[str] = []
    state: dict[str, int] = {}  # 0 = visiting, 1 = done

    def visit(nid: str) -> None:
        if state.get(nid) == 1:
            return
        if state.get(nid) == 0:
            raise IRError(f"dependency cycle involving '{nid}'")
        state[nid] = 0
        for dep in deps.get(nid, ()):
            visit(dep)
        state[nid] = 1
        order.append(nid)

    for node in nodes:
        visit(node["id"])
    return order


def _strip_none(value):
    if isinstance(value, dict):
        return {k: _strip_none(v) for k, v in value.items() if v is not None}
    if isinstance(value, list):
        return [_strip_none(v) for v in value]
    return value


def compile_ir(ir: dict) -> dict[str, str]:
    """Compile an IR graph into a complete Ansible project ({path: content})."""
    validate(ir)
    nodes = {n["id"]: n for n in ir["nodes"]}
    order = _topo_sort(ir["nodes"])
    ctx = {"region": ir["region"]}

    # symbol table: node id -> the Ansible expression yielding its output
    outputs = {
        nid: f"{{{{ {nid}_result.{BLOCKS[node['type']]['output']} }}}}"
        for nid, node in nodes.items()
    }

    tasks: list[dict] = []
    for nid in order:
        node = nodes[nid]
        spec = BLOCKS[node["type"]]
        refs = {}
        for port, value in (node.get("inputs") or {}).items():
            refs[port] = [outputs[r] for r in value] if isinstance(value, list) else outputs[value]
        rendered = spec["render"](node, refs, ctx)
        rendered = rendered if isinstance(rendered, list) else [rendered]
        rendered[-1]["register"] = f"{nid}_result"
        tasks.extend(_strip_none(task) for task in rendered)

    return _assemble(ir, tasks)


ANSIBLE_CFG = """[defaults]
inventory = inventory/aws_ec2.yml
host_key_checking = False
retry_files_enabled = False
interpreter_python = auto_silent
stdout_callback = yaml
"""

GITIGNORE = """*.pem
*.key
*.retry
*~
.venv/
__pycache__/
.env
"""

PREFLIGHT = """---
- name: Preflight checks
  hosts: localhost
  connection: local
  gather_facts: false
  tasks:
    - name: Verify AWS credentials
      amazon.aws.aws_caller_info:
      register: caller
    - name: Show identity
      ansible.builtin.debug:
        msg: "AWS account {{ caller.account }}"
"""

INVENTORY = """---
plugin: amazon.aws.aws_ec2
regions:
  - {region}
keyed_groups:
  - key: tags.Role
    prefix: role
"""


def _assemble(ir: dict, tasks: list[dict]) -> dict[str, str]:
    play = {
        "name": f"Provision {ir['name']}",
        "hosts": "localhost",
        "connection": "local",
        "gather_facts": False,
        "collections": ["amazon.aws", "community.aws"],
        "tasks": tasks,
    }
    site = "---\n" + yaml.dump([play], sort_keys=False, default_flow_style=False, width=120)
    group_vars = "---\n" + yaml.dump(
        {
            "aws_region": ir["region"],
            "default_ami": "ami-PLACEHOLDER",
            "common_tags": {"ManagedBy": "ansible", "GeneratedBy": "ansible-z", "Design": ir["name"]},
        },
        sort_keys=False,
    )
    return {
        "site.yml": site,
        "group_vars/all.yml": group_vars,
        "ansible.cfg": ANSIBLE_CFG,
        ".gitignore": GITIGNORE,
        "preflight.yml": PREFLIGHT,
        "inventory/aws_ec2.yml": INVENTORY.format(region=ir["region"]),
        "README.md": _readme(ir),
    }


def _readme(ir: dict) -> str:
    lines = [
        f"# {ir['name']} — generated by Ansible-Z (custom design)",
        "",
        f"Provider: {ir.get('provider', 'aws')} · Region: {ir['region']}",
        "",
        "## Resources",
        "",
    ]
    for node in ir["nodes"]:
        deps = node.get("inputs") or {}
        dep_str = ", ".join(f"{k} -> {v}" for k, v in deps.items()) or "—"
        lines.append(f"- **{node['id']}** (`{node['type']}`) — connects: {dep_str}")
    lines += [
        "",
        "## Run",
        "```bash",
        "ansible-galaxy collection install amazon.aws community.aws",
        "ansible-playbook preflight.yml",
        "ansible-playbook site.yml --check",
        "ansible-playbook site.yml",
        "```",
    ]
    return "\n".join(lines) + "\n"
