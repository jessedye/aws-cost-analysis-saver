#!/usr/bin/env python3
"""
AWS Cost Analysis Orchestrator
Runs all cost analysis scripts and generates a comprehensive report card.
"""

import subprocess
import sys
import os
import json
import re
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Tuple
from decimal import Decimal
from concurrent.futures import ThreadPoolExecutor, as_completed
from html_report_generator import generate_html_report

# Script configurations
ANALYZERS = [
    {
        'name': 'EC2 Snapshots',
        'script': 'ec2_snapshot_analyzer.py',
        'category': 'Storage',
        'enabled': True
    },
    {
        'name': 'S3 Buckets',
        'script': 's3_cost_analyzer.py',
        'category': 'Storage',
        'enabled': True
    },
    {
        'name': 'EBS Volumes',
        'script': 'ebs_volume_analyzer.py',
        'category': 'Storage',
        'enabled': True
    },
    {
        'name': 'Elastic IPs',
        'script': 'elastic_ip_analyzer.py',
        'category': 'Network',
        'enabled': True
    },
    {
        'name': 'Reserved Instances',
        'script': 'reserved_instance_analyzer.py',
        'category': 'Compute',
        'enabled': True
    },
    {
        'name': 'RDS Instances',
        'script': 'rds_cost_analyzer.py',
        'category': 'Database',
        'enabled': True
    },
    {
        'name': 'Savings Plans',
        'script': 'compute_savings_plan_analyzer.py',
        'category': 'Compute',
        'enabled': True
    },
    {
        'name': 'Lambda Functions',
        'script': 'lambda_cost_analyzer.py',
        'category': 'Compute',
        'enabled': True
    },
    {
        'name': 'NAT Gateways',
        'script': 'nat_gateway_analyzer.py',
        'category': 'Network',
        'enabled': True
    },
    {
        'name': 'Load Balancers',
        'script': 'load_balancer_analyzer.py',
        'category': 'Network',
        'enabled': True
    },
    {
        'name': 'CloudWatch Logs',
        'script': 'cloudwatch_logs_analyzer.py',
        'category': 'Monitoring',
        'enabled': True
    }
]

# Report output directory
REPORTS_DIR = 'cost_reports'


def get_actual_aws_costs() -> Tuple[float, float]:
    """Get actual AWS costs from Cost Explorer API."""
    try:
        # Get current month-to-date costs
        today = datetime.now()
        start_of_month = today.replace(day=1).strftime('%Y-%m-%d')
        end_of_month = (today + timedelta(days=1)).strftime('%Y-%m-%d')

        result = subprocess.run(
            [
                'aws', 'ce', 'get-cost-and-usage',
                '--time-period', f'Start={start_of_month},End={end_of_month}',
                '--granularity', 'MONTHLY',
                '--metrics', 'UnblendedCost',
                '--output', 'json'
            ],
            capture_output=True,
            text=True,
            timeout=30
        )

        if result.returncode == 0:
            data = json.loads(result.stdout)
            if data.get('ResultsByTime'):
                mtd_cost = float(data['ResultsByTime'][0]['Total']['UnblendedCost']['Amount'])

                # Project monthly cost based on days elapsed
                days_in_month = (today.replace(month=today.month % 12 + 1, day=1) - timedelta(days=1)).day if today.month != 12 else 31
                if today.month == 12:
                    days_in_month = 31
                else:
                    next_month = today.replace(month=today.month + 1, day=1)
                    days_in_month = (next_month - timedelta(days=1)).day

                day_of_month = today.day
                projected_monthly = (mtd_cost / day_of_month) * days_in_month if day_of_month > 0 else mtd_cost
                projected_yearly = projected_monthly * 12

                return projected_monthly, projected_yearly

        # If Cost Explorer fails, return None to fall back to old method
        return None, None

    except Exception as e:
        print(f"Warning: Could not fetch actual AWS costs from Cost Explorer: {e}")
        return None, None


def print_separator(char='=', length=80):
    """Print a separator line."""
    print(char * length)


def print_banner():
    """Print startup banner."""
    print_separator()
    print("AWS COST ANALYSIS - FULL REPORT")
    print_separator()
    print()
    print(f"Analysis Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Report Directory: {REPORTS_DIR}/")
    print()
    print_separator('-')
    print()


