"""
agents/explanation_agent.py — ExplanationAgent (AI Layer)
Uses LLM to translate the technical diagnosis into human-readable output.

LLM Priority:
  1. Google Gemini (gemini-1.5-flash) — preferred
  2. Groq (llama-3.3-70b-versatile) — fallback
  3. OpenAI (gpt-4o-mini) — fallback
  4. Rule-based template — final fallback (no API needed)
"""

import json
import re
import time
from typing import Optional
from rich.console import Console

from core.config import config
from core.models import (
    TransactionData,
    FailureDiagnosis,
    ContractContext,
    ExplanationResult,
)

console = Console()


# ─── Built-in Fallback Templates ──────────────────────────────────────────
# Used when no LLM API key is available. Category → template.

FALLBACK_TEMPLATES: dict[str, dict] = {
    "GAS": {
        "OUT_OF_GAS": {
            "explanation": (
                "Your transaction ran out of gas before it could finish. "
                "Gas is the computational fee that powers Ethereum operations. "
                "Your gas limit was too low for the complexity of this operation."
            ),
            "fix_steps": [
                "Increase the gas limit by 30-50% when resubmitting",
                "In MetaMask: click 'Edit' → 'Advanced' → increase Gas Limit",
                "Try using 'Auto' gas setting in your wallet",
            ],
        },
        "GAS_PRICE_TOO_LOW": {
            "explanation": (
                "Your transaction offered too low a gas price and was rejected by the network. "
                "Miners/validators prioritize higher-paying transactions."
            ),
            "fix_steps": [
                "Increase the gas price (GWEI) when resubmitting",
                "Check current network gas prices at etherscan.io/gastracker",
                "Use the 'Fast' or 'Standard' gas preset in your wallet",
            ],
        },
    },
    "BALANCE": {
        "MISSING_TOKEN_APPROVAL": {
            "explanation": (
                "The DeFi contract doesn't have permission to spend your tokens. "
                "Before interacting with DeFi protocols, you must first 'approve' "
                "them to access your tokens."
            ),
            "fix_steps": [
                "Go to the DeFi app and click 'Approve' for the token first",
                "Approve the exact amount you want to spend (or max approval)",
                "Wait for the approval transaction to confirm, then retry your original transaction",
            ],
        },
        "INSUFFICIENT_TOKEN_BALANCE": {
            "explanation": (
                "Your wallet doesn't have enough tokens to complete this transaction. "
                "The amount you tried to send or swap exceeds your current balance."
            ),
            "fix_steps": [
                "Check your token balance in your wallet",
                "Reduce the transaction amount to match your available balance",
                "Account for gas fees — you also need ETH for gas",
            ],
        },
        "INSUFFICIENT_ETH": {
            "explanation": (
                "You didn't send enough ETH with this transaction. "
                "Some operations require ETH to be sent as payment."
            ),
            "fix_steps": [
                "Increase the ETH value sent with the transaction",
                "Check if you have enough ETH in your wallet for both the operation and gas fees",
            ],
        },
    },
    "SLIPPAGE": {
        "SLIPPAGE_TOO_LOW": {
            "explanation": (
                "The token price moved too much between when you initiated the swap "
                "and when it was executed. Your slippage tolerance was too tight. "
                "This is a built-in protection to prevent you from getting a bad price."
            ),
            "fix_steps": [
                "Increase your slippage tolerance to 0.5% or 1% and retry",
                "For volatile tokens, try 2-5% slippage",
                "Trade during lower volatility periods or split into smaller trades",
                "In Uniswap: click the settings gear → adjust slippage tolerance",
            ],
        },
    },
    "DEADLINE": {
        "DEADLINE_EXPIRED": {
            "explanation": (
                "Your transaction took too long to be included in a block and the "
                "deadline you set expired. DeFi swaps include a deadline to protect "
                "you from executing at a much later (and potentially worse) price."
            ),
            "fix_steps": [
                "Simply resubmit the transaction — it will get a new deadline",
                "Increase the transaction deadline in your wallet settings",
                "Use a higher gas price to ensure faster confirmation",
            ],
        },
    },
    "ACCESS": {
        "ONLY_OWNER": {
            "explanation": (
                "This function can only be called by the contract's owner address. "
                "Your wallet address doesn't have the required administrative permissions."
            ),
            "fix_steps": [
                "Verify you are using the correct wallet address",
                "This is likely an admin-only function — you cannot call it from your address",
                "Contact the protocol team if you believe you should have access",
            ],
        },
        "CONTRACT_PAUSED": {
            "explanation": (
                "The smart contract is currently paused by its administrators. "
                "Protocols pause contracts during upgrades, security incidents, or maintenance."
            ),
            "fix_steps": [
                "Wait for the protocol to unpause — follow their official Twitter/Discord",
                "Check the protocol's status page for announcements",
                "Do not interact until the pause is lifted",
            ],
        },
        "BLACKLISTED": {
            "explanation": (
                "Your address has been blocked by this contract. "
                "Some tokens (like USDC, USDT) can blacklist addresses."
            ),
            "fix_steps": [
                "Contact the token/protocol team for clarification",
                "You may need to use a different wallet address",
            ],
        },
    },
    "LOGIC": {
        "INVALID_PARAMETER": {
            "explanation": (
                "One of the parameters you passed to the contract function was invalid. "
                "This could be a zero address, an amount outside allowed range, or other invalid input."
            ),
            "fix_steps": [
                "Double-check all input values (amounts, addresses, etc.)",
                "Ensure no fields are set to 0 if a value is required",
                "Verify you're using the correct token contract addresses",
            ],
        },
    },
    "UNKNOWN": {
        "UNKNOWN_REVERT": {
            "explanation": (
                "⚠️ Smart Contract Reversion: The contract rejected this transaction, but did not provide a standard human-readable explanation. "
                "This typically happens when a security check (like a slippage guard) is triggered or when the protocol uses custom internal error codes."
            ),
            "fix_steps": [
                "Verify your transaction inputs (amounts, token selection) are valid.",
                "Check the contract's official support channels for known issues.",
                "Ensure you have sufficient balance and have approved the contract to use it.",
                "Try increasing your slippage tolerance by 0.5% - 1%."
            ],
        },
    },
}


