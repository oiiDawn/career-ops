"""Run Tavily web search without a model or workflow state changes."""

import json
import os
import sys
from urllib.request import Request, urlopen


def tavily(endpoint: str, payload: dict) -> dict:
    """POST one Tavily API request; non-2xx responses raise with the response body."""
    key = os.environ.get("TAVILY_API_KEY")
    if not key:
        raise RuntimeError("TAVILY_API_KEY is not configured")
    request = Request(
        f"{os.environ.get('TAVILY_BASE_URL', 'https://api.tavily.com')}/{endpoint}",
        data=json.dumps(payload).encode(),
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
    )
    with urlopen(request, timeout=60) as response:
        return json.load(response)


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
