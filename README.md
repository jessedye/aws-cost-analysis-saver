# AWS Cost Analysis & Savings Tools

A comprehensive suite of Python scripts to analyze AWS costs and identify savings opportunities across multiple services.

## Overview

These scripts analyze your AWS environment to identify cost optimization opportunities including:
- Unused resources (snapshots, volumes, Elastic IPs)
- Storage optimization (GP2→GP3, S3→Glacier)
- Reserved Instance & Savings Plan recommendations
- RDS optimization opportunities

**IMPORTANT**: All scripts are **read-only** and make **no changes** to your AWS resources. They only analyze and report.

## Prerequisites

- Python 3.6+
- AWS CLI installed and configured
- AWS credentials with read-only access to:
  - EC2 (instances, volumes, snapshots, elastic IPs)
  - S3 (buckets and objects)
  - RDS (instances)
  - Lambda (functions)
  - ECS (clusters)

## Installation

1. Ensure AWS CLI is installed:
```bash
aws --version
```

2. Configure AWS credentials:
```bash
aws configure
```

3. Make scripts executable:
```bash
chmod +x *.py
```

## Quick Start

### Option 1: Run All Analyses (Recommended)

Generate a comprehensive report card with all cost analyses:

```bash
./analyze_all_costs.py
```

This will:
- Run all 7 cost analyzers
- Generate detailed reports in `cost_reports/YYYYMMDD_HHMMSS/`
- Create an **HTML report card** with visual dashboard
- Create a text summary report with total savings
- Create a JSON data file for programmatic access
- Create a `cost_reports/latest/` symlink to the most recent report

**Output**:
- `index.html` - Beautiful HTML report card (open in browser)
- `SUMMARY_REPORT_CARD.txt` - Text executive summary
- `report_data.json` - Structured data in JSON format
- Individual detailed reports for each analyzer

**View the HTML Report**:
```bash
# Open in default browser
open cost_reports/latest/index.html

# Or specify browser
firefox cost_reports/latest/index.html
google-chrome cost_reports/latest/index.html
```

### Option 2: Run Individual Analyzers

Run specific analyzers directly:

```bash
./ec2_snapshot_analyzer.py
./s3_cost_analyzer.py
./ebs_volume_analyzer.py
./elastic_ip_analyzer.py
./reserved_instance_analyzer.py
./rds_cost_analyzer.py
./compute_savings_plan_analyzer.py
```

## Available Analyzers

### 1. EC2 Snapshot Analyzer
**Script**: `ec2_snapshot_analyzer.py`

**Analyzes**:
- EBS snapshot ages and sizes
- Current snapshot storage costs
- Potential savings from deleting old snapshots (>90 days)

**Typical Savings**: Varies based on snapshot retention

**Example Output**:
```
Potential yearly savings: $1,200 from deleting 50 old snapshots
```

---

### 2. S3 Cost Analyzer
**Script**: `s3_cost_analyzer.py`

**Analyzes**:
- S3 bucket sizes and storage classes
- Current storage costs
- Savings from migrating to Glacier tiers

**Typical Savings**: 40-95% on archived data

**Example Output**:
```
Yearly savings: $5,400 by moving infrequently accessed data to Glacier
```

---

### 3. EBS Volume Analyzer
**Script**: `ebs_volume_analyzer.py`

**Analyzes**:
- Unattached (unused) EBS volumes
- GP2 volumes that could migrate to GP3
- Expensive Provisioned IOPS volumes

**Typical Savings**: 20% on GP2→GP3, 100% on unused volumes

**Example Output**:
```
Monthly waste: $450 from 10 unattached volumes
Yearly savings: $800 from GP2→GP3 migration
```

---

### 4. Elastic IP Analyzer
**Script**: `elastic_ip_analyzer.py`

**Analyzes**:
- Unattached Elastic IPs ($3.65/month each)
- IPs attached to stopped instances

**Typical Savings**: $3.65/month per unused IP

**Example Output**:
```
Yearly savings: $219 from releasing 5 unattached Elastic IPs
```

---

### 5. Reserved Instance Analyzer
**Script**: `reserved_instance_analyzer.py`

**Analyzes**:
- Running EC2 instances
- Current Reserved Instance coverage
- RI purchase recommendations

**Typical Savings**: 35-50% on committed workloads

