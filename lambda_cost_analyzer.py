#!/usr/bin/env python3
"""
Lambda Cost Analyzer
Analyzes Lambda function usage, memory allocation, and potential cost savings.
READ-ONLY - Makes no changes to AWS resources.
"""

import subprocess
import json
import sys
from typing import Dict, List, Tuple
from decimal import Decimal
from datetime import datetime, timedelta

# AWS Lambda Pricing (USD) - us-east-1 region
PRICE_PER_GB_SECOND = Decimal('0.0000166667')  # Per GB-second
PRICE_PER_MILLION_REQUESTS = Decimal('0.20')  # Per 1M requests
FREE_TIER_GB_SECONDS = 400000  # Per month
FREE_TIER_REQUESTS = 1000000  # Per month


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


def get_all_lambda_functions() -> List[Dict]:
    """Get list of all Lambda functions."""
    print("Fetching all Lambda functions...")
    success, output = run_command([
        'aws', 'lambda', 'list-functions',
        '--output', 'json'
    ])

    if not success:
        print(f"Error getting Lambda functions: {output}")
        return []

    try:
        data = json.loads(output) if output.strip() else {}
        functions = data.get('Functions', [])

        function_list = []
        for func in functions:
            function_list.append({
                'name': func.get('FunctionName', ''),
                'memory_mb': func.get('MemorySize', 128),
                'runtime': func.get('Runtime', 'unknown'),
                'timeout': func.get('Timeout', 3),
                'code_size': func.get('CodeSize', 0),
                'last_modified': func.get('LastModified', '')
            })

        return function_list

    except json.JSONDecodeError:
        print("Error parsing Lambda functions data")
        return []


def get_function_metrics(function_name: str) -> Dict:
    """Get CloudWatch metrics for a Lambda function (last 30 days)."""
    end_time = datetime.utcnow()
    start_time = end_time - timedelta(days=30)

    metrics = {
        'invocations': 0,
        'duration_avg': 0,
        'errors': 0
    }

    # Get invocations
    success, output = run_command([
        'aws', 'cloudwatch', 'get-metric-statistics',
        '--namespace', 'AWS/Lambda',
        '--metric-name', 'Invocations',
        '--dimensions', f'Name=FunctionName,Value={function_name}',
        '--start-time', start_time.isoformat(),
        '--end-time', end_time.isoformat(),
        '--period', '2592000',  # 30 days
        '--statistics', 'Sum',
        '--output', 'json'
    ])

    if success:
        try:
            data = json.loads(output)
            datapoints = data.get('Datapoints', [])
            if datapoints:
                metrics['invocations'] = int(datapoints[0].get('Sum', 0))
        except:
            pass

    # Get average duration
    success, output = run_command([
        'aws', 'cloudwatch', 'get-metric-statistics',
        '--namespace', 'AWS/Lambda',
        '--metric-name', 'Duration',
        '--dimensions', f'Name=FunctionName,Value={function_name}',
        '--start-time', start_time.isoformat(),
        '--end-time', end_time.isoformat(),
        '--period', '2592000',
        '--statistics', 'Average',
        '--output', 'json'
    ])

    if success:
        try:
            data = json.loads(output)
            datapoints = data.get('Datapoints', [])
            if datapoints:
                metrics['duration_avg'] = float(datapoints[0].get('Average', 0))
        except:
            pass

    # Get errors
    success, output = run_command([
        'aws', 'cloudwatch', 'get-metric-statistics',
        '--namespace', 'AWS/Lambda',
        '--metric-name', 'Errors',
        '--dimensions', f'Name=FunctionName,Value={function_name}',
        '--start-time', start_time.isoformat(),
        '--end-time', end_time.isoformat(),
        '--period', '2592000',
        '--statistics', 'Sum',
        '--output', 'json'
    ])

    if success:
        try:
            data = json.loads(output)
            datapoints = data.get('Datapoints', [])
            if datapoints:
                metrics['errors'] = int(datapoints[0].get('Sum', 0))
        except:
            pass

    return metrics


def calculate_lambda_cost(memory_mb: int, duration_ms: float, invocations: int) -> Decimal:
    """Calculate Lambda cost based on memory, duration, and invocations."""
    memory_gb = Decimal(memory_mb) / Decimal('1024')
    duration_seconds = Decimal(duration_ms) / Decimal('1000')

    # GB-seconds
    gb_seconds = memory_gb * duration_seconds * Decimal(invocations)

    # Apply free tier
    billable_gb_seconds = max(Decimal('0'), gb_seconds - Decimal(FREE_TIER_GB_SECONDS))

    # Compute cost
    compute_cost = billable_gb_seconds * PRICE_PER_GB_SECOND

    # Request cost
    billable_requests = max(0, invocations - FREE_TIER_REQUESTS)
    request_cost = Decimal(billable_requests) / Decimal('1000000') * PRICE_PER_MILLION_REQUESTS

    return compute_cost + request_cost


def format_currency(amount: Decimal) -> str:
    """Format decimal as currency."""
    return f"${amount:.2f}"


