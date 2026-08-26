"""Provider-neutral resource model shared by the AWS-family export targets.

The IR compiles into an ordered list of ``Resource`` declarations whose attribute
values may contain ``Ref`` / ``LocalRef`` / ``Raw`` / ``Block``. Each target emitter
(Terraform first; CloudFormation, Pulumi, CDK reuse this) renders those into its own
syntax — so the SAME canonical model yields ``aws_vpc.vpc1.id`` (Terraform),
``!Ref Vpc1`` (CloudFormation) or ``vpc1.id`` (Pulumi).
"""

from dataclasses import dataclass, field

from app.ir.compiler import _topo_sort, validate


@dataclass(frozen=True)
class Ref:
    """Reference to another IR node's primary resource (resolved per target)."""

    node: str
    attr: str = "id"


@dataclass(frozen=True)
class LocalRef:
    """Reference to a sibling resource emitted by the same block (e.g. NAT -> its EIP)."""

    type: str
    name: str
    attr: str = "id"


@dataclass(frozen=True)
class Raw:
    """A target-specific expression emitted verbatim (e.g. ``jsonencode({...})``)."""

    expr: str


@dataclass
class Block:
    """A nested, repeatable sub-block (Terraform ``name { ... }``)."""

    name: str
    attrs: dict


@dataclass
class Resource:
    """One canonical cloud resource."""

    type: str
    name: str
    attrs: dict = field(default_factory=dict)


# block type -> mapper(node, refs, ctx) -> list[Resource]; populated by aws_resources.py
AWS_RESOURCES: dict = {}


def register(block_type: str):
    """Decorator: register a block type's canonical AWS mapping."""

    def deco(fn):
        AWS_RESOURCES[block_type] = fn
        return fn

    return deco


def to_resources(ir: dict):
    """Compile an IR into ``(resources, primary, unmapped)``.

    * ``resources`` — ordered list[Resource]
    * ``primary``   — node id -> (resource_type, resource_name) for ``Ref`` resolution
                      (a block's FIRST resource is its primary / referenced one)
    * ``unmapped``  — block types with no AWS mapping yet (surfaced to the user)
    """
    validate(ir)
    nodes = {n["id"]: n for n in ir["nodes"]}
    order = _topo_sort(ir["nodes"])
    ctx = {"region": ir["region"], "name": ir["name"]}
    resources: list = []
    primary: dict = {}
    unmapped: list = []
    for nid in order:
        node = nodes[nid]
        mapper = AWS_RESOURCES.get(node["type"])
        if mapper is None:
            unmapped.append(node["type"])
            continue
        decls = mapper(node, node.get("inputs", {}), ctx)
        resources.extend(decls)
        if decls:  # a no-op block (e.g. datacenter) emits nothing
            primary[nid] = (decls[0].type, decls[0].name)
    return resources, primary, unmapped
