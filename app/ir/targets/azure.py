"""Azure Bicep target: a best-effort AWS -> Azure translation.

The IR is AWS-shaped, so this maps each block to its closest Azure analog (VPC -> virtual
network, security group -> NSG, S3 -> storage account, RDS -> a flexible database server,
SQS/SNS -> Service Bus, DynamoDB -> Cosmos DB, KMS -> Key Vault, CloudWatch -> Log
Analytics, IAM role -> a managed identity). Blocks without a clean Azure analog (compute
VMs, ALB, gateways, EKS/ECS, …) are reported as unmapped. Names that must be globally
unique (storage, databases) are emitted literally — rename them before deploying.
"""

import re

from app.ir.compiler import validate
from app.ir.targets.pulumi import Expr
from app.services.projectfmt import normalize_files


def _sym(node_id: str) -> str:
    name = re.sub(r"[^A-Za-z0-9_]", "_", node_id)
    return name if name[:1].isalpha() or name[:1] == "_" else "r_" + name


def _name(node_id: str, maxlen: int = 24) -> str:
    return re.sub(r"[^a-z0-9]", "", node_id.lower())[:maxlen] or "res"


def _bicep(value, indent: int) -> str:
    pad = "  " * indent
    if isinstance(value, Expr):
        return value.code
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, str):
        return "'" + value.replace("\\", "\\\\").replace("'", "\\'") + "'"
    if isinstance(value, list):
        if not value:
            return "[]"
        return "[\n" + "".join(f"{pad}  {_bicep(v, indent + 1)}\n" for v in value) + pad + "]"
    if isinstance(value, dict):
        if not value:
            return "{}"
        return "{\n" + "".join(f"{pad}  {k}: {_bicep(v, indent + 1)}\n" for k, v in value.items()) + pad + "}"
    return "null"


def _decl(nid: str, type_api: str, obj: dict) -> str:
    return f"resource {_sym(nid)} '{type_api}' = {_bicep(obj, 0)}"


def _loc():
    return Expr("location")


def _nsg_rule(name: str, port: int, source: str, priority: int) -> dict:
    return {"name": name, "properties": {
        "priority": priority, "direction": "Inbound", "access": "Allow", "protocol": "Tcp",
        "sourceAddressPrefix": source, "sourcePortRange": "*",
        "destinationAddressPrefix": "*", "destinationPortRange": str(port),
    }}


def _vpc(nid, node, refs):
    return [_decl(nid, "Microsoft.Network/virtualNetworks@2023-05-01", {
        "name": nid, "location": _loc(),
        "properties": {"addressSpace": {"addressPrefixes": [node["props"].get("cidr", "10.0.0.0/16")]}},
    })]


def _subnet(nid, node, refs):
    return [_decl(nid, "Microsoft.Network/virtualNetworks/subnets@2023-05-01", {
        "parent": Expr(_sym(refs["vpc"])),
        "name": nid,
        "properties": {"addressPrefix": node["props"].get("cidr", "10.0.1.0/24")},
    })]


def _security_group(nid, node, refs):
    p = node["props"]
    rules, pri = [], 100
    if p.get("ssh_cidr"):
        rules.append(_nsg_rule("ssh", 22, p["ssh_cidr"], pri)); pri += 10
    if p.get("allow_http"):
        rules.append(_nsg_rule("http", 80, "Internet", pri)); pri += 10
    if p.get("allow_https"):
        rules.append(_nsg_rule("https", 443, "Internet", pri)); pri += 10
    return [_decl(nid, "Microsoft.Network/networkSecurityGroups@2023-05-01", {
        "name": nid, "location": _loc(), "properties": {"securityRules": rules},
    })]


def _s3_bucket(nid, node, refs):
    return [_decl(nid, "Microsoft.Storage/storageAccounts@2023-01-01", {
        "name": "st" + _name(nid, 22), "location": _loc(),
        "sku": {"name": "Standard_LRS"}, "kind": "StorageV2", "properties": {},
    })]


def _rds(nid, node, refs):
    engine = node["props"].get("engine", "postgres")
    if engine == "mysql":
        type_api, version = "Microsoft.DBforMySQL/flexibleServers@2023-06-30", "8.0.21"
    else:
        type_api, version = "Microsoft.DBforPostgreSQL/flexibleServers@2023-06-01-preview", "16"
    return [_decl(nid, type_api, {
        "name": _name(nid, 60), "location": _loc(),
        "sku": {"name": "Standard_B1ms", "tier": "Burstable"},
        "properties": {
            "administratorLogin": node["props"].get("username", "appadmin"),
            "administratorLoginPassword": Expr("dbPassword"),
            "version": version,
            "storage": {"storageSizeGB": max(int(node["props"].get("storage", 32)), 32)},
        },
    })]


