#!/usr/bin/env python3
"""
Reserved Instance Analyzer
Analyzes EC2 instances and recommends Reserved Instance purchases for cost savings.
"""

import subprocess
import json
import sys
from typing import Dict, List, Tuple
from decimal import Decimal
from collections import defaultdict

# AWS EC2 On-Demand Pricing (USD per hour) - us-east-1 region
# Update these values based on your region and instance types
# These are sample prices - update with actual pricing
ON_DEMAND_PRICING = {
    't2.micro': Decimal('0.0116'),
    't2.small': Decimal('0.023'),
    't2.medium': Decimal('0.0464'),
    't3.micro': Decimal('0.0104'),
    't3.small': Decimal('0.0208'),
    't3.medium': Decimal('0.0416'),
    'm5.large': Decimal('0.096'),
    'm5.xlarge': Decimal('0.192'),
    'm5.2xlarge': Decimal('0.384'),
    'c5.large': Decimal('0.085'),
    'c5.xlarge': Decimal('0.17'),
    'c5.2xlarge': Decimal('0.34'),
}

# Reserved Instance discount percentages (1-year, no upfront)
# Typical savings range from 30-40% for 1-year, 40-60% for 3-year
RI_DISCOUNT_1YEAR = Decimal('0.35')  # 35% discount
RI_DISCOUNT_3YEAR = Decimal('0.50')  # 50% discount

# Minimum running hours per month to recommend RI (e.g., 500 hours = ~69% uptime)
MIN_HOURS_FOR_RI = 500


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


def get_all_instances() -> List[Dict]:
    """Get list of all EC2 instances."""
    print("Fetching all EC2 instances...")

    success, output = run_command([
        'aws', 'ec2', 'describe-instances',
        '--query', 'Reservations[].Instances[].[InstanceId,InstanceType,State.Name,Platform,Tags]',
        '--output', 'json'
    ])

    if not success:
        print(f"Error getting instances: {output}")
        return []

    try:
        instance_data = json.loads(output) if output.strip() else []
        if instance_data is None:
            instance_data = []

        instances = []
        for inst in instance_data:
            if inst and len(inst) >= 3:
                instance_id = inst[0]
                instance_type = inst[1]
                state = inst[2]
                platform = inst[3] if len(inst) > 3 and inst[3] else 'Linux'
                tags = inst[4] if len(inst) > 4 and inst[4] else []

                # Extract Name tag
                name = "No Name"
                if tags:
                    for tag in tags:
                        if tag.get('Key') == 'Name':
                            name = tag.get('Value', 'No Name')
                            break

                instances.append({
                    'id': instance_id,
                    'type': instance_type,
                    'state': state,
                    'platform': platform,
                    'name': name
                })

        return instances

    except json.JSONDecodeError:
        print("Error parsing instance data")
        return []


def get_reserved_instances() -> Dict[str, int]:
    """Get current Reserved Instances count by type."""
    print("Fetching Reserved Instances...")

    success, output = run_command([
        'aws', 'ec2', 'describe-reserved-instances',
        '--query', 'ReservedInstances[?State==`active`].[InstanceType,InstanceCount]',
        '--output', 'json'
    ])

    if not success:
        print(f"  Warning: Could not fetch RIs: {output}")
        return {}

    try:
        ri_data = json.loads(output) if output.strip() else []
        if ri_data is None:
            ri_data = []

        ri_count = defaultdict(int)
        for ri in ri_data:
            if ri and len(ri) >= 2:
                instance_type = ri[0]
                count = ri[1] or 1
                ri_count[instance_type] += count

        return dict(ri_count)

    except json.JSONDecodeError:
        print("  Warning: Error parsing RI data")
        return {}


def get_instance_price(instance_type: str) -> Decimal:
    """Get on-demand price for instance type."""
    # Return price from lookup, or estimate based on similar instance
    if instance_type in ON_DEMAND_PRICING:
        return ON_DEMAND_PRICING[instance_type]

    # If not in pricing table, return a default estimate
    print(f"  Warning: No pricing data for {instance_type}, using estimate")
    return Decimal('0.10')  # Default estimate


