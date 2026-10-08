"""Run Tavily web search without a model or workflow state changes."""

import json
import os
import sys
from urllib.request import Request, urlopen
from urllib.error import HTTPError


def tavily(endpoint: str, payload: dict) -> dict:
    """POST to Tavily, retrying once with the backup key on exhausted credits."""
    key = os.environ.get("TAVILY_API_KEY")
    if not key:
        raise RuntimeError("TAVILY_API_KEY is not configured")
    backup_key = os.environ.get("TAVILY_BACKUP_API_KEY")
    keys = [key]
    if backup_key and backup_key != key:
        keys.append(backup_key)
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
            if error.code not in (432, 433) or index == len(keys) - 1:
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
