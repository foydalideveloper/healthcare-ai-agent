"""Lightweight Supabase client using httpx (avoids heavy supabase-py dependencies).
Uses Supabase REST API (PostgREST) directly."""

from functools import lru_cache
import httpx
from app.config import get_settings


class SupabaseClient:
    """Lightweight Supabase PostgREST client."""

    def __init__(self, url: str, key: str):
        self.base_url = f"{url}/rest/v1"
        self.headers = {
            "apikey": key,
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "Prefer": "return=representation",
        }
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            headers=self.headers,
            timeout=30.0,
        )

    async def select(
        self, table: str, columns: str = "*",
        filters: dict | None = None, order: str | None = None,
        limit: int | None = None,
    ) -> list[dict]:
        params = {"select": columns}
        if filters:
            for key, val in filters.items():
                params[key] = val
        if order:
            params["order"] = order
        if limit:
            params["limit"] = str(limit)
        resp = await self._client.get(f"/{table}", params=params)
        resp.raise_for_status()
        return resp.json()

    async def insert(self, table: str, data: dict | list[dict]) -> list[dict]:
        resp = await self._client.post(f"/{table}", json=data)
        resp.raise_for_status()
        return resp.json()

    async def update(self, table: str, data: dict, filters: dict) -> list[dict]:
        params = {}
        for key, val in filters.items():
            params[key] = val
        resp = await self._client.patch(f"/{table}", params=params, json=data)
        resp.raise_for_status()
        return resp.json()

    async def delete(self, table: str, filters: dict) -> list[dict]:
        params = {}
        for key, val in filters.items():
            params[key] = val
        resp = await self._client.delete(f"/{table}", params=params)
        resp.raise_for_status()
        return resp.json()

    async def rpc(self, function_name: str, params: dict | None = None) -> dict:
        resp = await self._client.post(f"/rpc/{function_name}", json=params or {})
        resp.raise_for_status()
        return resp.json()


@lru_cache
def get_db() -> SupabaseClient:
    """Get Supabase client with anon key (respects RLS)."""
    settings = get_settings()
    return SupabaseClient(settings.supabase_url, settings.supabase_anon_key)


@lru_cache
def get_db_admin() -> SupabaseClient:
    """Get Supabase client with service role key (bypasses RLS).
    Use only for server-side operations."""
    settings = get_settings()
    return SupabaseClient(settings.supabase_url, settings.supabase_service_role_key)
