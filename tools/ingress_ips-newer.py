#!/usr/bin/env python3
"""
Collect ANY ingress-related IPs/CIDRs from AWS (region-scoped) and write a date-stamped CSV.

Covers (us-east-1 by default):
  - EC2 Security Group INGRESS rules (IPv4/IPv6 CIDRs, optional Prefix List expansion)
  - Network ACL inbound ALLOW entries (CIDRs)
  - Internet-facing Load Balancers (Classic, ALB, NLB) -> DNS resolved IPs (A/AAAA)
  - EC2 public IPs and Elastic IPs (with association context)
  - Public RDS instance/cluster endpoints -> DNS resolved IPs
  - API Gateway (REST v1, HTTP/WebSocket v2) endpoints -> DNS resolved IPs
  - WAFv2 IP sets (REGIONAL) -> CIDRs

CSV columns:
  account_id, region, source_kind, resource_type, resource_id, resource_name, ip_or_cidr,
  ip_version, protocol, port_range, direction, dns_name, rule_id_or_num, notes

Usage:
  pip install boto3
  python aws_any_ingress_ips.py
  python aws_any_ingress_ips.py --profile myprofile
  python aws_any_ingress_ips.py --region us-east-1 --no-resolve-dns
  python aws_any_ingress_ips.py --expand-prefix-lists --include-nacl-deny
"""

import argparse
import csv
import socket
import sys
from datetime import datetime, timezone
from typing import Dict, Iterable, List, Optional, Set, Tuple
import ipaddress

import boto3
from botocore.exceptions import ClientError, BotoCoreError


HEADER = [
    "account_id",
    "region",
    "source_kind",       # SecurityGroupCIDR, PrefixListEntry, NetworkACL, LoadBalancerIP, EC2PublicIP, EIP, RDSPublicIP, APIGatewayIP, WAF-IPSet
    "resource_type",     # security_group, network_acl, elb_classic, elbv2_alb, elbv2_nlb, ec2_instance, elastic_ip, rds_instance, rds_cluster, apigw_v1, apigw_v2, waf_ipset
    "resource_id",
    "resource_name",
    "ip_or_cidr",
    "ip_version",        # IPv4, IPv6, CIDR-v4, CIDR-v6, unknown
    "protocol",          # tcp/udp/icmp/- or n/a
    "port_range",        # e.g., 80, 443, 1024-65535, all, n/a
    "direction",         # ingress (or n/a)
    "dns_name",          # for LB/RDS/API GW rows
    "rule_id_or_num",    # SG rule id or NACL rule number
    "notes",
]

PROTO_MAP = {
    "6": "tcp",
    "17": "udp",
    "1": "icmp",
    "-1": "all",
}

def utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%SUTC")

def ip_ver(s: str) -> str:
    try:
        # Determine if single IP or CIDR
        net = ipaddress.ip_network(s, strict=False)
        return "CIDR-v6" if net.version == 6 else "CIDR-v4"
    except ValueError:
        try:
            ip = ipaddress.ip_address(s)
            return "IPv6" if ip.version == 6 else "IPv4"
        except ValueError:
            return "unknown"

def resolve_dns(host: str) -> Tuple[List[str], List[str]]:
    """Resolve A/AAAA with stdlib socket; dedupe."""
    v4: Set[str] = set()
    v6: Set[str] = set()
    try:
        info = socket.getaddrinfo(host, None)
        for fam, _stype, _proto, _canonname, sockaddr in info:
            if fam == socket.AF_INET:
                v4.add(sockaddr[0])
            elif fam == socket.AF_INET6:
                v6.add(sockaddr[0])
    except socket.gaierror:
        pass
    return sorted(v4), sorted(v6)

def get_account_id(session: boto3.session.Session) -> str:
    return session.client("sts").get_caller_identity()["Account"]

def ports_to_str(from_port: Optional[int], to_port: Optional[int], ip_protocol: str) -> str:
    if from_port is None and to_port is None:
        return "all"
    if to_port is None or from_port == to_port:
        return str(from_port)
    return f"{from_port}-{to_port}"

