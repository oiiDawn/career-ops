"""Verify ordered Tavily credentials, request preservation and failure boundaries."""

import io
import json
import os
from pathlib import Path
import sys
from urllib.error import HTTPError
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from career_ops.web_search import tavily, tavily_keys


def failure(code):
    return HTTPError("https://api.tavily.com/search", code, "failure", {}, io.BytesIO())


with patch.dict(os.environ, {"TAVILY_API_KEYS": json.dumps(["first", "second", "third"])}, clear=True):
    for endpoint, payload in (("search", {"query": "AI"}), ("extract", {"urls": ["https://example.com"]})):
        for code in (401, 432, 433):
            with patch("career_ops.web_search.urlopen", side_effect=[failure(code), failure(code), io.BytesIO(b'{"results": []}')]) as post:
                assert tavily(endpoint, payload) == {"results": []}
                requests = [call.args[0] for call in post.call_args_list]
                assert [r.get_header("Authorization") for r in requests] == ["Bearer first", "Bearer second", "Bearer third"]
                assert all(r.full_url == f"https://api.tavily.com/{endpoint}" for r in requests)
                assert all(r.data == requests[0].data for r in requests)
    with patch("career_ops.web_search.urlopen", side_effect=[failure(432), io.BytesIO(b'{"results": []}')]) as post:
        tavily("search", {"query": "AI"})
        assert post.call_count == 2
    with patch("career_ops.web_search.urlopen", return_value=io.BytesIO(b'{"results": []}')) as post:
        tavily("search", {"query": "AI"})
        assert post.call_count == 1
    for codes in ((400,), (429,), (500,), (432, 432, 433)):
        errors = [failure(code) for code in codes]
        with patch("career_ops.web_search.urlopen", side_effect=errors) as post:
            try:
                tavily("search", {"query": "AI"})
            except HTTPError as caught:
                assert caught is errors[-1]
            else:
                raise AssertionError("Expected request failure")
            assert post.call_count == len(codes)
    for invalid in ('', '[]', '{}', '["good", null]', '[""]', '["   "]', 'secret-not-json'):
        with patch.dict(os.environ, {"TAVILY_API_KEYS": invalid}):
            try:
                tavily_keys()
            except RuntimeError as error:
                assert str(error) == "TAVILY_API_KEYS must be a non-empty JSON array of strings"
            else:
                raise AssertionError("Expected invalid credential configuration")

print("Tavily ordered credential checks passed")
