import re
from typing import List, Optional, Dict, Any, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, func
from app.models.vendor import Vendor
from app.core.database import SessionLocal

class VendorService:
    """Service for vendor resolution, normalization, and deduplication."""

    def __init__(self, db: Session = None):
        self.db = db or SessionLocal()

    def normalize_vendor_name(self, name: str) -> str:
        """Normalize vendor name for consistent matching."""
        if not name or not isinstance(name, str):
            return ""

        # Convert to uppercase for case-insensitive matching
        normalized = name.strip().upper()

        # Remove common business suffixes
        normalized = re.sub(r'\s+(LLC|INC|LTD|CORP|CO|COMPANY|L\.L\.C\.|LIMITED|CORPORATION)$', '', normalized)

        # Remove common prefixes
        normalized = re.sub(r'^(THE|A|AN)\s+', '', normalized)

        # Normalize common abbreviations and misspellings
        replacements = {
            'AMAZON.COM': 'AMAZON',
            'AMAZON PRIME': 'AMAZON',
            'AMZN': 'AMAZON',
            'AMAZON.COM INC': 'AMAZON',
            'APPLE INC': 'APPLE',
            'APPLE COMPUTER': 'APPLE',
            'GOOGLE LLC': 'GOOGLE',
            'GOOGLE INC': 'GOOGLE',
            'MICROSOFT CORP': 'MICROSOFT',
            'MICROSOFT CORPORATION': 'MICROSOFT',
            'WAL-MART': 'WALMART',
            'WALMART STORES': 'WALMART',
            'TARGET CORP': 'TARGET',
            'TARGET CORPORATION': 'TARGET',
            'COSTCO WHOLESALE': 'COSTCO',
            'STARBUCKS COFFEE': 'STARBUCKS',
            'STARBUCKS CORP': 'STARBUCKS',
            'MCDONALD\'S': 'MCDONALDS',
            'MCDONALDS CORP': 'MCDONALDS',
            'UBER TECHNOLOGIES': 'UBER',
            'LYFT INC': 'LYFT',
            'NETFLIX INC': 'NETFLIX',
            'SPOTIFY USA': 'SPOTIFY',
            'PAYPAL INC': 'PAYPAL',
            'VENMO': 'PAYPAL',  # Common association
            'SQUARE INC': 'SQUARE',
            'SQUARESPACE': 'SQUARESPACE',
            'DROPBOX INC': 'DROPBOX',
            'ADOBE INC': 'ADOBE',
            'ADOBE SYSTEMS': 'ADOBE',
        }

        # Check for exact matches first
        if normalized in replacements:
            return replacements[normalized]

        # Check if any replacement key is contained in the normalized name
        for key, replacement in replacements.items():
            if key in normalized:
                return replacement

        # Remove extra whitespace and limit length
        normalized = re.sub(r'\s+', ' ', normalized).strip()
        return normalized[:100]

    def find_similar_vendors(self, name: str, threshold: float = 0.8) -> List[Tuple[Vendor, float]]:
        """Find vendors with similar names using fuzzy matching."""
        if not name:
            return []

        normalized_name = self.normalize_vendor_name(name)

        # Get all vendors from database
        vendors = self.db.query(Vendor).all()

        similar_vendors = []
        for vendor in vendors:
            # Compare normalized names using simple similarity
            similarity = self._calculate_similarity(normalized_name, vendor.normalized_name or vendor.name)

            if similarity >= threshold:
                similar_vendors.append((vendor, similarity))

        # Sort by similarity score (highest first)
        similar_vendors.sort(key=lambda x: x[1], reverse=True)

        return similar_vendors

    def _calculate_similarity(self, name1: str, name2: str) -> float:
        """Calculate simple string similarity ratio."""
        if not name1 or not name2:
            return 0.0

        # Simple implementation: check for common words and length similarity
        words1 = set(name1.split())
        words2 = set(name2.split())

        # Jaccard similarity for word overlap
        intersection = len(words1.intersection(words2))
        union = len(words1.union(words2))

        if union == 0:
            return 0.0

        word_similarity = intersection / union

        # Length similarity bonus
        len1, len2 = len(name1), len(name2)
        length_similarity = 1.0 - abs(len1 - len2) / max(len1, len2)

        # Combined score
        return (word_similarity * 0.7) + (length_similarity * 0.3)

    def resolve_vendor(self, vendor_name: str, auto_create: bool = True) -> Optional[Vendor]:
        """Resolve vendor name to existing vendor or create new one."""
        if not vendor_name:
            return None

        normalized_name = self.normalize_vendor_name(vendor_name)

        # First, try to find exact match on normalized name
        existing = self.db.query(Vendor).filter(
            Vendor.normalized_name == normalized_name
        ).first()

        if existing:
            return existing

        # Try fuzzy matching for similar names
        similar_vendors = self.find_similar_vendors(vendor_name, threshold=0.85)

        if similar_vendors:
            # Return the most similar vendor
            best_match, _ = similar_vendors[0]
            return best_match

        # No match found, create new vendor if auto_create is enabled
        if auto_create:
            new_vendor = Vendor(
                name=vendor_name,
                normalized_name=normalized_name
            )
            self.db.add(new_vendor)
            self.db.commit()
            self.db.refresh(new_vendor)
            return new_vendor

        return None

    def bulk_resolve_vendors(self, vendor_names: List[str], auto_create: bool = True) -> Dict[str, Vendor]:
        """Resolve multiple vendor names, reusing existing resolutions."""
        resolved = {}

        for name in vendor_names:
            if not name:
                continue

            # Check if we've already resolved this exact name
            if name in resolved:
                continue

            vendor = self.resolve_vendor(name, auto_create)
            if vendor:
                resolved[name] = vendor

        return resolved

    def merge_vendors(self, vendor_ids: List[int], keep_id: int) -> bool:
        """Merge multiple vendors into one, keeping the specified vendor."""
        if len(vendor_ids) < 2 or keep_id not in vendor_ids:
            return False

        try:
            # Update all transactions to point to the kept vendor
            from app.models.transaction import Transaction

            self.db.query(Transaction).filter(
                Transaction.vendor_id.in_(vendor_ids)
            ).filter(
                Transaction.vendor_id != keep_id
            ).update({Transaction.vendor_id: keep_id})

            # Delete the duplicate vendors
            self.db.query(Vendor).filter(
                Vendor.id.in_(vendor_ids)
            ).filter(
                Vendor.id != keep_id
            ).delete()

            self.db.commit()
            return True

        except Exception as e:
            self.db.rollback()
            return False

    def get_vendor_stats(self) -> Dict[str, Any]:
        """Get statistics about vendors in the database."""
        total_vendors = self.db.query(Vendor).count()

        # Count vendors by creation date (last 30 days)
        from datetime import datetime, timedelta
        thirty_days_ago = datetime.utcnow() - timedelta(days=30)
        recent_vendors = self.db.query(Vendor).filter(
            Vendor.created_at >= thirty_days_ago
        ).count()

        # Most common vendor names (top 10)
        from sqlalchemy import text
        top_vendors = self.db.execute(
            text("""
                SELECT v.name, COUNT(t.id) as transaction_count
                FROM vendors v
                LEFT JOIN transactions t ON v.id = t.vendor_id
                GROUP BY v.id, v.name
                ORDER BY transaction_count DESC
                LIMIT 10
            """)
        ).fetchall()

        return {
            "total_vendors": total_vendors,
            "recent_vendors": recent_vendors,
            "top_vendors": [
                {"name": row[0], "transaction_count": row[1]}
                for row in top_vendors
            ]
        }

    def __del__(self):
        """Cleanup database session."""
        if hasattr(self, 'db') and self.db:
            self.db.close()
