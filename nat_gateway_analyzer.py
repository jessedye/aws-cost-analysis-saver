#!/usr/bin/env python3
"""
NAT Gateway Cost Analyzer
Analyzes NAT Gateway usage and identifies underutilized or unused gateways.
READ-ONLY - Makes no changes to AWS resources.
"""

import subprocess
import json
import sys
from typing import Dict, List, Tuple
from decimal import Decimal
from datetime import datetime, timedelta

# AWS NAT Gateway Pricing (USD) - us-east-1 region
NAT_GATEWAY_HOURLY_RATE = Decimal('0.045')  # Per hour
NAT_GATEWAY_DATA_PROCESSING = Decimal('0.045')  # Per GB processed


def run_command(cmd: List[str]) -> Tuple[bool, str]:
    """Run a shell command and return success status and output."""
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=True
        )
        return True, result.stdout
    except subprocess.CalledProcessError as e:
        return False, e.stderr
    except FileNotFoundError:
        return False, "AWS CLI not found. Please install it first."


def get_all_nat_gateways() -> List[Dict]:
    """Get list of all NAT Gateways."""
    print("Fetching all NAT Gateways...")
    success, output = run_command([
        'aws', 'ec2', 'describe-nat-gateways',
        '--output', 'json'
    ])

    if not success:
        print(f"Error getting NAT Gateways: {output}")
        return []

    try:
        data = json.loads(output) if output.strip() else {}
        nat_gateways = data.get('NatGateways', [])

        gateway_list = []
        for nat in nat_gateways:
            if nat.get('State') != 'deleted':
                gateway_list.append({
                    'id': nat.get('NatGatewayId', ''),
                    'vpc_id': nat.get('VpcId', ''),
                    'subnet_id': nat.get('SubnetId', ''),
                    'state': nat.get('State', ''),
                    'created': nat.get('CreateTime', ''),
                    'addresses': nat.get('NatGatewayAddresses', [])
                })

        return gateway_list

    except json.JSONDecodeError:
        print("Error parsing NAT Gateway data")
        return []


def get_nat_gateway_metrics(nat_gateway_id: str) -> Dict:
    """Get CloudWatch metrics for a NAT Gateway (last 7 days)."""
    end_time = datetime.utcnow()
    start_time = end_time - timedelta(days=7)

    metrics = {
        'bytes_out': 0,
        'bytes_in': 0,
        'packets_out': 0,
        'active_connections': 0
    }

    # Get BytesOutToDestination
    success, output = run_command([
        'aws', 'cloudwatch', 'get-metric-statistics',
        '--namespace', 'AWS/NATGateway',
        '--metric-name', 'BytesOutToDestination',
        '--dimensions', f'Name=NatGatewayId,Value={nat_gateway_id}',
        '--start-time', start_time.isoformat(),
        '--end-time', end_time.isoformat(),
        '--period', '604800',  # 7 days
        '--statistics', 'Sum',
        '--output', 'json'
    ])

    if success:
        try:
            data = json.loads(output)
            datapoints = data.get('Datapoints', [])
            if datapoints:
                metrics['bytes_out'] = int(datapoints[0].get('Sum', 0))
        except:
            pass

    # Get BytesInFromSource
    success, output = run_command([
        'aws', 'cloudwatch', 'get-metric-statistics',
        '--namespace', 'AWS/NATGateway',
        '--metric-name', 'BytesInFromSource',
        '--dimensions', f'Name=NatGatewayId,Value={nat_gateway_id}',
        '--start-time', start_time.isoformat(),
        '--end-time', end_time.isoformat(),
        '--period', '604800',
        '--statistics', 'Sum',
        '--output', 'json'
    ])

    if success:
        try:
            data = json.loads(output)
            datapoints = data.get('Datapoints', [])
            if datapoints:
                metrics['bytes_in'] = int(datapoints[0].get('Sum', 0))
        except:
            pass

    # Get ActiveConnectionCount
    success, output = run_command([
        'aws', 'cloudwatch', 'get-metric-statistics',
        '--namespace', 'AWS/NATGateway',
        '--metric-name', 'ActiveConnectionCount',
        '--dimensions', f'Name=NatGatewayId,Value={nat_gateway_id}',
        '--start-time', start_time.isoformat(),
        '--end-time', end_time.isoformat(),
        '--period', '604800',
        '--statistics', 'Average',
        '--output', 'json'
    ])

    if success:
        try:
            data = json.loads(output)
            datapoints = data.get('Datapoints', [])
            if datapoints:
                metrics['active_connections'] = int(datapoints[0].get('Average', 0))
        except:
            pass

    return metrics


def calculate_nat_gateway_cost(data_gb: Decimal) -> Dict:
    """Calculate NAT Gateway costs."""
    # Monthly hourly cost (730 hours/month average)
    hours_per_month = Decimal('730')
    hourly_cost = NAT_GATEWAY_HOURLY_RATE * hours_per_month

    # Data processing cost
    data_cost = data_gb * NAT_GATEWAY_DATA_PROCESSING

    total_monthly = hourly_cost + data_cost

    return {
        'hourly_cost': hourly_cost,
        'data_cost': data_cost,
        'total_monthly': total_monthly
    }


def format_currency(amount: Decimal) -> str:
    """Format decimal as currency."""
    return f"${amount:.2f}"


def format_bytes(bytes_val: int) -> str:
    """Format bytes to human readable."""
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if bytes_val < 1024.0:
            return f"{bytes_val:.2f} {unit}"
        bytes_val /= 1024.0
    return f"{bytes_val:.2f} PB"


