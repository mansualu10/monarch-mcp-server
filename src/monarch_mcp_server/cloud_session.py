"""
Cloud-compatible session management for Monarch Money MCP Server.
Uses environment variables instead of macOS Keychain for cloud deployment.
"""

import logging
import os
from typing import Optional
from monarchmoney import MonarchMoney

logger = logging.getLogger(__name__)

ENV_VAR_TOKEN = "MONARCH_TOKEN"


class CloudMonarchSession:
    """Manages Monarch Money sessions using environment variables (for cloud deployment)."""

    def load_token(self) -> Optional[str]:
        """Load the authentication token from environment variable."""
        token = os.environ.get(ENV_VAR_TOKEN)
        if token:
            logger.info("Token loaded from environment variable")
            return token
        logger.warning("No MONARCH_TOKEN environment variable found")
        return None

    def get_authenticated_client(self) -> Optional[MonarchMoney]:
        """Get an authenticated MonarchMoney client."""
        token = self.load_token()
        if not token:
            return None

        try:
            client = MonarchMoney(token=token)
            logger.info("MonarchMoney client created with cloud token")
            return client
        except Exception as e:
            logger.error(f"Failed to create MonarchMoney client: {e}")
            return None


cloud_session = CloudMonarchSession()
