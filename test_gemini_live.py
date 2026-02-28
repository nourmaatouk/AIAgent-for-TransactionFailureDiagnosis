"""
test_gemini_live.py — Quick live test of Gemini API for ExplainDeFi
Run: python test_gemini_live.py
"""
import time
from core.models import TransactionData, FailureDiagnosis
from agents.explanation_agent import ExplanationAgent

print("⏳ Waiting 65s for Gemini quota to reset (free tier: 1 req/min)...")
time.sleep(65)

print("\n🧪 Testing ExplanationAgent with Gemini...\n")

tx = TransactionData(
    tx_hash="0x" + "a" * 64,
    from_address="0x" + "1" * 40,
    to_address="0x7a250d5630b4cf539739df2c5dacb4c659f2488d",
    value=0,
    gas_limit=300000,
    gas_used=120000,
    gas_price=50_000_000_000,
    status=0,
    block_number=17_000_000,
    revert_reason="INSUFFICIENT_OUTPUT_AMOUNT",
    function_name="swapExactTokensForTokens (Uniswap V2)",
)

diag = FailureDiagnosis(
    category="SLIPPAGE",
    sub_type="SLIPPAGE_TOO_LOW",
    raw_error="INSUFFICIENT_OUTPUT_AMOUNT",
    confidence=0.93,
    description="The price moved beyond your slippage tolerance before the transaction executed.",
)

agent = ExplanationAgent()
result = agent.explain(tx, diag)

print("\n" + "="*60)
print("✅ GEMINI EXPLANATION RESULT")
print("="*60)
print(f"\n📝 Explanation:\n{result.explanation}")
print(f"\n🔧 Fix Steps:")
for i, step in enumerate(result.fix_steps, 1):
    print(f"  {i}. {step}")
print(f"\n🤖 Provider   : {result.llm_provider}")
print(f"📊 Confidence : {result.confidence * 100:.0f}%")
print(f"🔬 Technical  : {result.technical_summary}")
print("="*60)