# ------------------------
# Security Groups (ingress)
# ------------------------
def sg_ingress_rows(session, region: str, expand_prefix_lists: bool) -> Iterable[List[str]]:
    ec2 = session.client("ec2", region_name=region)

    # SG metadata map
    sg_name: Dict[str, Tuple[str, Optional[str]]] = {}
    for page in ec2.get_paginator("describe_security_groups").paginate():
        for sg in page.get("SecurityGroups", []):
            sg_name[sg["GroupId"]] = (sg.get("GroupName", ""), sg.get("GroupId"))

    pl_cache: Dict[str, List[str]] = {}

    def expand_pl(prefix_list_id: str) -> List[str]:
        if prefix_list_id in pl_cache:
            return pl_cache[prefix_list_id]
        cidrs: List[str] = []
        try:
            paginator = ec2.get_paginator("get_managed_prefix_list_entries")
            for p in paginator.paginate(PrefixListId=prefix_list_id):
                for e in p.get("Entries", []):
                    if e.get("Cidr"):
                        cidrs.append(e["Cidr"])
        except (ClientError, BotoCoreError):
            cidrs = []
        pl_cache[prefix_list_id] = cidrs
        return cidrs

    paginator = ec2.get_paginator("describe_security_group_rules")
    for page in paginator.paginate(Filters=[{"Name": "is-egress", "Values": ["false"]}]):
        for r in page.get("SecurityGroupRules", []):
            if r.get("IsEgress"):
                continue
            gid = r.get("GroupId", "")
            gname = sg_name.get(gid, ("", ""))[0]
            sg_rule_id = r.get("SecurityGroupRuleId", "")
            ip_protocol = r.get("IpProtocol", "")
            port_range = ports_to_str(r.get("FromPort"), r.get("ToPort"), ip_protocol)
            desc = r.get("Description", "")

            if r.get("CidrIpv4"):
                yield ["", region, "SecurityGroupCIDR", "security_group", gid, gname,
                       r["CidrIpv4"], ip_ver(r["CidrIpv4"]), ip_protocol, port_range,
                       "ingress", "", sg_rule_id, desc]
            if r.get("CidrIpv6"):
                yield ["", region, "SecurityGroupCIDR", "security_group", gid, gname,
                       r["CidrIpv6"], ip_ver(r["CidrIpv6"]), ip_protocol, port_range,
                       "ingress", "", sg_rule_id, desc]
            if r.get("PrefixListId"):
                plid = r["PrefixListId"]
                if expand_prefix_lists:
                    cidrs = expand_pl(plid)
                    if cidrs:
                        for c in cidrs:
                            yield ["", region, "PrefixListEntry", "security_group", gid, gname,
                                   c, ip_ver(c), ip_protocol, port_range, "ingress", "",
                                   sg_rule_id, f"{desc} (from {plid})".strip()]
                    else:
                        yield ["", region, "PrefixListEntry", "security_group", gid, gname,
                               plid, "unknown", ip_protocol, port_range, "ingress", "",
                               sg_rule_id, f"{desc} (unexpanded)".strip()]
                else:
                    yield ["", region, "PrefixListEntry", "security_group", gid, gname,
                           plid, "unknown", ip_protocol, port_range, "ingress", "",
                           sg_rule_id, desc]

# ------------------------
# Network ACLs (ingress)
# ------------------------
def nacl_ingress_rows(session, region: str, include_deny: bool) -> Iterable[List[str]]:
    ec2 = session.client("ec2", region_name=region)
    paginator = ec2.get_paginator("describe_network_acls")
    for page in paginator.paginate():
        for acl in page.get("NetworkAcls", []):
            acl_id = acl.get("NetworkAclId", "")
            name_tag = next((t["Value"] for t in acl.get("Tags", []) if t.get("Key") == "Name"), "")
            for e in acl.get("Entries", []):
                if e.get("Egress"):
                    continue
                action = e.get("RuleAction", "").lower()
                if action != "allow" and not include_deny:
                    continue
                proto = PROTO_MAP.get(str(e.get("Protocol")), str(e.get("Protocol")))
                pr = "all"
                if e.get("PortRange"):
                    f = e["PortRange"].get("From")
                    t = e["PortRange"].get("To")
                    pr = str(f) if f == t else f"{f}-{t}"
                rule_num = str(e.get("RuleNumber", ""))
                notes = f"action={action}"

                if e.get("CidrBlock"):
                    cidr = e["CidrBlock"]
                    yield ["", region, "NetworkACL", "network_acl", acl_id, name_tag,
                           cidr, ip_ver(cidr), proto, pr, "ingress", "", rule_num, notes]
                if e.get("Ipv6CidrBlock"):
                    cidr6 = e["Ipv6CidrBlock"]
                    yield ["", region, "NetworkACL", "network_acl", acl_id, name_tag,
                           cidr6, ip_ver(cidr6), proto, pr, "ingress", "", rule_num, notes]

