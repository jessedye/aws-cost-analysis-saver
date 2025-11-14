#!/usr/bin/env python3
"""
RDS Cost Analyzer
Analyzes RDS instances for cost optimization opportunities including Reserved Instances,
right-sizing, and storage optimization.
This script only reads and analyzes - it does not make any changes.
"""

import subprocess
import json
import sys
from typing import Dict, List, Tuple
from decimal import Decimal
from collections import defaultdict

# AWS RDS On-Demand Pricing (USD per hour) - us-east-1 region, MySQL/PostgreSQL
# Update these values based on your region and database engine
RDS_ON_DEMAND_PRICING = {
    'db.t3.micro': Decimal('0.017'),
    'db.t3.small': Decimal('0.034'),
    'db.t3.medium': Decimal('0.068'),
    'db.t3.large': Decimal('0.136'),
    'db.m5.large': Decimal('0.192'),
    'db.m5.xlarge': Decimal('0.384'),
    'db.m5.2xlarge': Decimal('0.768'),
    'db.r5.large': Decimal('0.29'),
    'db.r5.xlarge': Decimal('0.58'),
    'db.r5.2xlarge': Decimal('1.16'),
}

# RDS Storage Pricing (per GB/month)
STORAGE_PRICING = {
    'gp2': Decimal('0.115'),  # General Purpose SSD
    'gp3': Decimal('0.115'),  # General Purpose SSD (newer)
    'io1': Decimal('0.125'),  # Provisioned IOPS SSD
    'magnetic': Decimal('0.10'),  # Magnetic (deprecated)
}

# IOPS Pricing for io1
IOPS_PRICE = Decimal('0.10')  # per IOPS per month

# Reserved Instance discount percentages
RI_DISCOUNT_1YEAR = Decimal('0.35')  # 35% discount
RI_DISCOUNT_3YEAR = Decimal('0.50')  # 50% discount

# Hours for calculations
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


def get_all_rds_instances() -> List[Dict]:
    """Get list of all RDS instances."""
    print("Fetching all RDS instances...")

    success, output = run_command([
        'aws', 'rds', 'describe-db-instances',
        '--query', 'DBInstances[].[DBInstanceIdentifier,DBInstanceClass,Engine,DBInstanceStatus,'
                   'AllocatedStorage,StorageType,Iops,MultiAZ,EngineVersion]',
        '--output', 'json'
    ])

    if not success:
        print(f"Error getting RDS instances: {output}")
        return []

    try:
        instance_data = json.loads(output) if output.strip() else []
        if instance_data is None:
            instance_data = []

        instances = []
        for inst in instance_data:
            if inst and len(inst) >= 4:
                db_id = inst[0]
                db_class = inst[1]
                engine = inst[2]
                status = inst[3]
                storage = inst[4] if len(inst) > 4 else 0
                storage_type = inst[5] if len(inst) > 5 else 'gp2'
                iops = inst[6] if len(inst) > 6 else 0
                multi_az = inst[7] if len(inst) > 7 else False
                engine_version = inst[8] if len(inst) > 8 else 'unknown'

                instances.append({
                    'id': db_id,
                    'class': db_class,
                    'engine': engine,
                    'status': status,
                    'storage_gb': storage or 0,
                    'storage_type': storage_type,
                    'iops': iops,
                    'multi_az': multi_az,
                    'engine_version': engine_version
                })

        return instances

    except json.JSONDecodeError:
        print("Error parsing RDS instance data")
        return []