**Example Output**:
```
1-Year RI savings: $12,500/year
3-Year RI savings: $18,750/year
```

---

### 6. RDS Cost Analyzer
**Script**: `rds_cost_analyzer.py`

**Analyzes**:
- RDS instance costs
- Reserved Instance opportunities
- Storage optimization (io1→gp3)

**Typical Savings**: 35-50% with RIs

**Example Output**:
```
3-Year RI savings: $8,400/year on RDS instances
```

---

### 7. Compute Savings Plan Analyzer
**Script**: `compute_savings_plan_analyzer.py`

**Analyzes**:
- EC2, Lambda, Fargate usage
- Savings Plan vs Reserved Instance comparison
- Commitment recommendations

**Typical Savings**: 35-60% on compute spend

**Example Output**:
```
3-Year Compute Savings Plan: $25,000/year savings
More flexible than Reserved Instances
```

## Understanding the Report Card

The summary report card (`SUMMARY_REPORT_CARD.txt`) contains:

### Executive Summary
```
Total Potential Savings:
  Monthly: $3,245.00
  Yearly: $38,940.00
```

### Savings Breakdown by Category
```
Storage:
  ✓ EC2 Snapshots         Monthly: $  100.00  Yearly: $  1,200.00
  ✓ S3 Buckets            Monthly: $  450.00  Yearly: $  5,400.00
  ✓ EBS Volumes           Monthly: $  520.00  Yearly: $  6,240.00

Network:
  ✓ Elastic IPs           Monthly: $   18.25  Yearly: $    219.00

Compute:
  ✓ Reserved Instances    Monthly: $1,562.50  Yearly: $ 18,750.00
  ✓ Savings Plans         Monthly: $2,083.33  Yearly: $ 25,000.00

Database:
  ✓ RDS Instances         Monthly: $  700.00  Yearly: $  8,400.00
```

### Top Recommendations
Lists opportunities by potential savings (highest first)

## Report Directory Structure

```
cost_reports/
├── latest -> 20241113_142530/  (symlink to most recent)
└── 20241113_142530/
    ├── index.html                              # ⭐ Main HTML report card (open this!)
    ├── SUMMARY_REPORT_CARD.txt                 # Text summary report
    ├── report_data.json                        # Structured JSON data
    ├── ec2_snapshot_analyzer_report.txt        # Detailed analysis reports
    ├── s3_cost_analyzer_report.txt
    ├── ebs_volume_analyzer_report.txt
    ├── elastic_ip_analyzer_report.txt
    ├── reserved_instance_analyzer_report.txt
    ├── rds_cost_analyzer_report.txt
    └── compute_savings_plan_analyzer_report.txt
```

The **HTML report card** (`index.html`) provides:
- Visual dashboard with cost breakdowns
- Color-coded status indicators
- Interactive category sections
- Top savings opportunities ranked by value
- Mobile-friendly responsive design
- Print-ready formatting

## Customizing for Your Region

Each script has pricing constants at the top. Update these for your AWS region:

**Example** (in `ebs_volume_analyzer.py`):
```python
# AWS EBS Pricing (USD per GB/month) - Update for your region
EBS_PRICING = {
    'gp2': Decimal('0.10'),  # us-east-1 pricing
    'gp3': Decimal('0.08'),
    # ... update based on your region
}
```

Find pricing at: https://aws.amazon.com/pricing/

## Best Practices

1. **Run regularly**: Schedule monthly cost analysis reviews
2. **Start with quick wins**: Focus on unattached resources first
3. **Test before implementing**: Validate in non-production environments
4. **Consider commitments carefully**: RIs and Savings Plans require long-term commitment
5. **Use tags**: Tag resources for better cost allocation
6. **Monitor trends**: Compare reports over time to track improvements

## Limitations

- **Read-only**: Scripts do not make changes (this is by design)
- **Pricing estimates**: Based on standard on-demand pricing
- **Regional**: Default pricing is us-east-1
- **Usage patterns**: Cannot analyze CloudWatch metrics for utilization
- **Actual costs**: For precise billing, use AWS Cost Explorer

## Troubleshooting

### "AWS CLI not found"
Install AWS CLI: https://aws.amazon.com/cli/

