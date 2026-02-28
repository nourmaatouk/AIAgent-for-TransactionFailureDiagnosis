"""
agents/contract_inspector_agent.py — ContractInspectorAgent
Fetches and parses smart contract context from Etherscan.

Purpose:
  - Retrieve ABI for the called contract
  - Decode the exact function being called
  - Find relevant require() conditions
  - Decode custom error selectors
  - Enrich the diagnosis with contract-level context
"""

import re
import json
import requests
from typing import Optional, Tuple
from rich.console import Console

from core.config import config
from core.models import TransactionData, ContractContext

console = Console()


class ContractInspectorAgent:
    """
    Fetches smart contract metadata from Etherscan to enrich the diagnosis.
    
    If the contract is not verified on Etherscan, this agent gracefully
    skips and returns an empty ContractContext (non-fatal).
    """

    def inspect(self, tx: TransactionData) -> ContractContext:
        """
        Main entry point.
        
        Args:
            tx: Transaction data containing contract address + selector
            
        Returns:
            ContractContext with ABI, function name, require statements
        """
        console.print(f"\n[bold cyan]🔬 ContractInspectorAgent[/bold cyan] — Inspecting contract...")

        address = tx.to_address
        if not address:
            console.print("[dim]  Skipped — no contract address (ETH transfer)[/dim]")
            return ContractContext(contract_address="")

        if not config.ETHERSCAN_API_KEY or config.ETHERSCAN_API_KEY == "your_etherscan_api_key_here":
            console.print("[yellow]  ⚠️  Etherscan API key not set — skipping contract inspection[/yellow]")
            return ContractContext(contract_address=address)

        # 1. Try to fetch ABI
        abi = self._fetch_abi(address)

        # 2. Try to fetch source code
        source_info = self._fetch_source(address)

        # 3. Decode function from ABI + selector
        function_name, function_sig = self._decode_function(abi, tx.function_selector)

        # 4. Extract require conditions from source
        require_conditions = self._extract_requires(source_info.get("source", ""), function_name)

        # 5. Decode custom errors from ABI
        custom_errors = self._extract_custom_errors(abi)

        ctx = ContractContext(
            contract_address=address,
            contract_name=source_info.get("name"),
            is_verified=source_info.get("is_verified", False),
            function_name=function_name or tx.function_name,
            function_signature=function_sig,
            require_conditions=require_conditions,
            custom_errors=custom_errors,
            abi_available=abi is not None,
        )

        self._print_result(ctx)
        return ctx

    def _fetch_abi(self, address: str) -> Optional[list]:
        """Fetch contract ABI from Etherscan."""
        try:
            params = {
                "module": "contract",
                "action": "getabi",
                "address": address,
                "apikey": config.ETHERSCAN_API_KEY,
            }
            resp = requests.get(
                config.ETHERSCAN_BASE_URL,
                params=params,
                timeout=config.ETHERSCAN_TIMEOUT
            )
            data = resp.json()
            if data.get("status") == "1" and data.get("result"):
                return json.loads(data["result"])
        except Exception as e:
            console.print(f"[dim]  ABI fetch error: {e}[/dim]")
        return None

    def _fetch_source(self, address: str) -> dict:
        """Fetch verified source code from Etherscan."""
        try:
            params = {
                "module": "contract",
                "action": "getsourcecode",
                "address": address,
                "apikey": config.ETHERSCAN_API_KEY,
            }
            resp = requests.get(
                config.ETHERSCAN_BASE_URL,
                params=params,
                timeout=config.ETHERSCAN_TIMEOUT
            )
            data = resp.json()
            if data.get("status") == "1" and data.get("result"):
                result = data["result"][0]
                source = result.get("SourceCode", "")
                name = result.get("ContractName", "Unknown")
                is_verified = bool(source and source != "")
                return {"source": source, "name": name, "is_verified": is_verified}
        except Exception as e:
            console.print(f"[dim]  Source fetch error: {e}[/dim]")
        return {"source": "", "name": None, "is_verified": False}

    def _decode_function(self, abi: Optional[list], selector: Optional[str]) -> Tuple[Optional[str], Optional[str]]:
        """
        Match the 4-byte selector against ABI entries to get the function name.
        Returns (name, full_signature)
        """
        if not abi or not selector:
            return None, None

        try:
            from web3 import Web3
            w3 = Web3()
            for item in abi:
                if item.get("type") == "function":
                    name = item.get("name", "")
                    inputs = item.get("inputs", [])
                    types = ",".join(i.get("type", "") for i in inputs)
                    sig = f"{name}({types})"
                    computed = w3.keccak(text=sig)[:4].hex()
                    if "0x" + computed == selector:
                        return name, sig
        except Exception as e:
            console.print(f"[dim]  Function decode error: {e}[/dim]")

        return None, None

    def _extract_requires(self, source: str, function_name: Optional[str]) -> list:
        """
        Extract require() statements from Solidity source.
        Optionally filters to statements near the called function.
        """
        if not source:
            return []

        # Find all require statements with their messages
        pattern = r'require\s*\([^;]+\)'
        matches = re.findall(pattern, source)

        # Clean up the matched statements
        cleaned = []
        for m in matches[:25]:  # Increased limit for better AI context
            m = re.sub(r'\s+', ' ', m).strip()
            cleaned.append(m)

        return cleaned

    def _extract_custom_errors(self, abi: Optional[list]) -> list:
        """Extract custom error definitions from ABI."""
        if not abi:
            return []
        errors = []
        for item in abi:
            if item.get("type") == "error":
                name = item.get("name", "")
                inputs = item.get("inputs", [])
                types = ",".join(i.get("type", "") for i in inputs)
                errors.append(f"{name}({types})")
        return errors

    def _print_result(self, ctx: ContractContext):
        """Print inspection result."""
        verified = "✅ Verified" if ctx.is_verified else "❌ Not verified"
        console.print(f"\n[bold]── Contract Inspection Result ──[/bold]")
        console.print(f"  Contract  : {ctx.contract_name or 'Unknown'} ({ctx.contract_address[:12]}...)")
        console.print(f"  Verified  : {verified}")
        console.print(f"  Function  : {ctx.function_name or 'Not decoded'}")
        console.print(f"  Requires  : {len(ctx.require_conditions)} found")
        console.print(f"  Errors    : {len(ctx.custom_errors)} custom errors")
