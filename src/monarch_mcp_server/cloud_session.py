"""
Cloud-compatible session management for Monarch Money MCP Server.
Uses environment variables and Azure Table Storage for token management.
Token is refreshed locally via push_monarch_token.py — NOT by automated server-side login.
"""

import logging
import os
from typing import Optional
from monarchmoney import MonarchMoney

logger = logging.getLogger(__name__)

ENV_VAR_TOKEN = "MONARCH_TOKEN"

# Azure Table Storage config for persisting tokens pushed from local machine
AZURE_STORAGE_CONNECTION_STRING = os.environ.get("AZURE_STORAGE_CONNECTION_STRING", "")
MONARCH_SESSION_TABLE = "monarchsession"
MONARCH_SESSION_PK = "token"
MONARCH_SESSION_RK = "current"


class CloudMonarchSession:
    """Manages Monarch Money sessions for cloud deployment.
    Token priority: in-memory cache > Azure Table Storage > MONARCH_TOKEN env var.
    Tokens are refreshed locally via push_monarch_token.py — never by automated login."""

    def __init__(self):
        self._cached_token: Optional[str] = None

    def load_token(self) -> Optional[str]:
        """Load token: in-memory cache > Azure Table Storage > env var."""
        if self._cached_token:
            return self._cached_token

        # Check Azure Table Storage (populated by push_monarch_token.py)
        token = self._load_from_table_storage()
        if token:
            self._cached_token = token
            logger.info("Token loaded from Azure Table Storage")
            return token

        # Fall back to env var secret
        token = os.environ.get(ENV_VAR_TOKEN)
        if token:
            self._cached_token = token
            logger.info("Token loaded from MONARCH_TOKEN environment variable")
            return token

        logger.warning("No Monarch token found — run push_monarch_token.py locally to refresh")
        return None

    def invalidate(self) -> None:
        """Clear the in-memory cache so the next call re-reads from Table Storage."""
        self._cached_token = None
        logger.info("In-memory token cache cleared")

    def _load_from_table_storage(self) -> Optional[str]:
        """Load token from Azure Table Storage."""
        if not AZURE_STORAGE_CONNECTION_STRING:
            return None
        try:
            from azure.data.tables import TableServiceClient
            service = TableServiceClient.from_connection_string(AZURE_STORAGE_CONNECTION_STRING)
            table = service.get_table_client(MONARCH_SESSION_TABLE)
            entity = table.get_entity(partition_key=MONARCH_SESSION_PK, row_key=MONARCH_SESSION_RK)
            return entity.get("token")
        except Exception:
            return None

    def save_token(self, token: str) -> None:
        """Persist token to Azure Table Storage (called by push_monarch_token.py via API)."""
        self._cached_token = token
        if not AZURE_STORAGE_CONNECTION_STRING:
            logger.warning("AZURE_STORAGE_CONNECTION_STRING not set — token not persisted")
            return
        try:
            from azure.data.tables import TableServiceClient
            service = TableServiceClient.from_connection_string(AZURE_STORAGE_CONNECTION_STRING)
            try:
                service.create_table(MONARCH_SESSION_TABLE)
            except Exception:
                pass  # already exists
            table = service.get_table_client(MONARCH_SESSION_TABLE)
            table.upsert_entity({
                "PartitionKey": MONARCH_SESSION_PK,
                "RowKey": MONARCH_SESSION_RK,
                "token": token,
            })
            logger.info("Token persisted to Azure Table Storage")
        except Exception as e:
            logger.warning(f"Could not persist token to Table Storage: {e}")

    def get_authenticated_client(self) -> Optional[MonarchMoney]:
        """Get an authenticated MonarchMoney client using the stored token."""
        token = self.load_token()
        if not token:
            return None
        try:
            return MonarchMoney(token=token)
        except Exception as e:
            logger.error(f"Failed to create MonarchMoney client: {e}")
            return None


cloud_session = CloudMonarchSession()