def get_reserved_instances() -> Dict[str, int]:
    """Get current RDS Reserved Instances count by class."""
    print("Fetching RDS Reserved Instances...")

    success, output = run_command([
        'aws', 'rds', 'describe-reserved-db-instances',
        '--query', 'ReservedDBInstances[?State==`active`].[DBInstanceClass,DBInstanceCount]',
        '--output', 'json'
    ])

    if not success:
        print(f"  Warning: Could not fetch RDS RIs: {output}")
        return {}

    try:
        ri_data = json.loads(output) if output.strip() else []
        if ri_data is None:
            ri_data = []

        ri_count = defaultdict(int)
        for ri in ri_data:
            if ri and len(ri) >= 2:
                db_class = ri[0]
                count = ri[1] or 1
                ri_count[db_class] += count

        return dict(ri_count)

    except json.JSONDecodeError:
        print("  Warning: Error parsing RDS RI data")
        return {}


def get_instance_price(db_class: str) -> Decimal:
    """Get on-demand hourly price for RDS instance class."""
    if db_class in RDS_ON_DEMAND_PRICING:
        return RDS_ON_DEMAND_PRICING[db_class]

    # Estimate if not in pricing table
    print(f"  Warning: No pricing data for {db_class}, using estimate")
    return Decimal('0.10')


def calculate_instance_cost(db_class: str, multi_az: bool = False) -> Decimal:
    """Calculate monthly instance cost."""
    hourly_price = get_instance_price(db_class)
    monthly_cost = hourly_price * HOURS_PER_MONTH

    # Multi-AZ deployments cost 2x
    if multi_az:
        monthly_cost *= 2

    return monthly_cost


def calculate_storage_cost(storage_gb: int, storage_type: str, iops: int = 0) -> Decimal:
    """Calculate monthly storage cost."""
    storage_price = STORAGE_PRICING.get(storage_type, STORAGE_PRICING['gp2'])
    storage_cost = Decimal(storage_gb) * storage_price

    # Add IOPS cost for io1
    if storage_type == 'io1' and iops > 0:
        storage_cost += Decimal(iops) * IOPS_PRICE

    return storage_cost


def calculate_total_cost(instance: Dict) -> Decimal:
    """Calculate total monthly cost for an RDS instance."""
    instance_cost = calculate_instance_cost(instance['class'], instance['multi_az'])
    storage_cost = calculate_storage_cost(
        instance['storage_gb'],
        instance['storage_type'],
        instance['iops'] or 0
    )
    return instance_cost + storage_cost


