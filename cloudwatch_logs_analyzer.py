#!/usr/bin/env python3
"""
CloudWatch Logs Cost Analyzer
Analyzes CloudWatch Log Groups for retention and storage optimization opportunities.
READ-ONLY - Makes no changes to AWS resources.
"""

import subprocess
import json
import sys
from typing import Dict, List, Tuple
from decimal import Decimal
from datetime import datetime

# AWS CloudWatch Logs Pricing (USD) - us-east-1 region
LOGS_INGESTION_PER_GB = Decimal('0.50')  # Data ingestion
LOGS_STORAGE_PER_GB = Decimal('0.03')  # Per GB/month
LOGS_ARCHIVE_PER_GB = Decimal('0.03')  # Archived logs


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


def get_all_log_groups() -> List[Dict]:
    """Get list of all CloudWatch Log Groups."""
    print("Fetching all CloudWatch Log Groups...")

    all_log_groups = []
    next_token = None

    while True:
        cmd = ['aws', 'logs', 'describe-log-groups', '--output', 'json']
        if next_token:
            cmd.extend(['--starting-token', next_token])

        success, output = run_command(cmd)

        if not success:
            print(f"Error getting log groups: {output}")
            break

        try:
            data = json.loads(output) if output.strip() else {}
            log_groups = data.get('logGroups', [])

            for lg in log_groups:
                all_log_groups.append({
                    'name': lg.get('logGroupName', ''),
                    'arn': lg.get('arn', ''),
                    'created': lg.get('creationTime', 0),
                    'retention': lg.get('retentionInDays', None),  # None means "Never expire"
                    'stored_bytes': lg.get('storedBytes', 0),
                    'metric_filter_count': lg.get('metricFilterCount', 0)
                })

            next_token = data.get('nextToken')
            if not next_token:
                break

        except json.JSONDecodeError:
            print("Error parsing log groups data")
            break

    return all_log_groups


def calculate_log_storage_cost(stored_bytes: int) -> Decimal:
    """Calculate monthly storage cost for logs."""
    stored_gb = Decimal(stored_bytes) / Decimal('1073741824')
    return stored_gb * LOGS_STORAGE_PER_GB


