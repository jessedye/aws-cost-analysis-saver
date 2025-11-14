#!/usr/bin/env python3
"""
Load Balancer Cost Analyzer
Analyzes ELB (Classic), ALB, and NLB usage to identify unused or underutilized load balancers.
READ-ONLY - Makes no changes to AWS resources.
"""

import subprocess
import json
import sys
from typing import Dict, List, Tuple
from decimal import Decimal
from datetime import datetime, timedelta

# AWS Load Balancer Pricing (USD) - us-east-1 region
# Application Load Balancer (ALB)
ALB_HOURLY_RATE = Decimal('0.0225')  # Per hour
ALB_LCU_HOURLY = Decimal('0.008')  # Per LCU-hour

# Network Load Balancer (NLB)
NLB_HOURLY_RATE = Decimal('0.0225')  # Per hour
NLB_LCU_HOURLY = Decimal('0.006')  # Per LCU-hour

# Classic Load Balancer (ELB)
ELB_HOURLY_RATE = Decimal('0.025')  # Per hour
ELB_DATA_GB = Decimal('0.008')  # Per GB processed


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


def get_classic_load_balancers() -> List[Dict]:
    """Get list of all Classic Load Balancers (ELB)."""
    success, output = run_command([
        'aws', 'elb', 'describe-load-balancers',
        '--output', 'json'
    ])

    if not success:
        return []

    try:
        data = json.loads(output) if output.strip() else {}
        lbs = data.get('LoadBalancerDescriptions', [])

        lb_list = []
        for lb in lbs:
            lb_list.append({
                'name': lb.get('LoadBalancerName', ''),
                'dns': lb.get('DNSName', ''),
                'type': 'classic',
                'created': lb.get('CreatedTime', ''),
                'instances': lb.get('Instances', []),
                'scheme': lb.get('Scheme', 'internet-facing')
            })

        return lb_list

    except json.JSONDecodeError:
        return []


def get_application_and_network_load_balancers() -> List[Dict]:
    """Get list of all Application and Network Load Balancers."""
    success, output = run_command([
        'aws', 'elbv2', 'describe-load-balancers',
        '--output', 'json'
    ])

    if not success:
        return []

    try:
        data = json.loads(output) if output.strip() else {}
        lbs = data.get('LoadBalancers', [])

        lb_list = []
        for lb in lbs:
            lb_type = lb.get('Type', 'application')
            lb_list.append({
                'name': lb.get('LoadBalancerName', ''),
                'arn': lb.get('LoadBalancerArn', ''),
                'dns': lb.get('DNSName', ''),
                'type': lb_type,
                'created': lb.get('CreatedTime', ''),
                'state': lb.get('State', {}).get('Code', ''),
                'scheme': lb.get('Scheme', 'internet-facing')
            })

        return lb_list

    except json.JSONDecodeError:
        return []


def get_target_health(lb_arn: str) -> int:
    """Get number of healthy targets for ALB/NLB."""
    # First get target groups
    success, output = run_command([
        'aws', 'elbv2', 'describe-target-groups',
        '--load-balancer-arn', lb_arn,
        '--output', 'json'
    ])

    if not success:
        return 0

    try:
        data = json.loads(output)
        target_groups = data.get('TargetGroups', [])

        total_healthy = 0
        for tg in target_groups:
            tg_arn = tg.get('TargetGroupArn', '')

            # Get health of targets
            success2, output2 = run_command([
                'aws', 'elbv2', 'describe-target-health',
                '--target-group-arn', tg_arn,
                '--output', 'json'
            ])

            if success2:
                health_data = json.loads(output2)
                descriptions = health_data.get('TargetHealthDescriptions', [])
                for desc in descriptions:
                    if desc.get('TargetHealth', {}).get('State') == 'healthy':
                        total_healthy += 1

        return total_healthy

    except:
        return 0


