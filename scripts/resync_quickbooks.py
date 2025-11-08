"""
Script to re-sync QuickBooks data with improved logging

This script will:
1. Find all active QuickBooks connections
2. Trigger a full sync for each connection
3. Display detailed logging to help debug amount extraction issues
"""

import sys
import os
import logging
from datetime import datetime, timedelta

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.core.database import SessionLocal
from app.models.quickbooks_connection import QuickBooksConnection
from app.services.quickbooks_oauth_service import QuickBooksOAuthService
from app.services.quickbooks_sync_service import QuickBooksSyncService

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def main():
    """Main function to re-sync QuickBooks data"""
    db = SessionLocal()
    
    try:
        # Get all active connections
        connections = db.query(QuickBooksConnection).filter(
            QuickBooksConnection.is_active == True
        ).all()
        
        if not connections:
            logger.warning("No active QuickBooks connections found")
            return
        
        logger.info(f"Found {len(connections)} active connection(s)")
        
        # Initialize services
        oauth_service = QuickBooksOAuthService()
        sync_service = QuickBooksSyncService(oauth_service)
        
        for connection in connections:
            logger.info(f"\n{'='*60}")
            logger.info(f"Syncing connection: {connection.id}")
            logger.info(f"Realm ID: {connection.realm_id}")
            logger.info(f"Company: {connection.company_name}")
            logger.info(f"Last sync: {connection.last_sync_at}")
            logger.info(f"{'='*60}\n")
            
            try:
                # Perform full sync for last 90 days
                date_from = datetime.utcnow() - timedelta(days=90)
                date_to = datetime.utcnow()
                
                sync_log = sync_service.sync_connection(
                    connection=connection,
                    db=db,
                    sync_type="full",
                    date_from=date_from,
                    date_to=date_to
                )
                
                logger.info(f"\nSync completed successfully!")
                logger.info(f"Vendors synced: {sync_log.vendors_synced}")
                logger.info(f"Transactions fetched: {sync_log.transactions_fetched}")
                logger.info(f"Transactions created: {sync_log.transactions_created}")
                logger.info(f"Transactions updated: {sync_log.transactions_updated}")
                logger.info(f"Transactions skipped: {sync_log.transactions_skipped}")
                logger.info(f"Duration: {sync_log.duration_seconds}s")
                
                # Check if any transactions have non-zero amounts
                from app.models.transaction import Transaction
                from sqlalchemy import func
                
                non_zero_count = db.query(func.count(Transaction.id)).filter(
                    Transaction.quickbooks_connection_id == connection.id,
                    Transaction.amount != 0
                ).scalar()
                
                zero_count = db.query(func.count(Transaction.id)).filter(
                    Transaction.quickbooks_connection_id == connection.id,
                    Transaction.amount == 0
                ).scalar()
                
                logger.info(f"\nTransaction amounts check:")
                logger.info(f"  Non-zero amounts: {non_zero_count}")
                logger.info(f"  Zero amounts: {zero_count}")
                
                if zero_count > 0 and non_zero_count == 0:
                    logger.warning("⚠️  All transactions have zero amounts!")
                    logger.warning("This suggests QuickBooks API is not returning amount data properly.")
                    logger.warning("Check your QuickBooks sandbox data or API permissions.")
                
            except Exception as e:
                logger.error(f"Error syncing connection {connection.id}: {str(e)}")
                continue
        
    finally:
        db.close()

if __name__ == "__main__":
    main()