def calculate_monthly_cost(instance_type: str, hours_per_month: int = 730) -> Decimal:
    """Calculate monthly on-demand cost."""
    hourly_price = get_instance_price(instance_type)
    return hourly_price * Decimal(hours_per_month)


def calculate_ri_savings(instance_type: str, count: int, hours_per_month: int = 730) -> Dict:
    """Calculate savings with Reserved Instances."""
    hourly_price = get_instance_price(instance_type)

    # On-demand costs
    monthly_ondemand = hourly_price * Decimal(hours_per_month) * count
    yearly_ondemand = monthly_ondemand * 12

    # RI costs (with discount)
    hourly_ri_1year = hourly_price * (1 - RI_DISCOUNT_1YEAR)
    hourly_ri_3year = hourly_price * (1 - RI_DISCOUNT_3YEAR)

    monthly_ri_1year = hourly_ri_1year * Decimal(hours_per_month) * count
    yearly_ri_1year = monthly_ri_1year * 12

    monthly_ri_3year = hourly_ri_3year * Decimal(hours_per_month) * count
    yearly_ri_3year = monthly_ri_3year * 12

    return {
        'monthly_ondemand': monthly_ondemand,
        'yearly_ondemand': yearly_ondemand,
        'monthly_ri_1year': monthly_ri_1year,
        'yearly_ri_1year': yearly_ri_1year,
        'savings_1year': yearly_ondemand - yearly_ri_1year,
        'monthly_ri_3year': monthly_ri_3year,
        'yearly_ri_3year': yearly_ri_3year,
        'savings_3year': yearly_ondemand - yearly_ri_3year,
    }


def format_currency(amount: Decimal) -> str:
    """Format decimal as currency."""
    return f"${amount:.2f}"


def print_separator(char='=', length=80):
    """Print a separator line."""
    print(char * length)


