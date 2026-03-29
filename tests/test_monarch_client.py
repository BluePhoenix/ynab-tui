"""Tests for Monarch client authentication handling."""

import asyncio

from ynab_tui.clients.monarch_client import MonarchClient
from ynab_tui.config import MonarchConfig


class FakeMonarchApiClient:
    """Minimal fake Monarch API client for auth tests."""

    def __init__(self):
        self.token = None
        self._headers = {}
        self.load_session_calls = []

    def set_token(self, token):
        self.token = token
        self._headers["Authorization"] = f"Token {token}"

    def load_session(self, session_path=None):
        self.load_session_calls.append(session_path)


def test_session_token_does_not_call_load_session():
    """Session tokens should be applied directly, not treated like pickle files."""
    api_client = FakeMonarchApiClient()
    client = MonarchClient(
        MonarchConfig(enabled=True, session_token="token-123"),
        api_client=api_client,
    )

    client._load_session(api_client)

    assert api_client.token == "token-123"
    assert api_client._headers["Authorization"] == "Token token-123"
    assert api_client.load_session_calls == []


class FakeGraphQLExecutor:
    """Minimal GraphQL client matching the installed gql signature."""

    def __init__(self):
        self.calls = []

    async def execute_async(self, request, **kwargs):
        self.calls.append((request, kwargs))
        return {"accounts": [{"id": "acc-1"}, {"id": "acc-2"}]}


class FakeMonarchApiClientWithOldGqlCall(FakeMonarchApiClient):
    """Fake client mimicking the installed monarchmoney gql_call incompatibility."""

    def __init__(self):
        super().__init__()
        self.graphql_client = FakeGraphQLExecutor()

    def _get_graphql_client(self):
        return self.graphql_client

    async def gql_call(self, operation, graphql_query, variables={}):
        return await self._get_graphql_client().execute_async(
            document=graphql_query,
            operation_name=operation,
            variable_values=variables,
        )

    async def get_accounts(self):
        return await self.gql_call("GetAccounts", "query")


def test_test_connection_applies_gql_compatibility_shim():
    """test_connection should patch older monarchmoney gql_call usage."""
    api_client = FakeMonarchApiClientWithOldGqlCall()
    client = MonarchClient(
        MonarchConfig(enabled=True, session_token="token-123"),
        api_client=api_client,
    )

    client._apply_compatibility_shims(api_client)
    result = client.test_connection()

    assert result == {"success": True, "account_count": 2}
    assert api_client.graphql_client.calls == [("query", {"operation_name": "GetAccounts", "variable_values": {}})]
