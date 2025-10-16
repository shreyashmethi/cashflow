"""
QuickBooks OAuth 2.0 Authentication Service

This service handles:
- OAuth flow initiation
- Authorization code exchange
- Token refresh
- Token storage and retrieval
"""
import os
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from intuit.oauth2 import OAuth2Client
from intuit.exceptions import AuthClientError
from sqlalchemy.orm import Session
from app.models.quickbooks_connection import QuickBooksConnection
import logging

logger = logging.getLogger(__name__)


class QuickBooksOAuthService:
    """Handles QuickBooks OAuth 2.0 authentication"""
    
    def __init__(self):
        self.client_id = os.getenv("QUICKBOOKS_CLIENT_ID")
        self.client_secret = os.getenv("QUICKBOOKS_CLIENT_SECRET")
        self.redirect_uri = os.getenv("QUICKBOOKS_REDIRECT_URI", "http://localhost:8000/api/quickbooks/callback")
        self.environment = os.getenv("QUICKBOOKS_ENVIRONMENT", "sandbox")  # sandbox or production
        
        if not self.client_id or not self.client_secret:
            logger.warning("QuickBooks credentials not configured. Set QUICKBOOKS_CLIENT_ID and QUICKBOOKS_CLIENT_SECRET")
    
    def get_authorization_url(self, state: Optional[str] = None) -> str:
        """
        Generate QuickBooks authorization URL
        
        Args:
            state: Optional state parameter for CSRF protection
            
        Returns:
            Authorization URL for user to visit
        """
        auth_client = OAuth2Client(
            client_id=self.client_id,
            client_secret=self.client_secret,
            redirect_uri=self.redirect_uri,
            environment=self.environment
        )
        
        scopes = [
            'com.intuit.quickbooks.accounting',  # Access to accounting data
        ]
        
        auth_url = auth_client.get_authorization_url(scopes, state=state)
        return auth_url
    
    def exchange_code_for_tokens(
        self, 
        authorization_code: str,
        realm_id: str,
        db: Session
    ) -> QuickBooksConnection:
        """
        Exchange authorization code for access and refresh tokens
        
        Args:
            authorization_code: Code received from QuickBooks callback
            realm_id: QuickBooks company ID
            db: Database session
            
        Returns:
            QuickBooksConnection object with stored tokens
        """
        auth_client = OAuth2Client(
            client_id=self.client_id,
            client_secret=self.client_secret,
            redirect_uri=self.redirect_uri,
            environment=self.environment
        )
        
        try:
            # Exchange code for tokens
            auth_client.get_bearer_token(authorization_code, realm_id=realm_id)
            
            # Calculate token expiration (typically 1 hour)
            expires_in = auth_client.expires_in  # seconds
            token_expires_at = datetime.utcnow() + timedelta(seconds=expires_in)
            
            # Check if connection already exists
            connection = db.query(QuickBooksConnection).filter(
                QuickBooksConnection.realm_id == realm_id
            ).first()
            
            if connection:
                # Update existing connection
                connection.access_token = auth_client.access_token
                connection.refresh_token = auth_client.refresh_token
                connection.token_expires_at = token_expires_at
                connection.is_active = True
                connection.sync_status = None
                connection.sync_error = None
            else:
                # Create new connection
                connection = QuickBooksConnection(
                    realm_id=realm_id,
                    access_token=auth_client.access_token,
                    refresh_token=auth_client.refresh_token,
                    token_expires_at=token_expires_at,
                    is_active=True
                )
                db.add(connection)
            
            db.commit()
            db.refresh(connection)
            
            logger.info(f"Successfully stored tokens for realm_id: {realm_id}")
            return connection
            
        except AuthClientError as e:
            logger.error(f"OAuth error: {str(e)}")
            raise Exception(f"Failed to exchange authorization code: {str(e)}")
    
    def refresh_tokens(self, connection: QuickBooksConnection, db: Session) -> QuickBooksConnection:
        """
        Refresh expired access token using refresh token
        
        Args:
            connection: QuickBooksConnection object
            db: Database session
            
        Returns:
            Updated QuickBooksConnection object
        """
        auth_client = OAuth2Client(
            client_id=self.client_id,
            client_secret=self.client_secret,
            redirect_uri=self.redirect_uri,
            environment=self.environment,
            refresh_token=connection.refresh_token
        )
        
        try:
            # Refresh the token
            auth_client.refresh()
            
            # Update connection with new tokens
            connection.access_token = auth_client.access_token
            connection.refresh_token = auth_client.refresh_token
            
            expires_in = auth_client.expires_in
            connection.token_expires_at = datetime.utcnow() + timedelta(seconds=expires_in)
            
            db.commit()
            db.refresh(connection)
            
            logger.info(f"Successfully refreshed tokens for realm_id: {connection.realm_id}")
            return connection
            
        except AuthClientError as e:
            logger.error(f"Token refresh error for realm_id {connection.realm_id}: {str(e)}")
            connection.is_active = False
            connection.sync_error = f"Token refresh failed: {str(e)}"
            db.commit()
            raise Exception(f"Failed to refresh token: {str(e)}")
    
    def get_valid_access_token(self, connection: QuickBooksConnection, db: Session) -> str:
        """
        Get a valid access token, refreshing if necessary
        
        Args:
            connection: QuickBooksConnection object
            db: Database session
            
        Returns:
            Valid access token
        """
        # Check if token is expired or will expire in next 5 minutes
        if datetime.utcnow() + timedelta(minutes=5) >= connection.token_expires_at:
            logger.info(f"Token expired for realm_id {connection.realm_id}, refreshing...")
            connection = self.refresh_tokens(connection, db)
        
        return connection.access_token
    
    def revoke_tokens(self, connection: QuickBooksConnection, db: Session) -> bool:
        """
        Revoke QuickBooks access tokens and deactivate connection
        
        Args:
            connection: QuickBooksConnection object
            db: Database session
            
        Returns:
            True if successful
        """
        auth_client = OAuth2Client(
            client_id=self.client_id,
            client_secret=self.client_secret,
            redirect_uri=self.redirect_uri,
            environment=self.environment,
            refresh_token=connection.refresh_token
        )
        
        try:
            # Revoke tokens
            auth_client.revoke()
            
            # Mark connection as inactive
            connection.is_active = False
            connection.sync_status = "disconnected"
            db.commit()
            
            logger.info(f"Successfully revoked tokens for realm_id: {connection.realm_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error revoking tokens for realm_id {connection.realm_id}: {str(e)}")
            return False
    
    def get_company_info(self, connection: QuickBooksConnection, db: Session) -> Dict[str, Any]:
        """
        Fetch company information from QuickBooks
        
        Args:
            connection: QuickBooksConnection object
            db: Database session
            
        Returns:
            Company information dict
        """
        from intuitlib.client import AuthClient
        from intuitlib.enums import Scopes
        
        # Get valid access token
        access_token = self.get_valid_access_token(connection, db)
        
        # Create QuickBooks client (you'll need to implement actual API call)
        # This is a placeholder for the actual implementation
        try:
            # TODO: Implement actual QuickBooks API call
            # This would use the QuickBooks Python SDK to fetch company info
            company_info = {
                "realm_id": connection.realm_id,
                "company_name": connection.company_name or "Unknown",
            }
            
            # Update company name if we got it
            if company_info.get("company_name") and not connection.company_name:
                connection.company_name = company_info["company_name"]
                db.commit()
            
            return company_info
            
        except Exception as e:
            logger.error(f"Error fetching company info: {str(e)}")
            raise

