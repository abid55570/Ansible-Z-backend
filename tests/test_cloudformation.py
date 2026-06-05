import json

from app.ir.targets import compile_target
from app.ir.targets.cloudformation import _bucket_name, _lid, compile_cloudformation

CFN_IR = {
    "version": 1, "provider": "aws", "region": "ap-south-1", "name": "cfn",
    "nodes": [
        {"id": "vpc", "type": "vpc", "props": {"cidr": "10.0.0.0/16"}},
        {"id": "pub", "type": "subnet", "props": {"cidr": "10.0.1.0/24", "public": True, "az": "ap-south-1a"}, "inputs": {"vpc": "vpc"}},
        {"id": "priv", "type": "subnet", "props": {"cidr": "10.0.2.0/24"}, "inputs": {"vpc": "vpc"}},
        {"id": "sg", "type": "security_group", "props": {"ssh_cidr": "1.2.3.4/32", "allow_http": True, "allow_https": True}, "inputs": {"vpc": "vpc"}},
        {"id": "sgbare", "type": "security_group", "props": {}, "inputs": {"vpc": "vpc"}},
        {"id": "web", "type": "ec2_instance", "props": {"ami": "ami-1"}, "inputs": {"subnet": "pub", "security_group": "sg"}},
        {"id": "web2", "type": "ec2_instance", "props": {}, "inputs": {"subnet": "priv", "security_group": "sgbare"}},
        {"id": "igw", "type": "igw", "props": {}, "inputs": {"vpc": "vpc"}},
        {"id": "nat", "type": "nat_gateway", "props": {}, "inputs": {"subnet": "pub"}},
        {"id": "rt", "type": "route_table", "props": {}, "inputs": {"vpc": "vpc", "subnets": ["pub"]}},
        {"id": "logs", "type": "s3_bucket", "props": {"bucket_name": "My_Logs", "versioning": True}},
        {"id": "assets", "type": "s3_bucket", "props": {}},
        {"id": "role", "type": "iam_role", "props": {}},
        {"id": "lb", "type": "alb", "props": {}, "inputs": {"subnets": ["pub", "priv"], "security_group": "sg"}},
        {"id": "tg", "type": "target_group", "props": {}, "inputs": {"vpc": "vpc"}},
        {"id": "db", "type": "rds", "props": {}, "inputs": {"subnets": "pub"}},  # single -> _listify coercion
        {"id": "ddb", "type": "dynamodb", "props": {}},
        {"id": "q", "type": "sqs", "props": {}},
        {"id": "topic", "type": "sns", "props": {}},
        {"id": "cw", "type": "cloudwatch", "props": {}},
        {"id": "wafnode", "type": "waf", "props": {}},  # unmapped in CFN
    ],
}


def test_compile_cloudformation_structure():
    files = compile_cloudformation(CFN_IR)
    assert {"template.json", "README.md", ".gitignore"} <= set(files)
    tpl = json.loads(files["template.json"])
    res = tpl["Resources"]
    assert tpl["AWSTemplateFormatVersion"] == "2010-09-09"
    assert res["vpc"]["Type"] == "AWS::EC2::VPC"
    assert res["pub"]["Properties"]["VpcId"] == {"Ref": "vpc"}                 # intrinsic Ref
    assert res["pub"]["Properties"]["MapPublicIpOnLaunch"] is True
    assert "MapPublicIpOnLaunch" not in res["priv"]["Properties"]
    assert "SecurityGroupIngress" in res["sg"]["Properties"]
    assert "SecurityGroupIngress" not in res["sgbare"]["Properties"]
    assert res["web"]["Properties"]["ImageId"] == "ami-1"
    assert res["web2"]["Properties"]["ImageId"] == {"Ref": "DefaultAmi"}
    assert res["igwAttach"]["Type"] == "AWS::EC2::VPCGatewayAttachment"
    assert res["nat"]["Properties"]["AllocationId"] == {"Fn::GetAtt": ["natEip", "AllocationId"]}
    assert res["rtAssoc0"]["Type"] == "AWS::EC2::SubnetRouteTableAssociation"
    assert res["logs"]["Properties"]["VersioningConfiguration"] == {"Status": "Enabled"}
    assert res["logs"]["Properties"]["BucketName"] == "my-logs"               # sanitized bucket name
    assert "VersioningConfiguration" not in res["assets"]["Properties"]
    assert res["role"]["Properties"]["AssumeRolePolicyDocument"]["Version"] == "2012-10-17"
    assert res["lb"]["Properties"]["Subnets"] == [{"Ref": "pub"}, {"Ref": "priv"}]
    assert res["db"]["Properties"]["MasterUserPassword"] == {"Ref": "DbPassword"}
    assert res["dbSubnets"]["Properties"]["SubnetIds"] == [{"Ref": "pub"}]     # single coerced to list
    assert "DefaultAmi" in tpl["Parameters"] and "DbPassword" in tpl["Parameters"]
    assert "waf" in files["README.md"]


def test_cloudformation_helpers_and_no_params_when_unused():
    assert _lid("web_sg") == "websg"
    assert _lid("---") == "R"
    assert _bucket_name("My_Bucket") == "my-bucket"
    ir = {"region": "r", "name": "n", "nodes": [{"id": "q", "type": "sqs", "props": {}}]}
    tpl = json.loads(compile_cloudformation(ir)["template.json"])
    assert "Parameters" not in tpl              # no DefaultAmi/DbPassword used
    assert "Not yet mapped" not in compile_cloudformation(ir)["README.md"]


def test_compile_target_dispatches_cloudformation():
    assert "template.json" in compile_target(CFN_IR, "cloudformation")
