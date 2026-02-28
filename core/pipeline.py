"""
core/pipeline.py — DiagnosisPipeline
Orchestrates the full 5-agent pipeline for transaction diagnosis.
"""

from rich.console import Console

from core.models import DiagnosisReport
from agents.tx_data_agent import TxDataAgent
from agents.failure_detection_agent import FailureDetectionAgent
from agents.contract_inspector_agent import ContractInspectorAgent
from agents.explanation_agent import ExplanationAgent
from agents.executor_agent import ExecutorAgent

console = Console()


class DiagnosisPipeline:
    """
    Orchestrates the 5-agent pipeline:
      1. TxDataAgent          → Fetch raw blockchain data
      2. FailureDetectionAgent → Classify failure with rules
      3. ContractInspectorAgent → Enrich with contract context
      4. ExplanationAgent      → Generate AI explanation
      5. ExecutorAgent         → Save and present results
    """

    def __init__(self):
        self.tx_agent = TxDataAgent()
        self.detection_agent = FailureDetectionAgent()
        self.inspector_agent = ContractInspectorAgent()
        self.explanation_agent = ExplanationAgent()
        self.executor_agent = ExecutorAgent()

    def run(self, tx_hash: str) -> DiagnosisReport:
        """
        Execute the full pipeline for a given transaction hash.
        
        Args:
            tx_hash: Ethereum transaction hash (0x...)
            
        Returns:
            Complete DiagnosisReport with all agent results
        """
        report = DiagnosisReport(tx_hash=tx_hash)

        # ── Step 1: Fetch transaction data ────────────────────────────
        try:
            report.tx_data = self.tx_agent.fetch(tx_hash)
        except Exception as e:
            report.pipeline_errors.append(f"TxDataAgent: {e}")
            console.print(f"[red]❌ TxDataAgent failed: {e}[/red]")
            return report  # Cannot continue without tx data

        # ── Step 2: Failure detection ────────────────────────────────
        try:
            report.diagnosis = self.detection_agent.detect(report.tx_data)
        except Exception as e:
            report.pipeline_errors.append(f"FailureDetectionAgent: {e}")
            console.print(f"[yellow]⚠️  FailureDetectionAgent failed: {e}[/yellow]")

        # ── Step 3: Contract inspection (optional) ───────────────────
        try:
            report.contract_context = self.inspector_agent.inspect(report.tx_data)
        except Exception as e:
            report.pipeline_errors.append(f"ContractInspectorAgent: {e}")
            console.print(f"[dim]⚠️  ContractInspectorAgent failed (non-fatal): {e}[/dim]")

        # ── Step 4: AI explanation ───────────────────────────────────
        try:
            if report.diagnosis:
                report.explanation = self.explanation_agent.explain(
                    report.tx_data,
                    report.diagnosis,
                    report.contract_context,
                )
        except Exception as e:
            report.pipeline_errors.append(f"ExplanationAgent: {e}")
            console.print(f"[yellow]⚠️  ExplanationAgent failed: {e}[/yellow]")

        # ── Step 5: Save and display ─────────────────────────────────
        try:
            report = self.executor_agent.execute(report)
        except Exception as e:
            report.pipeline_errors.append(f"ExecutorAgent: {e}")
            console.print(f"[yellow]⚠️  ExecutorAgent failed: {e}[/yellow]")

        return report
