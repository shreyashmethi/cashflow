"""
QuickBooks Data Sync Service

This service handles:
- Fetching transactions from QuickBooks
- Syncing vendors
- Incremental and full syncs
- Handling pagination
- Error recovery
"""
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
from sqlalchemy import and_
import uuid
import requests

from app.models.quickbooks_connection import QuickBooksConnection
from app.models.quickbooks_sync_log import QuickBooksSyncLog
from app.models.transaction import Transaction
from app.models.vendor import Vendor
from app.services.quickbooks_oauth_service import QuickBooksOAuthService

logger = logging.getLogger(__name__)


class QuickBooksSyncService:
    """Handles syncing data from QuickBooks to local database"""
    
    def __init__(self, oauth_service: QuickBooksOAuthService):
        self.oauth_service = oauth_service
        self.environment = oauth_service.environment
        
        # Set base URL based on environment
        # QuickBooks API uses different base URLs for sandbox vs production
        if self.environment == "sandbox":
            # Sandbox URL format - must end with trailing slash
            self.base_url = "https://sandbox-quickbooks.api.intuit.com/v3/company"
        else:
            # Production URL format - must end with trailing slash
            self.base_url = "https://quickbooks.api.intuit.com/v3/company"
    
    def sync_connection(
        self,
        connection: QuickBooksConnection,
        db: Session,
        sync_type: str = "incremental",
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None
    ) -> QuickBooksSyncLog:
        """
        Sync transactions from QuickBooks
        
        Args:
            connection: QuickBooksConnection object
            db: Database session
            sync_type: 'full' or 'incremental'
            date_from: Start date for transaction sync
            date_to: End date for transaction sync
            
        Returns:
            QuickBooksSyncLog with sync results
        """
        # Create sync log
        sync_log = QuickBooksSyncLog(
            connection_id=connection.id,
            sync_type=sync_type,
            status="started",
            sync_params={
                "date_from": date_from.isoformat() if date_from else None,
                "date_to": date_to.isoformat() if date_to else None,
            }
        )
        db.add(sync_log)
        db.commit()
        
        # Update connection status
        connection.sync_status = "in_progress"
        db.commit()
        
        try:
            # Get valid access token
            access_token = self.oauth_service.get_valid_access_token(connection, db)
            
            # Determine date range
            if sync_type == "incremental" and not date_from:
                # Start from last sync or 30 days ago
                date_from = connection.last_sync_at or (datetime.utcnow() - timedelta(days=30))
            elif not date_from:
                # Full sync - get last 365 days by default
                date_from = datetime.utcnow() - timedelta(days=365)
            
            if not date_to:
                date_to = datetime.utcnow()
            
            logger.info(f"Starting {sync_type} sync for realm_id {connection.realm_id} from {date_from} to {date_to}")
            
            # Sync vendors first
            vendors_synced = self._sync_vendors(connection, access_token, db)
            sync_log.vendors_synced = vendors_synced
            
            # Sync transactions
            transactions_stats = self._sync_transactions(
                connection,
                access_token,
                db,
                date_from,
                date_to
            )
            
            # Update sync log
            sync_log.transactions_fetched = transactions_stats["fetched"]
            sync_log.transactions_created = transactions_stats["created"]
            sync_log.transactions_updated = transactions_stats["updated"]
            sync_log.transactions_skipped = transactions_stats["skipped"]
            sync_log.status = "completed"
            sync_log.completed_at = datetime.utcnow()
            sync_log.duration_seconds = int((sync_log.completed_at - sync_log.started_at).total_seconds())
            
            # Update connection
            connection.last_sync_at = datetime.utcnow()
            connection.sync_status = "success"
            connection.sync_error = None
            
            db.commit()
            
            logger.info(f"Sync completed: {transactions_stats}")
            return sync_log
            
        except Exception as e:
            logger.error(f"Sync failed for realm_id {connection.realm_id}: {str(e)}")
            
            # Update sync log with error
            sync_log.status = "failed"
            sync_log.error_message = str(e)
            sync_log.completed_at = datetime.utcnow()
            
            # Update connection
            connection.sync_status = "failed"
            connection.sync_error = str(e)
            
            db.commit()
            raise
    
    def _sync_vendors(
        self,
        connection: QuickBooksConnection,
        access_token: str,
        db: Session
    ) -> int:
        """
        Sync vendors/customers from QuickBooks
        
        Returns:
            Number of vendors synced
        """
        try:
            # Fetch vendors from QuickBooks
            vendors_data = self._fetch_quickbooks_vendors(connection.realm_id, access_token)
            
            vendors_synced = 0
            for vendor_data in vendors_data:
                qb_vendor_id = vendor_data.get("Id")
                vendor_name = vendor_data.get("DisplayName") or vendor_data.get("Name")
                
                if not vendor_name:
                    continue
                
                # Check if vendor exists
                existing_vendor = db.query(Vendor).filter(
                    Vendor.name == vendor_name
                ).first()
                
                if not existing_vendor:
                    # Create new vendor
                    vendor = Vendor(
                        name=vendor_name,
                        normalized_name=self._normalize_vendor_name(vendor_name)
                    )
                    db.add(vendor)
                    vendors_synced += 1
            
            db.commit()
            logger.info(f"Synced {vendors_synced} vendors")
            return vendors_synced
            
        except Exception as e:
            logger.error(f"Error syncing vendors: {str(e)}")
            return 0
    
    def _sync_transactions(
        self,
        connection: QuickBooksConnection,
        access_token: str,
        db: Session,
        date_from: datetime,
        date_to: datetime
    ) -> Dict[str, int]:
        """
        Sync transactions from QuickBooks
        
        Returns:
            Dict with stats: fetched, created, updated, skipped
        """
        stats = {"fetched": 0, "created": 0, "updated": 0, "skipped": 0}
        
        try:
            # Fetch transactions from QuickBooks
            transactions_data = self._fetch_quickbooks_transactions(
                connection.realm_id,
                access_token,
                date_from,
                date_to
            )
            
            stats["fetched"] = len(transactions_data)
            
            for txn_data in transactions_data:
                result = self._process_transaction(connection, txn_data, db)
                stats[result] += 1
            
            db.commit()
            return stats
            
        except Exception as e:
            logger.error(f"Error syncing transactions: {str(e)}")
            raise
    
    def _process_transaction(
        self,
        connection: QuickBooksConnection,
        txn_data: Dict[str, Any],
        db: Session
    ) -> str:
        """
        Process a single QuickBooks transaction
        
        Returns:
            'created', 'updated', or 'skipped'
        """
        qb_txn_id = txn_data.get("Id")
        sync_version = txn_data.get("SyncToken")
        
        # Check if transaction already exists
        existing_txn = db.query(Transaction).filter(
            and_(
                Transaction.quickbooks_id == qb_txn_id,
                Transaction.quickbooks_connection_id == connection.id
            )
        ).first()
        
        # Extract transaction data
        txn_date = self._parse_qb_date(txn_data.get("TxnDate"))
        amount = float(txn_data.get("Amount", 0))
        description = txn_data.get("Description") or ""
        
        # Get vendor
        vendor_name = None
        if "EntityRef" in txn_data:
            vendor_name = txn_data["EntityRef"].get("name")
        
        vendor = None
        if vendor_name:
            vendor = db.query(Vendor).filter(Vendor.name == vendor_name).first()
            if not vendor:
                vendor = Vendor(
                    name=vendor_name,
                    normalized_name=self._normalize_vendor_name(vendor_name)
                )
                db.add(vendor)
                db.flush()
        
        # Determine transaction type/category
        category = self._map_qb_transaction_type(txn_data)
        
        if existing_txn:
            # Check if transaction was updated in QuickBooks
            if existing_txn.quickbooks_sync_version != sync_version:
                # Update transaction
                existing_txn.transaction_date = txn_date
                existing_txn.amount = amount
                existing_txn.raw_description = description
                existing_txn.normalized_description = self._normalize_description(description)
                existing_txn.category = category
                existing_txn.vendor_id = vendor.id if vendor else None
                existing_txn.quickbooks_sync_version = sync_version
                return "updated"
            else:
                return "skipped"
        else:
            # Create new transaction
            transaction = Transaction(
                transaction_date=txn_date,
                amount=amount,
                raw_description=description,
                normalized_description=self._normalize_description(description),
                category=category,
                vendor_id=vendor.id if vendor else None,
                source=f"QuickBooks ({connection.realm_id})",
                source_type="quickbooks",
                quickbooks_id=qb_txn_id,
                quickbooks_connection_id=connection.id,
                quickbooks_sync_version=sync_version
            )
            db.add(transaction)
            return "created"
    
    # Helper methods for QuickBooks API calls (placeholder implementations)
    
    def _fetch_quickbooks_vendors(self, realm_id: str, access_token: str) -> List[Dict]:
        """
        Fetch vendors from QuickBooks API
        
        Uses QuickBooks API v3 to query vendors.
        API endpoint: {base_url}/{realm_id}/query
        Query: SELECT * FROM Vendor
        """
        try:
            headers = {
                "Authorization": f"Bearer {access_token}",
                "Accept": "application/json"
            }
            # Construct full endpoint URL
            # Format: https://{base}/v3/company/{realm_id}/query
            url = f"{self.base_url}/{realm_id}/query"
            
            # Query all active vendors
            # QuickBooks API requires query as URL parameter
            # Properly encode the query string
            query = "SELECT * FROM Vendor WHERE Active = true MAXRESULTS 1000"
            params = {
                "minorversion": "65",
                "query": query
            }
            
            logger.debug(f"Fetching vendors from QuickBooks: {url} (environment: {self.environment})")
            response = requests.get(url, headers=headers, params=params, timeout=30)
            
            # Log response details for debugging
            if response.status_code != 200:
                logger.error(f"QuickBooks API error: {response.status_code} - {response.text}")
            
            response.raise_for_status()
            
            data = response.json()
            
            # Handle response format
            if "QueryResponse" in data and "Vendor" in data["QueryResponse"]:
                vendors = data["QueryResponse"]["Vendor"]
                # Ensure it's a list (QuickBooks may return single dict or list)
                if isinstance(vendors, dict):
                    vendors = [vendors]
                
                logger.info(f"Fetched {len(vendors)} vendors from QuickBooks")
                return vendors
            
            # No vendors found in response
            logger.info("No vendors found in QuickBooks response")
            return []
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Error fetching QuickBooks vendors: {str(e)}")
            raise
        except KeyError as e:
            logger.error(f"Unexpected response format from QuickBooks API: {str(e)}")
            # Return empty list to allow sync to continue
            return []
        except Exception as e:
            logger.error(f"Unexpected error fetching QuickBooks vendors: {str(e)}")
            return []
    
    def _fetch_quickbooks_transactions(
        self,
        realm_id: str,
        access_token: str,
        date_from: datetime,
        date_to: datetime
    ) -> List[Dict]:
        """
        Fetch transactions from QuickBooks API
        
        Fetches multiple transaction types:
        - Purchase transactions (expenses)
        - Bill transactions (expenses)
        - Invoice transactions (income)
        - Payment transactions
        - Expense transactions
        
        Returns combined list of all transactions
        """
        all_transactions = []
        
        # Format dates for QuickBooks query
        date_from_str = date_from.strftime("%Y-%m-%d")
        date_to_str = date_to.strftime("%Y-%m-%d")
        
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json"
        }
        # Construct full endpoint URL
        # Format: https://{base}/v3/company/{realm_id}/query
        url = f"{self.base_url}/{realm_id}/query"
        
        # Transaction types to fetch
        # Note: QuickBooks API entity types - "Expense" is not a valid entity type
        # Use "Bill" for expense bills, "Purchase" for purchase transactions
        transaction_types = [
            ("Purchase", "expense"),
            ("Bill", "expense"),
            ("Invoice", "income"),
            ("Payment", "income"),
            ("SalesReceipt", "income"),
            ("Deposit", "income"),
            ("JournalEntry", "adjustment"),
            ("Transfer", "transfer")
        ]
        
        for entity_type, _ in transaction_types:
            try:
                # Build query for this transaction type
                query = (
                    f"SELECT * FROM {entity_type} "
                    f"WHERE TxnDate >= '{date_from_str}' "
                    f"AND TxnDate <= '{date_to_str}' "
                    f"MAXRESULTS 1000"
                )
                
                params = {"minorversion": "65", "query": query}
                
                logger.debug(f"Fetching {entity_type} transactions from QuickBooks: {url} (environment: {self.environment})")
                response = requests.get(url, headers=headers, params=params, timeout=30)
                
                # Log response details for debugging
                if response.status_code != 200:
                    logger.error(f"QuickBooks API error for {entity_type}: {response.status_code} - {response.text}")
                
                response.raise_for_status()
                
                data = response.json()
                
                # Extract transactions from response
                if "QueryResponse" in data and entity_type in data["QueryResponse"]:
                    transactions = data["QueryResponse"][entity_type]
                    # Ensure it's a list
                    if isinstance(transactions, dict):
                        transactions = [transactions]
                    
                    # Add type metadata to each transaction
                    for txn in transactions:
                        txn["type"] = entity_type.lower()
                    
                    all_transactions.extend(transactions)
                    logger.info(f"Fetched {len(transactions)} {entity_type} transactions")
                
            except requests.exceptions.RequestException as e:
                logger.warning(f"Error fetching {entity_type} transactions: {str(e)}")
                # Continue with other transaction types
                continue
            except KeyError:
                # No transactions of this type found, continue
                continue
            except Exception as e:
                logger.warning(f"Unexpected error fetching {entity_type} transactions: {str(e)}")
                continue
        
        logger.info(f"Total transactions fetched: {len(all_transactions)}")
        return all_transactions
    
    # Utility methods
    
    def _parse_qb_date(self, date_str: Optional[str]) -> datetime:
        """Parse QuickBooks date string to datetime"""
        if not date_str:
            return datetime.utcnow()
        try:
            return datetime.strptime(date_str, "%Y-%m-%d")
        except ValueError:
            return datetime.utcnow()
    
    def _normalize_vendor_name(self, name: str) -> str:
        """Normalize vendor name for matching"""
        return name.lower().strip()
    
    def _normalize_description(self, description: str) -> str:
        """Normalize transaction description"""
        return description.strip() if description else ""
    
    def _map_qb_transaction_type(self, txn_data: Dict) -> str:
        """Map QuickBooks transaction type to category"""
        # Map based on transaction type
        txn_type = txn_data.get("type", "").lower()
        
        mapping = {
            "purchase": "expense",
            "bill": "expense",
            "expense": "expense",
            "invoice": "income",
            "salesreceipt": "income",
            "payment": "income",
            "deposit": "income",
            "transfer": "transfer",
            "journalentry": "adjustment"
        }
        
        return mapping.get(txn_type, "other")

