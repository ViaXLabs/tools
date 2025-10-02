import boto3
import csv
from datetime import datetime

def get_ingress_ips(region_name='us-east-1'):
    try:
        ec2 = boto3.client('ec2', region_name=region_name)
    except Exception as e:
        print(f"Error creating EC2 client: {e}")
        return []
    try:
        security_groups = ec2.describe_security_groups()['SecurityGroups']
    except Exception as e:
        print(f"Error describing security groups: {e}")
        return []
    ingress_ips = []
                cidr = ip_range.get('CidrIp')
                if cidr:
                    ingress_ips.append({
                        'GroupId': sg['GroupId'],
                        'GroupName': sg.get('GroupName', ''),
                        'CidrIp': cidr,
                        'Protocol': perm.get('IpProtocol', ''),
                        'FromPort': perm.get('FromPort', ''),
                        'ToPort': perm.get('ToPort', '')
                    })

    return ingress_ips

def write_csv(data, filename):
    fieldnames = ['GroupId', 'GroupName', 'CidrIp', 'Protocol', 'FromPort', 'ToPort']
    try:
        with open(filename, 'w', newline='') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            for row in data:
                writer.writerow(row)
if __name__ == '__main__':
    import argparse
    import os

    parser = argparse.ArgumentParser(description='Fetch AWS EC2 Security Group ingress IPs.')
    parser.add_argument('--region', type=str, default=os.environ.get('AWS_REGION', 'us-east-1'),
                        help='AWS region name (default: us-east-1 or AWS_REGION env var)')
    args = parser.parse_args()

    ips = get_ingress_ips(args.region)
    date_str = datetime.now().strftime('%Y%m%d_%H%M%S')
    write_csv(ips, filename)
    import os
    abs_path = os.path.abspath(filename)
    print(f'Ingress IPs written to {abs_path}')
    print(f'Ingress IPs written to {filename}')
    filename = f'ingress_ips_{date_str}.csv'
    write_csv(ips, filename)
    print(f'Ingress IPs written to {filename}')