class ExplanationAgent:
    """
    Generates human-readable explanations for DeFi transaction failures.
    
    Tries LLM providers in order, falls back to templates if none available.
    """

    def explain(
        self,
        tx: TransactionData,
        diagnosis: FailureDiagnosis,
        contract: Optional[ContractContext] = None,
    ) -> ExplanationResult:
        """
        Main entry point.
        
        Args:
            tx: Raw transaction data
            diagnosis: Structured failure diagnosis
            contract: Optional contract context
            
        Returns:
            ExplanationResult with explanation, fix steps, confidence
        """
        console.print(f"\n[bold cyan]🤖 ExplanationAgent[/bold cyan] — Generating AI explanation...")

        # Build context dictionary for prompt
        context = self._build_context(tx, diagnosis, contract)

        # Short-circuit if there was no failure
        if diagnosis.category == "NONE" or diagnosis.sub_type == "SUCCESS":
            console.print("  [green]✅ Transaction succeeded — no failure to explain.[/green]")
            return ExplanationResult(
                explanation="This transaction was completely successful! There is no failure to diagnose.",
                fix_steps=["No action required. Your transaction went through perfectly."],
                confidence=1.0,
                technical_summary="Status 1: Success.",
                llm_provider="System"
            )

        # Try LLM providers in priority order
        result = (
            self._try_gemini(context, diagnosis)
            or self._try_groq(context, diagnosis)
            or self._try_openai(context, diagnosis)
            or self._use_template(diagnosis)
        )

        console.print(f"  [green]✅ Explanation generated[/green] via [{result.llm_provider}] | Confidence: {result.confidence * 100:.0f}%")
        return result

    def _build_context(
        self,
        tx: TransactionData,
        diagnosis: FailureDiagnosis,
        contract: Optional[ContractContext],
    ) -> dict:
        """Assemble context dict for the LLM prompt."""
        return {
            "tx_hash": tx.tx_hash,
            "from_address": tx.from_address,
            "to_address": tx.to_address or "Unknown",
            "function_name": tx.function_name or (contract.function_name if contract else None) or "Unknown",
            "failure_category": diagnosis.category,
            "failure_sub_type": diagnosis.sub_type,
            "raw_error": diagnosis.raw_error or "None",
            "gas_used": tx.gas_used,
            "gas_limit": tx.gas_limit,
            "gas_percent": f"{tx.gas_used / tx.gas_limit * 100:.1f}%" if tx.gas_limit > 0 else "N/A",
            "revert_reason": tx.revert_reason or "No revert reason available",
            "contract_name": contract.contract_name if contract else "Unknown",
            "contract_verified": contract.is_verified if contract else False,
            "require_conditions": contract.require_conditions[:10] if contract else [],
            "custom_errors": contract.custom_errors if contract else [],
            "diagnosis_description": diagnosis.description,
            "confidence": diagnosis.confidence,
        }

    def _build_prompt(self, context: dict) -> str:
        """Build the LLM prompt from context."""
        return f"""You are a DeFi expert helping a user understand why their Ethereum transaction failed.

## Transaction Details
- Hash: {context['tx_hash'][:20]}...
- From: {context['from_address'][:20]}...
- Function Called: {context['function_name']}
- Failure Category: {context['failure_category']}
- Failure Type: {context['failure_sub_type']}
- Revert Reason: {context['revert_reason']}
- Gas Used / Limit: {context['gas_used']:,} / {context['gas_limit']:,} ({context['gas_percent']})
- Contract: {context['contract_name']} (Verified: {context['contract_verified']})
- Known Code Requirements: {', '.join(context['require_conditions'])}
- Defined Custom Errors: {', '.join(context['custom_errors'])}
- Preliminary Diagnosis: {context['diagnosis_description']}

## Your Task
Respond with ONLY a valid JSON object (no markdown, no extra text):

{{
  "explanation": "Write 2-3 sentences in simple language explaining exactly WHY this transaction failed. Focus on the core error (e.g., not enough tokens, price moved too fast).",
  "fix_steps": ["Step 1 - The immediate next move for the user", "Step 2 - Technical adjustment (e.g. increase slippage to X%)", "Step 3 - Verification step"],
  "confidence": 0.0,
  "technical_summary": "One sentence technical summary for developers."
}}

Rules:
- explanation: friendly, clear, 2-3 sentences max
- fix_steps: 2-4 concrete actionable steps
- confidence: float between 0.0 and 1.0
- technical_summary: one sentence max"""

    def _parse_llm_response(self, text: str, provider: str) -> Optional[ExplanationResult]:
        """Parse and validate JSON from LLM response."""
        try:
            # Strip markdown code blocks if present
            text = re.sub(r"```json\s*", "", text)
            text = re.sub(r"```\s*", "", text)
            text = text.strip()

            # Find JSON object
            match = re.search(r'\{.*\}', text, re.DOTALL)
            if not match:
                return None

            data = json.loads(match.group())

            return ExplanationResult(
                explanation=data.get("explanation", ""),
                fix_steps=data.get("fix_steps", []),
                confidence=float(data.get("confidence", 0.7)),
                technical_summary=data.get("technical_summary", ""),
                llm_provider=provider,
            )
        except Exception as e:
            console.print(f"[dim]  Parse error ({provider}): {e}[/dim]")
            return None

    def _try_gemini(self, context: dict, diagnosis: FailureDiagnosis) -> Optional[ExplanationResult]:
        """Try Google Gemini API using the new google-genai SDK."""
        if not config.GEMINI_API_KEY or config.GEMINI_API_KEY == "your_gemini_api_key_here":
            return None
        try:
            from google import genai
            from google.genai import types

            client = genai.Client(api_key=config.GEMINI_API_KEY)
            
            # Model list to try in order (some keys have different access)
            models_to_try = [
                config.LLM_MODEL or "gemini-2.0-flash",
                "gemini-1.5-flash",
                "gemini-pro"
            ]
            
            prompt = self._build_prompt(context)

            # Retry loop for models and rate limits
            for model_name in models_to_try:
                for attempt in range(2):
                    try:
                        response = client.models.generate_content(
                            model=model_name,
                            contents=prompt,
                            config=types.GenerateContentConfig(
                                temperature=0.3,
                                max_output_tokens=600,
                            ),
                        )
                        return self._parse_llm_response(response.text, f"Gemini ({model_name})")
                    except Exception as e:
                        err = str(e).lower()
                        # If model not found, try next model immediately
                        if "not found" in err or "404" in err:
                            break
                        # If rate limit, wait and retry SAME model once
                        if ("quota" in err or "429" in err or "rate" in err) and attempt == 0:
                            console.print(f"[yellow]  ⚠️  {model_name} rate limit hit — waiting 5s to retry...[/yellow]")
                            time.sleep(5)
                            continue
                        # If second failure or other error, try next model
                        break
            return None

        except Exception as e:
            err = str(e)
            if "quota" in err.lower() or "429" in err or "rate" in err.lower():
                console.print("[yellow]  ⚠️  Gemini quota exceeded — falling back to next provider[/yellow]")
            else:
                console.print(f"[yellow]  ⚠️  Gemini failed: {err[:120]}[/yellow]")
            return None


    def _try_groq(self, context: dict, diagnosis: FailureDiagnosis) -> Optional[ExplanationResult]:
        """Try Groq API."""
        if not config.GROQ_API_KEY or config.GROQ_API_KEY == "your_groq_api_key_here":
            return None
        try:
            from groq import Groq
            client = Groq(api_key=config.GROQ_API_KEY)
            prompt = self._build_prompt(context)
            response = client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=600,
            )
            return self._parse_llm_response(response.choices[0].message.content, "Groq")
        except Exception as e:
            console.print(f"[yellow]  ⚠️  Groq failed: {e}[/yellow]")
            return None

    def _try_openai(self, context: dict, diagnosis: FailureDiagnosis) -> Optional[ExplanationResult]:
        """Try OpenAI API."""
        if not config.OPENAI_API_KEY or config.OPENAI_API_KEY == "your_openai_api_key_here":
            return None
        try:
            from openai import OpenAI
            client = OpenAI(api_key=config.OPENAI_API_KEY)
            prompt = self._build_prompt(context)
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=600,
            )
            return self._parse_llm_response(response.choices[0].message.content, "OpenAI")
        except Exception as e:
            console.print(f"[yellow]  ⚠️  OpenAI failed: {e}[/yellow]")
            return None

    def _use_template(self, diagnosis: FailureDiagnosis) -> ExplanationResult:
        """
        Rule-based fallback — uses pre-written templates.
        Used when no LLM API key is configured.
        """
        console.print("[dim]  ℹ️  No LLM available — using built-in template[/dim]")

        category = diagnosis.category
        sub_type = diagnosis.sub_type

        template = (
            FALLBACK_TEMPLATES.get(category, {}).get(sub_type)
            or FALLBACK_TEMPLATES.get(category, {}).get(list(FALLBACK_TEMPLATES.get(category, {}).keys())[0] if FALLBACK_TEMPLATES.get(category) else "")
            or FALLBACK_TEMPLATES["UNKNOWN"]["UNKNOWN_REVERT"]
        )

        explanation = template["explanation"]
        # If Gemini failed and we are using a template, append the real revert reason
        if diagnosis.raw_error and diagnosis.raw_error != "No revert reason provided":
            explanation += f" (Chain Error: {diagnosis.raw_error})"

        return ExplanationResult(
            explanation=explanation,
            fix_steps=template["fix_steps"],
            confidence=diagnosis.confidence * 0.8,  # Slightly lower — template, not AI
            technical_summary=f"Failure category: {category} / {sub_type}. {diagnosis.description}",
            llm_provider="Template (no LLM configured)",
        )