def create_reports_directory() -> Path:
    """Create timestamped reports directory."""
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    reports_path = Path(REPORTS_DIR) / timestamp
    reports_path.mkdir(parents=True, exist_ok=True)

    # Also create a 'latest' symlink
    latest_path = Path(REPORTS_DIR) / 'latest'
    if latest_path.exists() or latest_path.is_symlink():
        latest_path.unlink()

    try:
        latest_path.symlink_to(timestamp, target_is_directory=True)
    except Exception:
        pass  # Symlinks might fail on some systems

    return reports_path


def run_analyzer(script: str, output_file: Path) -> Tuple[bool, str, str]:
    """Run an analyzer script and capture output."""
    script_path = Path(__file__).parent / script

    if not script_path.exists():
        return False, "", f"Script not found: {script}"

    try:
        result = subprocess.run(
            ['python3', str(script_path)],
            capture_output=True,
            text=True,
            timeout=300  # 5 minute timeout
        )

        output = result.stdout

        # Save detailed output to file
        with open(output_file, 'w') as f:
            f.write(output)
            if result.stderr:
                f.write("\n\nERRORS/WARNINGS:\n")
                f.write(result.stderr)

        return True, output, ""

    except subprocess.TimeoutExpired:
        return False, "", "Script timed out (>5 minutes)"
    except Exception as e:
        return False, "", str(e)


def extract_savings_from_output(output: str) -> Dict:
    """Extract cost savings information from analyzer output."""
    savings_data = {
        'monthly_savings': None,
        'yearly_savings': None,
        'current_monthly_cost': None,
        'current_yearly_cost': None,
        'found_issues': False
    }

    # Common patterns for savings
    patterns = {
        'monthly_savings': [
            r'Monthly Savings:\s*\$([0-9,.]+)',
            r'Monthly waste:\s*\$([0-9,.]+)',
            r'Total Monthly Savings:\s*\$([0-9,.]+)',
        ],
        'yearly_savings': [
            r'Yearly Savings:\s*\$([0-9,.]+)',
            r'Yearly waste:\s*\$([0-9,.]+)',
            r'Total Yearly Savings:\s*\$([0-9,.]+)',
            r'TOTAL POTENTIAL YEARLY SAVINGS:\s*\$([0-9,.]+)',
        ],
        'monthly_cost': [
            r'TOTAL MONTHLY COST:\s*\$([0-9,.]+)',
            r'Total Monthly Cost:\s*\$([0-9,.]+)',
        ],
        'yearly_cost': [
            r'TOTAL YEARLY COST:\s*\$([0-9,.]+)',
            r'Total Yearly Cost:\s*\$([0-9,.]+)',
            r'ESTIMATED YEARLY COST:\s*\$([0-9,.]+)',
        ]
    }

    # Try to extract monthly savings
    for pattern in patterns['monthly_savings']:
        match = re.search(pattern, output, re.IGNORECASE | re.MULTILINE)
        if match:
            try:
                savings_data['monthly_savings'] = float(match.group(1).replace(',', ''))
                savings_data['found_issues'] = True
                break
            except ValueError:
                pass

    # Try to extract yearly savings
    for pattern in patterns['yearly_savings']:
        match = re.search(pattern, output, re.IGNORECASE | re.MULTILINE)
        if match:
            try:
                savings_data['yearly_savings'] = float(match.group(1).replace(',', ''))
                savings_data['found_issues'] = True
                break
            except ValueError:
                pass

    # Try to extract current monthly cost
    for pattern in patterns['monthly_cost']:
        match = re.search(pattern, output, re.IGNORECASE | re.MULTILINE)
        if match:
            try:
                savings_data['current_monthly_cost'] = float(match.group(1).replace(',', ''))
                break
            except ValueError:
                pass

    # Try to extract current yearly cost
    for pattern in patterns['yearly_cost']:
        match = re.search(pattern, output, re.IGNORECASE | re.MULTILINE)
        if match:
            try:
                savings_data['current_yearly_cost'] = float(match.group(1).replace(',', ''))
                break
            except ValueError:
                pass

    # If we have monthly savings but not yearly, calculate it
    if savings_data['monthly_savings'] and not savings_data['yearly_savings']:
        savings_data['yearly_savings'] = savings_data['monthly_savings'] * 12

    # If we have yearly savings but not monthly, calculate it
    if savings_data['yearly_savings'] and not savings_data['monthly_savings']:
        savings_data['monthly_savings'] = savings_data['yearly_savings'] / 12

    # If we have monthly cost but not yearly, calculate it
    if savings_data['current_monthly_cost'] and not savings_data['current_yearly_cost']:
        savings_data['current_yearly_cost'] = savings_data['current_monthly_cost'] * 12

    # Check for optimization messages
    if any(keyword in output.lower() for keyword in [
        'no optimization', 'no savings', 'well-managed', 'excellent',
        'no old snapshots', 'no unattached', 'no rds instances found'
    ]):
        savings_data['found_issues'] = False

    return savings_data


