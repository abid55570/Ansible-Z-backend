from app.ir.targets import compile_target
from app.ir.targets.azure import _bicep, _name, _sym, compile_bicep

AZ_IR = {
    "version": 1, "provider": "aws", "region": "ap-south-1", "name": "az",
    "nodes": [
        {"id": "vpc", "type": "vpc", "props": {"cidr": "10.0.0.0/16"}},
        {"id": "pub", "type": "subnet", "props": {"cidr": "10.0.1.0/24"}, "inputs": {"vpc": "vpc"}},
        {"id": "sg", "type": "security_group", "props": {"ssh_cidr": "1.2.3.4/32", "allow_http": True, "allow_https": True}, "inputs": {"vpc": "vpc"}},
        {"id": "sgbare", "type": "security_group", "props": {}, "inputs": {"vpc": "vpc"}},
        {"id": "logs", "type": "s3_bucket", "props": {}},
        {"id": "pg", "type": "rds", "props": {"engine": "postgres"}, "inputs": {"subnets": ["pub"]}},
        {"id": "my", "type": "rds", "props": {"engine": "mysql"}, "inputs": {"subnets": ["pub"]}},
        {"id": "key", "type": "kms_key", "props": {}},
        {"id": "q", "type": "sqs", "props": {}},
        {"id": "topic", "type": "sns", "props": {}},
        {"id": "cw", "type": "cloudwatch", "props": {}},
        {"id": "ddb", "type": "dynamodb", "props": {}},
        {"id": "role", "type": "iam_role", "props": {}},
        {"id": "web", "type": "ec2_instance", "props": {}, "inputs": {"subnet": "pub", "security_group": "sg"}},  # no Azure analog here
    ],
}


def test_compile_bicep_translation():
    files = compile_bicep(AZ_IR)
    assert {"main.bicep", "README.md", ".gitignore"} <= set(files)
    m = files["main.bicep"]
    assert "param location string = 'eastus'" in m
    assert "@secure()" in m and "param dbPassword string" in m
    assert "resource vpc 'Microsoft.Network/virtualNetworks@" in m
    assert "resource pub 'Microsoft.Network/virtualNetworks/subnets@" in m and "parent: vpc" in m
    assert "Microsoft.Network/networkSecurityGroups@" in m
    assert "Microsoft.Storage/storageAccounts@" in m
    assert "Microsoft.DBforPostgreSQL/flexibleServers@" in m and "Microsoft.DBforMySQL/flexibleServers@" in m
    assert "administratorLoginPassword: dbPassword" in m
    assert "Microsoft.KeyVault/vaults@" in m
    assert "Microsoft.ServiceBus/namespaces@" in m and "Microsoft.ServiceBus/namespaces/queues@" in m
    assert "Microsoft.ServiceBus/namespaces/topics@" in m
    assert "Microsoft.OperationalInsights/workspaces@" in m
    assert "Microsoft.DocumentDB/databaseAccounts@" in m
    assert "Microsoft.ManagedIdentity/userAssignedIdentities@" in m
    assert "ec2_instance" in files["README.md"]  # no Azure analog -> unmapped


def test_bicep_helpers_and_edge_cases():
    assert _sym("web-sg") == "web_sg"
    assert _sym("9x") == "r_9x"
    assert _name("---") == "res"
    assert len(_name("a" * 30, 22)) == 22
    assert _bicep(None, 0) == "null"

    # only input-less unmapped block -> empty template body
    empty = compile_bicep({"region": "r", "name": "n", "nodes": [{"id": "fn", "type": "lambda", "props": {}}]})
    assert "No Azure-mappable resources" in empty["main.bicep"]
    assert "lambda" in empty["README.md"]

    # fully-mappable design (subnet IS an Azure resource) -> no unmapped note, no db param
    mapped = compile_bicep({"region": "r", "name": "n", "nodes": [
        {"id": "vpc", "type": "vpc", "props": {"cidr": "10.0.0.0/16"}},
        {"id": "logs", "type": "s3_bucket", "props": {}},
        {"id": "key", "type": "kms_key", "props": {}},
    ]})
    assert "Not mapped to Azure" not in mapped["README.md"]
    assert "dbPassword" not in mapped["main.bicep"]


def test_compile_target_dispatches_bicep():
    assert "main.bicep" in compile_target(AZ_IR, "bicep")
