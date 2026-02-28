"""
diagnose.py — CLI Entry Point for ExplainDeFi
Usage:
    python diagnose.py --tx 0xYOUR_TX_HASH
    python diagnose.py --tx 0xYOUR_TX_HASH --output json
    python diagnose.py --history
"""

import argparse
import json
import sys
from rich.console import Console
from rich.table import Table
from rich import box

console = Console()


def print_banner():
    console.print("""
[bold magenta]
  ███████╗██╗  ██╗██████╗ ██╗      █████╗ ██╗███╗   ██╗
  ██╔════╝╚██╗██╔╝██╔══██╗██║     ██╔══██╗██║████╗  ██║
  █████╗   ╚███╔╝ ██████╔╝██║     ███████║██║██╔██╗ ██║
  ██╔══╝   ██╔██╗ ██╔═══╝ ██║     ██╔══██║██║██║╚██╗██║
  ███████╗██╔╝ ██╗██║     ███████╗██║  ██║██║██║ ╚████║
  ╚══════╝╚═╝  ╚═╝╚═╝     ╚══════╝╚═╝  ╚═╝╚═╝╚═╝  ╚═══╝
  ██████╗ ███████╗███████╗██╗
  ██╔══██╗██╔════╝██╔════╝██║
  ██║  ██║█████╗  █████╗  ██║
  ██║  ██║██╔══╝  ██╔══╝  ██║
  ██████╔╝███████╗██║     ██║
  ╚═════╝ ╚══════╝╚═╝     ╚═╝
[/bold magenta]
[dim]AI-Powered DeFi Transaction Failure Diagnosis[/dim]
""")


def cmd_diagnose(tx_hash: str, output_format: str):
    """Run a full diagnosis on the given transaction hash."""
    from core.config import config
    from core.pipeline import DiagnosisPipeline

    # Validate API keys
    warnings = config.validate()
    for w in warnings:
        console.print(w)
    if warnings:
        console.print()

    pipeline = DiagnosisPipeline()
    report = pipeline.run(tx_hash)

    if output_format == "json":
        console.print(report.model_dump_json(indent=2))


def cmd_history(limit: int = 10):
    """Show recent diagnoses from the database."""
    try:
        from db.database import Database
        db = Database()
        reports = db.get_all_reports(limit=limit)
        db.close()

        if not reports:
            console.print("[yellow]No diagnoses found in database.[/yellow]")
            return

        table = Table(title="Recent Diagnoses", box=box.ROUNDED)
        table.add_column("Tx Hash", style="cyan", width=20)
        table.add_column("Timestamp", width=20)
        table.add_column("Category", style="bold")
        table.add_column("Sub-type")
        table.add_column("Confidence", justify="right")

        for r in reports:
            table.add_row(
                r["tx_hash"][:18] + "...",
                r["timestamp"][:19] if r["timestamp"] else "-",
                r.get("failure_category", "?"),
                r.get("failure_sub_type", "?"),
                f"{(r.get('confidence') or 0) * 100:.0f}%",
            )

        console.print(table)
    except Exception as e:
        console.print(f"[red]Failed to load history: {e}[/red]")


def main():
    parser = argparse.ArgumentParser(
        description="ExplainDeFi — AI-powered DeFi transaction failure diagnosis",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python diagnose.py --tx 0xabc123...
  python diagnose.py --tx 0xabc123... --output json
  python diagnose.py --history
  python diagnose.py --history --limit 20
        """,
    )

    parser.add_argument("--tx", type=str, help="Ethereum transaction hash to diagnose")
    parser.add_argument(
        "--output",
        type=str,
        choices=["rich", "json"],
        default="rich",
        help="Output format: 'rich' (default) or 'json'",
    )
    parser.add_argument("--history", action="store_true", help="Show recent diagnoses")
    parser.add_argument("--limit", type=int, default=10, help="Number of history entries (default: 10)")

    args = parser.parse_args()

    print_banner()

    if args.history:
        cmd_history(limit=args.limit)
    elif args.tx:
        cmd_diagnose(args.tx, args.output)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