def main():
    """Main function."""
    print_separator()
    print("RESERVED INSTANCE ANALYZER")
    print_separator()
    print()

    # Get all instances
    instances = get_all_instances()

    if not instances:
        print("No instances found or error accessing AWS.")
        sys.exit(1)

    print(f"Found {len(instances)} instance(s)\n")

    # Get current Reserved Instances
    reserved_instances = get_reserved_instances()

    # Analyze running instances
    running_instances = [i for i in instances if i['state'] == 'running']
    stopped_instances = [i for i in instances if i['state'] == 'stopped']

    print_separator()
    print("INSTANCE SUMMARY")
    print_separator()
    print()
    print(f"Total Instances: {len(instances)}")
    print(f"  Running: {len(running_instances)}")
    print(f"  Stopped: {len(stopped_instances)}")
    print()

    # Group running instances by type
    instance_types = defaultdict(list)
    for inst in running_instances:
        instance_types[inst['type']].append(inst)

    print_separator('-')
    print()

    # Display current RI coverage
    if reserved_instances:
        print_separator()
        print("CURRENT RESERVED INSTANCES")
        print_separator()
        print()
        for inst_type, count in reserved_instances.items():
            print(f"  {inst_type}: {count} instance(s)")
        print()
        print_separator('-')
        print()

    # Calculate current costs
    print_separator()
    print("CURRENT ON-DEMAND COSTS (Assuming 24/7 operation)")
    print_separator()
    print()

    total_monthly_cost = Decimal('0')
    for inst_type, instances_list in instance_types.items():
        count = len(instances_list)
        # Subtract any existing RIs
        ri_covered = reserved_instances.get(inst_type, 0)
        uncovered = max(0, count - ri_covered)

        monthly_cost = calculate_monthly_cost(inst_type, 730) * count
        total_monthly_cost += monthly_cost

        print(f"{inst_type}:")
        print(f"  Running Instances: {count}")
        if ri_covered > 0:
            print(f"  Covered by RIs: {ri_covered}")
            print(f"  Uncovered (On-Demand): {uncovered}")
        print(f"  Monthly Cost: {format_currency(monthly_cost)}")
        print(f"  Yearly Cost: {format_currency(monthly_cost * 12)}")
        print()

    print_separator('-')
    print(f"TOTAL MONTHLY COST: {format_currency(total_monthly_cost)}")
    print(f"TOTAL YEARLY COST: {format_currency(total_monthly_cost * 12)}")
    print_separator('-')
    print()

    # Calculate RI recommendations
    print_separator()
    print("RESERVED INSTANCE RECOMMENDATIONS")
    print_separator()
    print()
    print(f"Recommendations for instances running >{MIN_HOURS_FOR_RI} hours/month (~{MIN_HOURS_FOR_RI//30} hrs/day)")
    print("Assuming continuous 24/7 operation for running instances")
    print()
    print_separator('-')
    print()

    total_1year_savings = Decimal('0')
    total_3year_savings = Decimal('0')
    has_recommendations = False

    for inst_type, instances_list in sorted(instance_types.items()):
        count = len(instances_list)
        ri_covered = reserved_instances.get(inst_type, 0)
        uncovered = count - ri_covered

        if uncovered > 0:
            has_recommendations = True
            savings = calculate_ri_savings(inst_type, uncovered, 730)

            total_1year_savings += savings['savings_1year']
            total_3year_savings += savings['savings_3year']

            print(f"{inst_type} - {uncovered} instance(s) recommended for RI")
            print(f"  Current On-Demand Cost: {format_currency(savings['yearly_ondemand'])}/year")
            print()
            print(f"  1-Year RI (No Upfront):")
            print(f"    Yearly Cost: {format_currency(savings['yearly_ri_1year'])}")
            print(f"    Yearly Savings: {format_currency(savings['savings_1year'])} ({RI_DISCOUNT_1YEAR * 100:.0f}% off)")
            print()
            print(f"  3-Year RI (No Upfront):")
            print(f"    Yearly Cost: {format_currency(savings['yearly_ri_3year'])}")
            print(f"    Yearly Savings: {format_currency(savings['savings_3year'])} ({RI_DISCOUNT_3YEAR * 100:.0f}% off)")
            print()
            print_separator('-')
            print()

    if not has_recommendations:
        print("All running instances are already covered by Reserved Instances!")
        print("No additional RIs needed at this time.")
        print()

    # Display summary
    if has_recommendations:
        print_separator()
        print("POTENTIAL SAVINGS SUMMARY")
        print_separator()
        print()
        print(f"{'RI Term':<20} {'Yearly Savings':<20} {'3-Year Total Savings'}")
        print_separator('-')
        print(f"{'1-Year RI':<20} {format_currency(total_1year_savings):<20} {format_currency(total_1year_savings * 1)}")
        print(f"{'3-Year RI':<20} {format_currency(total_3year_savings):<20} {format_currency(total_3year_savings * 3)}")
        print_separator('-')
        print()

    # Show recommendations
    print_separator()
    print("RECOMMENDATIONS")
    print_separator()
    print()

    if has_recommendations:
        print("1. Consider purchasing Reserved Instances for consistently running workloads")
        print(f"   - 1-Year RI: Save {format_currency(total_1year_savings)}/year")
        print(f"   - 3-Year RI: Save {format_currency(total_3year_savings)}/year")
        print()
        print("2. RI Purchase Options:")
        print("   - No Upfront: Lower commitment, pay monthly")
        print("   - Partial Upfront: ~5% additional discount")
        print("   - All Upfront: ~10% additional discount")
        print()
        print("3. Consider Convertible RIs for flexibility to change instance types")
        print()
        print("4. Also evaluate Savings Plans as an alternative:")
        print("   - More flexibility across instance types")
        print("   - Apply to Lambda and Fargate as well")
        print("   - Similar discounts to RIs")
    else:
        print("1. Great job! Your instances are well-covered by Reserved Instances")
        print("2. Monitor for new instances that may need RI coverage")
        print("3. Review RI utilization to ensure you're not over-provisioned")

    print()
    print_separator('-')
    print()
    print(f"NOTE: This analysis assumes 24/7 operation (730 hours/month)")
    print(f"Discount rates: 1-Year RI = {RI_DISCOUNT_1YEAR * 100:.0f}%, 3-Year RI = {RI_DISCOUNT_3YEAR * 100:.0f}%")
    print("Update ON_DEMAND_PRICING and discount rates for accurate calculations")
    print("Pricing based on us-east-1 region")
    print_separator()


if __name__ == '__main__':
    main()
