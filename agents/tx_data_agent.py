"""
agents/tx_data_agent.py — TxDataAgent
Fetches all on-chain data for a given transaction hash.

Data Sources:
  - Ethereum RPC (via Alchemy) for tx, receipt, revert reason
  - Etherscan API for additional context (optional)
"""

import json
import requests
from typing import Optional, Tuple
from web3 import Web3
from web3.exceptions import TransactionNotFound
from rich.console import Console

from core.config import config
from core.models import TransactionData

console = Console()


# ─── Known 4-byte function selectors ───────────────────────────────────────
# Maps selector → human-readable function name for common DeFi protocols
KNOWN_SELECTORS: dict[str, str] = {
    "0x38ed1739": "swapExactTokensForTokens (Uniswap V2)",
    "0x8803dbee": "swapTokensForExactTokens (Uniswap V2)",
    "0x7ff36ab5": "swapExactETHForTokens (Uniswap V2)",
    "0x18cbafe5": "swapExactTokensForETH (Uniswap V2)",
    "0x5c11d795": "swapExactTokensForTokensSupportingFeeOnTransferTokens (Uniswap V2)",
    "0x414bf389": "exactInputSingle (Uniswap V3)",
    "0xc04b8d59": "exactInput (Uniswap V3)",
    "0xdb3e2198": "exactOutputSingle (Uniswap V3)",
    "0x09b81346": "exactOutput (Uniswap V3)",
    "0xa9059cbb": "transfer (ERC-20)",
    "0x23b872dd": "transferFrom (ERC-20)",
    "0x095ea7b3": "approve (ERC-20)",
    "0xe8e33700": "addLiquidity (Uniswap V2)",
    "0xf305d719": "addLiquidityETH (Uniswap V2)",
    "0xbaa2abde": "removeLiquidity (Uniswap V2)",
    "0x2e1a7d4d": "withdraw (WETH)",
    "0xd0e30db0": "deposit (WETH)",
    "0x1249c58b": "mint (various)",
    "0x4e71d92d": "claim (various)",
    "0x3d18b912": "getReward (Staking)",
    "0x2e7ba6ef": "claim (Airdrop)",
    "0xa694fc3a": "stake (Staking)",
    "0x2def6620": "unstake (Staking)",
}