# ------------------------
# Load Balancers (internet-facing)
# ------------------------
def lb_rows(session, region: str, resolve: bool) -> Iterable[List[str]]:
    # Classic ELB
    elb = session.client("elb", region_name=region)
    paginator = elb.get_paginator("describe_load_balancers")
    for page in paginator.paginate():
        for d in page.get("LoadBalancerDescriptions", []):
            scheme = d.get("Scheme", "internet-facing")
            if scheme != "internet-facing":
                continue
            dns = d.get("DNSName", "")
            name = d.get("LoadBalancerName", "")
            rid = name
            if resolve and dns:
                v4, v6 = resolve_dns(dns)
                for ip in v4:
                    yield ["", region, "LoadBalancerIP", "elb_classic", rid, name,
                           ip, ip_ver(ip), "n/a", "n/a", "ingress", dns, "", "resolved from DNS"]
                for ip in v6:
                    yield ["", region, "LoadBalancerIP", "elb_classic", rid, name,
                           ip, ip_ver(ip), "n/a", "n/a", "ingress", dns, "", "resolved from DNS"]

    # ALB/NLB
    elbv2 = session.client("elbv2", region_name=region)
    paginator2 = elbv2.get_paginator("describe_load_balancers")
    for page in paginator2.paginate():
        for lb in page.get("LoadBalancers", []):
            if lb.get("Scheme") != "internet-facing":
                continue
            lb_type = lb.get("Type", "application")
            rtype = "elbv2_alb" if lb_type == "application" else "elbv2_nlb"
            dns = lb.get("DNSName", "")
            name = lb.get("LoadBalancerName", "")
            rid = lb.get("LoadBalancerArn", "")
            if resolve and dns:
                v4, v6 = resolve_dns(dns)
                for ip in v4:
                    yield ["", region, "LoadBalancerIP", rtype, rid, name,
                           ip, ip_ver(ip), "n/a", "n/a", "ingress", dns, "", "resolved from DNS"]
                for ip in v6:
                    yield ["", region, "LoadBalancerIP", rtype, rid, name,
                           ip, ip_ver(ip), "n/a", "n/a", "ingress", dns, "", "resolved from DNS"]

# ------------------------
# EC2 public IPs and Elastic IPs
# ------------------------
def ec2_public_rows(session, region: str) -> Iterable[List[str]]:
    ec2 = session.client("ec2", region_name=region)
    # EC2 instances with public IPv4
    paginator = ec2.get_paginator("describe_instances")
    for page in paginator.paginate():
        for r in page.get("Reservations", []):
            for inst in r.get("Instances", []):
                inst_id = inst.get("InstanceId", "")
                name_tag = next((t["Value"] for t in inst.get("Tags", []) if t.get("Key") == "Name"), "")
                # Instance-level public IPv4
                if inst.get("PublicIpAddress"):
                    ip = inst["PublicIpAddress"]
                    yield ["", region, "EC2PublicIP", "ec2_instance", inst_id, name_tag,
                           ip, ip_ver(ip), "n/a", "n/a", "ingress", "", "", "instance-assigned"]
                # Interface associations (covers EIP associations too)
                for eni in inst.get("NetworkInterfaces", []):
                    assoc = eni.get("Association", {})
                    if assoc.get("PublicIp"):
                        ip = assoc["PublicIp"]
                        note = "eni-association"
                        if assoc.get("IpOwnerId"):
                            note += f"; owner={assoc['IpOwnerId']}"
                        yield ["", region, "EC2PublicIP", "ec2_instance", inst_id, name_tag,
                               ip, ip_ver(ip), "n/a", "n/a", "ingress", "", "", note]

    # Elastic IPs (whether attached or not)
    paginator2 = ec2.get_paginator("describe_addresses")
    for page in paginator2.paginate():
        for eip in page.get("Addresses", []):
            ip = eip.get("PublicIp")
            if not ip:
                continue
            rid = eip.get("AllocationId") or eip.get("PublicIp")
            assoc = eip.get("AssociationId")
            notes = "attached" if assoc else "unattached"
            assoc_bits = []
            if eip.get("InstanceId"):
                assoc_bits.append(f"instance={eip['InstanceId']}")
            if eip.get("NetworkInterfaceId"):
                assoc_bits.append(f"eni={eip['NetworkInterfaceId']}")
            if eip.get("PrivateIpAddress"):
                assoc_bits.append(f"private={eip['PrivateIpAddress']}")
            if assoc_bits:
                notes += " (" + ", ".join(assoc_bits) + ")"
            yield ["", region, "EIP", "elastic_ip", rid, "",
                   ip, ip_ver(ip), "n/a", "n/a", "ingress", "", "", notes]

