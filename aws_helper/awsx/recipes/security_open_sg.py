"""security.open-security-groups

Finds security groups with inbound rules open to 0.0.0.0/0 or ::/0 on
sensitive ports (SSH, RDP, DB ports), and which ENIs/instances actually use
them -- the useful part standard CLI output doesn't give you in one shot.
"""
from __future__ import annotations
import click
from awsx.registry import register
from awsx.aws import client

_SENSITIVE_PORTS = {22: "SSH", 3389: "RDP", 3306: "MySQL", 5432: "Postgres",
                     6379: "Redis", 27017: "MongoDB", 9200: "Elasticsearch"}


@register(
    name="open-security-groups",
    group="security",
    summary="Find security groups open to the internet on sensitive ports, with attached ENIs",
    params=[
        click.Option(["--all-ports"], is_flag=True, default=False,
                      help="Flag ANY 0.0.0.0/0 ingress, not just sensitive ports"),
    ],
)
def run(session, region, dry_run, all_ports=False, **kwargs):
    ec2 = client(session, "ec2", region)
    groups = [
        g for page in ec2.get_paginator("describe_security_groups").paginate()
        for g in page["SecurityGroups"]
    ]

    findings = []
    for g in groups:
        exposed_rules = []
        for perm in g.get("IpPermissions", []):
            open_to_world = any(
                r.get("CidrIp") == "0.0.0.0/0" for r in perm.get("IpRanges", [])
            ) or any(
                r.get("CidrIpv6") == "::/0" for r in perm.get("Ipv6Ranges", [])
            )
            if not open_to_world:
                continue
            from_port = perm.get("FromPort")
            to_port = perm.get("ToPort")
            if all_ports:
                exposed_rules.append({"from_port": from_port, "to_port": to_port, "protocol": perm.get("IpProtocol")})
            elif from_port is not None:
                for port, label in _SENSITIVE_PORTS.items():
                    if from_port <= port <= (to_port or from_port):
                        exposed_rules.append({"port": port, "service": label})

        if exposed_rules:
            enis = ec2.describe_network_interfaces(
                Filters=[{"Name": "group-id", "Values": [g["GroupId"]]}]
            )["NetworkInterfaces"]
            attached_to = [
                {
                    "interface_id": eni["NetworkInterfaceId"],
                    "attachment": (eni.get("Attachment") or {}).get("InstanceId", "unattached"),
                }
                for eni in enis
            ]
            findings.append({
                "GroupId": g["GroupId"],
                "GroupName": g["GroupName"],
                "VpcId": g.get("VpcId"),
                "exposed_rules": exposed_rules,
                "attached_interfaces": attached_to,
                "in_use": len(attached_to) > 0,
            })

    return {"region": region, "flagged_count": len(findings), "security_groups": findings}
