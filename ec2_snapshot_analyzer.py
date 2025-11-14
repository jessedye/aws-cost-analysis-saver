#!/usr/bin/env python3
"""
EC2 Snapshot Cost Analyzer
Analyzes EBS snapshot ages, current costs, and potential savings from deleting old snapshots.
"""

import subprocess
import json
import sys
from datetime import datetime, timezone
from typing import Dict, List, Tuple
from decimal import Decimal

# AWS EBS Snapshot Pricing (USD per GB/month) - us-east-1 region
# Update these values based on your region
SNAPSHOT_PRICE_PER_GB = Decimal('0.05')  # Standard snapshot storage

# Age threshold for identifying old snapshots (in days)
OLD_SNAPSHOT_THRESHOLD = 90


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


def get_all_snapshots() -> List[Dict]:
    """Get list of all EBS snapshots owned by the account."""
    print("Fetching all EBS snapshots...")

    success, output = run_command([
        'aws', 'ec2', 'describe-snapshots',
        '--owner-ids', 'self',
        '--query', 'Snapshots[].[SnapshotId,VolumeSize,StartTime,Description,State,VolumeId]',
        '--output', 'json'
    ])

    if not success:
        print(f"Error getting snapshots: {output}")
        return []

    try:
        snapshot_data = json.loads(output) if output.strip() else []
        if snapshot_data is None:
            snapshot_data = []

        snapshots = []
        for snap in snapshot_data:
            if snap and len(snap) >= 5:
                snapshot_id = snap[0]
                size_gb = snap[1] or 0
                start_time = snap[2]
                description = snap[3] or "No description"
                state = snap[4]
                volume_id = snap[5] or "Unknown"

                # Parse the start time
                try:
                    created_date = datetime.fromisoformat(start_time.replace('Z', '+00:00'))
                    age_days = (datetime.now(timezone.utc) - created_date).days
                except (ValueError, AttributeError):
                    created_date = None
                    age_days = 0

                snapshots.append({
                    'id': snapshot_id,
                    'size_gb': Decimal(size_gb),
                    'created_date': created_date,
                    'age_days': age_days,
                    'description': description,
                    'state': state,
                    'volume_id': volume_id
                })

        return snapshots

    except json.JSONDecodeError:
        print("Error parsing snapshot data")
        return []


