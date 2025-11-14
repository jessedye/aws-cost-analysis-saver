#!/usr/bin/env python3
"""
S3 Cost Analyzer
Analyzes S3 bucket sizes, current storage costs, and potential savings with Glacier storage.
"""

import subprocess
import json
import re
import sys
from typing import Dict, List, Tuple
from decimal import Decimal

# AWS S3 Pricing (USD per GB/month) - us-east-1 region
# Update these values based on your region
PRICING = {
    'STANDARD': Decimal('0.023'),
    'STANDARD_IA': Decimal('0.0125'),
    'INTELLIGENT_TIERING': Decimal('0.023'),  # Frequent access tier
    'ONEZONE_IA': Decimal('0.01'),
    'GLACIER_IR': Decimal('0.004'),  # Glacier Instant Retrieval
    'GLACIER': Decimal('0.0036'),
    'DEEP_ARCHIVE': Decimal('0.00099'),
}


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


def get_all_buckets() -> List[str]:
    """Get list of all S3 buckets."""
    print("Fetching all S3 buckets...")
    success, output = run_command(['aws', 's3', 'ls'])

    if not success:
        print(f"Error getting buckets: {output}")
        return []

    buckets = []
    for line in output.strip().split('\n'):
        if line:
            # Format: "2023-01-01 12:00:00 bucket-name"
            parts = line.split()
            if len(parts) >= 3:
                bucket_name = parts[2]
                buckets.append(bucket_name)

    return buckets


def parse_size(size_str: str) -> Decimal:
    """Convert human-readable size to GB."""
    size_str = size_str.strip()

    # Match number and unit
    match = re.match(r'([\d.]+)\s*([KMGTP]i?B?)?', size_str, re.IGNORECASE)
    if not match:
        return Decimal('0')

    value = Decimal(match.group(1))
    unit = (match.group(2) or 'B').upper()

    # Convert to GB
    multipliers = {
        'B': Decimal('0.000000001'),
        'KB': Decimal('0.000001'),
        'KIB': Decimal('0.000001'),
        'MB': Decimal('0.001'),
        'MIB': Decimal('0.001'),
        'GB': Decimal('1'),
        'GIB': Decimal('1'),
        'TB': Decimal('1000'),
        'TIB': Decimal('1000'),
        'PB': Decimal('1000000'),
        'PIB': Decimal('1000000'),
    }

    for key in multipliers:
        if unit.startswith(key):
            return value * multipliers[key]

    return value * Decimal('0.000000001')  # Default to bytes


def get_bucket_size(bucket_name: str) -> Decimal:
    """Get total size of a bucket in GB."""
    print(f"  Analyzing {bucket_name}...", end='', flush=True)

    success, output = run_command([
        'aws', 's3', 'ls',
        f's3://{bucket_name}',
        '--recursive',
        '--summarize',
        '--human-readable'
    ])

    if not success:
        print(f" ERROR")
        print(f"    Error: {output}")
        return Decimal('0')

    # Look for "Total Size: X.XX GiB" or similar
    size_match = re.search(r'Total Size:\s*([\d.]+\s*[KMGTP]i?B)', output, re.IGNORECASE)

    if size_match:
        size_str = size_match.group(1)
        size_gb = parse_size(size_str)
        print(f" {size_str} ({size_gb:.2f} GB)")
        return size_gb

    print(" 0 GB (empty)")
    return Decimal('0')


def get_storage_class_distribution(bucket_name: str) -> Dict[str, Decimal]:
    """Get distribution of storage classes in a bucket."""
    # Using CloudWatch metrics or S3 Inventory would be more accurate,
    # but this is a simplified approach using aws s3api

    success, output = run_command([
        'aws', 's3api', 'list-objects-v2',
        '--bucket', bucket_name,
        '--query', 'Contents[].[StorageClass, Size]',
        '--output', 'json'
    ])

    if not success:
        # If listing fails, assume STANDARD storage
        return {}

    try:
        objects = json.loads(output) if output.strip() else []
        if objects is None:  # Handle case where AWS returns null for empty buckets
            objects = []
        distribution = {}

        for obj in objects:
            if obj and len(obj) >= 2:
                storage_class = obj[0] if obj[0] else 'STANDARD'
                size_bytes = obj[1] or 0
                size_gb = Decimal(size_bytes) / Decimal('1073741824')  # Convert to GB

                if storage_class not in distribution:
                    distribution[storage_class] = Decimal('0')
                distribution[storage_class] += size_gb

        return distribution
    except json.JSONDecodeError:
        return {}


def calculate_monthly_cost(size_gb: Decimal, storage_class: str) -> Decimal:
    """Calculate monthly cost for given size and storage class."""
    price_per_gb = PRICING.get(storage_class, PRICING['STANDARD'])
    return size_gb * price_per_gb