class TxDataAgent:
    """
    Agent responsible for fetching all on-chain data for a transaction.
    
    Pipeline:
      1. Connect to Ethereum via RPC
      2. Fetch transaction object
      3. Fetch transaction receipt
      4. Decode revert reason (replay via eth_call)
      5. Decode function selector
      6. Package into TransactionData model
    """

    def __init__(self):
        self.w3 = self._connect()

    def _connect(self) -> Web3:
        """Connect to Ethereum node, try Alchemy first then public fallback."""
        rpcs = []
        if config.ETHEREUM_RPC_URL:
            rpcs.append(config.ETHEREUM_RPC_URL)
        # Public fallback nodes (rate-limited but functional for testing)
        rpcs.append("https://eth.llamarpc.com")
        rpcs.append("https://rpc.ankr.com/eth")

        for rpc in rpcs:
            try:
                w3 = Web3(Web3.HTTPProvider(rpc, request_kwargs={"timeout": config.RPC_TIMEOUT}))
                if w3.is_connected():
                    console.print(f"[green]✅ Connected to Ethereum node[/green]: {rpc[:50]}...")
                    return w3
            except Exception:
                continue

        raise ConnectionError("❌ Could not connect to any Ethereum RPC node. Check your ALCHEMY_API_KEY in .env")

    def fetch(self, tx_hash: str) -> TransactionData:  # noqa
        """
        Main entry point. Fetches all data for a transaction hash.
        
        Args:
            tx_hash: Full Ethereum transaction hash (0x + 64 hex chars)
            
        Returns:
            TransactionData model populated with all available on-chain data
        """
        tx_hash = tx_hash.strip().lower()
        console.print(f"\n[bold cyan]🔍 TxDataAgent[/bold cyan] — Fetching: {tx_hash[:20]}...")

        # Step 1: Get raw transaction
        tx = self._get_transaction(tx_hash)

        # Step 2: Get transaction receipt
        receipt = self._get_receipt(tx_hash)

        # Step 3: Decode revert reason
        revert_reason = self._get_revert_reason(tx, receipt)

        # Step 4: Decode function selector
        selector, function_name = self._decode_selector(tx)

        # Step 5: Build and return model
        data = TransactionData(
            tx_hash=tx_hash,
            from_address=tx.get("from", ""),
            to_address=tx.get("to", None),
            value=int(tx.get("value", 0)),
            gas_limit=int(tx.get("gas", 0)),
            gas_used=int(receipt.get("gasUsed", 0)),
            gas_price=int(tx.get("gasPrice", 0)),
            status=int(receipt.get("status", 0)),
            block_number=int(receipt.get("blockNumber", 0)),
            revert_reason=revert_reason,
            function_selector=str(selector) if selector else None,
            function_name=function_name,
            input_data=tx.get("input", "0x").hex() if hasattr(tx.get("input"), "hex") else str(tx.get("input", "0x")),
            logs=self._sanitize_logs(receipt.get("logs", [])),
        )

        self._print_summary(data)
        return data

    def _sanitize_logs(self, logs: list) -> list:
        """Convert any HexBytes in logs to standard hex strings for JSON serialization."""
        clean_logs = []
        for log in logs:
            clean_log = {}
            for k, v in dict(log).items():
                if hasattr(v, "hex"):
                    clean_log[k] = v.hex()
                elif isinstance(v, list):
                    clean_log[k] = [x.hex() if hasattr(x, "hex") else str(x) for x in v]
                else:
                    clean_log[k] = v
            clean_logs.append(clean_log)
        return clean_logs

    def _get_transaction(self, tx_hash: str) -> dict:
        """Fetch raw transaction data."""
        try:
            tx = self.w3.eth.get_transaction(tx_hash)
            return dict(tx)
        except TransactionNotFound:
            raise ValueError(f"Transaction not found: {tx_hash}\nMake sure the hash is correct and exists on Ethereum mainnet.")
        except Exception as e:
            raise RuntimeError(f"Failed to fetch transaction: {e}")

    def _get_receipt(self, tx_hash: str) -> dict:
        """Fetch transaction receipt (contains status, gasUsed, logs)."""
        try:
            receipt = self.w3.eth.get_transaction_receipt(tx_hash)
            if receipt is None:
                raise ValueError("Transaction is still pending — no receipt available yet.")
            return dict(receipt)
        except Exception as e:
            raise RuntimeError(f"Failed to fetch receipt: {e}")

    def _get_revert_reason(self, tx: dict, receipt: dict) -> Optional[str]:
        """
        Decode the revert reason by replaying the transaction via eth_call
        at the block BEFORE it was mined. This triggers the same revert
        and we capture the error message.
        """
        # Only attempt if transaction actually failed
        if receipt.get("status") == 1:
            return None

        try:
            block = int(receipt.get("blockNumber", 0))
            call_params = {
                "from": tx.get("from"),
                "to": tx.get("to"),
                "data": tx.get("input", "0x"),
                "gas": hex(int(tx.get("gas", 0))),
                "gasPrice": hex(int(tx.get("gasPrice", 0))),
                "value": hex(int(tx.get("value", 0))),
            }

            # Use eth_call at the block before to replay
            self.w3.eth.call(call_params, block - 1)
            return None  # If no exception, was not a revert

        except Exception as e:
            error_str = str(e)

            # Extract the human-readable part from the error
            reason = self._parse_revert_string(error_str)
            console.print(f"[yellow]📋 Revert Reason:[/yellow] {reason}")
            return reason

    def _parse_revert_string(self, error: str) -> str:
        """
        Extract clean revert message from the raw exception string.
        Handles multiple formats from different RPC providers.
        """
        error = str(error)

        # Try JSON parsing first (Alchemy format)
        try:
            if "{" in error and "}" in error:
                start = error.index("{")
                end = error.rindex("}") + 1
                data = json.loads(error[start:end])
                # Navigate nested JSON structure
                msg = (
                    data.get("message")
                    or data.get("error", {}).get("message")
                    or data.get("data", {}).get("message")
                )
                if msg:
                    # Strip "execution reverted: " prefix
                    msg = msg.replace("execution reverted: ", "").strip()
                    return msg
        except Exception:
            pass

        # String extraction fallback
        for prefix in ["execution reverted: ", "revert ", "VM Exception: revert "]:
            if prefix in error:
                return error.split(prefix, 1)[1].split("\n")[0].strip()

        # Return cleaned version of full error
        return error[:300].strip()

    def _decode_selector(self, tx: dict) -> Tuple[Optional[str], Optional[str]]:
        """
        Decode the first 4 bytes of calldata to identify the function called.
        Returns (selector_hex, human_readable_name)
        """
        input_data = tx.get("input", "0x")
        if hasattr(input_data, "hex"):
            input_data = input_data.hex()
        else:
            input_data = str(input_data)
            
        if not input_data or input_data == "0x" or len(input_data) < 10:
            return None, "ETH Transfer (no function call)"

        selector = input_data[:10].lower()  # "0x" + 8 hex chars
        name = KNOWN_SELECTORS.get(selector, f"Unknown function ({selector})")
        return selector, name

    def _print_summary(self, data: TransactionData):
        """Print a formatted summary of fetched data to console."""
        status_icon = "✅" if data.status == 1 else "❌"
        gas_pct = (data.gas_used / data.gas_limit * 100) if data.gas_limit > 0 else 0

        console.print(f"\n[bold]── Transaction Summary ──[/bold]")
        console.print(f"  Status    : {status_icon} {'Success' if data.status == 1 else 'FAILED'}")
        console.print(f"  From      : {data.from_address}")
        console.print(f"  To        : {data.to_address}")
        console.print(f"  Function  : {data.function_name}")
        console.print(f"  Gas Used  : {data.gas_used:,} / {data.gas_limit:,} ({gas_pct:.1f}%)")
        console.print(f"  Block     : {data.block_number:,}")
        if data.revert_reason:
            console.print(f"  [red]Revert    : {data.revert_reason}[/red]")