### "Error getting [resource]"
Check AWS credentials and permissions:
```bash
aws sts get-caller-identity
aws ec2 describe-instances --max-items 1
```

### "Script timed out"
- Large environments may take longer
- Run individual scripts instead of `analyze_all_costs.py`
- Increase timeout in the orchestrator script

### Permission Denied
Make scripts executable:
```bash
chmod +x *.py
```

## Using the JSON Data

The `report_data.json` file contains structured data for programmatic access:

```json
{
  "generated_at": "2024-11-13T14:25:30",
  "summary": {
    "total_monthly_savings": 3245.50,
    "total_yearly_savings": 38940.00,
    "current_monthly_cost": 12500.00,
    "current_yearly_cost": 150000.00,
    "savings_percentage": 25.96
  },
  "categories": { ... },
  "analyses": [ ... ]
}
```

Use this for:
- Custom dashboards
- Automated alerting
- Trend analysis over time
- Integration with BI tools

## Integration Ideas

### Cron Job (Weekly Reports)
```bash
# Add to crontab (run every Monday at 9 AM)
0 9 * * 1 cd /path/to/aws-cost-analysis-saver && ./analyze_all_costs.py
```

### Email HTML Reports
```bash
#!/bin/bash
./analyze_all_costs.py

# Email the HTML report
cat cost_reports/latest/index.html | mail -a "Content-Type: text/html" \
  -s "AWS Cost Report - $(date +%Y-%m-%d)" team@example.com

# Or attach the file
echo "See attached HTML report" | mail -s "AWS Cost Report" \
  -A cost_reports/latest/index.html team@example.com
```

### Slack Notifications with Savings Summary
```bash
#!/bin/bash
./analyze_all_costs.py

# Extract savings from JSON
SAVINGS=$(python3 -c "import json; data=json.load(open('cost_reports/latest/report_data.json')); print(f\"\${data['summary']['total_yearly_savings']:,.0f}\")")

# Post to Slack
curl -X POST -H 'Content-type: application/json' \
  --data "{\"text\":\"💰 AWS Cost Analysis Complete\n\nPotential Yearly Savings: $SAVINGS\n\nView report: file://$(pwd)/cost_reports/latest/index.html\"}" \
  YOUR_SLACK_WEBHOOK_URL
```

### Hosting Reports on Web Server
```bash
# Copy reports to web server document root
./analyze_all_costs.py
cp -r cost_reports/latest /var/www/html/aws-cost-report
# Access at: http://yourserver/aws-cost-report/index.html
```

### Tracking Trends Over Time
```bash
# Keep historical JSON data
./analyze_all_costs.py
cp cost_reports/latest/report_data.json historical_data/report_$(date +%Y%m%d).json

# Analyze trends with Python
python3 -c "
import json, glob
reports = [json.load(open(f)) for f in sorted(glob.glob('historical_data/*.json'))]
for r in reports:
    print(f\"{r['generated_at']}: \${r['summary']['total_yearly_savings']:,.0f} potential savings\")
"
```

## Contributing

To add a new analyzer:

1. Create script following the naming pattern: `[service]_cost_analyzer.py`
2. Include savings output in format: `Yearly Savings: $X,XXX.XX`
3. Add to `ANALYZERS` list in `analyze_all_costs.py`
4. Update this README

## Safety Notes

- Scripts are **read-only** and make **no changes**
- Always validate recommendations before taking action
- Consider backup/recovery before deleting resources
- Test in non-production environments first
- Understand commitment terms for RIs and Savings Plans

## License

MIT License - Feel free to modify and use as needed

## Support

For issues or questions:
1. Check AWS credentials and permissions
2. Verify AWS CLI is working: `aws ec2 describe-instances`
3. Review error messages in detailed reports
4. Ensure scripts have execute permissions

## Next Steps After Analysis

1. **Review Reports**: Read the summary report card
2. **Prioritize**: Focus on high-value, low-risk optimizations first
3. **Validate**: Confirm resources are truly unused before deletion
4. **Plan**: Create implementation timeline
5. **Test**: Start with non-production environments
6. **Monitor**: Track actual savings after implementation
7. **Repeat**: Run analyses monthly to catch new opportunities

---

**Remember**: The goal is continuous optimization, not one-time savings. Regular analysis helps maintain cost efficiency as your AWS environment evolves.
