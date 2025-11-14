#!/usr/bin/env python3
"""
HTML Report Generator for AWS Cost Analysis
Creates a professional HTML report card with charts and visualizations.
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List


def generate_html_report(results: List[Dict], reports_path: Path, total_monthly: float, total_yearly: float, total_current_monthly: float, total_current_yearly: float):
    """Generate HTML report with styling and charts."""

    # Calculate category totals
    categories = {}
    for result in [r for r in results if r['success']]:
        category = result['category']
        if category not in categories:
            categories[category] = {
                'monthly': 0,
                'yearly': 0,
                'items': []
            }
        savings = result['savings']
        categories[category]['monthly'] += savings['monthly_savings'] or 0
        categories[category]['yearly'] += savings['yearly_savings'] or 0
        categories[category]['items'].append(result)

    # Get top opportunities
    top_opportunities = sorted(
        [r for r in results if r['success'] and r['savings']['yearly_savings']],
        key=lambda x: x['savings']['yearly_savings'] or 0,
        reverse=True
    )[:5]

    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AWS Cost Analysis Report Card</title>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}

        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
            background: #f5f7fa;
            padding: 20px;
            color: #2c3e50;
        }}

        .container {{
            max-width: 1200px;
            margin: 0 auto;
            background: white;
            border-radius: 8px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
            overflow: hidden;
        }}

        .header {{
            background: #2c5aa0;
            color: white;
            padding: 40px;
            text-align: center;
        }}

        .header h1 {{
            font-size: 2.5em;
            margin-bottom: 10px;
            font-weight: 700;
        }}

        .header .subtitle {{
            font-size: 1.1em;
            opacity: 0.9;
        }}

        .header .date {{
            margin-top: 15px;
            font-size: 0.95em;
            opacity: 0.8;
        }}

        .summary {{
            background: #34495e;
            color: white;
            padding: 40px;
            text-align: center;
        }}

        .summary-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 30px;
            margin-top: 30px;
        }}

        .summary-card {{
            background: rgba(255, 255, 255, 0.15);
            padding: 25px;
            border-radius: 8px;
            border: 1px solid rgba(255, 255, 255, 0.2);
        }}

        .summary-card .label {{
            font-size: 0.9em;
            opacity: 0.9;
            margin-bottom: 10px;
        }}

        .summary-card .value {{
            font-size: 2.5em;
            font-weight: 700;
            line-height: 1;
        }}

        .summary-card .subvalue {{
            font-size: 0.85em;
            margin-top: 8px;
            opacity: 0.85;
        }}

        .content {{
            padding: 40px;
        }}

        .section {{
            margin-bottom: 40px;
        }}

        .section-title {{
            font-size: 1.8em;
            font-weight: 700;
            margin-bottom: 20px;
            color: #2c5aa0;
            border-bottom: 3px solid #2c5aa0;
            padding-bottom: 10px;
        }}

        .category {{
            margin-bottom: 30px;
            border: 1px solid #dce3e8;
            border-radius: 8px;
            overflow: hidden;
        }}

        .category-header {{
            background: #3b6ea5;
            color: white;
            padding: 20px;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }}

        .category-header h3 {{
            font-size: 1.4em;
            font-weight: 600;
        }}

        .category-header .total {{
            font-size: 1.2em;
            font-weight: 700;
        }}

        .category-items {{
            padding: 0;
        }}

        .item {{
            padding: 20px;
            border-bottom: 1px solid #e0e0e0;
            display: grid;
            grid-template-columns: auto 1fr auto;
            gap: 20px;
            align-items: center;
            transition: background 0.2s;
        }}

        .item:hover {{
            background: #f8f9fa;
        }}

        .item:last-child {{
            border-bottom: none;
        }}

        .item .status {{
            width: 40px;
            height: 40px;
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 1.1em;
        }}

        .item .status.optimized {{
            background: #27ae60;
            color: white;
        }}

        .item .status.opportunity {{
            background: #e67e22;
            color: white;
        }}

        .item .info {{
            flex: 1;
        }}

        .item .name {{
            font-size: 1.1em;
            font-weight: 600;
            margin-bottom: 5px;
        }}

        .item .description {{
            font-size: 0.9em;
            color: #666;
        }}

        .item .savings {{
            text-align: right;
        }}

        .item .savings .monthly {{
            font-size: 0.9em;
            color: #666;
            margin-bottom: 5px;
        }}

        .item .savings .yearly {{
            font-size: 1.4em;
            font-weight: 700;
            color: #27ae60;
        }}

        .opportunities {{
            background: #fef5e7;
            border: 2px solid #e67e22;
            border-radius: 8px;
            padding: 30px;
        }}

        .opportunity-list {{
            list-style: none;
            counter-reset: opportunity-counter;
        }}

        .opportunity-item {{
            counter-increment: opportunity-counter;
            padding: 20px;
            margin-bottom: 15px;
            background: white;
            border-radius: 8px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
            display: grid;
            grid-template-columns: auto 1fr auto;
            gap: 20px;
            align-items: center;
        }}

        .opportunity-item:before {{
            content: counter(opportunity-counter);
            background: #e67e22;
            color: white;
            width: 40px;
            height: 40px;
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            font-weight: 700;
            font-size: 1.2em;
        }}

        .opportunity-info {{
            flex: 1;
        }}

        .opportunity-name {{
            font-size: 1.1em;
            font-weight: 600;
            margin-bottom: 5px;
            color: #2c3e50;
        }}

        .opportunity-details {{
            font-size: 0.9em;
            color: #7f8c8d;
        }}

        .opportunity-savings {{
            font-size: 1.5em;
            font-weight: 700;
            color: #27ae60;
            text-align: right;
        }}

        .footer {{
            background: #f8f9fa;
            padding: 30px;
            text-align: center;
            color: #666;
            font-size: 0.9em;
        }}

        .footer .warning {{
            background: #fef5e7;
            border: 1px solid #e67e22;
            border-radius: 8px;
            padding: 15px;
            margin-top: 20px;
            color: #7d6608;
        }}

        .progress-bar {{
            background: #e0e0e0;
            border-radius: 10px;
            height: 20px;
            overflow: hidden;
            margin-top: 10px;
        }}

        .progress-fill {{
            background: #27ae60;
            height: 100%;
            transition: width 0.5s;
        }}

        @media print {{
            @page {{
                margin: 0.75in;
                size: letter portrait;
            }}

            body {{
                background: white !important;
                padding: 0;
                color: #000 !important;
            }}

            .container {{
                max-width: 100%;
                box-shadow: none !important;
                border-radius: 0;
            }}

            .header {{
                background: #2c5aa0 !important;
                -webkit-print-color-adjust: exact;
                print-color-adjust: exact;
                color: white !important;
                page-break-after: avoid;
                padding: 20px !important;
            }}

            .summary {{
                background: #34495e !important;
                -webkit-print-color-adjust: exact;
                print-color-adjust: exact;
                color: white !important;
                page-break-after: avoid;
                page-break-inside: avoid;
                padding: 20px !important;
            }}

            .summary-grid {{
                gap: 15px !important;
            }}

            .summary-card {{
                background: rgba(255, 255, 255, 0.15) !important;
                -webkit-print-color-adjust: exact;
                print-color-adjust: exact;
                page-break-inside: avoid;
            }}

            .content {{
                padding: 20px 0 !important;
            }}

            .section {{
                page-break-inside: avoid;
                margin-bottom: 30px !important;
            }}

            .section-title {{
                color: #2c5aa0 !important;
                -webkit-print-color-adjust: exact;
                print-color-adjust: exact;
                page-break-after: avoid;
            }}

            .category {{
                page-break-inside: avoid;
                border: 1px solid #dce3e8 !important;
            }}

            .category-header {{
                background: #3b6ea5 !important;
                -webkit-print-color-adjust: exact;
                print-color-adjust: exact;
                color: white !important;
                page-break-after: avoid;
            }}

            .item {{
                page-break-inside: avoid;
            }}

            .item:hover {{
                background: transparent !important;
            }}

            .item .status.optimized {{
                background: #27ae60 !important;
                -webkit-print-color-adjust: exact;
                print-color-adjust: exact;
                color: white !important;
            }}

            .item .status.opportunity {{
                background: #e67e22 !important;
                -webkit-print-color-adjust: exact;
                print-color-adjust: exact;
                color: white !important;
            }}

            .item .savings .yearly {{
                color: #27ae60 !important;
                -webkit-print-color-adjust: exact;
                print-color-adjust: exact;
            }}

            .opportunities {{
                background: #fef5e7 !important;
                border: 2px solid #e67e22 !important;
                -webkit-print-color-adjust: exact;
                print-color-adjust: exact;
                page-break-inside: avoid;
            }}

            .opportunity-item {{
                page-break-inside: avoid;
            }}

            .opportunity-item:before {{
                background: #e67e22 !important;
                -webkit-print-color-adjust: exact;
                print-color-adjust: exact;
                color: white !important;
            }}

            .opportunity-savings {{
                color: #27ae60 !important;
                -webkit-print-color-adjust: exact;
                print-color-adjust: exact;
            }}

            .footer {{
                page-break-before: avoid;
                page-break-inside: avoid;
            }}

            .footer .warning {{
                background: #fef5e7 !important;
                border: 1px solid #e67e22 !important;
                -webkit-print-color-adjust: exact;
                print-color-adjust: exact;
            }}

            /* Hide unnecessary elements in print */
            .no-print {{
                display: none !important;
            }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1><i class="fas fa-dollar-sign"></i> AWS Cost Analysis Report Card</h1>
            <div class="subtitle">Comprehensive Cost Optimization Analysis</div>
            <div class="date">Generated: {datetime.now().strftime('%B %d, %Y at %I:%M %p')}</div>
        </div>

        <div class="summary">
            <h2 style="margin-bottom: 30px;">Executive Summary</h2>
            <div class="summary-grid">
                <div class="summary-card">
                    <div class="label">Current Monthly Spend</div>
                    <div class="value">${total_current_monthly:,.0f}</div>
                    <div class="subvalue">${total_current_yearly:,.0f}/year</div>
                </div>
                <div class="summary-card">
                    <div class="label">Potential Monthly Savings</div>
                    <div class="value">${total_monthly:,.0f}</div>
                    <div class="subvalue">${total_yearly:,.0f}/year</div>
                </div>
                <div class="summary-card">
                    <div class="label">Cost Reduction</div>
                    <div class="value">{(total_yearly / total_current_yearly * 100) if total_current_yearly > 0 else 0:.1f}%</div>
                    <div class="subvalue">Potential Savings</div>
                </div>
                <div class="summary-card">
                    <div class="label">Analyses Run</div>
                    <div class="value">{sum(1 for r in results if r['success'])}</div>
                    <div class="subvalue">of {len(results)} total</div>
                </div>
            </div>
        </div>

        <div class="content">
"""

    # Add top opportunities section
    if top_opportunities:
        html_content += """
            <div class="section">
                <h2 class="section-title"><i class="fas fa-bullseye"></i> Top Savings Opportunities</h2>
                <div class="opportunities">
                    <ul class="opportunity-list">
"""
        for opp in top_opportunities:
            yearly_savings = opp['savings']['yearly_savings'] or 0
            html_content += f"""
                        <li class="opportunity-item">
                            <div class="opportunity-info">
                                <div class="opportunity-name">{opp['name']}</div>
                                <div class="opportunity-details">See detailed report: {opp['report_file']}</div>
                            </div>
                            <div class="opportunity-savings">${yearly_savings:,.0f}/yr</div>
                        </li>
"""
        html_content += """
                    </ul>
                </div>
            </div>
"""

    # Add category breakdown
    html_content += """
            <div class="section">
                <h2 class="section-title"><i class="fas fa-chart-pie"></i> Savings Breakdown by Category</h2>
"""

    for category_name, category_data in sorted(categories.items()):
        category_monthly = category_data['monthly']
        category_yearly = category_data['yearly']

        html_content += f"""
                <div class="category">
                    <div class="category-header">
                        <h3>{category_name}</h3>
                        <div class="total">${category_yearly:,.2f}/year</div>
                    </div>
                    <div class="category-items">
"""

        for item in category_data['items']:
            savings = item['savings']
            monthly = savings['monthly_savings'] or 0
            yearly = savings['yearly_savings'] or 0
            has_savings = savings['found_issues']

            status_class = 'opportunity' if has_savings else 'optimized'
            status_icon = '<i class="fas fa-lightbulb"></i>' if has_savings else '<i class="fas fa-check"></i>'

            html_content += f"""
                        <div class="item">
                            <div class="status {status_class}">{status_icon}</div>
                            <div class="info">
                                <div class="name">{item['name']}</div>
                                <div class="description">{'Optimization opportunity found' if has_savings else 'Already optimized'}</div>
                            </div>
                            <div class="savings">
                                <div class="monthly">${monthly:,.2f}/month</div>
                                <div class="yearly">${yearly:,.2f}/year</div>
                            </div>
                        </div>
"""

        html_content += """
                    </div>
                </div>
"""

    html_content += """
            </div>

            <div class="section">
                <h2 class="section-title"><i class="fas fa-file-alt"></i> Detailed Reports</h2>
                <p style="margin-bottom: 20px;">Individual detailed reports have been saved to:</p>
                <ul style="list-style: none; padding-left: 0;">
"""

    for result in [r for r in results if r['success']]:
        html_content += f"""
                    <li style="padding: 10px; margin-bottom: 8px; background: #f8f9fa; border-radius: 6px;">
                        <strong>{result['name']}:</strong> <code>{result['report_file']}</code>
                    </li>
"""

    html_content += f"""
                </ul>
            </div>
        </div>

        <div class="footer">
            <p><strong>Next Steps:</strong></p>
            <p style="margin-top: 10px;">
                1. Review detailed reports for specific recommendations<br>
                2. Prioritize high-value, low-risk optimizations<br>
                3. Validate with your team before implementing changes<br>
                4. Test in non-production environments first
            </p>
            <div class="warning">
                <strong><i class="fas fa-exclamation-triangle"></i> Important:</strong> All analyses are read-only and make no changes to your AWS resources.
                Always backup critical data before making changes.
            </div>
            <p style="margin-top: 20px; color: #999;">
                Report generated by AWS Cost Analysis Tools | {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}<br>
                Location: {reports_path}
            </p>
        </div>
    </div>
</body>
</html>
"""

    # Write HTML file
    html_file = reports_path / 'index.html'
    with open(html_file, 'w') as f:
        f.write(html_content)

    # Also create a JSON data file for potential API use
    json_data = {
        'generated_at': datetime.now().isoformat(),
        'summary': {
            'total_monthly_savings': total_monthly,
            'total_yearly_savings': total_yearly,
            'current_monthly_cost': total_current_monthly,
            'current_yearly_cost': total_current_yearly,
            'savings_percentage': (total_yearly / total_current_yearly * 100) if total_current_yearly > 0 else 0
        },
        'categories': {
            name: {
                'monthly_savings': data['monthly'],
                'yearly_savings': data['yearly'],
                'item_count': len(data['items'])
            }
            for name, data in categories.items()
        },
        'analyses': [
            {
                'name': r['name'],
                'category': r['category'],
                'success': r['success'],
                'savings': {
                    'monthly': r['savings']['monthly_savings'],
                    'yearly': r['savings']['yearly_savings'],
                    'current_monthly': r['savings']['current_monthly_cost'],
                    'current_yearly': r['savings']['current_yearly_cost']
                } if r['success'] else None,
                'report_file': r.get('report_file')
            }
            for r in results
        ]
    }

    json_file = reports_path / 'report_data.json'
    with open(json_file, 'w') as f:
        json.dump(json_data, f, indent=2)

    return html_file, json_file
