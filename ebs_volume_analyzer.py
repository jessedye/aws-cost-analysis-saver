#!/usr/bin/env python3
"""
EBS Volume Cost Analyzer
Identifies unused, unattached, and underutilized EBS volumes for cost savings.
This script only reads and analyzes - it does not make any changes.
"""

import subprocess
import json
import sys
from datetime import datetime, timezone
from typing import Dict, List, Tuple
from decimal import Decimal

# AWS EBS Pricing (USD per GB/month) - us-east-1 region
# Update these values based on your region
EBS_PRICING = {
    'gp2': Decimal('0.10'),      # General Purpose SSD
    'gp3': Decimal('0.08'),      # General Purpose SSD (newer)
    'io1': Decimal('0.125'),     # Provisioned IOPS SSD
    'io2': Decimal('0.125'),     # Provisioned IOPS SSD (newer)
    'st1': Decimal('0.045'),     # Throughput Optimized HDD
    'sc1': Decimal('0.015'),     # Cold HDD
    'standard': Decimal('0.05'), # Magnetic (previous generation)
}

# IOPS pricing (for io1/io2)
IOPS_PRICING = Decimal('0.065')  # per provisioned IOPS per month


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


def get_all_volumes() -> List[Dict]:
    """Get list of all EBS volumes."""
    print("Fetching all EBS volumes...")

    success, output = run_command([
        'aws', 'ec2', 'describe-volumes',
        '--query', 'Volumes[].[VolumeId,Size,VolumeType,State,Attachments,Iops,CreateTime,Tags]',
        '--output', 'json'
    ])

    if not success:
        print(f"Error getting volumes: {output}")
        return []

    try:
        volume_data = json.loads(output) if output.strip() else []
        if volume_data is None:
            volume_data = []

        volumes = []
        for vol in volume_data:
            if vol and len(vol) >= 5:
                volume_id = vol[0]
                size_gb = vol[1] or 0
                volume_type = vol[2] or 'gp2'
                state = vol[3]
                attachments = vol[4] or []
                iops = vol[5] if len(vol) > 5 else 0
                create_time = vol[6] if len(vol) > 6 else None
                tags = vol[7] if len(vol) > 7 else []

                # Parse creation time
                try:
                    created_date = datetime.fromisoformat(create_time.replace('Z', '+00:00'))
                    age_days = (datetime.now(timezone.utc) - created_date).days
                except (ValueError, AttributeError, TypeError):
                    created_date = None
                    age_days = 0

                # Extract Name tag
                name = "No Name"
                if tags:
                    for tag in tags:
                        if tag.get('Key') == 'Name':
                            name = tag.get('Value', 'No Name')
                            break

                # Determine attachment status
                is_attached = len(attachments) > 0
                instance_id = None
                if is_attached and attachments[0]:
                    instance_id = attachments[0].get('InstanceId', 'Unknown')

                volumes.append({
                    'id': volume_id,
                    'name': name,
                    'size_gb': Decimal(size_gb),
                    'type': volume_type,
                    'state': state,
                    'is_attached': is_attached,
                    'instance_id': instance_id,
                    'iops': iops or 0,
                    'created_date': created_date,
                    'age_days': age_days
                })

        return volumes

    except json.JSONDecodeError:
        print("Error parsing volume data")
        return []


def calculate_volume_cost(volume: Dict) -> Decimal:
    """Calculate monthly cost for a volume."""
    volume_type = volume['type']
    size_gb = volume['size_gb']
    iops = volume['iops']

    # Base storage cost
    price_per_gb = EBS_PRICING.get(volume_type, EBS_PRICING['gp2'])
    storage_cost = size_gb * price_per_gb

    # Add IOPS cost for provisioned IOPS volumes
    iops_cost = Decimal('0')
    if volume_type in ['io1', 'io2'] and iops > 0:
        iops_cost = Decimal(iops) * IOPS_PRICING

    return storage_cost + iops_cost


def format_currency(amount: Decimal) -> str:
    """Format decimal as currency."""
    return f"${amount:.2f}"


def format_date(dt: datetime) -> str:
    """Format datetime for display."""
    if dt is None:
        return "Unknown"
    return dt.strftime("%Y-%m-%d")


def print_separator(char='=', length=80):
    """Print a separator line."""
    print(char * length)


