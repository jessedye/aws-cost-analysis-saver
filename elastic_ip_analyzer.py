#!/usr/bin/env python3
"""
Elastic IP Analyzer
Identifies unattached Elastic IPs that are costing money and could be released.
"""

import subprocess
import json
import sys
from typing import Dict, List, Tuple
from decimal import Decimal

# AWS Elastic IP Pricing (USD per hour for unattached IPs)
# Attached IPs are free, unattached IPs are charged
UNATTACHED_EIP_HOURLY_COST = Decimal('0.005')  # $0.005 per hour in us-east-1

# Additional IP cost (for instances with multiple IPs)
ADDITIONAL_IP_HOURLY_COST = Decimal('0.005')  # Same rate as unattached

# Hours per month for cost calculation
HOURS_PER_MONTH = 730
HOURS_PER_YEAR = 8760


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


def get_all_elastic_ips() -> List[Dict]:
    """Get list of all Elastic IPs."""
    print("Fetching all Elastic IP addresses...")

    success, output = run_command([
        'aws', 'ec2', 'describe-addresses',
        '--query', 'Addresses[].[PublicIp,AllocationId,InstanceId,AssociationId,NetworkInterfaceId,PrivateIpAddress,Tags]',
        '--output', 'json'
    ])

    if not success:
        print(f"Error getting Elastic IPs: {output}")
        return []

    try:
        eip_data = json.loads(output) if output.strip() else []
        if eip_data is None:
            eip_data = []

        elastic_ips = []
        for eip in eip_data:
            if eip and len(eip) >= 2:
                public_ip = eip[0]
                allocation_id = eip[1]
                instance_id = eip[2] if len(eip) > 2 and eip[2] else None
                association_id = eip[3] if len(eip) > 3 and eip[3] else None
                network_interface_id = eip[4] if len(eip) > 4 and eip[4] else None
                private_ip = eip[5] if len(eip) > 5 and eip[5] else None
                tags = eip[6] if len(eip) > 6 and eip[6] else []

                # Extract Name tag
                name = "No Name"
                if tags:
                    for tag in tags:
                        if tag.get('Key') == 'Name':
                            name = tag.get('Value', 'No Name')
                            break

                # Determine if attached
                is_attached = instance_id is not None or network_interface_id is not None

                elastic_ips.append({
                    'public_ip': public_ip,
                    'allocation_id': allocation_id,
                    'instance_id': instance_id,
                    'association_id': association_id,
                    'network_interface_id': network_interface_id,
                    'private_ip': private_ip,
                    'is_attached': is_attached,
                    'name': name
                })

        return elastic_ips

    except json.JSONDecodeError:
        print("Error parsing Elastic IP data")
        return []


def get_instance_state(instance_id: str) -> str:
    """Get the state of an EC2 instance."""
    if not instance_id:
        return "N/A"

    success, output = run_command([
        'aws', 'ec2', 'describe-instances',
        '--instance-ids', instance_id,
        '--query', 'Reservations[0].Instances[0].State.Name',
        '--output', 'text'
    ])

    if success and output.strip():
        return output.strip()
    return "unknown"


def calculate_monthly_cost(is_attached: bool) -> Decimal:
    """Calculate monthly cost for an Elastic IP."""
    if not is_attached:
        return UNATTACHED_EIP_HOURLY_COST * HOURS_PER_MONTH
    return Decimal('0')


def format_currency(amount: Decimal) -> str:
    """Format decimal as currency."""
    return f"${amount:.2f}"


def print_separator(char='=', length=80):
    """Print a separator line."""
    print(char * length)