def calculate_ri_savings(db_class: str, count: int, multi_az: bool = False) -> Dict:
    """Calculate savings with RDS Reserved Instances."""
    monthly_ondemand = calculate_instance_cost(db_class, multi_az) * count
    yearly_ondemand = monthly_ondemand * 12

    # RI costs (with discount)
    monthly_ri_1year = monthly_ondemand * (1 - RI_DISCOUNT_1YEAR)
    yearly_ri_1year = monthly_ri_1year * 12

    monthly_ri_3year = monthly_ondemand * (1 - RI_DISCOUNT_3YEAR)
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
    print("RDS COST ANALYZER")
    print_separator()
    print()

    # Get all RDS instances
    instances = get_all_rds_instances()

    if not instances:
        print("No RDS instances found or error accessing AWS.")
        sys.exit(1)

    print(f"Found {len(instances)} RDS instance(s)\n")

    # Get Reserved Instances
    reserved_instances = get_reserved_instances()

    # Categorize instances
    available_instances = [i for i in instances if i['status'] == 'available']
    stopped_instances = [i for i in instances if i['status'] == 'stopped']
    other_instances = [i for i in instances if i['status'] not in ['available', 'stopped']]

    print_separator()
    print("RDS INSTANCE SUMMARY")
    print_separator()
    print()
    print(f"Total RDS Instances: {len(instances)}")
    print(f"  Available (Running): {len(available_instances)}")
    print(f"  Stopped: {len(stopped_instances)}")
    if other_instances:
        print(f"  Other States: {len(other_instances)}")
    print()

    # Group by instance class
    class_summary = defaultdict(list)
    for inst in available_instances:
        class_summary[inst['class']].append(inst)

    print("Instance Classes:")
    for db_class, inst_list in sorted(class_summary.items()):
        multi_az_count = sum(1 for i in inst_list if i['multi_az'])
        print(f"  {db_class}: {len(inst_list)} instance(s)", end='')
        if multi_az_count > 0:
            print(f" ({multi_az_count} Multi-AZ)")
        else:
            print()
    print()
    print_separator('-')
    print()

    # Current RI coverage
    if reserved_instances:
        print_separator()
        print("CURRENT RDS RESERVED INSTANCES")
        print_separator()
        print()
        for db_class, count in reserved_instances.items():
            print(f"  {db_class}: {count} Reserved Instance(s)")
        print()
        print_separator('-')
        print()

    # Calculate current costs
    print_separator()
    print("CURRENT RDS COSTS")
    print_separator()
    print()

    total_monthly_cost = Decimal('0')
    total_instance_cost = Decimal('0')
    total_storage_cost = Decimal('0')

    for inst in available_instances:
        instance_cost = calculate_instance_cost(inst['class'], inst['multi_az'])
        storage_cost = calculate_storage_cost(inst['storage_gb'], inst['storage_type'], inst['iops'] or 0)
        total_cost = instance_cost + storage_cost

        total_monthly_cost += total_cost
        total_instance_cost += instance_cost
        total_storage_cost += storage_cost

        print(f"{inst['id']}:")
        print(f"  Class: {inst['class']}, Engine: {inst['engine']}")
        print(f"  Multi-AZ: {inst['multi_az']}, Storage: {inst['storage_gb']} GB ({inst['storage_type']})")
        print(f"  Instance Cost: {format_currency(instance_cost)}/month")
        print(f"  Storage Cost: {format_currency(storage_cost)}/month")
        print(f"  Total: {format_currency(total_cost)}/month")
        print()

    print_separator('-')
    print(f"TOTAL INSTANCE COST: {format_currency(total_instance_cost)}/month")
    print(f"TOTAL STORAGE COST: {format_currency(total_storage_cost)}/month")
    print(f"TOTAL MONTHLY COST: {format_currency(total_monthly_cost)}")
    print(f"TOTAL YEARLY COST: {format_currency(total_monthly_cost * 12)}")
    print_separator('-')
    print()

    # RI Recommendations
    print_separator()
    print("RESERVED INSTANCE RECOMMENDATIONS")
    print_separator()
    print()

    total_1year_savings = Decimal('0')
    total_3year_savings = Decimal('0')
    has_recommendations = False

    for db_class, inst_list in sorted(class_summary.items()):
        count = len(inst_list)
        ri_covered = reserved_instances.get(db_class, 0)
        uncovered = count - ri_covered

        # Check if any are Multi-AZ (for accurate calculation)
        has_multi_az = any(i['multi_az'] for i in inst_list)

        if uncovered > 0:
            has_recommendations = True
            savings = calculate_ri_savings(db_class, uncovered, has_multi_az)

            total_1year_savings += savings['savings_1year']
            total_3year_savings += savings['savings_3year']

            print(f"{db_class} - {uncovered} instance(s) recommended for RI")
            if has_multi_az:
                print(f"  (Includes Multi-AZ pricing)")
            print(f"  Current On-Demand Cost: {format_currency(savings['yearly_ondemand'])}/year")
            print()
            print(f"  1-Year RI:")
            print(f"    Yearly Cost: {format_currency(savings['yearly_ri_1year'])}")
            print(f"    Yearly Savings: {format_currency(savings['savings_1year'])} ({RI_DISCOUNT_1YEAR * 100:.0f}% off)")
            print()
            print(f"  3-Year RI:")
            print(f"    Yearly Cost: {format_currency(savings['yearly_ri_3year'])}")
            print(f"    Yearly Savings: {format_currency(savings['savings_3year'])} ({RI_DISCOUNT_3YEAR * 100:.0f}% off)")
            print()
            print_separator('-')
            print()

    if not has_recommendations:
        print("All running instances are covered by Reserved Instances!")
        print()

    # Storage Optimization
    io1_instances = [i for i in available_instances if i['storage_type'] == 'io1']
    if io1_instances:
        print_separator()
        print("STORAGE OPTIMIZATION OPPORTUNITIES")
        print_separator()
        print()
        print(f"Found {len(io1_instances)} instance(s) using Provisioned IOPS (io1)")
        print()

        for inst in io1_instances:
            storage_cost = calculate_storage_cost(inst['storage_gb'], inst['storage_type'], inst['iops'] or 0)
            gp2_cost = calculate_storage_cost(inst['storage_gb'], 'gp2', 0)
            savings = storage_cost - gp2_cost

            if savings > 0:
                print(f"{inst['id']}:")
                print(f"  Current (io1): {format_currency(storage_cost)}/month")
                print(f"  If using gp2: {format_currency(gp2_cost)}/month")
                print(f"  Monthly Savings: {format_currency(savings)}")
                print(f"  Yearly Savings: {format_currency(savings * 12)}")
                print()

        print("NOTE: Only migrate from io1 to gp2/gp3 if IOPS requirements allow")
        print_separator('-')
        print()

    # Recommendations
    print_separator()
    print("RECOMMENDATIONS")
    print_separator()
    print()

    recommendations = []

    if has_recommendations:
        recommendations.append(
            f"1. PURCHASE Reserved Instances for cost savings:"
        )
        recommendations.append(
            f"   - 1-Year RI: Save {format_currency(total_1year_savings)}/year"
        )
        recommendations.append(
            f"   - 3-Year RI: Save {format_currency(total_3year_savings)}/year"
        )

    if io1_instances:
        recommendations.append(
            f"2. REVIEW {len(io1_instances)} instance(s) using Provisioned IOPS storage"
        )
        recommendations.append(
            "   - Consider migrating to gp3 for better price/performance"
        )
        recommendations.append(
            "   - gp3 offers up to 16,000 IOPS at base price"
        )

    recommendations.append(
        f"3. MONITOR database utilization:"
    )
    recommendations.append(
        "   - Use CloudWatch metrics (CPU, Memory, IOPS)"
    )
    recommendations.append(
        "   - Right-size instances based on actual usage"
    )
    recommendations.append(
        "   - Consider Aurora Serverless for variable workloads"
    )

    recommendations.append(
        f"4. IMPLEMENT cost controls:"
    )
    recommendations.append(
        "   - Stop non-production databases outside business hours"
    )
    recommendations.append(
        "   - Use snapshot lifecycle policies"
    )
    recommendations.append(
        "   - Enable automated backups with appropriate retention"
    )

    if stopped_instances:
        recommendations.append(
            f"5. REVIEW {len(stopped_instances)} stopped instance(s)"
        )
        recommendations.append(
            "   - Stopped RDS instances still incur storage charges"
        )
        recommendations.append(
            "   - Consider snapshots and termination for long-term stopped instances"
        )

    for rec in recommendations:
        print(rec)

    print()

    # Summary
    if total_1year_savings > 0 or total_3year_savings > 0:
        print_separator('-')
        print("POTENTIAL YEARLY SAVINGS:")
        if total_1year_savings > 0:
            print(f"  With 1-Year RIs: {format_currency(total_1year_savings)}")
        if total_3year_savings > 0:
            print(f"  With 3-Year RIs: {format_currency(total_3year_savings)}")
        print_separator('-')
        print()

    print("NOTE: Pricing based on us-east-1 region for MySQL/PostgreSQL")
    print("Update RDS_ON_DEMAND_PRICING for your region and engine")
    print(f"RI Discounts: 1-Year = {RI_DISCOUNT_1YEAR * 100:.0f}%, 3-Year = {RI_DISCOUNT_3YEAR * 100:.0f}%")
    print_separator()


if __name__ == '__main__':
    main()
