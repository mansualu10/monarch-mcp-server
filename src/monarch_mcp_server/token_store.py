"""
Persistent OAuth token store backed by Azure Table Storage.
Falls back to in-memory dicts when AZURE_STORAGE_CONNECTION_STRING is not set.
"""

import logging
import os
import time
from typing import Optional

logger = logging.getLogger(__name__)

AZURE_STORAGE_CONNECTION_STRING = os.environ.get("AZURE_STORAGE_CONNECTION_STRING", "")
TABLE_NAME = "oauthtokens"

# Partition keys for each token type
PK_ACCESS_TOKEN = "access_token"
PK_REFRESH_TOKEN = "refresh_token"
PK_AUTH_CODE = "auth_code"
PK_OAUTH_STATE = "oauth_state"
PK_REGISTERED_CLIENT = "registered_client"


class TableTokenStore:
    """
    Persistent token store using Azure Table Storage.
    Each entry is stored as a table entity with:
      - PartitionKey: token type (access_token, refresh_token, etc.)
      - RowKey: the token/code/state/client_id value
      - Additional columns: serialized data fields + expires timestamp
    """

    def __init__(self, connection_string: str, table_name: str = TABLE_NAME):
        from azure.data.tables import TableServiceClient

        self._service = TableServiceClient.from_connection_string(connection_string)
        self._table = self._service.get_table_client(table_name)
        logger.info("TableTokenStore connected to Azure Table Storage")

    def _put(self, partition_key: str, row_key: str, data: dict) -> None:
        entity = {
            "PartitionKey": partition_key,
            "RowKey": row_key,
            **{k: _serialize(v) for k, v in data.items()},
        }
        self._table.upsert_entity(entity)

    def _get(self, partition_key: str, row_key: str) -> Optional[dict]:
        try:
            entity = self._table.get_entity(partition_key=partition_key, row_key=row_key)
            data = {k: v for k, v in entity.items() if k not in ("PartitionKey", "RowKey", "odata.etag", "Timestamp")}
            data = {k: _deserialize(v) for k, v in data.items()}
            # Check expiration
            if "expires" in data and data["expires"] < time.time():
                self._delete(partition_key, row_key)
                return None
            return data
        except Exception:
            return None

    def _delete(self, partition_key: str, row_key: str) -> None:
        try:
            self._table.delete_entity(partition_key=partition_key, row_key=row_key)
        except Exception:
            pass

    def _pop(self, partition_key: str, row_key: str) -> Optional[dict]:
        data = self._get(partition_key, row_key)
        if data is not None:
            self._delete(partition_key, row_key)
        return data

    # --- Access Tokens ---
    def set_access_token(self, token: str, data: dict) -> None:
        self._put(PK_ACCESS_TOKEN, token, data)

    def get_access_token(self, token: str) -> Optional[dict]:
        return self._get(PK_ACCESS_TOKEN, token)

    def delete_access_token(self, token: str) -> None:
        self._delete(PK_ACCESS_TOKEN, token)

    # --- Refresh Tokens ---
    def set_refresh_token(self, token: str, data: dict) -> None:
        self._put(PK_REFRESH_TOKEN, token, data)

    def get_refresh_token(self, token: str) -> Optional[dict]:
        return self._get(PK_REFRESH_TOKEN, token)

    def pop_refresh_token(self, token: str) -> Optional[dict]:
        return self._pop(PK_REFRESH_TOKEN, token)

    def delete_refresh_token(self, token: str) -> None:
        self._delete(PK_REFRESH_TOKEN, token)

    # --- Auth Codes ---
    def set_auth_code(self, code: str, data: dict) -> None:
        self._put(PK_AUTH_CODE, code, data)

    def pop_auth_code(self, code: str) -> Optional[dict]:
        return self._pop(PK_AUTH_CODE, code)

    # --- OAuth States ---
    def set_oauth_state(self, state: str, data: dict) -> None:
        self._put(PK_OAUTH_STATE, state, data)

    def pop_oauth_state(self, state: str) -> Optional[dict]:
        return self._pop(PK_OAUTH_STATE, state)

    # --- Registered Clients ---
    def set_registered_client(self, client_id: str, data: dict) -> None:
        self._put(PK_REGISTERED_CLIENT, client_id, data)

    def get_registered_client(self, client_id: str) -> Optional[dict]:
        return self._get(PK_REGISTERED_CLIENT, client_id)

    # --- Cleanup ---
    def cleanup_expired(self) -> None:
        """Remove all expired entities across all partition keys."""
        now = time.time()
        for pk in [PK_ACCESS_TOKEN, PK_REFRESH_TOKEN, PK_AUTH_CODE, PK_OAUTH_STATE]:
            try:
                entities = self._table.query_entities(
                    query_filter=f"PartitionKey eq '{pk}'",
                    select=["PartitionKey", "RowKey", "expires"],
                )
                for entity in entities:
                    expires = entity.get("expires")
                    if expires is not None and float(expires) < now:
                        self._delete(pk, entity["RowKey"])
            except Exception as e:
                logger.warning(f"Cleanup error for {pk}: {e}")


