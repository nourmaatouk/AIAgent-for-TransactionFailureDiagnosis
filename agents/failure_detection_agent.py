"""
agents/failure_detection_agent.py — FailureDetectionAgent
Deterministic rule-based engine to classify DeFi transaction failures.

This agent applies a priority-ordered set of rules against the raw
transaction data and produces a structured FailureDiagnosis object.
No LLM calls — pure logic, fast and reliable.
"""

import re
from typing import Optional
from rich.console import Console

from core.models import TransactionData, FailureDiagnosis

console = Console()


# ─── Failure Categories ────────────────────────────────────────────────────
class Category:
    GAS = "GAS"
    BALANCE = "BALANCE"
    SLIPPAGE = "SLIPPAGE"
    ACCESS = "ACCESS"
    LOGIC = "LOGIC"
    DEADLINE = "DEADLINE"
    UNKNOWN = "UNKNOWN"


# ─── Sub-types ────────────────────────────────────────────────────────────
class SubType:
    OUT_OF_GAS = "OUT_OF_GAS"
    GAS_TOO_LOW = "GAS_PRICE_TOO_LOW"
    INSUFFICIENT_ETH = "INSUFFICIENT_ETH"
    INSUFFICIENT_TOKEN = "INSUFFICIENT_TOKEN_BALANCE"
    MISSING_APPROVAL = "MISSING_TOKEN_APPROVAL"
    ALLOWANCE_EXCEEDED = "ALLOWANCE_EXCEEDED"
    SLIPPAGE = "SLIPPAGE_TOO_LOW"
    DEADLINE_EXPIRED = "DEADLINE_EXPIRED"
    ONLY_OWNER = "ONLY_OWNER"
    CONTRACT_PAUSED = "CONTRACT_PAUSED"
    BLACKLISTED = "BLACKLISTED"
    REENTRANCY = "REENTRANCY_GUARD"
    INVALID_PARAM = "INVALID_PARAMETER"
    OVERFLOW = "ARITHMETIC_OVERFLOW"
    UNKNOWN = "UNKNOWN_REVERT"


