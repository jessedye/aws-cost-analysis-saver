#!/usr/bin/env python3
"""
Compute Savings Plan Analyzer
Analyzes EC2, Lambda, and Fargate usage to recommend Compute Savings Plans.
Savings Plans offer more flexibility than Reserved Instances across compute services.
"""

import subprocess
import json
import sys
from typing import Dict, List, Tuple
from decimal import Decimal
from collections import defaultdict

# AWS EC2 On-Demand Pricing (USD per hour) - us-east-1 region
# This is a subset - update based on your usage
ON_DEMAND_PRICING = {
    't2.micro': Decimal('0.0116'),
    't2.small': Decimal('0.023'),
    't2.medium': Decimal('0.0464'),
    't3.micro': Decimal('0.0104'),
    't3.small': Decimal('0.0208'),
    't3.medium': Decimal('0.0416'),
    't3.large': Decimal('0.0832'),
    'm5.large': Decimal('0.096'),
    'm5.xlarge': Decimal('0.192'),
    'm5.2xlarge': Decimal('0.384'),
    'm5.4xlarge': Decimal('0.768'),
    'c5.large': Decimal('0.085'),
    'c5.xlarge': Decimal('0.17'),
    'c5.2xlarge': Decimal('0.34'),
    'r5.large': Decimal('0.126'),
    'r5.xlarge': Decimal('0.252'),
    'r5.2xlarge': Decimal('0.504'),
}

# Lambda pricing (per GB-second)
LAMBDA_PRICE_PER_GB_SECOND = Decimal('0.0000166667')
LAMBDA_REQUEST_PRICE = Decimal('0.0000002')  # per request

# Fargate pricing (per vCPU-hour and per GB-hour)
FARGATE_VCPU_PRICE = Decimal('0.04048')
FARGATE_GB_PRICE = Decimal('0.004445')

# Savings Plan discount rates
COMPUTE_SP_1YEAR_DISCOUNT = Decimal('0.35')  # 35% for 1-year
COMPUTE_SP_3YEAR_DISCOUNT = Decimal('0.50')  # 50% for 3-year
EC2_SP_1YEAR_DISCOUNT = Decimal('0.45')      # 45% for 1-year (less flexible)
EC2_SP_3YEAR_DISCOUNT = Decimal('0.60')      # 60% for 3-year (less flexible)

HOURS_PER_MONTH = 730


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


def get_all_ec2_instances() -> List[Dict]:
    """Get list of all running EC2 instances."""
    print("Fetching EC2 instances...")

    success, output = run_command([
        'aws', 'ec2', 'describe-instances',
        '--filters', 'Name=instance-state-name,Values=running',
        '--query', 'Reservations[].Instances[].[InstanceId,InstanceType,Platform,Tags]',
        '--output', 'json'
    ])

    if not success:
        print(f"  Warning: Error getting EC2 instances: {output}")
        return []

    try:
        instance_data = json.loads(output) if output.strip() else []
        if instance_data is None:
            instance_data = []

        instances = []
        for inst in instance_data:
            if inst and len(inst) >= 2:
                instance_id = inst[0]
                instance_type = inst[1]
                platform = inst[2] if len(inst) > 2 and inst[2] else 'Linux'
                tags = inst[3] if len(inst) > 3 and inst[3] else []

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
                    'platform': platform,
                    'name': name
                })

        return instances

    except json.JSONDecodeError:
        print("  Warning: Error parsing EC2 instance data")
        return []


def get_lambda_functions() -> List[Dict]:
    """Get list of Lambda functions (simplified - actual usage requires CloudWatch)."""
    print("Fetching Lambda functions...")

    success, output = run_command([
        'aws', 'lambda', 'list-functions',
        '--query', 'Functions[].[FunctionName,MemorySize,Runtime]',
        '--output', 'json'
    ])

    if not success:
        print(f"  Warning: Error getting Lambda functions: {output}")
        return []

    try:
        function_data = json.loads(output) if output.strip() else []
        if function_data is None:
            function_data = []

        functions = []
        for func in function_data:
            if func and len(func) >= 2:
                name = func[0]
                memory_mb = func[1] or 128
                runtime = func[2] if len(func) > 2 else 'unknown'

                functions.append({
                    'name': name,
                    'memory_mb': memory_mb,
                    'runtime': runtime
                })

        return functions

    except json.JSONDecodeError:
        print("  Warning: Error parsing Lambda function data")
        return []