# ------------------------
# RDS public endpoints
# ------------------------
def rds_rows(session, region: str, resolve: bool) -> Iterable[List[str]]:
    rds = session.client("rds", region_name=region)
    # Instances
    marker = None
    while True:
        kwargs = {"Marker": marker} if marker else {}
        resp = rds.describe_db_instances(**kwargs)
        for db in resp.get("DBInstances", []):
            if not db.get("PubliclyAccessible"):
                continue
            addr = db.get("Endpoint", {}).get("Address")
            if not addr:
                continue
            name = db.get("DBInstanceIdentifier", "")
            rid = name
            if resolve:
                v4, v6 = resolve_dns(addr)
                for ip in v4 + v6:
                    yield ["", region, "RDSPublicIP", "rds_instance", rid, name,
                           ip, ip_ver(ip), "n/a", "n/a", "ingress", addr, "", "resolved from DNS"]
        marker = resp.get("Marker")
        if not marker:
            break
    # Clusters (Aurora)
    marker = None
    while True:
        kwargs = {"Marker": marker} if marker else {}
        resp = rds.describe_db_clusters(**kwargs)
        for cl in resp.get("DBClusters", []):
            if not cl.get("PubliclyAccessible"):
                continue
            for addr in filter(None, [cl.get("Endpoint"), cl.get("ReaderEndpoint")]):
                name = cl.get("DBClusterIdentifier", "")
                rid = name
                if resolve:
                    v4, v6 = resolve_dns(addr)
                    for ip in v4 + v6:
                        yield ["", region, "RDSPublicIP", "rds_cluster", rid, name,
                               ip, ip_ver(ip), "n/a", "n/a", "ingress", addr, "", "resolved from DNS"]
        marker = resp.get("Marker")
        if not marker:
            break

# ------------------------
# API Gateway endpoints
# ------------------------
def apigw_rows(session, region: str, resolve: bool) -> Iterable[List[str]]:
    # REST (v1)
    agw = session.client("apigateway", region_name=region)
    position = None
    rest_ids: List[Tuple[str, str, List[str]]] = []  # (id, name, types)
    while True:
        kwargs = {"position": position, "limit": 500} if position else {"limit": 500}
        resp = agw.get_rest_apis(**kwargs)
        for item in resp.get("items", []):
            types = (item.get("endpointConfiguration", {}) or {}).get("types", [])
            rest_ids.append((item.get("id", ""), item.get("name", ""), types))
        position = resp.get("position")
        if not position:
            break
    for api_id, name, types in rest_ids:
        # Only public types (EDGE or REGIONAL). PRIVATE is skipped.
        if "PRIVATE" in types:
            continue
        host = f"{api_id}.execute-api.{region}.amazonaws.com"
        if resolve:
            v4, v6 = resolve_dns(host)
            for ip in v4 + v6:
                yield ["", region, "APIGatewayIP", "apigw_v1", api_id, name,
                       ip, ip_ver(ip), "n/a", "n/a", "ingress", host, "", "resolved from DNS"]

    # HTTP/WebSocket (v2)
    agw2 = session.client("apigatewayv2", region_name=region)
    next_token = None
    while True:
        kwargs = {"NextToken": next_token} if next_token else {}
        resp = agw2.get_apis(**kwargs)
        for api in resp.get("Items", []):
            api_id = api.get("ApiId", "")
            name = api.get("Name", "")
            endpoint = api.get("ApiEndpoint", "")
            # v2 APIs can be PRIVATE; If endpoint missing, skip
            if not endpoint:
                continue
            if resolve:
                host = endpoint.replace("https://", "").replace("wss://", "").strip("/")
                v4, v6 = resolve_dns(host)
                for ip in v4 + v6:
                    yield ["", region, "APIGatewayIP", "apigw_v2", api_id, name,
                           ip, ip_ver(ip), "n/a", "n/a", "ingress", host, "", "resolved from DNS"]
        next_token = resp.get("NextToken")
        if not next_token:
            break

