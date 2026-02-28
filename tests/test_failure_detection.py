"""
tests/test_failure_detection.py
Unit tests for FailureDetectionAgent — tests all rule categories.
"""

import pytest
from agents.failure_detection_agent import FailureDetectionAgent
from core.models import TransactionData


def make_tx(**kwargs) -> TransactionData:
    """Helper to create a TransactionData with test defaults."""
    defaults = dict(
        tx_hash="0x" + "a" * 64,
        from_address="0x" + "1" * 40,
        to_address="0x" + "2" * 40,
        value=0,
        gas_limit=300000,
        gas_used=100000,
        gas_price=50_000_000_000,
        status=0,
        block_number=17_000_000,
    )
    defaults.update(kwargs)
    return TransactionData(**defaults)


@pytest.fixture
def agent():
    return FailureDetectionAgent()


# ── Gas Rules ─────────────────────────────────────────────────────────────

def test_out_of_gas(agent):
    tx = make_tx(gas_limit=300_000, gas_used=299_999)
    result = agent.detect(tx)
    assert result.category == "GAS"
    assert result.sub_type == "OUT_OF_GAS"
    assert result.confidence >= 0.90


def test_gas_used_not_full(agent):
    """If gasUsed is way below limit, should NOT be OUT_OF_GAS."""
    tx = make_tx(gas_limit=300_000, gas_used=50_000, revert_reason="execution reverted")
    result = agent.detect(tx)
    assert result.sub_type != "OUT_OF_GAS"


def test_gas_price_too_low(agent):
    tx = make_tx(revert_reason="transaction underpriced")
    result = agent.detect(tx)
    assert result.category == "GAS"
    assert result.sub_type == "GAS_PRICE_TOO_LOW"


# ── Slippage Rules ────────────────────────────────────────────────────────

def test_slippage_uniswap(agent):
    tx = make_tx(revert_reason="execution reverted: INSUFFICIENT_OUTPUT_AMOUNT")
    result = agent.detect(tx)
    assert result.category == "SLIPPAGE"
    assert result.sub_type == "SLIPPAGE_TOO_LOW"


def test_slippage_generic(agent):
    tx = make_tx(revert_reason="execution reverted: Too little received")
    result = agent.detect(tx)
    assert result.category == "SLIPPAGE"


# ── Deadline Rules ────────────────────────────────────────────────────────

def test_deadline_expired(agent):
    tx = make_tx(revert_reason="UniswapV2Router: EXPIRED")
    result = agent.detect(tx)
    assert result.category == "DEADLINE"
    assert result.sub_type == "DEADLINE_EXPIRED"


# ── Balance Rules ─────────────────────────────────────────────────────────

def test_missing_approval(agent):
    tx = make_tx(revert_reason="execution reverted: TRANSFER_FROM_FAILED")
    result = agent.detect(tx)
    assert result.category == "BALANCE"
    assert result.sub_type == "MISSING_TOKEN_APPROVAL"


def test_insufficient_allowance(agent):
    tx = make_tx(revert_reason="ERC20: insufficient allowance")
    result = agent.detect(tx)
    assert result.category == "BALANCE"
    assert result.sub_type == "MISSING_TOKEN_APPROVAL"


def test_insufficient_token_balance(agent):
    tx = make_tx(revert_reason="ERC20: transfer amount exceeds balance")
    result = agent.detect(tx)
    assert result.category == "BALANCE"
    assert result.sub_type == "INSUFFICIENT_TOKEN_BALANCE"


# ── Access Control Rules ──────────────────────────────────────────────────

def test_only_owner(agent):
    tx = make_tx(revert_reason="Ownable: caller is not the owner")
    result = agent.detect(tx)
    assert result.category == "ACCESS"
    assert result.sub_type == "ONLY_OWNER"


def test_paused(agent):
    tx = make_tx(revert_reason="Pausable: paused")
    result = agent.detect(tx)
    assert result.category == "ACCESS"
    assert result.sub_type == "CONTRACT_PAUSED"


def test_blacklisted(agent):
    tx = make_tx(revert_reason="Account is blacklisted")
    result = agent.detect(tx)
    assert result.category == "ACCESS"
    assert result.sub_type == "BLACKLISTED"


# ── Logic Rules ───────────────────────────────────────────────────────────

def test_arithmetic_overflow(agent):
    tx = make_tx(revert_reason="Arithmetic overflow")
    result = agent.detect(tx)
    assert result.category == "LOGIC"
    assert result.sub_type == "ARITHMETIC_OVERFLOW"


def test_invalid_param(agent):
    tx = make_tx(revert_reason="Invalid address")
    result = agent.detect(tx)
    assert result.category == "LOGIC"
    assert result.sub_type == "INVALID_PARAMETER"


# ── Unknown Fallback ──────────────────────────────────────────────────────

def test_unknown_fallback(agent):
    tx = make_tx(revert_reason=None)
    result = agent.detect(tx)
    assert result.category == "UNKNOWN"
    assert result.confidence < 0.6  # Low confidence for unknown


def test_success_not_diagnosed(agent):
    tx = make_tx(status=1)
    result = agent.detect(tx)
    assert result.category == "NONE"
    assert result.sub_type == "SUCCESS"
