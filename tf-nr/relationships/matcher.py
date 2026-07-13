"""
Minimal NerdGraph (New Relic GraphQL API) client.

Auth: New Relic User API key, read from the NEW_RELIC_API_KEY env var
(never pass it on the command line or hard-code it in a script -- it
will show up in shell history).

Docs: https://docs.newrelic.com/docs/apis/nerdgraph/get-started/introduction-new-relic-nerdgraph/
Explorer (great for verifying field names against your account's schema
before scripting against them): https://api.newrelic.com/graphiql
"""
from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass
from typing import Any, Optional

import requests

logger = logging.getLogger("nr_rel.client")

US_ENDPOINT = "https://api.newrelic.com/graphql"
EU_ENDPOINT = "https://api.eu.newrelic.com/graphql"


class NerdGraphError(RuntimeError):
    """Raised when NerdGraph returns transport or GraphQL-level errors."""


@dataclass
class NerdGraphClient:
    api_key: str
    region: str = "US"  # "US" or "EU"
    timeout: int = 30
    max_retries: int = 3
    retry_backoff_seconds: float = 1.5

    def __post_init__(self) -> None:
        if not self.api_key:
            raise NerdGraphError(
                "No API key provided. Set NEW_RELIC_API_KEY (a User API key, "
                "prefix NRAK-...) in your environment or .env file."
            )
        self.endpoint = EU_ENDPOINT if self.region.upper() == "EU" else US_ENDPOINT

    @classmethod
    def from_env(cls) -> "NerdGraphClient":
        api_key = os.environ.get("NEW_RELIC_API_KEY", "")
        region = os.environ.get("NEW_RELIC_REGION", "US")
        return cls(api_key=api_key, region=region)

    def execute(self, query: str, variables: Optional[dict[str, Any]] = None) -> dict[str, Any]:
        """Run a GraphQL query/mutation. Returns the `data` object.

        Raises NerdGraphError on transport failure or GraphQL `errors`.
        """
        payload = {"query": query, "variables": variables or {}}
        headers = {
            "Content-Type": "application/json",
            "Api-Key": self.api_key,
        }

        last_exc: Optional[Exception] = None
        for attempt in range(1, self.max_retries + 1):
            try:
                resp = requests.post(
                    self.endpoint, json=payload, headers=headers, timeout=self.timeout
                )
            except requests.RequestException as exc:
                last_exc = exc
                logger.warning("NerdGraph request failed (attempt %d/%d): %s", attempt, self.max_retries, exc)
                time.sleep(self.retry_backoff_seconds * attempt)
                continue

            if resp.status_code == 429:
                wait = self.retry_backoff_seconds * attempt * 2
                logger.warning("Rate limited by NerdGraph, backing off %.1fs", wait)
                time.sleep(wait)
                continue

            if resp.status_code >= 500:
                logger.warning("NerdGraph server error %s (attempt %d/%d)", resp.status_code, attempt, self.max_retries)
                time.sleep(self.retry_backoff_seconds * attempt)
                continue

            if resp.status_code != 200:
                raise NerdGraphError(f"NerdGraph HTTP {resp.status_code}: {resp.text[:500]}")

            body = resp.json()
            if "errors" in body and body["errors"]:
                raise NerdGraphError(f"NerdGraph GraphQL errors: {body['errors']}")

            return body.get("data", {})

        raise NerdGraphError(f"NerdGraph request failed after {self.max_retries} attempts: {last_exc}")