# ------------------------
# WAFv2 IP sets (REGIONAL)
# ------------------------
def waf_rows(session, region: str) -> Iterable[List[str]]:
    try:
        waf = session.client("wafv2", region_name=region)
        next_marker = None
        while True:
            kwargs = {"Scope": "REGIONAL", "Limit": 100}
            if next_marker:
                kwargs["NextMarker"] = next_marker
            resp = waf.list_ip_sets(**kwargs)
            for s in resp.get("IPSets", []):
                name = s.get("Name", "")
                sid = s.get("Id", "")
                scope = s.get("Scope", "REGIONAL")
                desc = waf.get_ip_set(Name=name, Scope=scope, Id=sid)
                for addr in desc.get("IPSet", {}).get("Addresses", []):
                    yield ["", region, "WAF-IPSet", "waf_ipset", sid, name,
                           addr, ip_ver(addr), "n/a", "n/a", "ingress", "", "", "wafv2 ipset"]
            next_marker = resp.get("NextMarker")
            if not next_marker:
                break
    except (ClientError, BotoCoreError):
        # No permission or no WAF in region; skip silently
        return

# ------------------------
def main():
    ap = argparse.ArgumentParser(description="Export ANY ingress-related IPs/CIDRs in a region to a date-stamped CSV.")
    ap.add_argument("--profile", help="AWS profile to use")
    ap.add_argument("--region", default="us-east-1", help="AWS region to scan (default: us-east-1)")
    ap.add_argument("--output", help="Output CSV filename (default auto date-stamped)")
    ap.add_argument("--expand-prefix-lists", action="store_true", help="Expand SG Prefix Lists into CIDRs (requires ec2:GetManagedPrefixListEntries)")
    ap.add_argument("--include-nacl-deny", action="store_true", help="Include NACL DENY rules (default: only ALLOW)")
    ap.add_argument("--no-resolve-dns", action="store_true", help="Do not resolve DNS names to IPs for LB/RDS/API GW")
    ap.add_argument("--skip", default="", help="Comma-separated categories to skip: sg,nacl,lb,ec2,eip,rds,apigw,waf")
    args = ap.parse_args()

    session_kwargs = {}
    if args.profile:
        session_kwargs["profile_name"] = args.profile
    session = boto3.Session(**session_kwargs)

    try:
        account_id = get_account_id(session)
    except (ClientError, BotoCoreError) as e:
        print(f"[ERROR] STS failed: {e}", file=sys.stderr)
        sys.exit(2)

    region = args.region
    out_name = args.output or f"aws_ingress_any_{region}_{utc_stamp()}.csv"
    resolve = not args.no_resolve_dns

    skip_set = {s.strip().lower() for s in args.skip.split(",") if s.strip()}

    writers = []

    rows_written = 0
    with open(out_name, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(HEADER)

        def write(row: List[str]):
            nonlocal rows_written
            row[0] = account_id
            w.writerow(row)
            rows_written += 1

        if "sg" not in skip_set:
            for r in sg_ingress_rows(session, region, expand_prefix_lists=args.expand_prefix_lists):
                write(r)

        if "nacl" not in skip_set:
            for r in nacl_ingress_rows(session, region, include_deny=args.include_nacl_deny):
                write(r)

        if "lb" not in skip_set:
            for r in lb_rows(session, region, resolve=resolve):
                write(r)

        if "ec2" not in skip_set or "eip" not in skip_set:
            for r in ec2_public_rows(session, region):
                # This function yields both EC2PublicIP and EIP rows; honor skip flags
                if r[2] == "EC2PublicIP" and "ec2" in skip_set:
                    continue
                if r[2] == "EIP" and "eip" in skip_set:
                    continue
                write(r)

        if "rds" not in skip_set:
            for r in rds_rows(session, region, resolve=resolve):
                write(r)

        if "apigw" not in skip_set:
            for r in apigw_rows(session, region, resolve=resolve):
                write(r)

        if "waf" not in skip_set:
            for r in waf_rows(session, region):
                write(r)

    print(f"Done. Wrote {rows_written} row(s) to {out_name} for account {account_id} in region {region}.")

if __name__ == "__main__":
    main()