class FailureDetectionAgent:
    """
    Applies deterministic rules to classify why a transaction failed.
    
    Rules are checked in priority order — first match wins.
    Each rule returns a FailureDiagnosis or None (if rule doesn't apply).
    """

    def detect(self, tx: TransactionData) -> FailureDiagnosis:
        """
        Main entry point. 
        
        Args:
            tx: Populated TransactionData from TxDataAgent
            
        Returns:
            FailureDiagnosis with category, sub_type, confidence, details
        """
        console.print(f"\n[bold cyan]🔎 FailureDetectionAgent[/bold cyan] — Analyzing failure...")

        # If transaction actually succeeded, no diagnosis needed
        if tx.status == 1:
            return FailureDiagnosis(
                category="NONE",
                sub_type="SUCCESS",
                confidence=1.0,
                description="Transaction succeeded — no failure to diagnose.",
            )

        revert = (tx.revert_reason or "").strip()
        revert_lower = revert.lower()

        # ── Apply rules in priority order ────────────────────────────────
        result = (
            self._check_out_of_gas(tx)
            or self._check_gas_price(revert_lower)
            or self._check_slippage(revert_lower)
            or self._check_deadline(revert_lower)
            or self._check_missing_approval(revert_lower)
            or self._check_insufficient_token(revert_lower)
            or self._check_insufficient_eth(tx, revert_lower)
            or self._check_only_owner(revert_lower)
            or self._check_paused(revert_lower)
            or self._check_blacklisted(revert_lower)
            or self._check_reentrancy(revert_lower)
            or self._check_overflow(revert_lower)
            or self._check_invalid_param(revert_lower)
            or self._fallback(revert, tx)
        )
        
        # If still unknown but has raw error, try mapping by general keywords
        # If still unknown but has raw error (even hex), try mapping selectors
        if result and result.category == Category.UNKNOWN:
            result = self._map_hex_selectors(revert) or self._map_generic_keywords(revert_lower) or result

        self._print_result(result)
        return result

    def _map_hex_selectors(self, revert: str) -> Optional[FailureDiagnosis]:
        """Try to map standard or known DeFi custom error selectors."""
        if not revert or not revert.startswith("0x") or len(revert) < 10:
            return None
        
        selector = revert[:10].lower()
        
        # Standard Solidity / DeFi selectors
        mapping = {
            "0x08c379a0": (Category.UNKNOWN, SubType.UNKNOWN, "Generic Error message."),
            "0x4e487b71": (Category.LOGIC, SubType.OVERFLOW, "Arithmetic Panic (overflow/underflow)."),
            "0x0dc14910": (Category.SLIPPAGE, SubType.SLIPPAGE, "Uniswap V3: Insufficient output amount."),
            "0x124d7730": (Category.DEADLINE, SubType.DEADLINE_EXPIRED, "Uniswap V3: Transaction expired."),
            "0xf4282570": (Category.ACCESS, SubType.ONLY_OWNER, "Access restricted (Only Owner)."),
            "0x8baa579f": (Category.LOGIC, SubType.INVALID_PARAM, "Invalid function parameter."),
        }
        
        if selector in mapping:
            cat, sub, desc = mapping[selector]
            return FailureDiagnosis(
                category=cat, sub_type=sub, raw_error=revert, confidence=0.85, description=desc
            )
        return None

    # ── Individual Detection Rules ────────────────────────────────────────

    def _check_out_of_gas(self, tx: TransactionData) -> Optional[FailureDiagnosis]:
        """
        Gas exhaustion: gasUsed ≥ 99% of gasLimit.
        When a tx runs out of gas, gasUsed equals gasLimit exactly.
        """
        if tx.gas_limit > 0 and tx.gas_used >= tx.gas_limit * 0.99:
            return FailureDiagnosis(
                category=Category.GAS,
                sub_type=SubType.OUT_OF_GAS,
                raw_error=tx.revert_reason,
                confidence=0.97,
                details={
                    "gas_used": tx.gas_used,
                    "gas_limit": tx.gas_limit,
                    "percent_used": round(tx.gas_used / tx.gas_limit * 100, 2),
                },
                description=f"Transaction ran out of gas ({tx.gas_used:,} used = {tx.gas_limit:,} limit).",
            )
        return None

    def _check_gas_price(self, revert: str) -> Optional[FailureDiagnosis]:
        """Gas price too low — transaction not accepted by miners."""
        patterns = ["transaction underpriced", "gas price too low", "intrinsic gas too low"]
        if any(p in revert for p in patterns):
            return FailureDiagnosis(
                category=Category.GAS,
                sub_type=SubType.GAS_TOO_LOW,
                raw_error=revert,
                confidence=0.95,
                description="Transaction gas price was too low to be accepted by the network.",
            )
        return None

    def _check_slippage(self, revert: str) -> Optional[FailureDiagnosis]:
        """Slippage protection triggered — price moved too much."""
        patterns = [
            "insufficient_output_amount",
            "excessive_input_amount",
            "too little received",
            "slippage",
            "price impact too high",
            "k",  # Uniswap V2 invariant check (broad — low priority)
        ]
        # Use specific patterns first
        specific = [
            "insufficient_output_amount",
            "excessive_input_amount",
            "too little received",
            "slippage",
            "price impact too high",
            "insufficient_output_amount",
            "insufficient output",
            "amount out is below",
            "min return",
            "minimum return",
            "k",  # Uniswap V2 constant product formula violation
        ]
        if any(p in revert for p in specific):
            return FailureDiagnosis(
                category=Category.SLIPPAGE,
                sub_type=SubType.SLIPPAGE,
                raw_error=revert,
                confidence=0.93,
                description="The price moved beyond your slippage tolerance before the transaction executed.",
            )
        return None

    def _check_deadline(self, revert: str) -> Optional[FailureDiagnosis]:
        """Transaction submitted after its deadline expired."""
        patterns = ["expired", "deadline", "transaction too old"]
        if any(p in revert for p in patterns):
            return FailureDiagnosis(
                category=Category.DEADLINE,
                sub_type=SubType.DEADLINE_EXPIRED,
                raw_error=revert,
                confidence=0.92,
                description="The transaction deadline expired — it was confirmed too late.",
            )
        return None

    def _check_missing_approval(self, revert: str) -> Optional[FailureDiagnosis]:
        """Token approval/allowance missing or insufficient."""
        patterns = [
            "transfer_from_failed",
            "transferfrom failed",
            "allowance",
            "approve",
            "erc20: insufficient allowance",
            "not approved",
            "stf",  # Short for SafeTransferFrom failed
            "insufficient allowance",
            "not allowance",
        ]
        if any(p in revert for p in patterns):
            return FailureDiagnosis(
                category=Category.BALANCE,
                sub_type=SubType.MISSING_APPROVAL,
                raw_error=revert,
                confidence=0.90,
                description="The spender contract was not approved to use your tokens.",
            )
        return None

    def _check_insufficient_token(self, revert: str) -> Optional[FailureDiagnosis]:
        """Token balance is too low."""
        patterns = [
            "erc20: transfer amount exceeds balance",
            "transfer amount exceeds balance",
            "insufficient balance",
            "balance too low",
            "insufficient token",
            "insufficient funds",
            "transfer_failed",
            "transfer failed",
        ]
        if any(p in revert for p in patterns):
            return FailureDiagnosis(
                category=Category.BALANCE,
                sub_type=SubType.INSUFFICIENT_TOKEN,
                raw_error=revert,
                confidence=0.93,
                description="Your token balance is too low for this transaction.",
            )
        return None

    def _check_insufficient_eth(self, tx: TransactionData, revert: str) -> Optional[FailureDiagnosis]:
        """Not enough ETH sent with transaction."""
        patterns = [
            "insufficient eth",
            "msg.value too low",
            "not enough eth",
            "value must be",
        ]
        if any(p in revert for p in patterns):
            return FailureDiagnosis(
                category=Category.BALANCE,
                sub_type=SubType.INSUFFICIENT_ETH,
                raw_error=revert,
                confidence=0.90,
                details={"value_sent_wei": tx.value},
                description="Not enough ETH was sent with the transaction.",
            )
        return None

    def _check_only_owner(self, revert: str) -> Optional[FailureDiagnosis]:
        """Access restricted to contract owner."""
        patterns = [
            "ownable: caller is not the owner",
            "caller is not the owner",
            "only owner",
            "not owner",
            "onlyowner",
            "forbidden",
        ]
        if any(p in revert for p in patterns):
            return FailureDiagnosis(
                category=Category.ACCESS,
                sub_type=SubType.ONLY_OWNER,
                raw_error=revert,
                confidence=0.96,
                description="Only the contract owner can call this function.",
            )
        return None

    def _check_paused(self, revert: str) -> Optional[FailureDiagnosis]:
        """Contract is paused by the admin."""
        patterns = ["pausable: paused", "contract is paused", "paused", "is paused"]
        if any(p in revert for p in patterns):
            return FailureDiagnosis(
                category=Category.ACCESS,
                sub_type=SubType.CONTRACT_PAUSED,
                raw_error=revert,
                confidence=0.95,
                description="The contract is currently paused — no operations are allowed.",
            )
        return None

    def _check_blacklisted(self, revert: str) -> Optional[FailureDiagnosis]:
        """Address is blacklisted."""
        patterns = ["blacklisted", "blocked", "sanctioned", "banned"]
        if any(p in revert for p in patterns):
            return FailureDiagnosis(
                category=Category.ACCESS,
                sub_type=SubType.BLACKLISTED,
                raw_error=revert,
                confidence=0.92,
                description="Your address is blocked by this contract.",
            )
        return None

    def _check_reentrancy(self, revert: str) -> Optional[FailureDiagnosis]:
        """Reentrancy guard triggered."""
        patterns = ["reentrant call", "reentrancy", "nonreentrant"]
        if any(p in revert for p in patterns):
            return FailureDiagnosis(
                category=Category.ACCESS,
                sub_type=SubType.REENTRANCY,
                raw_error=revert,
                confidence=0.91,
                description="Reentrancy guard blocked this transaction (likely a contract interaction loop).",
            )
        return None

    def _check_overflow(self, revert: str) -> Optional[FailureDiagnosis]:
        """Arithmetic overflow/underflow."""
        patterns = ["arithmetic", "overflow", "underflow", "division by zero", "math"]
        if any(p in revert for p in patterns):
            return FailureDiagnosis(
                category=Category.LOGIC,
                sub_type=SubType.OVERFLOW,
                raw_error=revert,
                confidence=0.88,
                description="An arithmetic overflow or underflow occurred in the contract.",
            )
        return None

    def _check_invalid_param(self, revert: str) -> Optional[FailureDiagnosis]:
        """Invalid function parameter."""
        patterns = [
            "invalid",
            "zero address",
            "invalid address",
            "invalid amount",
            "must be greater",
            "must be less",
            "out of bounds",
        ]
        if any(p in revert for p in patterns):
            return FailureDiagnosis(
                category=Category.LOGIC,
                sub_type=SubType.INVALID_PARAM,
                raw_error=revert,
                confidence=0.80,
                description="An invalid parameter was passed to the contract function.",
            )
        return None

    def _fallback(self, revert: str, tx: TransactionData) -> FailureDiagnosis:
        """Last resort — unknown failure."""
        return FailureDiagnosis(
            category=Category.UNKNOWN,
            sub_type=SubType.UNKNOWN,
            raw_error=revert if revert else "No revert reason available",
            confidence=0.10,
            description="The specific reason for this failure could not be determined automatically.",
        )

    def _map_generic_keywords(self, revert: str) -> Optional[FailureDiagnosis]:
        """One last attempt to map unknown reverts using common single keywords."""
        if not revert: return None
        
        mapping = {
            "slippage": (Category.SLIPPAGE, SubType.SLIPPAGE, "Slippage-related swap failure."),
            "gas": (Category.GAS, SubType.OUT_OF_GAS, "Potential gas-related failure."),
            "allowance": (Category.BALANCE, SubType.MISSING_APPROVAL, "Token approval issue."),
            "balance": (Category.BALANCE, SubType.INSUFFICIENT_TOKEN, "Insufficient token balance."),
            "owner": (Category.ACCESS, SubType.ONLY_OWNER, "Admin-only permission issue."),
            "paused": (Category.ACCESS, SubType.CONTRACT_PAUSED, "Contract is currently paused."),
        }
        
        for kw, (cat, sub, desc) in mapping.items():
            if kw in revert:
                return FailureDiagnosis(
                    category=cat, sub_type=sub, raw_error=revert, confidence=0.4, description=desc
                )
        return None

    def _print_result(self, result: FailureDiagnosis):
        """Print detection result to console."""
        color = {
            "GAS": "red",
            "BALANCE": "yellow",
            "SLIPPAGE": "magenta",
            "ACCESS": "blue",
            "LOGIC": "cyan",
            "DEADLINE": "orange3",
            "UNKNOWN": "white",
        }.get(result.category, "white")

        console.print(f"\n[bold]── Failure Detection Result ──[/bold]")
        console.print(f"  Category  : [{color}]{result.category}[/{color}]")
        console.print(f"  Sub-type  : {result.sub_type}")
        console.print(f"  Confidence: {result.confidence * 100:.0f}%")
        console.print(f"  Summary   : {result.description}")
