from app.services.cost import estimate


def test_estimate_covers_every_pricing_branch():
    ir = {
        "region": "ap-south-1",  # multiplier 1.0 -> exact baseline prices
        "nodes": [
            {"id": "web", "type": "ec2_instance", "props": {"instance_type": "t3.small"}},
            {"id": "db", "type": "rds", "props": {"instance_class": "db.t3.micro", "storage": 50}},
            {"id": "ng", "type": "eks_nodegroup", "props": {"desired_size": 3, "instance_type": "t3.medium"}},
            {"id": "svc", "type": "ecs_service", "props": {"cpu": "1024", "memory": "2048", "desired_count": 2}},
            {"id": "nat", "type": "nat_gateway", "props": {}},
            {"id": "lb", "type": "alb", "props": {}},
            {"id": "eks", "type": "eks_cluster", "props": {}},
            {"id": "tgw", "type": "transit_gateway", "props": {}},
            {"id": "ep", "type": "vpc_endpoint", "props": {}},
            {"id": "key", "type": "kms_key", "props": {}},
            {"id": "wafacl", "type": "waf", "props": {}},
            {"id": "s3", "type": "s3_bucket", "props": {}},  # usage-based
            {"id": "vpc", "type": "vpc", "props": {}},       # no direct charge
        ],
    }
    result = estimate(ir)
    assert result["currency"] == "USD" and result["region"] == "ap-south-1"
    by_id = {i["id"]: i for i in result["items"]}
    assert by_id["web"]["monthly"] == round(0.0208 * 730, 2)  # t3.small
    assert by_id["ng"]["monthly"] == round(0.0416 * 730 * 3, 2)  # 3 x t3.medium
    assert by_id["eks"]["monthly"] == round(0.10 * 730, 2)
    assert by_id["key"]["monthly"] == 1.0
    assert by_id["wafacl"]["monthly"] == 5.0
    assert by_id["s3"]["note"] == "usage-based"
    assert by_id["vpc"]["monthly"] == 0.0
    assert result["monthly_total"] == round(sum(i["monthly"] for i in result["items"]), 2)
    assert result["monthly_total"] > 0


def test_estimate_default_region_and_empty_design():
    assert estimate({"region": "mars-1", "nodes": []})["monthly_total"] == 0.0  # unknown region -> default mult
    assert estimate({})["region"] == "us-east-1"  # default region when omitted