def get_ecs_clusters() -> List[str]:
    """Get list of ECS clusters."""
    print("Fetching ECS clusters...")

    success, output = run_command([
        'aws', 'ecs', 'list-clusters',
        '--output', 'json'
    ])

    if not success:
        print(f"  Warning: Error getting ECS clusters: {output}")
        return []

    try:
        data = json.loads(output) if output.strip() else {}
        cluster_arns = data.get('clusterArns', [])
        return cluster_arns

    except json.JSONDecodeError:
        print("  Warning: Error parsing ECS cluster data")
        return []


def get_instance_price(instance_type: str) -> Decimal:
    """Get on-demand price for instance type."""
    if instance_type in ON_DEMAND_PRICING:
        return ON_DEMAND_PRICING[instance_type]

    # Estimate if not in pricing table
    return Decimal('0.10')


def calculate_ec2_monthly_cost(instance_type: str) -> Decimal:
    """Calculate monthly on-demand cost for EC2 instance."""
    hourly_price = get_instance_price(instance_type)
    return hourly_price * HOURS_PER_MONTH


def calculate_savings_plan_savings(monthly_cost: Decimal, plan_type: str, term: str) -> Dict:
    """Calculate savings with Savings Plans."""
    yearly_cost = monthly_cost * 12

    if plan_type == 'compute':
        discount_1year = COMPUTE_SP_1YEAR_DISCOUNT
        discount_3year = COMPUTE_SP_3YEAR_DISCOUNT
    else:  # ec2
        discount_1year = EC2_SP_1YEAR_DISCOUNT
        discount_3year = EC2_SP_3YEAR_DISCOUNT

    if term == '1year':
        sp_monthly = monthly_cost * (1 - discount_1year)
        sp_yearly = sp_monthly * 12
        savings = yearly_cost - sp_yearly
        discount = discount_1year
    else:  # 3year
        sp_monthly = monthly_cost * (1 - discount_3year)
        sp_yearly = sp_monthly * 12
        savings = yearly_cost - sp_yearly
        discount = discount_3year

    return {
        'ondemand_monthly': monthly_cost,
        'ondemand_yearly': yearly_cost,
        'sp_monthly': sp_monthly,
        'sp_yearly': sp_yearly,
        'savings_yearly': savings,
        'discount_percent': discount * 100
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
    print("COMPUTE SAVINGS PLAN ANALYZER")
    print_separator()
    print()

    # Gather compute resources
    ec2_instances = get_all_ec2_instances()
    lambda_functions = get_lambda_functions()
    ecs_clusters = get_ecs_clusters()

    print()
    print_separator()
    print("COMPUTE RESOURCE SUMMARY")
    print_separator()
    print()
    print(f"EC2 Instances (Running): {len(ec2_instances)}")
    print(f"Lambda Functions: {len(lambda_functions)}")
    print(f"ECS Clusters: {len(ecs_clusters)}")
    print()
    print_separator('-')
    print()

    # Analyze EC2 instances
    if not ec2_instances:
        print("No running EC2 instances found.")
        print("Savings Plans are most beneficial for consistent compute usage.")
        print()
        print_separator()
        sys.exit(0)

    # Group instances by type
    instance_types = defaultdict(list)
    for inst in ec2_instances:
        instance_types[inst['type']].append(inst)

    print_separator()
    print("EC2 INSTANCE BREAKDOWN")
    print_separator()
    print()

    total_ec2_monthly = Decimal('0')

    for inst_type, instances in sorted(instance_types.items()):
        count = len(instances)
        monthly_cost = calculate_ec2_monthly_cost(inst_type) * count
        total_ec2_monthly += monthly_cost

        print(f"{inst_type}:")
        print(f"  Count: {count}")
        print(f"  Monthly Cost: {format_currency(monthly_cost)}")
        print(f"  Yearly Cost: {format_currency(monthly_cost * 12)}")
        print()

    print_separator('-')
    print(f"TOTAL EC2 MONTHLY COST: {format_currency(total_ec2_monthly)}")
    print(f"TOTAL EC2 YEARLY COST: {format_currency(total_ec2_monthly * 12)}")
    print_separator('-')
    print()

    # Calculate Savings Plan options
    print_separator()
    print("SAVINGS PLAN RECOMMENDATIONS")
    print_separator()
    print()
    print("Savings Plans offer flexibility to change instance types, regions, and services")
    print("Two types available:")
    print("  1. Compute Savings Plans: Most flexible (EC2, Lambda, Fargate)")
    print("  2. EC2 Instance Savings Plans: Higher discount, EC2 only")
    print()
    print_separator('-')
    print()

    # Compute Savings Plan (more flexible)
    print("OPTION 1: COMPUTE SAVINGS PLAN (Most Flexible)")
    print_separator('-')
    print()
    print("Benefits:")
    print("  - Applies to EC2, Lambda, and Fargate")
    print("  - Change instance families, sizes, OS, tenancy, regions")
    print("  - Ideal for dynamic workloads")
    print()

    compute_1year = calculate_savings_plan_savings(total_ec2_monthly, 'compute', '1year')
    compute_3year = calculate_savings_plan_savings(total_ec2_monthly, 'compute', '3year')

    print(f"1-Year Compute Savings Plan ({compute_1year['discount_percent']:.0f}% discount):")
    print(f"  Current On-Demand: {format_currency(compute_1year['ondemand_yearly'])}/year")
    print(f"  With Savings Plan: {format_currency(compute_1year['sp_yearly'])}/year")
    print(f"  Yearly Savings: {format_currency(compute_1year['savings_yearly'])}")
    print(f"  Monthly Commitment: {format_currency(compute_1year['sp_monthly'])}")
    print()

    print(f"3-Year Compute Savings Plan ({compute_3year['discount_percent']:.0f}% discount):")
    print(f"  Current On-Demand: {format_currency(compute_3year['ondemand_yearly'])}/year")
    print(f"  With Savings Plan: {format_currency(compute_3year['sp_yearly'])}/year")
    print(f"  Yearly Savings: {format_currency(compute_3year['savings_yearly'])}")
    print(f"  3-Year Total Savings: {format_currency(compute_3year['savings_yearly'] * 3)}")
    print(f"  Monthly Commitment: {format_currency(compute_3year['sp_monthly'])}")
    print()
    print_separator('-')
    print()

    # EC2 Instance Savings Plan (less flexible, higher discount)
    print("OPTION 2: EC2 INSTANCE SAVINGS PLAN (Higher Discount, Less Flexible)")
    print_separator('-')
    print()
    print("Benefits:")
    print("  - Higher discount than Compute Savings Plans")
    print("  - EC2 instances only (same region and instance family)")
    print("  - Ideal for stable, predictable EC2 workloads")
    print()

    ec2_1year = calculate_savings_plan_savings(total_ec2_monthly, 'ec2', '1year')
    ec2_3year = calculate_savings_plan_savings(total_ec2_monthly, 'ec2', '3year')

    print(f"1-Year EC2 Savings Plan ({ec2_1year['discount_percent']:.0f}% discount):")
    print(f"  Current On-Demand: {format_currency(ec2_1year['ondemand_yearly'])}/year")
    print(f"  With Savings Plan: {format_currency(ec2_1year['sp_yearly'])}/year")
    print(f"  Yearly Savings: {format_currency(ec2_1year['savings_yearly'])}")
    print(f"  Monthly Commitment: {format_currency(ec2_1year['sp_monthly'])}")
    print()

    print(f"3-Year EC2 Savings Plan ({ec2_3year['discount_percent']:.0f}% discount):")
    print(f"  Current On-Demand: {format_currency(ec2_3year['ondemand_yearly'])}/year")
    print(f"  With Savings Plan: {format_currency(ec2_3year['sp_yearly'])}/year")
    print(f"  Yearly Savings: {format_currency(ec2_3year['savings_yearly'])}")
    print(f"  3-Year Total Savings: {format_currency(ec2_3year['savings_yearly'] * 3)}")
    print(f"  Monthly Commitment: {format_currency(ec2_3year['sp_monthly'])}")
    print()
    print_separator('-')
    print()

    # Comparison table
    print_separator()
    print("SAVINGS COMPARISON")
    print_separator()
    print()
    print(f"{'Plan Type':<35} {'Term':<8} {'Yearly Savings':<20} {'Discount'}")
    print_separator('-')
    print(f"{'Current On-Demand':<35} {'-':<8} {format_currency(total_ec2_monthly * 12):<20} {'0%'}")
    print(f"{'Compute Savings Plan':<35} {'1-Year':<8} {format_currency(compute_1year['savings_yearly']):<20} {f\"{compute_1year['discount_percent']:.0f}%\"}")
    print(f"{'Compute Savings Plan':<35} {'3-Year':<8} {format_currency(compute_3year['savings_yearly']):<20} {f\"{compute_3year['discount_percent']:.0f}%\"}")
    print(f"{'EC2 Instance Savings Plan':<35} {'1-Year':<8} {format_currency(ec2_1year['savings_yearly']):<20} {f\"{ec2_1year['discount_percent']:.0f}%\"}")
    print(f"{'EC2 Instance Savings Plan':<35} {'3-Year':<8} {format_currency(ec2_3year['savings_yearly']):<20} {f\"{ec2_3year['discount_percent']:.0f}%\"}")
    print_separator('-')
    print()

    # Recommendations
    print_separator()
    print("RECOMMENDATIONS")
    print_separator()
    print()

    print("1. CHOOSE THE RIGHT PLAN TYPE:")
    print()
    print("   Compute Savings Plan if:")
    print("     - You use Lambda or Fargate in addition to EC2")
    print("     - You need flexibility to change instance types/regions")
    print("     - Your workload is dynamic or evolving")
    print()
    print("   EC2 Instance Savings Plan if:")
    print("     - You only use EC2 instances")
    print("     - Your instance types and regions are stable")
    print("     - You want maximum savings on EC2")
    print()

    print("2. RECOMMENDED COMMITMENT:")
    if total_ec2_monthly * 12 > 10000:
        recommended = compute_3year
        print(f"   3-Year Compute Savings Plan: {format_currency(recommended['sp_monthly'])}/month")
        print(f"   Projected savings: {format_currency(recommended['savings_yearly'] * 3)} over 3 years")
    elif total_ec2_monthly * 12 > 1000:
        recommended = compute_1year
        print(f"   1-Year Compute Savings Plan: {format_currency(recommended['sp_monthly'])}/month")
        print(f"   Projected savings: {format_currency(recommended['savings_yearly'])} per year")
    else:
        print("   Consider Savings Plans when monthly spend exceeds $100")
        print("   Current spend may be too variable for optimal Savings Plan benefit")
    print()

    print("3. IMPLEMENTATION TIPS:")
    print("   - Start with 50-75% of baseline usage to maintain flexibility")
    print("   - Monitor utilization in Cost Explorer after purchase")
    print("   - Use No Upfront payment option for better cash flow")
    print("   - Can purchase multiple Savings Plans over time")
    print()

    print("4. ADDITIONAL OPTIMIZATIONS:")
    print("   - Review instance types for right-sizing opportunities")
    print("   - Consider Spot Instances for fault-tolerant workloads")
    print("   - Stop/start non-production instances outside business hours")
    if lambda_functions:
        print(f"   - Optimize {len(lambda_functions)} Lambda function(s) for cost and performance")
    print()

    print("5. COST VISIBILITY:")
    print("   - Enable AWS Cost Explorer")
    print("   - Set up AWS Budgets with alerts")
    print("   - Tag resources for cost allocation")
    print("   - Review Savings Plan recommendations monthly")
    print()

    print_separator('-')
    print(f"BEST OPTION: 3-Year Compute Savings Plan")
    print(f"Total Potential Savings: {format_currency(compute_3year['savings_yearly'] * 3)} over 3 years")
    print_separator('-')
    print()

    print("NOTE: Actual savings depend on consistent usage patterns")
    print("Review AWS Cost Explorer's Savings Plan recommendations for personalized analysis")
    print("Pricing based on us-east-1 region")
    print(f"Discount estimates: Compute SP (1Y={COMPUTE_SP_1YEAR_DISCOUNT*100:.0f}%, 3Y={COMPUTE_SP_3YEAR_DISCOUNT*100:.0f}%)")
    print(f"                    EC2 SP (1Y={EC2_SP_1YEAR_DISCOUNT*100:.0f}%, 3Y={EC2_SP_3YEAR_DISCOUNT*100:.0f}%)")
    print_separator()


if __name__ == '__main__':
    main()
