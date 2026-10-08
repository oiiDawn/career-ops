"""Verify Tavily credit fallback preserves requests and propagates other failures."""

import io
import os
from pathlib import Path
import sys
from urllib.error import HTTPError
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from career_ops.web_search import tavily


def failure(code):
    return HTTPError("https://api.tavily.com/search", code, "failure", {}, io.BytesIO())


with patch.dict(os.environ, {"TAVILY_API_KEY": "primary", "TAVILY_BACKUP_API_KEY": "backup"}, clear=True):
    for endpoint, payload in (("search", {"query": "AI"}), ("extract", {"urls": ["https://example.com"]})):
        for code in (432, 433):
            with patch("career_ops.web_search.urlopen", side_effect=[failure(code), io.BytesIO(b'{"results": []}')]) as post:
                assert tavily(endpoint, payload) == {"results": []}
                first, second = [call.args[0] for call in post.call_args_list]
                assert first.get_header("Authorization") == "Bearer primary"
                assert second.get_header("Authorization") == "Bearer backup"
                assert first.full_url == second.full_url == f"https://api.tavily.com/{endpoint}"
                assert first.data == second.data
    with patch("career_ops.web_search.urlopen", return_value=io.BytesIO(b'{"results": []}')) as post:
        tavily("search", {"query": "AI"})
        assert post.call_count == 1
    for code in (400, 401, 429, 500):
        error = failure(code)
        with patch("career_ops.web_search.urlopen", side_effect=error) as post:
            try:
                tavily("search", {"query": "AI"})
            except HTTPError as caught:
                assert caught is error
            else:
                raise AssertionError("Expected primary error")
            assert post.call_count == 1
    backup_error = failure(432)
    with patch("career_ops.web_search.urlopen", side_effect=[failure(432), backup_error]) as post:
        try:
            tavily("search", {"query": "AI"})
        except HTTPError as caught:
            assert caught is backup_error
        else:
            raise AssertionError("Expected backup error")
        assert post.call_count == 2
    for backup in ("", "primary"):
        with patch.dict(os.environ, {"TAVILY_BACKUP_API_KEY": backup}):
            with patch("career_ops.web_search.urlopen", side_effect=failure(432)) as post:
                try:
                    tavily("search", {"query": "AI"})
                except HTTPError:
                    pass
                else:
                    raise AssertionError("Expected exhausted credits error")
                assert post.call_count == 1

print("Tavily fallback checks passed")
