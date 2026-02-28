"""
core/config.py — Centralized configuration for ExplainDeFi
Loads all settings from .env file
"""

import os
from typing import List
from dotenv import load_dotenv

# Load .env file from project root
load_dotenv()


class Config:
    # ── Blockchain RPC ──
    ALCHEMY_API_KEY: str = os.getenv("ALCHEMY_API_KEY", "")
    ETHEREUM_RPC_URL: str = os.getenv(
        "ETHEREUM_RPC_URL",
        f"https://eth-mainnet.g.alchemy.com/v2/{os.getenv('ALCHEMY_API_KEY', '')}"
    )

    # ── Etherscan ──
    ETHERSCAN_API_KEY: str = os.getenv("ETHERSCAN_API_KEY", "")
    ETHERSCAN_BASE_URL: str = "https://api.etherscan.io/api"

    # ── LLM ──
    LLM_PROVIDER: str = os.getenv("LLM_PROVIDER", "gemini")
    LLM_MODEL: str = os.getenv("LLM_MODEL", "gemini-2.0-flash")
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
    GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "")
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")

    # ── Database ──
    DB_PATH: str = os.getenv("DB_PATH", "./db/explaindefi.db")

    # ── App ──
    DEBUG: bool = os.getenv("DEBUG", "false").lower() == "true"
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")

    # ── Timeouts ──
    RPC_TIMEOUT: int = 30
    ETHERSCAN_TIMEOUT: int = 15
    LLM_TIMEOUT: int = 60

    @classmethod
    def validate(cls) -> List[str]:
        """Check which required keys are missing. Returns list of warnings."""
        warnings = []
        if not cls.ALCHEMY_API_KEY or cls.ALCHEMY_API_KEY == "your_alchemy_api_key_here":
            warnings.append("⚠️  ALCHEMY_API_KEY not set — blockchain data unavailable")
        if not cls.ETHERSCAN_API_KEY or cls.ETHERSCAN_API_KEY == "your_etherscan_api_key_here":
            warnings.append("⚠️  ETHERSCAN_API_KEY not set — contract inspection disabled")
        if not cls.GEMINI_API_KEY or cls.GEMINI_API_KEY == "your_gemini_api_key_here":
            if not cls.GROQ_API_KEY or cls.GROQ_API_KEY == "your_groq_api_key_here":
                warnings.append("⚠️  No LLM API key set — AI explanation disabled")
        return warnings


# Singleton instance
config = Config()