def get_lb_metrics(lb_name: str, lb_type: str) -> Dict:
    """Get CloudWatch metrics for a load balancer (last 7 days)."""
    end_time = datetime.utcnow()
    start_time = end_time - timedelta(days=7)

    metrics = {
        'request_count': 0,
        'active_connections': 0,
        'processed_bytes': 0
    }

    namespace = 'AWS/ELB' if lb_type == 'classic' else 'AWS/ApplicationELB' if lb_type == 'application' else 'AWS/NetworkELB'
    dimension_name = 'LoadBalancerName' if lb_type == 'classic' else 'LoadBalancer'

    # For ALB/NLB, need to extract the proper dimension value from ARN
    dimension_value = lb_name

    # Get RequestCount
    metric_name = 'RequestCount' if lb_type in ['classic', 'application'] else 'ProcessedBytes'
    success, output = run_command([
        'aws', 'cloudwatch', 'get-metric-statistics',
        '--namespace', namespace,
        '--metric-name', metric_name,
        '--dimensions', f'Name={dimension_name},Value={dimension_value}',
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
                if lb_type in ['classic', 'application']:
                    metrics['request_count'] = int(datapoints[0].get('Sum', 0))
                else:
                    metrics['processed_bytes'] = int(datapoints[0].get('Sum', 0))
        except:
            pass

    return metrics


def calculate_lb_cost(lb_type: str, data_gb: Decimal = Decimal('0')) -> Decimal:
    """Calculate load balancer monthly cost."""
    hours_per_month = Decimal('730')

    if lb_type == 'classic':
        hourly_cost = ELB_HOURLY_RATE * hours_per_month
        data_cost = data_gb * ELB_DATA_GB
        return hourly_cost + data_cost
    elif lb_type == 'application':
        # Base cost + minimal LCU cost (1 LCU for low usage)
        hourly_cost = ALB_HOURLY_RATE * hours_per_month
        lcu_cost = ALB_LCU_HOURLY * hours_per_month
        return hourly_cost + lcu_cost
    else:  # network
        # Base cost + minimal LCU cost
        hourly_cost = NLB_HOURLY_RATE * hours_per_month
        lcu_cost = NLB_LCU_HOURLY * hours_per_month
        return hourly_cost + lcu_cost


def format_currency(amount: Decimal) -> str:
    """Format decimal as currency."""
    return f"${amount:.2f}"


def print_separator(char='=', length=80):
    """Print a separator line."""
    print(char * length)


def main():
    """Main function."""
    print_separator()
    print("LOAD BALANCER COST ANALYZER")
    print_separator()
    print()

    print("Fetching all Load Balancers...")

    # Get all load balancers
    classic_lbs = get_classic_load_balancers()
    modern_lbs = get_application_and_network_load_balancers()

    all_lbs = classic_lbs + modern_lbs

    if not all_lbs:
        print("No Load Balancers found or error accessing AWS.")
        print()
        print("TOTAL MONTHLY COST: $0.00")
        print("ESTIMATED YEARLY COST: $0.00")
        print()
        print("Monthly Savings: $0.00")
        print("Yearly Savings: $0.00")
        print_separator()
        sys.exit(0)

    print(f"Found {len(all_lbs)} Load Balancer(s)")
    print(f"  Classic: {len(classic_lbs)}")
    print(f"  Application: {len([lb for lb in modern_lbs if lb['type'] == 'application'])}")
    print(f"  Network: {len([lb for lb in modern_lbs if lb['type'] == 'network'])}")
    print()
    print_separator('-')
    print()

    # Analyze each load balancer
    lb_analysis = []
    total_monthly_cost = Decimal('0')
    unused_lbs = []
    no_targets_lbs = []

    for lb in all_lbs:
        print(f"Analyzing {lb['name']} ({lb['type'].upper()})...", end='', flush=True)

        # Get metrics
        metrics = get_lb_metrics(lb['name'], lb['type'])

        # For ALB/NLB, check targets
        targets = 0
        if lb['type'] in ['application', 'network']:
            targets = get_target_health(lb['arn'])
        elif lb['type'] == 'classic':
            targets = len(lb.get('instances', []))

        # Calculate cost
        monthly_cost = calculate_lb_cost(lb['type'])
        total_monthly_cost += monthly_cost

        # Identify issues
        is_unused = (metrics['request_count'] == 0 and metrics['processed_bytes'] == 0)
        has_no_targets = (targets == 0)

        if is_unused:
            unused_lbs.append({
                'lb': lb,
                'cost': monthly_cost
            })

        if has_no_targets and not is_unused:
            no_targets_lbs.append({
                'lb': lb,
                'cost': monthly_cost
            })

        lb_analysis.append({
            'lb': lb,
            'metrics': metrics,
            'cost': monthly_cost,
            'targets': targets,
            'unused': is_unused,
            'no_targets': has_no_targets
        })

        print(f" {metrics['request_count']} requests, {targets} targets, {format_currency(monthly_cost)}/mo")

    print()
    print_separator('-')
    print()

    # Calculate costs
    print_separator()
    print("CURRENT COSTS")
    print_separator()
    print()
    print(f"Total Load Balancers: {len(all_lbs)}")
    print(f"TOTAL MONTHLY COST: {format_currency(total_monthly_cost)}")
    print(f"ESTIMATED YEARLY COST: {format_currency(total_monthly_cost * 12)}")
    print_separator('-')
    print()

    # Savings opportunities
    total_savings = Decimal('0')

    if unused_lbs:
        print_separator()
        print("UNUSED LOAD BALANCERS (No traffic in last 7 days)")
        print_separator()
        print()
        print(f"Found {len(unused_lbs)} unused Load Balancer(s)")
        print()

        unused_savings = Decimal('0')
        for item in unused_lbs:
            lb = item['lb']
            cost = item['cost']
            unused_savings += cost
            print(f"  • {lb['name']} ({lb['type'].upper()})")
            print(f"    DNS: {lb['dns']}")
            print(f"    Monthly Cost: {format_currency(cost)}")
            print()

        total_savings += unused_savings
        print(f"Potential Monthly Savings: {format_currency(unused_savings)}")
        print(f"Potential Yearly Savings: {format_currency(unused_savings * 12)}")
        print()
        print("RECOMMENDATION: Delete unused load balancers")
        print_separator('-')
        print()

    if no_targets_lbs:
        print_separator()
        print("LOAD BALANCERS WITH NO TARGETS")
        print_separator()
        print()
        print(f"Found {len(no_targets_lbs)} Load Balancer(s) with no registered targets")
        print()
        for item in no_targets_lbs:
            lb = item['lb']
            cost = item['cost']
            print(f"  • {lb['name']} ({lb['type'].upper()})")
            print(f"    Monthly Cost: {format_currency(cost)}")
            print()

        print("RECOMMENDATION: Review and delete or register targets")
        print_separator('-')
        print()

    # Summary
    print_separator()
    print("SUMMARY")
    print_separator()
    print()

    if total_savings > 0:
        print(f"Potential Savings from Unused Load Balancers:")
        print(f"  Monthly Savings: {format_currency(total_savings)}")
        print(f"  Yearly Savings: {format_currency(total_savings * 12)}")
    else:
        print("✓ No unused Load Balancers found")
        print()
        print("Monthly Savings: $0.00")
        print("Yearly Savings: $0.00")

    print()
    print("NOTE: Load Balancers incur hourly charges even when idle.")
    print("      Classic ELB: ~$18.25/month, ALB/NLB: ~$16.43/month (base rate)")
    print_separator()


if __name__ == '__main__':
    main()