class InMemoryTokenStore:
    """In-memory fallback when Azure Table Storage is not configured."""

    def __init__(self):
        self._access_tokens: dict[str, dict] = {}
        self._refresh_tokens: dict[str, dict] = {}
        self._auth_codes: dict[str, dict] = {}
        self._oauth_states: dict[str, dict] = {}
        self._registered_clients: dict[str, dict] = {}
        logger.info("InMemoryTokenStore initialized (no persistence)")

    def set_access_token(self, token: str, data: dict) -> None:
        self._access_tokens[token] = data

    def get_access_token(self, token: str) -> Optional[dict]:
        data = self._access_tokens.get(token)
        if data and data.get("expires", float("inf")) < time.time():
            del self._access_tokens[token]
            return None
        return data

    def delete_access_token(self, token: str) -> None:
        self._access_tokens.pop(token, None)

    def set_refresh_token(self, token: str, data: dict) -> None:
        self._refresh_tokens[token] = data

    def get_refresh_token(self, token: str) -> Optional[dict]:
        data = self._refresh_tokens.get(token)
        if data and data.get("expires", float("inf")) < time.time():
            del self._refresh_tokens[token]
            return None
        return data

    def pop_refresh_token(self, token: str) -> Optional[dict]:
        data = self._refresh_tokens.pop(token, None)
        if data and data.get("expires", float("inf")) < time.time():
            return None
        return data

    def delete_refresh_token(self, token: str) -> None:
        self._refresh_tokens.pop(token, None)

    def set_auth_code(self, code: str, data: dict) -> None:
        self._auth_codes[code] = data

    def pop_auth_code(self, code: str) -> Optional[dict]:
        return self._auth_codes.pop(code, None)

    def set_oauth_state(self, state: str, data: dict) -> None:
        self._oauth_states[state] = data

    def pop_oauth_state(self, state: str) -> Optional[dict]:
        return self._oauth_states.pop(state, None)

    def set_registered_client(self, client_id: str, data: dict) -> None:
        self._registered_clients[client_id] = data

    def get_registered_client(self, client_id: str) -> Optional[dict]:
        return self._registered_clients.get(client_id)

    def cleanup_expired(self) -> None:
        now = time.time()
        for store in [self._access_tokens, self._refresh_tokens, self._auth_codes, self._oauth_states]:
            for key in list(store.keys()):
                if store[key].get("expires", float("inf")) < now:
                    del store[key]


def create_token_store() -> TableTokenStore | InMemoryTokenStore:
    """Factory: use Azure Table Storage if configured, else in-memory."""
    conn_str = AZURE_STORAGE_CONNECTION_STRING
    if conn_str:
        try:
            store = TableTokenStore(conn_str)
            logger.info("Using Azure Table Storage for persistent token storage")
            return store
        except Exception as e:
            logger.error(f"Failed to connect to Azure Table Storage: {e}")
            logger.warning("Falling back to in-memory token storage")
    else:
        logger.info("AZURE_STORAGE_CONNECTION_STRING not set — using in-memory token storage")
    return InMemoryTokenStore()


def _serialize(value) -> str:
    """Serialize a value for Table Storage (all values stored as strings)."""
    import json
    if isinstance(value, (list, dict)):
        return json.dumps(value)
    return str(value)


def _deserialize(value):
    """Attempt to deserialize a string value back to its original type."""
    import json
    if not isinstance(value, str):
        return value
    # Try float (for timestamps/expires)
    try:
        f = float(value)
        if "." in value or f > 1e9:  # looks like a timestamp or float
            return f
        return int(f) if f == int(f) else f
    except (ValueError, OverflowError):
        pass
    # Try JSON (for lists/dicts)
    try:
        return json.loads(value)
    except (json.JSONDecodeError, ValueError):
        pass
    return value