def generate_summary_report(results: List[Dict], reports_path: Path, total_current_monthly: float, total_current_yearly: float):
    """Generate summary report card."""
    summary_file = reports_path / 'SUMMARY_REPORT_CARD.txt'

    total_monthly_savings = 0.0
    total_yearly_savings = 0.0

    successful_analyses = []
    failed_analyses = []

    for result in results:
        if result['success']:
            successful_analyses.append(result)
            savings = result['savings']
            if savings['monthly_savings']:
                total_monthly_savings += savings['monthly_savings']
            if savings['yearly_savings']:
                total_yearly_savings += savings['yearly_savings']
        else:
            failed_analyses.append(result)

    with open(summary_file, 'w') as f:
        f.write("=" * 80 + "\n")
        f.write("AWS COST OPTIMIZATION REPORT CARD\n")
        f.write("=" * 80 + "\n")
        f.write(f"\nGenerated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"Report Location: {reports_path}\n\n")
        f.write("=" * 80 + "\n\n")

        # Executive Summary
        f.write("EXECUTIVE SUMMARY\n")
        f.write("-" * 80 + "\n\n")
        f.write(f"Total Analyses Run: {len(results)}\n")
        f.write(f"  Successful: {len(successful_analyses)}\n")
        f.write(f"  Failed: {len(failed_analyses)}\n\n")

        if total_current_monthly > 0:
            f.write(f"Current Monthly Spend (from Cost Explorer): ${total_current_monthly:,.2f}\n")
            f.write(f"Current Yearly Spend (projected): ${total_current_yearly:,.2f}\n\n")
        else:
            f.write(f"NOTE: Could not retrieve actual AWS costs from Cost Explorer API.\n")
            f.write(f"      Percentage savings cannot be calculated.\n\n")

        f.write(f"TOTAL POTENTIAL SAVINGS:\n")
        f.write(f"  Monthly: ${total_monthly_savings:,.2f}\n")
        f.write(f"  Yearly: ${total_yearly_savings:,.2f}\n\n")

        if total_current_yearly > 0 and total_yearly_savings > 0:
            savings_percent = (total_yearly_savings / total_current_yearly) * 100
            f.write(f"Potential Cost Reduction: {savings_percent:.1f}%\n\n")

        f.write("=" * 80 + "\n\n")

        # Breakdown by Category
        f.write("SAVINGS BREAKDOWN BY CATEGORY\n")
        f.write("-" * 80 + "\n\n")

        # Group by category
        categories = {}
        for result in successful_analyses:
            category = result['category']
            if category not in categories:
                categories[category] = []
            categories[category].append(result)

        for category, items in sorted(categories.items()):
            category_monthly = sum(r['savings']['monthly_savings'] or 0 for r in items)
            category_yearly = sum(r['savings']['yearly_savings'] or 0 for r in items)

            f.write(f"{category}:\n")
            for result in items:
                savings = result['savings']
                monthly = savings['monthly_savings'] or 0
                yearly = savings['yearly_savings'] or 0
                status = "✓" if savings['found_issues'] else "✓ (Optimized)"

                f.write(f"  {status} {result['name']:<25} ")
                f.write(f"Monthly: ${monthly:>8,.2f}  Yearly: ${yearly:>10,.2f}\n")

            f.write(f"  {'-' * 76}\n")
            f.write(f"  Category Total: {' ' * 17}")
            f.write(f"Monthly: ${category_monthly:>8,.2f}  Yearly: ${category_yearly:>10,.2f}\n\n")

        f.write("=" * 80 + "\n\n")

        # Detailed Analysis Summary
        f.write("DETAILED ANALYSIS SUMMARY\n")
        f.write("-" * 80 + "\n\n")

        for result in successful_analyses:
            f.write(f"{result['name']} ({result['category']})\n")
            f.write(f"  Report: {result['report_file']}\n")

            savings = result['savings']
            if savings['current_monthly_cost']:
                f.write(f"  Current Cost: ${savings['current_monthly_cost']:,.2f}/month\n")
            if savings['monthly_savings']:
                f.write(f"  Potential Savings: ${savings['monthly_savings']:,.2f}/month")
                f.write(f" (${savings['yearly_savings']:,.2f}/year)\n")
            else:
                f.write(f"  Status: Already optimized\n")

            f.write("\n")

        # Failed Analyses
        if failed_analyses:
            f.write("=" * 80 + "\n\n")
            f.write("FAILED ANALYSES\n")
            f.write("-" * 80 + "\n\n")

            for result in failed_analyses:
                f.write(f"{result['name']}: {result['error']}\n")

            f.write("\n")

        # Recommendations
        f.write("=" * 80 + "\n\n")
        f.write("TOP RECOMMENDATIONS\n")
        f.write("-" * 80 + "\n\n")

        # Sort by savings
        sorted_results = sorted(
            [r for r in successful_analyses if r['savings']['yearly_savings']],
            key=lambda x: x['savings']['yearly_savings'] or 0,
            reverse=True
        )

        if sorted_results:
            f.write("Priority order by potential savings:\n\n")
            for i, result in enumerate(sorted_results[:5], 1):
                yearly = result['savings']['yearly_savings'] or 0
                f.write(f"{i}. {result['name']}: ${yearly:,.2f}/year potential savings\n")
                f.write(f"   See detailed report: {result['report_file']}\n\n")
        else:
            f.write("Great job! All analyzed resources are already optimized.\n")
            f.write("Continue monitoring for new optimization opportunities.\n\n")

        f.write("=" * 80 + "\n\n")
        f.write("NEXT STEPS\n")
        f.write("-" * 80 + "\n\n")
        f.write("1. Review detailed reports in this directory\n")
        f.write("2. Prioritize high-value optimizations\n")
        f.write("3. Validate recommendations with your team\n")
        f.write("4. Implement changes in a test environment first\n")
        f.write("5. Schedule regular cost analysis reviews\n\n")
        f.write("NOTE: All scripts are read-only and make no changes to your AWS resources.\n")
        f.write("=" * 80 + "\n")

    return summary_file


def run_analyzer_with_timing(analyzer: Dict, reports_path: Path) -> Tuple[Dict, float]:
    """Run a single analyzer and return results with timing."""
    start_time = time.time()

    # Generate report filename
    report_file = reports_path / f"{analyzer['script'].replace('.py', '')}_report.txt"

    # Run the analyzer
    success, output, error = run_analyzer(analyzer['script'], report_file)

    elapsed = time.time() - start_time

    if success:
        # Extract savings information
        savings = extract_savings_from_output(output)

        result = {
            'name': analyzer['name'],
            'category': analyzer['category'],
            'script': analyzer['script'],
            'success': True,
            'report_file': report_file.name,
            'savings': savings,
            'elapsed': elapsed
        }
    else:
        result = {
            'name': analyzer['name'],
            'category': analyzer['category'],
            'script': analyzer['script'],
            'success': False,
            'error': error,
            'elapsed': elapsed
        }

    return result, elapsed


def main():
    """Main function."""
    print_banner()

    # Create reports directory
    print("Creating reports directory...")
    reports_path = create_reports_directory()
    print(f"Reports will be saved to: {reports_path}\n")
    print_separator('-')
    print()

    # Count enabled analyzers
    enabled_analyzers = [a for a in ANALYZERS if a.get('enabled', True)]
    print(f"Running {len(enabled_analyzers)} analyzers in parallel...\n")

    # Run all analyzers in parallel
    results = []
    total_start_time = time.time()

    with ThreadPoolExecutor(max_workers=min(len(enabled_analyzers), 10)) as executor:
        # Submit all analyzer tasks
        future_to_analyzer = {
            executor.submit(run_analyzer_with_timing, analyzer, reports_path): analyzer
            for analyzer in enabled_analyzers
        }

        # Process results as they complete
        for future in as_completed(future_to_analyzer):
            analyzer = future_to_analyzer[future]
            try:
                result, elapsed = future.result()
                results.append(result)

                # Print result
                if result['success']:
                    print(f"✓ {result['name']} - {elapsed:.1f}s")
                    if result['savings']['yearly_savings']:
                        print(f"  → Potential Savings: ${result['savings']['yearly_savings']:,.2f}/year")
                    else:
                        print(f"  → Status: Already optimized")
                else:
                    print(f"✗ {result['name']} - {elapsed:.1f}s")
                    print(f"  → Failed: {result['error']}")

            except Exception as exc:
                print(f"✗ {analyzer['name']} generated an exception: {exc}")
                results.append({
                    'name': analyzer['name'],
                    'category': analyzer['category'],
                    'script': analyzer['script'],
                    'success': False,
                    'error': str(exc)
                })

    total_elapsed = time.time() - total_start_time

    # Calculate estimated sequential time
    total_analyzer_time = sum(r.get('elapsed', 0) for r in results)
    speedup = total_analyzer_time / total_elapsed if total_elapsed > 0 else 1

    print()
    print_separator('-')
    print()
    print(f"⚡ Performance Statistics:")
    print(f"  Total wall time (parallel): {total_elapsed:.1f}s")
    print(f"  Total analyzer time (if sequential): {total_analyzer_time:.1f}s")
    print(f"  Speedup: {speedup:.1f}x faster")
    print(f"  Time saved: {total_analyzer_time - total_elapsed:.1f}s")
    print()
    print_separator('-')
    print()

    # Calculate totals for reports
    total_monthly = sum(r['savings']['monthly_savings'] or 0
                       for r in results if r['success'])
    total_yearly = sum(r['savings']['yearly_savings'] or 0
                      for r in results if r['success'])

    # Get actual AWS costs from Cost Explorer instead of summing individual analyzer costs
    print("Fetching actual AWS costs from Cost Explorer...")
    actual_monthly, actual_yearly = get_actual_aws_costs()

    if actual_monthly is not None:
        total_current_monthly = actual_monthly
        total_current_yearly = actual_yearly
        print(f"✓ Actual AWS costs retrieved: ${actual_monthly:,.2f}/month (${actual_yearly:,.2f}/year)")
    else:
        # Fallback: Don't sum individual costs as they can be misleading
        # Instead, set to 0 and note that Cost Explorer data is unavailable
        total_current_monthly = 0
        total_current_yearly = 0
        print("⚠ Could not retrieve actual AWS costs from Cost Explorer")
        print("  (Individual analyzer costs are not summed as they may overlap)")

    print()

    # Generate summary report
    print("Generating summary report card...")
    summary_file = generate_summary_report(results, reports_path, total_current_monthly, total_current_yearly)
    print(f"✓ Summary report saved to: {summary_file.name}\n")

    # Generate HTML report
    print("Generating HTML report...")
    html_file, json_file = generate_html_report(
        results,
        reports_path,
        total_monthly,
        total_yearly,
        total_current_monthly,
        total_current_yearly
    )
    print(f"✓ HTML report saved to: {html_file.name}")
    print(f"✓ JSON data saved to: {json_file.name}\n")

    # Display summary on console
    print_separator()
    print("QUICK SUMMARY")
    print_separator()
    print()

    print(f"Total Potential Savings:")
    print(f"  Monthly: ${total_monthly:,.2f}")
    print(f"  Yearly: ${total_yearly:,.2f}")
    print()

    if total_current_yearly > 0:
        print(f"Current Annual Spend: ${total_current_yearly:,.2f}")
        print(f"Potential Cost Reduction: {(total_yearly / total_current_yearly * 100):.1f}%")
        print()

    successful = sum(1 for r in results if r['success'])
    failed = sum(1 for r in results if not r['success'])

    print(f"Analyses: {successful} successful, {failed} failed")
    print()
    print_separator('-')
    print()
    print(f"📊 Full reports available at: {reports_path}/")
    print(f"📄 HTML Report (open in browser): {html_file}")
    print(f"📄 Text Summary: {summary_file}")
    print(f"📄 JSON Data: {json_file}")
    print()
    print("To view HTML report:")
    print(f"  open {html_file}")
    print(f"  # or: firefox {html_file}")
    print(f"  # or: google-chrome {html_file}")
    print()
    print_separator()


if __name__ == '__main__':
    main()
