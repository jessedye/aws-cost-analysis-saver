# Quick Start Guide

## Run Complete Analysis

```bash
./analyze_all_costs.py
```

This will:
1. Run all 7 cost analyzers
2. Create a timestamped report directory
3. Generate 3 types of reports:
   - **HTML Report** (`index.html`) - Beautiful visual dashboard
   - **Text Report** (`SUMMARY_REPORT_CARD.txt`) - Executive summary
   - **JSON Data** (`report_data.json`) - Structured data

## View Your Report

```bash
# Open HTML report in browser
open cost_reports/latest/index.html

# Or with specific browser
firefox cost_reports/latest/index.html
```

## What You'll See

### HTML Dashboard Includes:
- 💰 Total potential savings (monthly & yearly)
- 📊 Savings breakdown by category
- 🎯 Top 5 opportunities ranked by value
- ✓ Status for each AWS service analyzed
- 📄 Links to detailed reports

### Color Coding:
- 🟢 Green checkmark = Already optimized
- 🟠 Orange lightbulb = Savings opportunity found

## Individual Analyzers

Run specific analyses:

```bash
./ec2_snapshot_analyzer.py          # Old snapshots
./s3_cost_analyzer.py                # S3 → Glacier savings
./ebs_volume_analyzer.py             # Unattached volumes
./elastic_ip_analyzer.py             # Unused Elastic IPs
./reserved_instance_analyzer.py      # EC2 RI recommendations
./rds_cost_analyzer.py               # RDS optimization
./compute_savings_plan_analyzer.py   # Savings Plans
```

## Example Output

```
Running EC2 Snapshots Analysis...
  ✓ Complete - Report saved to: ec2_snapshot_analyzer_report.txt
  → Potential Savings: $1,200.00/year

Running S3 Buckets Analysis...
  ✓ Complete - Report saved to: s3_cost_analyzer_report.txt
  → Potential Savings: $5,400.00/year

...

Generating HTML report...
✓ HTML report saved to: index.html

QUICK SUMMARY
================================================================================

Total Potential Savings:
  Monthly: $3,245.00
  Yearly: $38,940.00

📊 Full reports available at: cost_reports/20241113_142530/
📄 HTML Report (open in browser): index.html
```

## Schedule Regular Analysis

Add to crontab for weekly reports:

```bash
# Run every Monday at 9 AM
crontab -e

# Add this line:
0 9 * * 1 cd /path/to/aws-cost-analysis-saver && ./analyze_all_costs.py
```

## Troubleshooting

**"AWS CLI not found"**
```bash
# Install AWS CLI
brew install awscli  # macOS
# or: apt-get install awscli  # Ubuntu
# or: yum install awscli  # Amazon Linux
```

**"Permission denied"**
```bash
chmod +x *.py
```

**"Error getting resources"**
```bash
# Check AWS credentials
aws configure
aws sts get-caller-identity
```

## Next Steps

1. Review HTML report in browser
2. Focus on top 3-5 opportunities
3. Read detailed reports for implementation steps
4. Validate with team before making changes
5. Test in non-production first

## Important Reminders

- ✅ All scripts are **read-only**
- ✅ No changes are made to AWS resources
- ✅ Safe to run anytime
- ⚠️ Always backup before deleting resources
- ⚠️ Test RI/SP purchases carefully (commitment required)

---

For detailed documentation, see [README.md](README.md)
