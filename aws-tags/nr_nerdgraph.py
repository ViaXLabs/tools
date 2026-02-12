import os
import time
from typing import Any, Dict, Optional

import requests

NERDGRAPH_ENDPOINT = "https://api.newrelic.com/graphql"


class NerdGraphError(RuntimeError):
    pass


def _mask_key(key: str) -> str:
    if not key:
        return ""
    if len(key) <= 6:
        return "***"
    return key[:3] + "***" + key[-3:]


class NerdGraphClient:
    """
    NerdGraph client using env var NR_API_KEY.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        endpoint: str = NERDGRAPH_ENDPOINT,
        timeout_s: int = 60,
        max_retries: int = 5,
        backoff_base_s: float = 1.0,
    ):
        self.api_key = api_key or os.environ.get("NR_API_KEY")
        if not self.api_key:
            raise ValueError("NR_API_KEY is not set (or api_key not provided).")

        self.endpoint = endpoint
        self.timeout_s = timeout_s
        self.max_retries = max_retries
        self.backoff_base_s = backoff_base_s

    def graphql(self, query: str, variables: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        headers = {"Content-Type": "application/json", "API-Key": self.api_key}
        payload = {"query": query, "variables": variables or {}}

        last_err = None
        for attempt in range(1, self.max_retries + 1):
            try:
                resp = requests.post(self.endpoint, headers=headers, json=payload, timeout=self.timeout_s)

                if resp.status_code in (429, 500, 502, 503, 504):
                    time.sleep(self.backoff_base_s * (2 ** (attempt - 1)))
                    continue

                if resp.status_code != 200:
                    raise NerdGraphError(f"HTTP {resp.status_code}: {resp.text}")

                data = resp.json()
                if data.get("errors"):
                    raise NerdGraphError(f"GraphQL errors: {data['errors']}")

                return data

            except (requests.RequestException, ValueError, NerdGraphError) as e:
                last_err = e
                if attempt < self.max_retries:
                    time.sleep(self.backoff_base_s * (2 ** (attempt - 1)))
                    continue
                break

        raise NerdGraphError(
            f"NerdGraph request failed after {self.max_retries} retries. "
            f"Last error: {last_err}. API key={_mask_key(self.api_key)}"
        )
