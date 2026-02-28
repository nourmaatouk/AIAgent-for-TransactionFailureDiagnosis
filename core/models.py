"""
core/models.py — Pydantic data models shared across all agents
"""

from pydantic import BaseModel, field_validator
from typing import Optional, List, Dict, Any
from datetime import datetime


# ──────────────────────────────────────────────
# 1. Raw Transaction Data (from TxDataAgent)
# ──────────────────────────────────────────────

class TransactionData(BaseModel):
    tx_hash: str
    from_address: str
    to_address: Optional[str] = None          # None if contract creation
    value: int = 0                             # ETH value in wei
    gas_limit: int = 0                         # Gas limit set by user
    gas_used: int = 0                          # Gas actually consumed
    gas_price: int = 0                         # Gas price in wei
    status: int = 0                            # 0 = failed, 1 = success
    block_number: int = 0
    revert_reason: Optional[str] = None        # Decoded revert string
    function_selector: Optional[str] = None    # First 4 bytes of input
    function_name: Optional[str] = None        # Decoded name if ABI known
    input_data: Optional[str] = None           # Full calldata (hex)
    logs: List[Dict[str, Any]] = []            # Event logs from receipt
    error_message: Optional[str] = None        # Raw error if any

    @field_validator("tx_hash")
    @classmethod
    def validate_tx_hash(cls, v: str) -> str:
        v = v.strip().lower()
        if not v.startswith("0x") or len(v) != 66:
            raise ValueError(f"Invalid transaction hash: {v}")
        return v


# ──────────────────────────────────────────────
# 2. Failure Diagnosis (from FailureDetectionAgent)
# ──────────────────────────────────────────────

class FailureDiagnosis(BaseModel):
    category: str                              # GAS, BALANCE, SLIPPAGE, ACCESS, LOGIC, UNKNOWN
    sub_type: str                              # OUT_OF_GAS, MISSING_APPROVAL, etc.
    raw_error: Optional[str] = None
    confidence: float = 0.0                    # 0.0 to 1.0
    details: Dict[str, Any] = {}               # Extra structured info
    description: str = ""                      # One-line human summary


# ──────────────────────────────────────────────
# 3. Contract Context (from ContractInspectorAgent)
# ──────────────────────────────────────────────

class ContractContext(BaseModel):
    contract_address: str
    contract_name: Optional[str] = None
    is_verified: bool = False
    function_name: Optional[str] = None
    function_signature: Optional[str] = None
    require_conditions: List[str] = []        # require() statements found
    custom_errors: List[str] = []             # Custom error definitions
    abi_available: bool = False


# ──────────────────────────────────────────────
# 4. LLM Explanation (from ExplanationAgent)
# ──────────────────────────────────────────────

class ExplanationResult(BaseModel):
    explanation: str                           # User-friendly plain English
    fix_steps: List[str] = []                  # Ordered list of fix actions
    confidence: float = 0.0
    technical_summary: str = ""               # Short technical recap
    llm_provider: str = ""                     # Which LLM was used


# ──────────────────────────────────────────────
# 5. Full Diagnosis Report (final output)
# ──────────────────────────────────────────────

class DiagnosisReport(BaseModel):
    tx_hash: str
    timestamp: str = ""
    tx_data: Optional[TransactionData] = None
    diagnosis: Optional[FailureDiagnosis] = None
    contract_context: Optional[ContractContext] = None
    explanation: Optional[ExplanationResult] = None
    pipeline_errors: List[str] = []           # Non-fatal errors during pipeline

    def model_post_init(self, __context: Any) -> None:
        if not self.timestamp:
            self.timestamp = datetime.utcnow().isoformat()

    def is_complete(self) -> bool:
        return (
            self.tx_data is not None
            and self.diagnosis is not None
            and self.explanation is not None
        )

    def summary(self) -> str:
        """Returns a one-line summary of the diagnosis."""
        if self.diagnosis and self.explanation:
            return f"[{self.diagnosis.category}] {self.explanation.explanation[:100]}..."
        return "Diagnosis incomplete"


# ──────────────────────────────────────────────
# 6. API Request/Response Models
# ──────────────────────────────────────────────

class DiagnoseRequest(BaseModel):
    tx_hash: str

    @field_validator("tx_hash")
    @classmethod
    def validate_hash(cls, v: str) -> str:
        v = v.strip().lower()
        if not v.startswith("0x") or len(v) != 66:
            raise ValueError("Invalid Ethereum transaction hash. Must be 0x + 64 hex characters.")
        return v


class DiagnoseResponse(BaseModel):
    success: bool
    tx_hash: str
    report: Optional[DiagnosisReport] = None
    error: Optional[str] = None