def _kms_key(nid, node, refs):
    return [_decl(nid, "Microsoft.KeyVault/vaults@2023-07-01", {
        "name": "kv" + _name(nid, 22), "location": _loc(),
        "properties": {
            "sku": {"family": "A", "name": "standard"},
            "tenantId": Expr("subscription().tenantId"),
            "enableRbacAuthorization": True,
        },
    })]


def _servicebus(nid, child_type, child_kind):
    ns = _decl(nid, "Microsoft.ServiceBus/namespaces@2022-10-01-preview", {
        "name": "sb" + _name(nid, 48), "location": _loc(), "sku": {"name": "Standard"},
    })
    child = _decl(nid + "_" + child_kind, child_type, {
        "parent": Expr(_sym(nid)), "name": child_kind, "properties": {},
    })
    return [ns, child]


def _sqs(nid, node, refs):
    return _servicebus(nid, "Microsoft.ServiceBus/namespaces/queues@2022-10-01-preview", "queue")


def _sns(nid, node, refs):
    return _servicebus(nid, "Microsoft.ServiceBus/namespaces/topics@2022-10-01-preview", "topic")


def _cloudwatch(nid, node, refs):
    return [_decl(nid, "Microsoft.OperationalInsights/workspaces@2022-10-01", {
        "name": nid, "location": _loc(),
        "properties": {"sku": {"name": "PerGB2018"}, "retentionInDays": node["props"].get("retention_days", 30)},
    })]


def _dynamodb(nid, node, refs):
    return [_decl(nid, "Microsoft.DocumentDB/databaseAccounts@2023-11-15", {
        "name": _name(nid, 44), "location": _loc(), "kind": "GlobalDocumentDB",
        "properties": {
            "databaseAccountOfferType": "Standard",
            "locations": [{"locationName": _loc(), "failoverPriority": 0}],
        },
    })]


def _iam_role(nid, node, refs):
    return [_decl(nid, "Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31", {"name": nid, "location": _loc()})]


BICEP_BUILDERS = {
    "vpc": _vpc, "subnet": _subnet, "security_group": _security_group, "s3_bucket": _s3_bucket,
    "rds": _rds, "kms_key": _kms_key, "sqs": _sqs, "sns": _sns, "cloudwatch": _cloudwatch,
    "dynamodb": _dynamodb, "iam_role": _iam_role,
}


def compile_bicep(ir: dict) -> dict:
    """Compile an IR design into an Azure Bicep template (best-effort AWS -> Azure)."""
    validate(ir)
    nodes = {n["id"]: n for n in ir["nodes"]}
    decls: list = []
    unmapped: list = []
    for node in ir["nodes"]:
        builder = BICEP_BUILDERS.get(node["type"])
        if builder is None:
            unmapped.append(node["type"])
            continue
        decls.extend(builder(node["id"], node, node.get("inputs", {})))

    body = "\n\n".join(decls)
    params = ["@description('Azure region')\nparam location string = 'eastus'"]
    if "dbPassword" in body:
        params.append("@secure()\n@description('Database administrator password')\nparam dbPassword string")
    head = f"// {ir['name']} - generated by Neviri-Ansi (Azure Bicep, AWS->Azure best-effort)\n\n"
    main = head + "\n\n".join(params) + "\n\n" + (body + "\n" if body else "// No Azure-mappable resources in this design.\n")
    return normalize_files({
        "main.bicep": main,
        ".gitignore": "*.tfstate\n",
        "README.md": _readme(ir, unmapped),
    })


def _readme(ir: dict, unmapped: list) -> str:
    lines = [
        f"# {ir['name']} - Azure Bicep",
        "",
        "Best-effort AWS -> Azure translation. **Review carefully** — names that must be globally",
        "unique (storage accounts, databases, Service Bus) are placeholders; adjust before deploying.",
        "",
        "## Deploy",
        "```bash",
        "az group create -n my-rg -l eastus",
        "az deployment group create -g my-rg --template-file main.bicep",
        "```",
    ]
    if unmapped:
        lines += ["", "## Not mapped to Azure", "",
                  "These AWS components have no clean Azure analog here and were skipped:", ""]
        lines += [f"- `{u}`" for u in sorted(set(unmapped))]
    return "\n".join(lines) + "\n"