def main():
    """Main function."""
    print_separator()
    print("EBS VOLUME COST ANALYZER")
    print_separator()
    print()

    # Get all volumes
    volumes = get_all_volumes()

    if not volumes:
        print("No volumes found or error accessing AWS.")
        sys.exit(1)

    print(f"Found {len(volumes)} volume(s)\n")

    # Categorize volumes
    available_volumes = [v for v in volumes if v['state'] == 'available']
    attached_volumes = [v for v in volumes if v['is_attached']]
    in_use_volumes = [v for v in volumes if v['state'] == 'in-use']

    print_separator()
    print("VOLUME SUMMARY")
    print_separator()
    print()
    print(f"Total Volumes: {len(volumes)}")
    print(f"  In-Use (Attached): {len(attached_volumes)}")
    print(f"  Available (Unattached): {len(available_volumes)}")
    print()

    # Calculate totals by type
    type_summary = {}
    for vol in volumes:
        vol_type = vol['type']
        if vol_type not in type_summary:
            type_summary[vol_type] = {'count': 0, 'size': Decimal('0')}
        type_summary[vol_type]['count'] += 1
        type_summary[vol_type]['size'] += vol['size_gb']

    print("Volume Types:")
    for vol_type, data in sorted(type_summary.items()):
        print(f"  {vol_type}: {data['count']} volume(s), {data['size']:.2f} GB")
    print()
    print_separator('-')
    print()

    # Calculate current costs
    print_separator()
    print("CURRENT EBS COSTS")
    print_separator()
    print()

    total_monthly_cost = Decimal('0')
    attached_cost = Decimal('0')
    available_cost = Decimal('0')

    for vol in volumes:
        cost = calculate_volume_cost(vol)
        total_monthly_cost += cost
        if vol['is_attached']:
            attached_cost += cost
        elif vol['state'] == 'available':
            available_cost += cost

    print(f"Total Monthly Cost: {format_currency(total_monthly_cost)}")
    print(f"Total Yearly Cost: {format_currency(total_monthly_cost * 12)}")
    print()
    print(f"Attached Volumes: {format_currency(attached_cost)}/month")
    print(f"Unattached Volumes: {format_currency(available_cost)}/month")
    print()
    print_separator('-')
    print()

    # Analyze unattached volumes
    if available_volumes:
        print_separator()
        print("UNATTACHED VOLUMES (Cost Savings Opportunity)")
        print_separator()
        print()
        print(f"Found {len(available_volumes)} unattached volume(s)")
        print(f"Total Size: {sum(v['size_gb'] for v in available_volumes):.2f} GB")
        print()
        print(f"Monthly Waste: {format_currency(available_cost)}")
        print(f"Yearly Waste: {format_currency(available_cost * 12)}")
        print()
        print_separator('-')
        print()

        # Show details
        print(f"{'Volume ID':<23} {'Type':<8} {'Size':<12} {'Monthly Cost':<15} {'Age':<12} {'Name'}")
        print_separator('-')

        # Sort by cost (highest first)
        available_sorted = sorted(available_volumes,
                                 key=lambda x: calculate_volume_cost(x),
                                 reverse=True)

        for vol in available_sorted:
            cost = calculate_volume_cost(vol)
            print(f"{vol['id']:<23} {vol['type']:<8} {vol['size_gb']:>6.2f} GB   "
                  f"{format_currency(cost):<15} {vol['age_days']:>4} days   {vol['name']}")

        print_separator('-')
        print()
    else:
        print_separator()
        print("NO UNATTACHED VOLUMES FOUND")
        print_separator()
        print()
        print("All volumes are currently attached. Great job!")
        print()

    # GP2 to GP3 optimization
    gp2_volumes = [v for v in volumes if v['type'] == 'gp2']
    if gp2_volumes:
        print_separator()
        print("GP2 TO GP3 MIGRATION OPPORTUNITY")
        print_separator()
        print()
        print("GP3 volumes offer better performance at 20% lower cost than GP2")
        print()

        gp2_size = sum(v['size_gb'] for v in gp2_volumes)
        gp2_cost = sum(calculate_volume_cost(v) for v in gp2_volumes)
        gp3_cost = gp2_size * EBS_PRICING['gp3']
        savings = gp2_cost - gp3_cost

        print(f"GP2 Volumes: {len(gp2_volumes)}")
        print(f"Total GP2 Size: {gp2_size:.2f} GB")
        print()
        print(f"Current GP2 Cost: {format_currency(gp2_cost)}/month")
        print(f"Estimated GP3 Cost: {format_currency(gp3_cost)}/month")
        print()
        print(f"Monthly Savings: {format_currency(savings)}")
        print(f"Yearly Savings: {format_currency(savings * 12)}")
        print()
        print_separator('-')
        print()

    # Oversized volume detection (io1/io2 with high IOPS)
    provisioned_iops_volumes = [v for v in volumes if v['type'] in ['io1', 'io2'] and v['iops'] > 0]
    if provisioned_iops_volumes:
        print_separator()
        print("PROVISIONED IOPS VOLUMES (Review Needed)")
        print_separator()
        print()
        print("Provisioned IOPS volumes are expensive. Verify they're still needed.")
        print()

        total_iops_cost = Decimal('0')
        for vol in provisioned_iops_volumes:
            cost = calculate_volume_cost(vol)
            storage_cost = vol['size_gb'] * EBS_PRICING.get(vol['type'], Decimal('0.125'))
            iops_cost = cost - storage_cost
            total_iops_cost += iops_cost

            print(f"Volume: {vol['id']}")
            print(f"  Size: {vol['size_gb']} GB, IOPS: {vol['iops']}")
            print(f"  Storage Cost: {format_currency(storage_cost)}/month")
            print(f"  IOPS Cost: {format_currency(iops_cost)}/month")
            print(f"  Total: {format_currency(cost)}/month")
            print(f"  Attached: {'Yes' if vol['is_attached'] else 'No'}")
            print()

        print(f"Total IOPS charges: {format_currency(total_iops_cost)}/month")
        print(f"Consider migrating to GP3 if you don't need >16,000 IOPS")
        print()
        print_separator('-')
        print()

    # Show recommendations
    print_separator()
    print("RECOMMENDATIONS")
    print_separator()
    print()

    recommendations = []

    if available_volumes:
        recommendations.append(
            f"1. DELETE {len(available_volumes)} unattached volume(s) to save "
            f"{format_currency(available_cost * 12)}/year"
        )
        recommendations.append(
            "   - Create snapshots before deletion if data might be needed"
        )
        recommendations.append(
            "   - Snapshots cost $0.05/GB/month vs volume storage costs"
        )

    if gp2_volumes:
        recommendations.append(
            f"2. MIGRATE {len(gp2_volumes)} GP2 volume(s) to GP3 to save "
            f"{format_currency((gp2_cost - gp3_cost) * 12)}/year"
        )
        recommendations.append(
            "   - GP3 offers 20% cost savings with better baseline performance"
        )
        recommendations.append(
            "   - Migration can be done with minimal downtime"
        )

    if provisioned_iops_volumes:
        recommendations.append(
            f"3. REVIEW {len(provisioned_iops_volumes)} provisioned IOPS volume(s)"
        )
        recommendations.append(
            "   - Verify high IOPS are actually needed for workload"
        )
        recommendations.append(
            "   - Consider GP3 which provides 3,000 IOPS baseline"
        )

    recommendations.append(
        f"4. IMPLEMENT lifecycle management:"
    )
    recommendations.append(
        "   - Tag volumes with expiration dates"
    )
    recommendations.append(
        "   - Set up CloudWatch alarms for unattached volumes"
    )
    recommendations.append(
        "   - Automate snapshot creation and old snapshot cleanup"
    )

    if not available_volumes and not gp2_volumes:
        recommendations = [
            "1. Excellent! Your EBS volumes are well-optimized",
            "2. Continue monitoring for unattached volumes",
            "3. Review volume types quarterly for optimization opportunities"
        ]

    for rec in recommendations:
        print(rec)

    print()

    # Calculate total potential savings
    total_savings = available_cost
    if gp2_volumes:
        total_savings += (gp2_cost - gp3_cost)

    if total_savings > 0:
        print_separator('-')
        print(f"TOTAL POTENTIAL YEARLY SAVINGS: {format_currency(total_savings * 12)}")
        print_separator('-')
        print()

    print("NOTE: Always create snapshots before deleting volumes")
    print("Snapshot storage ($0.05/GB/month) is cheaper than volume storage")
    print()
    print("Pricing based on us-east-1 region. Update EBS_PRICING for your region.")
    print_separator()


if __name__ == '__main__':
    main()