def print_separator(char='=', length=80):
    """Print a separator line."""
    print(char * length)


def main():
    """Main function."""
    print_separator()
    print("NAT GATEWAY COST ANALYZER")
    print_separator()
    print()

    # Get all NAT Gateways
    nat_gateways = get_all_nat_gateways()

    if not nat_gateways:
        print("No NAT Gateways found or error accessing AWS.")
        print()
        print("TOTAL MONTHLY COST: $0.00")
        print("ESTIMATED YEARLY COST: $0.00")
        print()
        print("Monthly Savings: $0.00")
        print("Yearly Savings: $0.00")
        print_separator()
        sys.exit(0)

    print(f"Found {len(nat_gateways)} NAT Gateway(s)\n")
    print_separator('-')
    print()

    # Analyze each NAT Gateway
    gateway_analysis = []
    total_monthly_cost = Decimal('0')
    unused_gateways = []
    low_usage_gateways = []

    for nat in nat_gateways:
        print(f"Analyzing {nat['id']}...", end='', flush=True)
        metrics = get_nat_gateway_metrics(nat['id'])

        # Calculate total data processed (7 days, extrapolate to 30 days)
        bytes_total_7d = metrics['bytes_out'] + metrics['bytes_in']
        bytes_total_30d = bytes_total_7d * 4.28  # 30/7 days
        data_gb_30d = Decimal(bytes_total_30d) / Decimal('1073741824')  # Convert to GB

        # Calculate cost
        costs = calculate_nat_gateway_cost(data_gb_30d)
        total_monthly_cost += costs['total_monthly']

        # Identify issues
        is_unused = (metrics['bytes_out'] == 0 and metrics['bytes_in'] == 0)
        is_low_usage = (data_gb_30d < Decimal('10') and not is_unused)  # Less than 10GB/month

        if is_unused:
            unused_gateways.append({
                'nat': nat,
                'cost': costs['total_monthly']
            })

        if is_low_usage:
            low_usage_gateways.append({
                'nat': nat,
                'metrics': metrics,
                'cost': costs['total_monthly'],
                'data_gb': data_gb_30d
            })

        gateway_analysis.append({
            'nat': nat,
            'metrics': metrics,
            'cost': costs,
            'data_gb': data_gb_30d,
            'unused': is_unused,
            'low_usage': is_low_usage
        })

        print(f" {format_bytes(bytes_total_7d)}/week, {format_currency(costs['total_monthly'])}/mo")

    print()
    print_separator('-')
    print()

    # Calculate costs
    print_separator()
    print("CURRENT COSTS")
    print_separator()
    print()
    print(f"Total NAT Gateways: {len(nat_gateways)}")
    print(f"TOTAL MONTHLY COST: {format_currency(total_monthly_cost)}")
    print(f"ESTIMATED YEARLY COST: {format_currency(total_monthly_cost * 12)}")
    print_separator('-')
    print()

    # Savings opportunities
    total_savings = Decimal('0')

    if unused_gateways:
        print_separator()
        print("UNUSED NAT GATEWAYS (No traffic in last 7 days)")
        print_separator()
        print()
        print(f"Found {len(unused_gateways)} unused NAT Gateway(s)")
        print()

        unused_savings = Decimal('0')
        for item in unused_gateways:
            nat = item['nat']
            cost = item['cost']
            unused_savings += cost
            print(f"  • {nat['id']}")
            print(f"    VPC: {nat['vpc_id']}")
            print(f"    Subnet: {nat['subnet_id']}")
            print(f"    Monthly Cost: {format_currency(cost)}")
            print(f"    State: {nat['state']}")
            print()

        total_savings += unused_savings
        print(f"Potential Monthly Savings: {format_currency(unused_savings)}")
        print(f"Potential Yearly Savings: {format_currency(unused_savings * 12)}")
        print()
        print("RECOMMENDATION: Delete unused NAT Gateways")
        print_separator('-')
        print()

    if low_usage_gateways:
        print_separator()
        print("LOW-USAGE NAT GATEWAYS (<10 GB/month)")
        print_separator()
        print()
        print(f"Found {len(low_usage_gateways)} low-usage NAT Gateway(s)")
        print()
        for item in low_usage_gateways:
            nat = item['nat']
            cost = item['cost']
            data_gb = item['data_gb']
            print(f"  • {nat['id']}")
            print(f"    VPC: {nat['vpc_id']}")
            print(f"    Data Usage: {data_gb:.2f} GB/month")
            print(f"    Monthly Cost: {format_currency(cost)}")
            print()

        print("RECOMMENDATION: Consider using NAT Instance or VPC endpoints instead")
        print("                NAT Instance (t3.nano) costs ~$3.80/month vs ~$32.85/month for NAT Gateway")
        print_separator('-')
        print()

    # Summary
    print_separator()
    print("SUMMARY")
    print_separator()
    print()

    if total_savings > 0:
        print(f"Potential Savings from Unused Gateways:")
        print(f"  Monthly Savings: {format_currency(total_savings)}")
        print(f"  Yearly Savings: {format_currency(total_savings * 12)}")
    else:
        print("✓ No unused NAT Gateways found")
        print()
        print("Monthly Savings: $0.00")
        print("Yearly Savings: $0.00")

    print()
    print("NOTE: NAT Gateways are charged hourly plus data processing fees.")
    print("      Each NAT Gateway costs ~$32.85/month base rate.")
    print("      Consider VPC endpoints for AWS services to reduce NAT Gateway usage.")
    print_separator()


if __name__ == '__main__':
    main()
