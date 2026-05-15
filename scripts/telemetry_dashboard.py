#!/usr/bin/env python3
"""Telemetry dashboard for devin-delegate with HTML and CLI visualization."""
from __future__ import annotations

import json
import os
import sys
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any


class TelemetryDashboard:
    """Dashboard for visualizing devin-delegate telemetry data."""
    
    def __init__(self, repo_root: Path | None = None):
        """Initialize the dashboard with repository root."""
        if repo_root is None:
            try:
                import subprocess
                proc = subprocess.run(
                    ["git", "rev-parse", "--show-toplevel"],
                    capture_output=True,
                    text=True,
                    check=False,
                )
                if proc.returncode == 0 and proc.stdout.strip():
                    repo_root = Path(proc.stdout.strip())
                else:
                    repo_root = Path.cwd()
            except Exception:
                repo_root = Path.cwd()
        
        self.repo_root = repo_root
        self.events_path = repo_root / "artifacts" / "devin-delegate" / "events.jsonl"
        self.history_path = repo_root / "artifacts" / "devin-delegate" / "history.jsonl"
    
    def load_events(self, days: int = 14) -> list[dict[str, Any]]:
        """Load telemetry events from the events file."""
        if not self.events_path.exists():
            return []
        
        cutoff = datetime.now().replace(tzinfo=None) - timedelta(days=days)
        events = []
        
        try:
            lines = self.events_path.read_text(encoding="utf-8", errors="ignore").strip().splitlines()
            for line in lines:
                try:
                    event = json.loads(line)
                    timestamp_str = event.get("timestamp", "")
                    if timestamp_str:
                        try:
                            timestamp = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
                            # Convert to naive datetime for comparison
                            timestamp_naive = timestamp.replace(tzinfo=None)
                            if timestamp_naive >= cutoff:
                                events.append(event)
                        except ValueError:
                            # Include events with invalid timestamps
                            events.append(event)
                    else:
                        events.append(event)
                except json.JSONDecodeError:
                    continue
        except OSError:
            pass
        
        return events
    
    def load_history(self, limit: int = 100) -> list[dict[str, Any]]:
        """Load task history from the history file."""
        if not self.history_path.exists():
            return []
        
        history = []
        try:
            lines = self.history_path.read_text(encoding="utf-8", errors="ignore").strip().splitlines()
            recent_lines = lines[-limit:] if len(lines) > limit else lines
            for line in recent_lines:
                try:
                    history.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        except OSError:
            pass
        
        return history
    
    def generate_stats(self, days: int = 14) -> dict[str, Any]:
        """Generate statistics from telemetry data."""
        events = self.load_events(days)
        
        if not events:
            return {
                "total_calls": 0,
                "successful_calls": 0,
                "failed_calls": 0,
                "fallback_rate": 0.0,
                "avg_latency_ms": 0.0,
                "total_cost_usd": 0.0,
                "total_savings_usd": 0.0,
                "auth_errors": 0,
                "timeouts": 0,
                "task_classes": {},
                "daily_stats": {}
            }
        
        stats = {
            "total_calls": len(events),
            "successful_calls": 0,
            "failed_calls": 0,
            "fallback_used": 0,
            "total_latency_ms": 0.0,
            "total_cost_usd": 0.0,
            "total_savings_usd": 0.0,
            "auth_errors": 0,
            "timeouts": 0,
            "task_classes": defaultdict(int),
            "daily_stats": defaultdict(lambda: {"calls": 0, "success": 0, "cost": 0.0})
        }
        
        for event in events:
            status = event.get("status", "unknown")
            if status == "ok":
                stats["successful_calls"] += 1
            else:
                stats["failed_calls"] += 1
            
            if event.get("fallback_used"):
                stats["fallback_used"] += 1
            
            latency = event.get("latency_ms", 0.0)
            stats["total_latency_ms"] += latency
            
            cost = event.get("estimated_cost_usd", 0.0)
            stats["total_cost_usd"] += cost
            
            savings = event.get("estimated_savings_usd", 0.0)
            stats["total_savings_usd"] += savings
            
            if status == "auth_error":
                stats["auth_errors"] += 1
            
            if event.get("error_category") == "timeout":
                stats["timeouts"] += 1
            
            task_class = event.get("task_class", "unknown")
            stats["task_classes"][task_class] += 1
            
            # Daily stats
            timestamp_str = event.get("timestamp", "")
            if timestamp_str:
                try:
                    timestamp = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
                    # Convert to naive datetime for consistent handling
                    timestamp_naive = timestamp.replace(tzinfo=None)
                    date_key = timestamp_naive.strftime("%Y-%m-%d")
                    stats["daily_stats"][date_key]["calls"] += 1
                    if status == "ok":
                        stats["daily_stats"][date_key]["success"] += 1
                    stats["daily_stats"][date_key]["cost"] += cost
                except ValueError:
                    pass
        
        # Calculate derived stats
        total_calls = stats["total_calls"]
        stats["fallback_rate"] = (stats["fallback_used"] / total_calls * 100) if total_calls > 0 else 0.0
        stats["avg_latency_ms"] = (stats["total_latency_ms"] / total_calls) if total_calls > 0 else 0.0
        stats["success_rate"] = (stats["successful_calls"] / total_calls * 100) if total_calls > 0 else 0.0
        
        return dict(stats)
    
    def render_cli_dashboard(self, days: int = 14) -> str:
        """Render a CLI-based dashboard."""
        stats = self.generate_stats(days)
        
        output = []
        output.append("╔════════════════════════════════════════════════════════════╗")
        output.append("║          Devin Delegate Telemetry Dashboard                ║")
        output.append("╚════════════════════════════════════════════════════════════╝")
        output.append("")
        
        # Overview
        output.append("📊 OVERVIEW (Last {} days)".format(days))
        output.append("─" * 60)
        output.append(f"   Total Calls:     {stats['total_calls']}")
        output.append(f"   Success Rate:    {stats['success_rate']:.1f}%")
        output.append(f"   Fallback Rate:   {stats['fallback_rate']:.1f}%")
        output.append(f"   Avg Latency:     {stats['avg_latency_ms']:.0f}ms")
        output.append("")
        
        # Costs
        output.append("💰 COST ANALYSIS")
        output.append("─" * 60)
        output.append(f"   Total Cost:      ${stats['total_cost_usd']:.4f}")
        output.append(f"   Total Savings:   ${stats['total_savings_usd']:.4f}")
        output.append(f"   Net Savings:     ${stats['total_savings_usd'] - stats['total_cost_usd']:.4f}")
        output.append("")
        
        # Errors
        output.append("⚠️  ERROR ANALYSIS")
        output.append("─" * 60)
        output.append(f"   Auth Errors:     {stats['auth_errors']}")
        output.append(f"   Timeouts:        {stats['timeouts']}")
        output.append(f"   Other Failures:  {stats['failed_calls'] - stats['auth_errors'] - stats['timeouts']}")
        output.append("")
        
        # Task Classes
        output.append("📋 TASK CLASS DISTRIBUTION")
        output.append("─" * 60)
        sorted_classes = sorted(stats['task_classes'].items(), key=lambda x: x[1], reverse=True)
        for task_class, count in sorted_classes:
            percentage = (count / stats['total_calls'] * 100) if stats['total_calls'] > 0 else 0
            bar_length = int(percentage / 2)
            bar = "█" * bar_length
            output.append(f"   {task_class:15s} {count:3d} ({percentage:5.1f}%) {bar}")
        output.append("")
        
        # Daily Stats
        output.append("📅 DAILY BREAKDOWN")
        output.append("─" * 60)
        sorted_days = sorted(stats['daily_stats'].items(), reverse=True)
        for date, day_stats in sorted_days[:7]:  # Last 7 days
            success_rate = (day_stats['success'] / day_stats['calls'] * 100) if day_stats['calls'] > 0 else 0
            output.append(f"   {date}  {day_stats['calls']:3d} calls  {success_rate:5.1f}% success  ${day_stats['cost']:.4f}")
        
        output.append("")
        output.append("💡 TIP: Use --html to generate an interactive HTML dashboard")
        
        return "\n".join(output)
    
    def render_html_dashboard(self, days: int = 14, output_file: Path | None = None) -> str:
        """Render an HTML-based dashboard."""
        stats = self.generate_stats(days)
        history = self.load_history(50)
        
        # Generate daily chart data
        daily_labels = []
        daily_calls = []
        daily_costs = []
        sorted_days = sorted(stats['daily_stats'].items())
        for date, day_stats in sorted_days:
            daily_labels.append(date)
            daily_calls.append(day_stats['calls'])
            daily_costs.append(day_stats['cost'])
        
        # Generate task class chart data
        task_labels = []
        task_counts = []
        sorted_classes = sorted(stats['task_classes'].items(), key=lambda x: x[1], reverse=True)
        for task_class, count in sorted_classes:
            task_labels.append(task_class)
            task_counts.append(count)
        
        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Devin Delegate Telemetry Dashboard</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 20px;
        }}
        
        .container {{
            max-width: 1200px;
            margin: 0 auto;
        }}
        
        .header {{
            background: white;
            border-radius: 10px;
            padding: 30px;
            margin-bottom: 20px;
            box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
        }}
        
        .header h1 {{
            color: #333;
            margin-bottom: 5px;
        }}
        
        .header p {{
            color: #666;
            font-size: 14px;
        }}
        
        .stats-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 20px;
            margin-bottom: 20px;
        }}
        
        .stat-card {{
            background: white;
            border-radius: 10px;
            padding: 20px;
            box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
        }}
        
        .stat-card h3 {{
            color: #666;
            font-size: 12px;
            text-transform: uppercase;
            margin-bottom: 10px;
        }}
        
        .stat-card .value {{
            color: #333;
            font-size: 28px;
            font-weight: bold;
        }}
        
        .stat-card .subtext {{
            color: #999;
            font-size: 12px;
            margin-top: 5px;
        }}
        
        .charts-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(400px, 1fr));
            gap: 20px;
            margin-bottom: 20px;
        }}
        
        .chart-card {{
            background: white;
            border-radius: 10px;
            padding: 20px;
            box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
        }}
        
        .chart-card h3 {{
            color: #333;
            margin-bottom: 15px;
        }}
        
        .history-section {{
            background: white;
            border-radius: 10px;
            padding: 20px;
            box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
        }}
        
        .history-section h3 {{
            color: #333;
            margin-bottom: 15px;
        }}
        
        .history-item {{
            padding: 10px;
            border-bottom: 1px solid #eee;
        }}
        
        .history-item:last-child {{
            border-bottom: none;
        }}
        
        .history-item .task {{
            color: #333;
            font-weight: 500;
        }}
        
        .history-item .timestamp {{
            color: #999;
            font-size: 12px;
        }}
        
        .success {{ color: #10b981; }}
        .error {{ color: #ef4444; }}
        .warning {{ color: #f59e0b; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🚀 Devin Delegate Telemetry Dashboard</h1>
            <p>Last {days} days • Generated on {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
        </div>
        
        <div class="stats-grid">
            <div class="stat-card">
                <h3>Total Calls</h3>
                <div class="value">{stats['total_calls']}</div>
                <div class="subtext">All delegations</div>
            </div>
            
            <div class="stat-card">
                <h3>Success Rate</h3>
                <div class="value">{stats['success_rate']:.1f}%</div>
                <div class="subtext">{stats['successful_calls']} successful</div>
            </div>
            
            <div class="stat-card">
                <h3>Fallback Rate</h3>
                <div class="value">{stats['fallback_rate']:.1f}%</div>
                <div class="subtext">{stats['fallback_used']} fallbacks</div>
            </div>
            
            <div class="stat-card">
                <h3>Avg Latency</h3>
                <div class="value">{stats['avg_latency_ms']:.0f}ms</div>
                <div class="subtext">Response time</div>
            </div>
            
            <div class="stat-card">
                <h3>Total Cost</h3>
                <div class="value">${stats['total_cost_usd']:.4f}</div>
                <div class="subtext">Devin + fallbacks</div>
            </div>
            
            <div class="stat-card">
                <h3>Total Savings</h3>
                <div class="value">${stats['total_savings_usd']:.4f}</div>
                <div class="subtext">vs parent agent</div>
            </div>
        </div>
        
        <div class="charts-grid">
            <div class="chart-card">
                <h3>📅 Daily Calls</h3>
                <canvas id="dailyChart"></canvas>
            </div>
            
            <div class="chart-card">
                <h3>📋 Task Class Distribution</h3>
                <canvas id="taskChart"></canvas>
            </div>
        </div>
        
        <div class="history-section">
            <h3>📜 Recent Tasks</h3>
            <div class="history-list">
"""
        
        # Add recent history
        for item in history[:10]:
            task = item.get('task', 'Unknown task')
            timestamp = item.get('timestamp', '')
            if timestamp:
                try:
                    dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                    timestamp = dt.strftime('%Y-%m-%d %H:%M')
                except ValueError:
                    pass
            
            html += f"""
                <div class="history-item">
                    <div class="task">{task[:80]}{'...' if len(task) > 80 else ''}</div>
                    <div class="timestamp">{timestamp}</div>
                </div>
"""
        
        html += """
            </div>
        </div>
    </div>
    
    <script>
        // Daily calls chart
        const dailyCtx = document.getElementById('dailyChart').getContext('2d');
        new Chart(dailyCtx, {{
            type: 'line',
            data: {{
                labels: """ + json.dumps(daily_labels) + """,
                datasets: [{{
                    label: 'Calls',
                    data: """ + json.dumps(daily_calls) + """,
                    borderColor: '#667eea',
                    backgroundColor: 'rgba(102, 126, 234, 0.1)',
                    fill: true,
                    tension: 0.4
                }}]
            }},
            options: {{
                responsive: true,
                plugins: {{
                    legend: {{
                        display: false
                    }}
                }}
            }}
        }});
        
        // Task class distribution chart
        const taskCtx = document.getElementById('taskChart').getContext('2d');
        new Chart(taskCtx, {{
            type: 'doughnut',
            data: {{
                labels: """ + json.dumps(task_labels) + """,
                datasets: [{{
                    data: """ + json.dumps(task_counts) + """,
                    backgroundColor: [
                        '#667eea',
                        '#764ba2',
                        '#f093fb',
                        '#f5576c',
                        '#4facfe',
                        '#00f2fe'
                    ]
                }}]
            }},
            options: {{
                responsive: true
            }}
        }});
    </script>
</body>
</html>
"""
        
        if output_file:
            output_file = Path(output_file)
            output_file.parent.mkdir(parents=True, exist_ok=True)
            output_file.write_text(html, encoding="utf-8")
            print(f"✅ HTML dashboard saved to {output_file}")
        
        return html


def main() -> int:
    """CLI entry point for telemetry dashboard."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Telemetry dashboard for devin-delegate")
    parser.add_argument("--days", type=int, default=14, help="Number of days to analyze (default: 14)")
    parser.add_argument("--html", action="store_true", help="Generate HTML dashboard")
    parser.add_argument("--output", "-o", help="Output file for HTML dashboard")
    parser.add_argument("--repo-root", help="Repository root path")
    
    args = parser.parse_args()
    
    repo_root = Path(args.repo_root) if args.repo_root else None
    dashboard = TelemetryDashboard(repo_root)
    
    if args.html:
        output_file = Path(args.output) if args.output else None
        dashboard.render_html_dashboard(days=args.days, output_file=output_file)
        return 0
    else:
        print(dashboard.render_cli_dashboard(days=args.days))
        return 0


if __name__ == "__main__":
    sys.exit(main())