def main():
    """Main function."""
    print_separator()
    print("ELASTIC IP COST ANALYZER")
    print_separator()
    print()

    # Get all Elastic IPs
    elastic_ips = get_all_elastic_ips()

    if not elastic_ips:
        print("No Elastic IPs found or error accessing AWS.")
        print()
        print("This is actually good - you're not paying for any Elastic IPs!")
        print_separator()
        sys.exit(0)

    print(f"Found {len(elastic_ips)} Elastic IP(s)\n")

    # Get instance states for attached IPs
    print("Checking instance states...")
    for eip in elastic_ips:
        if eip['instance_id']:
            eip['instance_state'] = get_instance_state(eip['instance_id'])
        else:
            eip['instance_state'] = 'N/A'

    # Categorize Elastic IPs
    attached_running = [e for e in elastic_ips if e['is_attached'] and e.get('instance_state') == 'running']
    attached_stopped = [e for e in elastic_ips if e['is_attached'] and e.get('instance_state') == 'stopped']
    unattached = [e for e in elastic_ips if not e['is_attached']]

    print()
    print_separator()
    print("ELASTIC IP SUMMARY")
    print_separator()
    print()
    print(f"Total Elastic IPs: {len(elastic_ips)}")
    print(f"  Attached to Running Instances: {len(attached_running)} (FREE)")
    print(f"  Attached to Stopped Instances: {len(attached_stopped)} (CHARGED)")
    print(f"  Unattached: {len(unattached)} (CHARGED)")
    print()
    print_separator('-')
    print()

    # Calculate costs
    print_separator()
    print("CURRENT ELASTIC IP COSTS")
    print_separator()
    print()

    # Unattached IPs cost
    unattached_cost = len(unattached) * UNATTACHED_EIP_HOURLY_COST * HOURS_PER_MONTH

    # Attached to stopped instances also cost
    stopped_cost = len(attached_stopped) * UNATTACHED_EIP_HOURLY_COST * HOURS_PER_MONTH

    total_monthly_cost = unattached_cost + stopped_cost
    total_yearly_cost = total_monthly_cost * 12

    print(f"Unattached IPs ({len(unattached)}):")
    print(f"  Monthly Cost: {format_currency(unattached_cost)}")
    print(f"  Yearly Cost: {format_currency(unattached_cost * 12)}")
    print()

    if attached_stopped:
        print(f"IPs Attached to Stopped Instances ({len(attached_stopped)}):")
        print(f"  Monthly Cost: {format_currency(stopped_cost)}")
        print(f"  Yearly Cost: {format_currency(stopped_cost * 12)}")
        print()

    print_separator('-')
    print(f"TOTAL MONTHLY COST: {format_currency(total_monthly_cost)}")
    print(f"TOTAL YEARLY COST: {format_currency(total_yearly_cost)}")
    print_separator('-')
    print()

    # Show unattached IPs
    if unattached:
        print_separator()
        print("UNATTACHED ELASTIC IPs (IMMEDIATE SAVINGS OPPORTUNITY)")
        print_separator()
        print()
        print(f"These {len(unattached)} Elastic IP(s) are not attached to any instance")
        print(f"Monthly waste: {format_currency(unattached_cost)}")
        print(f"Yearly waste: {format_currency(unattached_cost * 12)}")
        print()
        print_separator('-')
        print()

        print(f"{'Elastic IP':<16} {'Allocation ID':<26} {'Monthly Cost':<15} {'Name'}")
        print_separator('-')

        for eip in unattached:
            cost = calculate_monthly_cost(False)
            print(f"{eip['public_ip']:<16} {eip['allocation_id']:<26} {format_currency(cost):<15} {eip['name']}")

        print_separator('-')
        print()

    # Show IPs attached to stopped instances
    if attached_stopped:
        print_separator()
        print("ELASTIC IPs ATTACHED TO STOPPED INSTANCES")
        print_separator()
        print()
        print(f"These {len(attached_stopped)} Elastic IP(s) are attached to stopped instances")
        print("You are being charged while the instances are stopped!")
        print()
        print(f"Monthly cost: {format_currency(stopped_cost)}")
        print(f"Yearly cost: {format_currency(stopped_cost * 12)}")
        print()
        print_separator('-')
        print()

        print(f"{'Elastic IP':<16} {'Instance ID':<20} {'State':<10} {'Monthly Cost':<15} {'Name'}")
        print_separator('-')

        for eip in attached_stopped:
            cost = calculate_monthly_cost(False)
            instance_id = eip['instance_id'] or 'N/A'
            print(f"{eip['public_ip']:<16} {instance_id:<20} {eip['instance_state']:<10} "
                  f"{format_currency(cost):<15} {eip['name']}")

        print_separator('-')
        print()

    # Show attached to running instances (no cost)
    if attached_running:
        print_separator()
        print("ELASTIC IPs ATTACHED TO RUNNING INSTANCES (No Charge)")
        print_separator()
        print()
        print(f"{len(attached_running)} Elastic IP(s) properly attached to running instances")
        print()

        print(f"{'Elastic IP':<16} {'Instance ID':<20} {'State':<10} {'Name'}")
        print_separator('-')

        for eip in attached_running:
            instance_id = eip['instance_id'] or eip.get('network_interface_id', 'N/A')
            print(f"{eip['public_ip']:<16} {instance_id:<20} {eip['instance_state']:<10} {eip['name']}")

        print_separator('-')
        print()

    # Show recommendations
    print_separator()
    print("RECOMMENDATIONS")
    print_separator()
    print()

    if unattached or attached_stopped:
        recommendations = []

        if unattached:
            recommendations.append(
                f"1. RELEASE {len(unattached)} unattached Elastic IP(s) to save "
                f"{format_currency(unattached_cost * 12)}/year"
            )
            recommendations.append(
                "   Command: aws ec2 release-address --allocation-id <ALLOCATION_ID>"
            )
            recommendations.append(
                "   WARNING: Released IPs cannot be recovered"
            )

        if attached_stopped:
            recommendations.append(
                f"2. REVIEW {len(attached_stopped)} Elastic IP(s) attached to stopped instances"
            )
            recommendations.append(
                "   Options:"
            )
            recommendations.append(
                "   a) Start the instances if they should be running"
            )
            recommendations.append(
                "   b) Release the IP if the instance will stay stopped"
            )
            recommendations.append(
                "   c) Disassociate and release if not needed"
            )
            recommendations.append(
                f"   Potential savings: {format_currency(stopped_cost * 12)}/year"
            )

        recommendations.append(
            f"3. SET UP CloudWatch alarms for unattached Elastic IPs"
        )
        recommendations.append(
            "   - Alert when IPs become unattached"
        )
        recommendations.append(
            "   - Automate cleanup of forgotten IPs"
        )

        recommendations.append(
            f"4. CONSIDER alternatives to Elastic IPs:"
        )
        recommendations.append(
            "   - Use AWS Global Accelerator for static IPs"
        )
        recommendations.append(
            "   - Use DNS with short TTL for dynamic IPs"
        )
        recommendations.append(
            "   - Use Application/Network Load Balancers"
        )

        for rec in recommendations:
            print(rec)

        print()
        print_separator('-')
        print(f"TOTAL POTENTIAL YEARLY SAVINGS: {format_currency(total_yearly_cost)}")
        print_separator('-')

    else:
        print("1. Excellent! All Elastic IPs are properly attached to running instances")
        print("2. You are not wasting money on unattached IPs")
        print("3. Continue monitoring to ensure IPs stay attached")
        print()
        print("Best Practice: Release IPs when instances are terminated")

    print()
    print("PRICING INFORMATION:")
    print(f"  Unattached Elastic IP: {format_currency(UNATTACHED_EIP_HOURLY_COST)}/hour")
    print(f"  Monthly cost per unattached IP: {format_currency(UNATTACHED_EIP_HOURLY_COST * HOURS_PER_MONTH)}")
    print(f"  Attached to running instance: FREE")
    print()
    print("NOTE: Elastic IPs attached to stopped instances are charged!")
    print("Pricing based on us-east-1 region")
    print_separator()


if __name__ == '__main__':
    main()
