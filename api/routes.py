"""
api/routes.py — FastAPI endpoints
"""

from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel
from typing import List, Dict, Any, Optional

from core.models import DiagnosisReport, DiagnoseRequest, DiagnoseResponse
from core.pipeline import DiagnosisPipeline
from db.database import Database

router = APIRouter()

@router.post("/diagnose", response_model=DiagnoseResponse)
async def diagnose_transaction(request: DiagnoseRequest):
    """
    Diagnose a given Ethereum transaction hash.
    Checks cache first, otherwise runs the full pipeline.
    """
    tx_hash = request.tx_hash.strip().lower()

    # 1. Check database first (cache hit)
    try:
        db = Database()
        cached = db.get_report(tx_hash)
        if cached:
            # Rebuild full DiagnosisReport from DB row
            from core.models import TransactionData, FailureDiagnosis, ExplanationResult, ContractContext
            
            # Map DB row back to the Pydantic models the frontend expects
            tx_data = TransactionData(
                tx_hash=tx_hash,
                from_address=cached.get("from_address") or "",
                to_address=cached.get("contract_address"),
                gas_used=cached.get("gas_used") or 0,
                gas_limit=cached.get("gas_limit") or 0,
                status=0 if cached.get("status") == "failed" else 1,
                revert_reason=cached.get("raw_error"),
                function_name=cached.get("function_name") or "Unknown"
            )
            
            diagnosis = FailureDiagnosis(
                category=cached.get("failure_category") or "UNKNOWN",
                sub_type=cached.get("failure_sub_type") or "UNKNOWN",
                raw_error=cached.get("raw_error") or "",
                confidence=cached.get("confidence") or 0.0,
                description=cached.get("technical_summary") or ""
            )
            
            explanation = ExplanationResult(
                explanation=cached.get("explanation") or "",
                fix_steps=eval(cached.get("fix_steps") or "[]"),
                confidence=cached.get("confidence") or 0.0,
                technical_summary=cached.get("technical_summary") or "",
                llm_provider=cached.get("llm_provider") or "System"
            )
            
            contract_ctx = ContractContext(
                contract_address=cached.get("contract_address") or "",
                contract_name=cached.get("contract_name"),
                function_name=cached.get("function_name")
            )

            return DiagnoseResponse(
                success=True,
                tx_hash=tx_hash,
                report=DiagnosisReport(
                    tx_hash=tx_hash,
                    timestamp=cached.get("timestamp") or "",
                    tx_data=tx_data,
                    diagnosis=diagnosis,
                    explanation=explanation,
                    contract_context=contract_ctx
                )
            )
    except Exception as e:
        print(f"DB Error: {e}")

    # 2. Cache miss -> run pipeline
    try:
        pipeline = DiagnosisPipeline()
        report = pipeline.run(tx_hash)

        # Ensure we have at least partial success
        if not report.tx_data:
            raise HTTPException(status_code=400, detail="Could not retrieve transaction data. Is the hash correct?")

        return DiagnoseResponse(
            success=True,
            tx_hash=tx_hash,
            report=report
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/history", response_model=List[Dict[str, Any]])
async def get_history(limit: int = 20):
    """Get history of diagnosed transactions."""
    try:
        db = Database()
        reports = db.get_all_reports(limit)
        return reports
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