def calculate_snapshot_cost(size_gb: Decimal) -> Decimal:
    """Calculate monthly cost for a snapshot."""
    return size_gb * SNAPSHOT_PRICE_PER_GB


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
    print("EC2 SNAPSHOT COST ANALYZER")
    print_separator()
    print()

    # Get all snapshots
    snapshots = get_all_snapshots()

    if not snapshots:
        print("No snapshots found or error accessing AWS.")
        sys.exit(1)

    print(f"Found {len(snapshots)} snapshot(s)\n")

    # Categorize snapshots
    old_snapshots = [s for s in snapshots if s['age_days'] >= OLD_SNAPSHOT_THRESHOLD]
    recent_snapshots = [s for s in snapshots if s['age_days'] < OLD_SNAPSHOT_THRESHOLD]

    # Calculate totals
    total_size = sum(s['size_gb'] for s in snapshots)
    old_size = sum(s['size_gb'] for s in old_snapshots)
    recent_size = sum(s['size_gb'] for s in recent_snapshots)

    total_cost = sum(calculate_snapshot_cost(s['size_gb']) for s in snapshots)
    old_cost = sum(calculate_snapshot_cost(s['size_gb']) for s in old_snapshots)
    recent_cost = sum(calculate_snapshot_cost(s['size_gb']) for s in recent_snapshots)

    # Display summary
    print_separator()
    print("SNAPSHOT SUMMARY")
    print_separator()
    print()
    print(f"Total Snapshots: {len(snapshots)}")
    print(f"  Recent (< {OLD_SNAPSHOT_THRESHOLD} days): {len(recent_snapshots)}")
    print(f"  Old (>= {OLD_SNAPSHOT_THRESHOLD} days): {len(old_snapshots)}")
    print()
    print(f"Total Storage: {total_size:.2f} GB")
    print(f"  Recent snapshots: {recent_size:.2f} GB")
    print(f"  Old snapshots: {old_size:.2f} GB")
    print()
    print_separator('-')
    print()

    # Display current costs
    print_separator()
    print("CURRENT SNAPSHOT COSTS")
    print_separator()
    print()
    print(f"Total Monthly Cost: {format_currency(total_cost)}")
    print(f"Total Yearly Cost: {format_currency(total_cost * 12)}")
    print()
    print(f"Recent Snapshots Monthly Cost: {format_currency(recent_cost)}")
    print(f"Old Snapshots Monthly Cost: {format_currency(old_cost)}")
    print()
    print_separator('-')
    print()

    # Display potential savings
    if old_snapshots:
        print_separator()
        print(f"POTENTIAL SAVINGS (Deleting Snapshots Older Than {OLD_SNAPSHOT_THRESHOLD} Days)")
        print_separator()
        print()
        print(f"Number of Old Snapshots: {len(old_snapshots)}")
        print(f"Total Size of Old Snapshots: {old_size:.2f} GB")
        print()
        print(f"Monthly Savings: {format_currency(old_cost)}")
        print(f"Yearly Savings: {format_currency(old_cost * 12)}")
        print()
        print_separator('-')
        print()

        # Show details of old snapshots
        print_separator()
        print(f"DETAILED LIST OF OLD SNAPSHOTS (>= {OLD_SNAPSHOT_THRESHOLD} days)")
        print_separator()
        print()

        # Sort by age (oldest first)
        old_snapshots_sorted = sorted(old_snapshots, key=lambda x: x['age_days'], reverse=True)

        print(f"{'Snapshot ID':<22} {'Age':<12} {'Size':<12} {'Monthly Cost':<15} {'Created':<12} {'Volume ID'}")
        print_separator('-')

        for snap in old_snapshots_sorted:
            cost = calculate_snapshot_cost(snap['size_gb'])
            print(f"{snap['id']:<22} {snap['age_days']:>4} days   {snap['size_gb']:>6.2f} GB   "
                  f"{format_currency(cost):<15} {format_date(snap['created_date']):<12} {snap['volume_id']}")

        print_separator('-')
        print()

        # Show age distribution
        print_separator()
        print("AGE DISTRIBUTION OF OLD SNAPSHOTS")
        print_separator()
        print()

        age_ranges = [
            (90, 180, "90-180 days"),
            (180, 365, "180-365 days (6 months - 1 year)"),
            (365, 730, "1-2 years"),
            (730, float('inf'), "2+ years")
        ]

        for min_age, max_age, label in age_ranges:
            range_snapshots = [s for s in old_snapshots if min_age <= s['age_days'] < max_age]
            if range_snapshots:
                range_size = sum(s['size_gb'] for s in range_snapshots)
                range_cost = sum(calculate_snapshot_cost(s['size_gb']) for s in range_snapshots)
                print(f"{label}:")
                print(f"  Count: {len(range_snapshots)}")
                print(f"  Size: {range_size:.2f} GB")
                print(f"  Monthly Cost: {format_currency(range_cost)}")
                print(f"  Yearly Cost: {format_currency(range_cost * 12)}")
                print()

        print_separator('-')
        print()
    else:
        print_separator()
        print(f"NO OLD SNAPSHOTS FOUND (>= {OLD_SNAPSHOT_THRESHOLD} days)")
        print_separator()
        print()
        print("All snapshots are less than 90 days old. No immediate savings opportunity.")
        print()

    # Show recommendations
    print_separator()
    print("RECOMMENDATIONS")
    print_separator()
    print()

    if old_snapshots:
        print(f"1. Review the {len(old_snapshots)} snapshot(s) older than {OLD_SNAPSHOT_THRESHOLD} days")
        print("2. Verify these snapshots are no longer needed:")
        print("   - Check if the source volume still exists")
        print("   - Verify if there are newer snapshots available")
        print("   - Confirm with relevant teams before deletion")
        print()
        print("3. Consider implementing a snapshot lifecycle policy:")
        print("   - Automate snapshot creation and deletion")
        print("   - Set retention periods based on business requirements")
        print("   - Use AWS Data Lifecycle Manager (DLM) for automation")
        print()
        print(f"4. Potential yearly savings: {format_currency(old_cost * 12)}")
    else:
        print("1. Your snapshots are well-managed!")
        print("2. Consider implementing automated lifecycle policies to maintain this")
        print("3. Regularly review snapshots to ensure they're still needed")

    print()
    print("NOTE: Before deleting any snapshots, ensure you have proper backups")
    print("and that the snapshots are truly no longer needed.")
    print()
    print(f"Pricing based on us-east-1 region (${SNAPSHOT_PRICE_PER_GB}/GB/month).")
    print("Update SNAPSHOT_PRICE_PER_GB for your region.")
    print_separator()


if __name__ == '__main__':
    main()