def calculate_savings(size_gb: Decimal, current_class: str, target_class: str) -> Dict:
    """Calculate savings when moving from current to target storage class."""
    current_cost = calculate_monthly_cost(size_gb, current_class)
    target_cost = calculate_monthly_cost(size_gb, target_class)
    savings = current_cost - target_cost
    savings_percent = (savings / current_cost * 100) if current_cost > 0 else Decimal('0')

    return {
        'current_cost': current_cost,
        'target_cost': target_cost,
        'savings': savings,
        'savings_percent': savings_percent
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
    print("S3 COST ANALYZER")
    print_separator()
    print()

    # Get all buckets
    buckets = get_all_buckets()

    if not buckets:
        print("No buckets found or error accessing AWS.")
        sys.exit(1)

    print(f"Found {len(buckets)} bucket(s)\n")
    print_separator('-')

    # Analyze each bucket
    bucket_data = []
    total_size = Decimal('0')

    for bucket in buckets:
        size_gb = get_bucket_size(bucket)
        total_size += size_gb

        # Try to get storage class distribution
        distribution = get_storage_class_distribution(bucket)

        # If we have distribution data, use it; otherwise assume STANDARD
        if distribution:
            primary_class = max(distribution, key=distribution.get)
        else:
            primary_class = 'STANDARD'

        bucket_data.append({
            'name': bucket,
            'size_gb': size_gb,
            'storage_class': primary_class,
            'distribution': distribution
        })

    print_separator('-')
    print()

    # Calculate costs
    print_separator()
    print("CURRENT COSTS")
    print_separator()
    print()

    total_current_cost = Decimal('0')

    for bucket in bucket_data:
        if bucket['size_gb'] > 0:
            cost = calculate_monthly_cost(bucket['size_gb'], bucket['storage_class'])
            total_current_cost += cost

            print(f"Bucket: {bucket['name']}")
            print(f"  Size: {bucket['size_gb']:.2f} GB")
            print(f"  Storage Class: {bucket['storage_class']}")
            print(f"  Monthly Cost: {format_currency(cost)}")
            print()

    print_separator('-')
    print(f"TOTAL SIZE: {total_size:.2f} GB")
    print(f"TOTAL MONTHLY COST: {format_currency(total_current_cost)}")
    print(f"ESTIMATED YEARLY COST: {format_currency(total_current_cost * 12)}")
    print_separator('-')
    print()

    # Calculate savings with Glacier options
    if total_size > 0:
        print_separator()
        print("POTENTIAL SAVINGS WITH GLACIER STORAGE")
        print_separator()
        print()

        # Glacier Instant Retrieval
        print("GLACIER INSTANT RETRIEVAL")
        print("(Instant access, cheaper than Standard)")
        print_separator('-')

        glacier_ir_total_cost = Decimal('0')
        glacier_ir_total_savings = Decimal('0')

        for bucket in bucket_data:
            if bucket['size_gb'] > 0:
                calc = calculate_savings(bucket['size_gb'], bucket['storage_class'], 'GLACIER_IR')
                glacier_ir_total_cost += calc['target_cost']
                glacier_ir_total_savings += calc['savings']

                if calc['savings'] > 0:
                    print(f"{bucket['name']}:")
                    print(f"  Current: {format_currency(calc['current_cost'])}/mo ({bucket['storage_class']})")
                    print(f"  Glacier IR: {format_currency(calc['target_cost'])}/mo")
                    print(f"  Savings: {format_currency(calc['savings'])}/mo ({calc['savings_percent']:.1f}%)")
                    print()

        print_separator('-')
        print(f"Total Monthly Cost with Glacier IR: {format_currency(glacier_ir_total_cost)}")
        print(f"Total Monthly Savings: {format_currency(glacier_ir_total_savings)}")
        print(f"Total Yearly Savings: {format_currency(glacier_ir_total_savings * 12)}")
        print_separator('-')
        print()

        # Glacier Deep Archive
        print("GLACIER DEEP ARCHIVE")
        print("(12-hour retrieval, lowest cost)")
        print_separator('-')

        deep_archive_total_cost = Decimal('0')
        deep_archive_total_savings = Decimal('0')

        for bucket in bucket_data:
            if bucket['size_gb'] > 0:
                calc = calculate_savings(bucket['size_gb'], bucket['storage_class'], 'DEEP_ARCHIVE')
                deep_archive_total_cost += calc['target_cost']
                deep_archive_total_savings += calc['savings']

                if calc['savings'] > 0:
                    print(f"{bucket['name']}:")
                    print(f"  Current: {format_currency(calc['current_cost'])}/mo ({bucket['storage_class']})")
                    print(f"  Deep Archive: {format_currency(calc['target_cost'])}/mo")
                    print(f"  Savings: {format_currency(calc['savings'])}/mo ({calc['savings_percent']:.1f}%)")
                    print()

        print_separator('-')
        print(f"Total Monthly Cost with Deep Archive: {format_currency(deep_archive_total_cost)}")
        print(f"Total Monthly Savings: {format_currency(deep_archive_total_savings)}")
        print(f"Total Yearly Savings: {format_currency(deep_archive_total_savings * 12)}")
        print_separator('-')
        print()

        # Summary comparison
        print_separator()
        print("STORAGE CLASS COMPARISON SUMMARY")
        print_separator()
        print()
        print(f"{'Storage Class':<30} {'Monthly Cost':<15} {'Yearly Cost':<15} {'Yearly Savings'}")
        print_separator('-')
        print(f"{'Current (Mixed)':<30} {format_currency(total_current_cost):<15} {format_currency(total_current_cost * 12):<15} {'baseline'}")
        print(f"{'Glacier Instant Retrieval':<30} {format_currency(glacier_ir_total_cost):<15} {format_currency(glacier_ir_total_cost * 12):<15} {format_currency(glacier_ir_total_savings * 12)}")
        print(f"{'Glacier Deep Archive':<30} {format_currency(deep_archive_total_cost):<15} {format_currency(deep_archive_total_cost * 12):<15} {format_currency(deep_archive_total_savings * 12)}")
        print_separator('-')
        print()

        print("NOTE: This analysis assumes all data could be moved to Glacier.")
        print("Consider access patterns and retrieval costs when planning migration.")
        print("Glacier IR: Instant access, ideal for archives accessed quarterly")
        print("Deep Archive: 12-hour retrieval, ideal for long-term archives")
        print()
        print("Pricing based on us-east-1 region. Update PRICING dict for your region.")
        print_separator()


if __name__ == '__main__':
    main()
