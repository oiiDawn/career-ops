"""Run Tavily web search without a model or workflow state changes."""

import json
import os
import sys
from urllib.request import Request, urlopen
from urllib.error import HTTPError


def tavily_keys() -> list[str]:
    """Read the ordered, non-empty JSON array of Tavily credentials."""
    try:
        keys = json.loads(os.environ.get("TAVILY_API_KEYS", "[]"))
    except json.JSONDecodeError:
        raise RuntimeError("TAVILY_API_KEYS must be a non-empty JSON array of strings") from None
    if not isinstance(keys, list) or not keys or any(not isinstance(key, str) or not key.strip() for key in keys):
        raise RuntimeError("TAVILY_API_KEYS must be a non-empty JSON array of strings")
    return keys


def tavily(endpoint: str, payload: dict) -> dict:
    """Try credentials in order until one succeeds or a request-level error occurs."""
    keys = tavily_keys()
    for index, request_key in enumerate(keys):
        request = Request(
            f"{os.environ.get('TAVILY_BASE_URL', 'https://api.tavily.com')}/{endpoint}",
            data=json.dumps(payload).encode(),
            headers={"Authorization": f"Bearer {request_key}", "Content-Type": "application/json"},
        )
        try:
            with urlopen(request, timeout=60) as response:
                return json.load(response)
        except HTTPError as error:
            if error.code not in (401, 432, 433) or index == len(keys) - 1:
                raise
            error.close()


def main() -> None:
    from career_ops import context  # noqa: F401 - loads the project .env

    request = json.load(sys.stdin)
    query = request.get("query")
    if not isinstance(query, str) or not query.strip():
        raise ValueError("Search query must be a non-empty string")
    result = tavily("search", {"query": query, "max_results": 20})
    if not isinstance(result.get("results"), list):
        raise RuntimeError("Search returned invalid results")
    json.dump([{"title": item.get("title", ""), "url": item.get("url", ""),
                "description": item.get("content", ""), "position": index + 1}
               for index, item in enumerate(result["results"])], sys.stdout, ensure_ascii=False)


if __name__ == "__main__":
    main()