def calculate_savings_with_retention(stored_bytes: int, current_retention: int, new_retention: int) -> Decimal:
    """Calculate savings if retention is reduced."""
    if current_retention is None or current_retention == 0:
        # Assume logs grow linearly, reducing retention reduces storage proportionally
        reduction_factor = Decimal(new_retention) / Decimal('365')  # Assume 1 year of data currently
    else:
        reduction_factor = Decimal(new_retention) / Decimal(current_retention)

    current_cost = calculate_log_storage_cost(stored_bytes)
    new_cost = current_cost * reduction_factor
    return current_cost - new_cost


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
    print("CLOUDWATCH LOGS COST ANALYZER")
    print_separator()
    print()

    # Get all log groups
    log_groups = get_all_log_groups()

    if not log_groups:
        print("No CloudWatch Log Groups found or error accessing AWS.")
        print()
        print("TOTAL MONTHLY COST: $0.00")
        print("ESTIMATED YEARLY COST: $0.00")
        print()
        print("Monthly Savings: $0.00")
        print("Yearly Savings: $0.00")
        print_separator()
        sys.exit(0)

    print(f"Found {len(log_groups)} Log Group(s)\n")
    print_separator('-')
    print()

    # Analyze log groups
    total_stored_bytes = 0
    total_monthly_cost = Decimal('0')
    never_expire_groups = []
    long_retention_groups = []
    large_log_groups = []

    for lg in log_groups:
        stored_bytes = lg['stored_bytes']
        total_stored_bytes += stored_bytes

        cost = calculate_log_storage_cost(stored_bytes)
        total_monthly_cost += cost

        # Identify issues
        retention = lg['retention']
        stored_gb = stored_bytes / (1024**3)

        if retention is None:
            never_expire_groups.append({
                'lg': lg,
                'cost': cost
            })

        if retention and retention > 365:  # More than 1 year
            long_retention_groups.append({
                'lg': lg,
                'cost': cost
            })

        if stored_gb > 10:  # More than 10GB
            large_log_groups.append({
                'lg': lg,
                'cost': cost
            })

    print_separator()
    print("CURRENT COSTS")
    print_separator()
    print()
    print(f"Total Log Groups: {len(log_groups)}")
    print(f"Total Storage: {format_bytes(total_stored_bytes)}")
    print(f"TOTAL MONTHLY COST: {format_currency(total_monthly_cost)}")
    print(f"ESTIMATED YEARLY COST: {format_currency(total_monthly_cost * 12)}")
    print_separator('-')
    print()

    # Savings opportunities
    total_savings = Decimal('0')

    if never_expire_groups:
        print_separator()
        print("LOG GROUPS WITH NO RETENTION POLICY (Never Expire)")
        print_separator()
        print()
        print(f"Found {len(never_expire_groups)} log group(s) with indefinite retention")
        print()

        never_expire_savings = Decimal('0')
        for item in sorted(never_expire_groups, key=lambda x: x['lg']['stored_bytes'], reverse=True)[:10]:
            lg = item['lg']
            cost = item['cost']
            # Estimate savings if reduced to 90 days retention
            potential_savings = calculate_savings_with_retention(lg['stored_bytes'], None, 90)
            never_expire_savings += potential_savings

            print(f"  • {lg['name']}")
            print(f"    Storage: {format_bytes(lg['stored_bytes'])}")
            print(f"    Current Cost: {format_currency(cost)}/month")
            print(f"    Potential Savings (90-day retention): {format_currency(potential_savings)}/month")
            print()

        if len(never_expire_groups) > 10:
            print(f"  ... and {len(never_expire_groups) - 10} more")
            print()

        total_savings += never_expire_savings
        print(f"Potential Monthly Savings: {format_currency(never_expire_savings)}")
        print(f"Potential Yearly Savings: {format_currency(never_expire_savings * 12)}")
        print()
        print("RECOMMENDATION: Set retention policies on log groups (30, 60, 90 days)")
        print_separator('-')
        print()

    if long_retention_groups:
        print_separator()
        print("LOG GROUPS WITH LONG RETENTION (>365 days)")
        print_separator()
        print()
        print(f"Found {len(long_retention_groups)} log group(s) with retention >1 year")
        print()

        for item in sorted(long_retention_groups, key=lambda x: x['lg']['stored_bytes'], reverse=True)[:5]:
            lg = item['lg']
            print(f"  • {lg['name']}")
            print(f"    Retention: {lg['retention']} days")
            print(f"    Storage: {format_bytes(lg['stored_bytes'])}")
            print()

        print("RECOMMENDATION: Review if long retention is necessary")
        print("                Consider exporting old logs to S3 (cheaper)")
        print_separator('-')
        print()

    if large_log_groups:
        print_separator()
        print("LARGE LOG GROUPS (>10 GB)")
        print_separator()
        print()
        print(f"Found {len(large_log_groups)} log group(s) with >10GB storage")
        print()

        for item in sorted(large_log_groups, key=lambda x: x['lg']['stored_bytes'], reverse=True)[:10]:
            lg = item['lg']
            cost = item['cost']
            print(f"  • {lg['name']}")
            print(f"    Storage: {format_bytes(lg['stored_bytes'])}")
            print(f"    Retention: {lg['retention'] if lg['retention'] else 'Never expire'} days")
            print(f"    Monthly Cost: {format_currency(cost)}")
            print()

        print("RECOMMENDATION: Export large log groups to S3 for long-term storage")
        print("                S3 storage is ~$0.023/GB vs CloudWatch $0.03/GB")
        print_separator('-')
        print()

    # Summary
    print_separator()
    print("SUMMARY")
    print_separator()
    print()

    if total_savings > 0:
        print(f"Potential Savings from Retention Optimization:")
        print(f"  Monthly Savings: {format_currency(total_savings)}")
        print(f"  Yearly Savings: {format_currency(total_savings * 12)}")
    else:
        print("✓ Log retention policies appear well-configured")
        print()
        print("Monthly Savings: $0.00")
        print("Yearly Savings: $0.00")

    print()
    print("NOTE: CloudWatch Logs charges for ingestion and storage.")
    print("      Set appropriate retention policies to control costs.")
    print("      Export old logs to S3 for cheaper long-term storage.")
    print_separator()


if __name__ == '__main__':
    main()
