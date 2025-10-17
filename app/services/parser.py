import os
import shutil
import tempfile
import re
import hashlib
import json
from datetime import datetime
from decimal import Decimal, InvalidOperation
from fastapi import UploadFile
from typing import List, Dict, Any, Optional, Set, Tuple

from app.config import PipelineConfig
from app.pipeline.loaders import detect_doc_type
from app.pipeline.extractors import DocumentExtractor, CsvExtractor, ExcelExtractor

class TransactionNormalizer:
    """Handles normalization of parsed transaction data to canonical format."""

    # Common field name variations
    FIELD_MAPPINGS = {
        'date': ['date', 'transaction_date', 'posting_date', 'value_date', 'trans_date', 'date_posted'],
        'amount': ['amount', 'value', 'sum', 'total', 'debit', 'credit', 'balance'],
        'description': ['description', 'memo', 'reference', 'details', 'particulars', 'transaction_details'],
        'vendor': ['vendor', 'merchant', 'payee', 'beneficiary', 'counterparty', 'name', 'company', 'business'],
        'category': ['category', 'type', 'transaction_type', 'class', 'classification'],
        'balance': ['balance', 'running_balance', 'account_balance']
    }

    # Category normalization mappings
    CATEGORY_MAPPINGS = {
        'income': ['income', 'deposit', 'credit', 'salary', 'revenue', 'refund', 'interest'],
        'expense': ['expense', 'debit', 'payment', 'purchase', 'withdrawal', 'fee', 'charge'],
        'transfer': ['transfer', 'internal', 'between_accounts', 'movement']
    }

    # Common currency symbols and patterns
    CURRENCY_PATTERNS = [
        (r'^\$', 'USD'),  # Dollar
        (r'^£', 'GBP'),  # Pound
        (r'^€', 'EUR'),  # Euro
        (r'^¥', 'JPY'),  # Yen
        (r'^₹', 'INR'),  # Rupee
        (r'USD\s*\$', 'USD'),  # USD followed by $
        (r'CAD\s*\$', 'CAD'),  # CAD followed by $
    ]

    def __init__(self, cfg: PipelineConfig):
        self.cfg = cfg

    def _normalize_field_names(self, record: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize field names to canonical format."""
        normalized = {}

        for field, variations in self.FIELD_MAPPINGS.items():
            for variation in variations:
                if variation in record:
                    value = record[variation]
                    if field == 'amount' and isinstance(value, str):
                        value = self._parse_amount(value)
                    elif field == 'date' and isinstance(value, str):
                        value = self._parse_date(value)
                    normalized[field] = value
                    break

        # Copy any unmapped fields
        for key, value in record.items():
            if not any(key in variations for variations in self.FIELD_MAPPINGS.values()):
                normalized[f"extra_{key}"] = value

        return normalized

    def _parse_amount(self, amount_str: str) -> Optional[float]:
        """Parse amount string to float, handling currency symbols and formatting."""
        if not amount_str or not isinstance(amount_str, str):
            return None

        # Remove common currency symbols and whitespace
        cleaned = re.sub(r'[^\d.,\-+()]', '', amount_str.strip())

        # Handle parentheses for negative amounts
        if cleaned.startswith('(') and cleaned.endswith(')'):
            cleaned = '-' + cleaned[1:-1]

        try:
            # Try to parse as decimal first for precision
            return float(Decimal(cleaned.replace(',', '')))
        except (InvalidOperation, ValueError):
            return None

    def _parse_date(self, date_str: str) -> Optional[datetime]:
        """Parse date string to datetime object."""
        if not date_str or not isinstance(date_str, str):
            return None

        # Common date formats to try
        date_formats = [
            '%Y-%m-%d',      # 2024-01-15
            '%m/%d/%Y',      # 01/15/2024
            '%d/%m/%Y',      # 15/01/2024
            '%Y/%m/%d',      # 2024/01/15
            '%m-%d-%Y',      # 01-15-2024
            '%d-%m-%Y',      # 15-01-2024
            '%Y%m%d',        # 20240115
            '%m%d%Y',        # 01152024
            '%d%m%Y',        # 15012024
        ]

        for fmt in date_formats:
            try:
                return datetime.strptime(date_str.strip(), fmt)
            except ValueError:
                continue

        return None

    def _normalize_vendor(self, vendor_str: str) -> str:
        """Normalize vendor name for consistency."""
        if not vendor_str or not isinstance(vendor_str, str):
            return ""

        # Basic normalization rules
        normalized = vendor_str.strip().upper()

        # Remove common prefixes/suffixes
        normalized = re.sub(r'^(THE|A|AN)\s+', '', normalized)
        normalized = re.sub(r'\s+(LLC|INC|LTD|CORP|CO|COMPANY|L\.L\.C\.)$', '', normalized)

        # Normalize common abbreviations
        abbreviations = {
            'AMAZON': 'AMAZON',
            'AMZN': 'AMAZON',
            'APPLE': 'APPLE',
            'GOOGLE': 'GOOGLE',
            'MICROSOFT': 'MICROSOFT',
            'WALMART': 'WALMART',
            'TARGET': 'TARGET',
            'COSTCO': 'COSTCO',
            'STARBUCKS': 'STARBUCKS',
            'MCDONALDS': 'MCDONALDS',
            'UBER': 'UBER',
            'LYFT': 'LYFT',
        }

        for abbr, full in abbreviations.items():
            if abbr in normalized:
                return full

        return normalized[:100]  # Limit length

    def _normalize_category(self, category_str: str) -> str:
        """Normalize category to standard values."""
        if not category_str or not isinstance(category_str, str):
            return "uncategorized"

        category_lower = category_str.lower().strip()

        for standard_category, variations in self.CATEGORY_MAPPINGS.items():
            if any(var in category_lower for var in variations):
                return standard_category

        return "uncategorized"

    def _generate_transaction_hash(self, date: datetime, amount: float, vendor: str) -> str:
        """Generate hash for duplicate detection."""
        # Create a normalized string for hashing
        hash_input = f"{date.strftime('%Y%m%d')}_{amount:.2f}_{vendor.upper()}"
        return hashlib.md5(hash_input.encode()).hexdigest()

    def normalize_transaction(self, record: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize a single transaction record."""
        normalized = self._normalize_field_names(record)

        # Normalize vendor and category if present
        if 'vendor' in normalized and normalized['vendor']:
            normalized['vendor'] = self._normalize_vendor(str(normalized['vendor']))

        if 'category' in normalized and normalized['category']:
            normalized['category'] = self._normalize_category(str(normalized['category']))

        # Generate hash for duplicate detection
        if 'date' in normalized and 'amount' in normalized and 'vendor' in normalized:
            normalized['transaction_hash'] = self._generate_transaction_hash(
                normalized['date'],
                normalized['amount'],
                normalized['vendor']
            )

        return normalized

class FileParser:
    def __init__(self, file: UploadFile, cfg: Optional[PipelineConfig] = None):
        self.file = file
        self.cfg = cfg or PipelineConfig()
        self.normalizer = TransactionNormalizer(self.cfg)

    async def parse(self) -> Dict[str, Any]:
        """Parse file and return normalized transactions with metadata."""
        # Create a temporary directory to store the uploaded file
        temp_dir = tempfile.mkdtemp()
        file_path = os.path.join(temp_dir, self.file.filename)

        # Save the uploaded file to the temporary location
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(self.file.file, buffer)

        try:
            doc_type = detect_doc_type(file_path)

            # Extract raw records based on file type
            if doc_type == "csv":
                extractor = CsvExtractor(self.cfg)
                result = extractor.extract(file_path)
                raw_records = result.get("records", [])
            elif doc_type == "excel":
                extractor = ExcelExtractor(self.cfg)
                result = extractor.extract(file_path)
                raw_records = result.get("records", [])
            elif doc_type in ["pdf", "image", "word", "html", "text", "powerpoint"]:
                # Use document extractor for unstructured documents
                extractor = DocumentExtractor(self.cfg)
                result = extractor.extract_textual(file_path)
                # For unstructured docs, we'll try to extract as a single record
                raw_records = [result] if result else []
            else:
                return {
                    "success": False,
                    "error": f"Unsupported file type: {doc_type}",
                    "records": [],
                    "metadata": {"file_type": doc_type}
                }

            # Normalize records
            normalized_records = []
            seen_hashes: Set[str] = set()
            duplicates = []

            for record in raw_records:
                normalized = self.normalizer.normalize_transaction(record)

                # Check for duplicates
                if 'transaction_hash' in normalized:
                    hash_val = normalized['transaction_hash']
                    if hash_val in seen_hashes:
                        duplicates.append(normalized)
                        continue
                    seen_hashes.add(hash_val)

                normalized_records.append(normalized)

            return {
                "success": True,
                "records": normalized_records,
                "duplicates": duplicates,
                "metadata": {
                    "file_type": doc_type,
                    "total_raw_records": len(raw_records),
                    "normalized_records": len(normalized_records),
                    "duplicates_found": len(duplicates)
                }
            }

        finally:
            # Clean up the temporary directory
            shutil.rmtree(temp_dir)