def print_separator(char='=', length=80):
    """Print a separator line."""
    print(char * length)


def main():
    """Main function."""
    print_separator()
    print("LAMBDA COST ANALYZER")
    print_separator()
    print()

    # Get all Lambda functions
    functions = get_all_lambda_functions()

    if not functions:
        print("No Lambda functions found or error accessing AWS.")
        print()
        print("TOTAL MONTHLY COST: $0.00")
        print("ESTIMATED YEARLY COST: $0.00")
        print()
        print("Monthly Savings: $0.00")
        print("Yearly Savings: $0.00")
        print_separator()
        sys.exit(0)

    print(f"Found {len(functions)} Lambda function(s)\n")
    print_separator('-')
    print()

    # Analyze each function
    function_analysis = []
    total_monthly_cost = Decimal('0')
    unused_functions = []
    over_provisioned = []

    for func in functions:
        print(f"Analyzing {func['name']}...", end='', flush=True)
        metrics = get_function_metrics(func['name'])

        # Calculate monthly cost (based on 30-day data)
        if metrics['invocations'] > 0:
            monthly_cost = calculate_lambda_cost(
                func['memory_mb'],
                metrics['duration_avg'],
                metrics['invocations']
            )
        else:
            monthly_cost = Decimal('0')

        total_monthly_cost += monthly_cost

        # Identify issues
        is_unused = metrics['invocations'] == 0
        is_over_provisioned = (metrics['duration_avg'] > 0 and
                              func['timeout'] * 1000 > metrics['duration_avg'] * 3)

        if is_unused:
            unused_functions.append(func)

        if is_over_provisioned and not is_unused:
            over_provisioned.append({
                'function': func,
                'metrics': metrics,
                'cost': monthly_cost
            })

        function_analysis.append({
            'function': func,
            'metrics': metrics,
            'cost': monthly_cost,
            'unused': is_unused,
            'over_provisioned': is_over_provisioned
        })

        print(f" {metrics['invocations']} invocations, {format_currency(monthly_cost)}/mo")

    print()
    print_separator('-')
    print()

    # Calculate costs
    print_separator()
    print("CURRENT COSTS")
    print_separator()
    print()
    print(f"Total Lambda Functions: {len(functions)}")
    print(f"TOTAL MONTHLY COST: {format_currency(total_monthly_cost)}")
    print(f"ESTIMATED YEARLY COST: {format_currency(total_monthly_cost * 12)}")
    print_separator('-')
    print()

    # Savings opportunities
    total_savings = Decimal('0')

    if unused_functions:
        print_separator()
        print("UNUSED FUNCTIONS (0 invocations in last 30 days)")
        print_separator()
        print()
        print(f"Found {len(unused_functions)} unused function(s)")
        print()
        for func in unused_functions:
            print(f"  • {func['name']}")
            print(f"    Last Modified: {func['last_modified']}")
        print()
        print("RECOMMENDATION: Review and consider deleting unused functions")
        print_separator('-')
        print()

    if over_provisioned:
        print_separator()
        print("OVER-PROVISIONED FUNCTIONS (Timeout > 3x Average Duration)")
        print_separator()
        print()
        print(f"Found {len(over_provisioned)} over-provisioned function(s)")
        print()
        for item in over_provisioned:
            func = item['function']
            metrics = item['metrics']
            avg_duration_sec = metrics['duration_avg'] / 1000
            print(f"  • {func['name']}")
            print(f"    Timeout: {func['timeout']}s, Avg Duration: {avg_duration_sec:.2f}s")
            print(f"    Consider reducing timeout to ~{int(avg_duration_sec * 2)}s")
        print()
        print("RECOMMENDATION: Reduce timeout settings for over-provisioned functions")
        print_separator('-')
        print()

    # Summary
    print_separator()
    print("SUMMARY")
    print_separator()
    print()

    if unused_functions or over_provisioned:
        print(f"Issues Found:")
        print(f"  Unused Functions: {len(unused_functions)}")
        print(f"  Over-provisioned Functions: {len(over_provisioned)}")
        print()
        print("POTENTIAL OPTIMIZATION:")
        print("  • Delete or archive unused functions")
        print("  • Right-size memory and timeout settings")
        print("  • Review and optimize cold start times")
        print()

        # Conservative savings estimate (5-10% from optimization)
        estimated_savings = total_monthly_cost * Decimal('0.05')
        total_savings = estimated_savings

        print(f"Monthly Savings: {format_currency(estimated_savings)}")
        print(f"Yearly Savings: {format_currency(estimated_savings * 12)}")
    else:
        print("✓ All Lambda functions appear to be well-optimized")
        print("  No unused or significantly over-provisioned functions found")
        print()
        print("Monthly Savings: $0.00")
        print("Yearly Savings: $0.00")

    print()
    print("NOTE: Lambda costs are often low due to pay-per-use model and free tier.")
    print("Focus on high-invocation functions for maximum savings impact.")
    print_separator()


if __name__ == '__main__':
    main()
