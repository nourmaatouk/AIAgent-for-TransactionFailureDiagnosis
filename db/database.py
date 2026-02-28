"""
db/database.py — SQLite persistence layer
Stores and retrieves diagnosis reports.
"""

import os
import json
import sqlite3
from typing import Optional, List
from datetime import datetime
from rich.console import Console

from core.config import config
from core.models import DiagnosisReport

console = Console()


class Database:
    """Lightweight SQLite wrapper for storing diagnosis reports."""

    def __init__(self):
        db_path = config.DB_PATH
        # Ensure directory exists
        os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self._create_tables()

    def _create_tables(self):
        """Create database schema if not exists."""
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS diagnoses (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                tx_hash          TEXT UNIQUE NOT NULL,
                timestamp        TEXT NOT NULL,
                status           TEXT,
                failure_category TEXT,
                failure_sub_type TEXT,
                raw_error        TEXT,
                explanation      TEXT,
                fix_steps        TEXT,
                confidence       REAL,
                technical_summary TEXT,
                llm_provider     TEXT,
                contract_address TEXT,
                contract_name    TEXT,
                function_name    TEXT,
                gas_used         INTEGER,
                gas_limit        INTEGER,
                from_address     TEXT,
                created_at       TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        self.conn.commit()

    def save_report(self, report: DiagnosisReport):
        """Save a diagnosis report to the database."""
        tx = report.tx_data
        diag = report.diagnosis
        expl = report.explanation
        contract = report.contract_context

        self.conn.execute("""
            INSERT OR REPLACE INTO diagnoses (
                tx_hash, timestamp, status,
                failure_category, failure_sub_type, raw_error,
                explanation, fix_steps, confidence, technical_summary, llm_provider,
                contract_address, contract_name, function_name,
                gas_used, gas_limit, from_address
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            report.tx_hash,
            report.timestamp,
            "failed" if (tx and tx.status == 0) else "success",
            diag.category if diag else None,
            diag.sub_type if diag else None,
            diag.raw_error if diag else None,
            expl.explanation if expl else None,
            json.dumps(expl.fix_steps) if expl else None,
            expl.confidence if expl else None,
            expl.technical_summary if expl else None,
            expl.llm_provider if expl else None,
            contract.contract_address if contract else None,
            contract.contract_name if contract else None,
            tx.function_name if tx else None,
            tx.gas_used if tx else None,
            tx.gas_limit if tx else None,
            tx.from_address if tx else None,
        ))
        self.conn.commit()

    def get_report(self, tx_hash: str) -> Optional[dict]:
        """Retrieve a cached report by tx hash."""
        cursor = self.conn.execute(
            "SELECT * FROM diagnoses WHERE tx_hash = ?", (tx_hash.lower(),)
        )
        row = cursor.fetchone()
        if not row:
            return None
        cols = [desc[0] for desc in cursor.description]
        return dict(zip(cols, row))

    def get_all_reports(self, limit: int = 20) -> List[dict]:
        """Retrieve recent diagnosis reports."""
        cursor = self.conn.execute(
            "SELECT tx_hash, timestamp, failure_category, failure_sub_type, confidence "
            "FROM diagnoses ORDER BY created_at DESC LIMIT ?",
            (limit,)
        )
        cols = [desc[0] for desc in cursor.description]
        return [dict(zip(cols, row)) for row in cursor.fetchall()]

    def close(self):
        self.conn.close()
