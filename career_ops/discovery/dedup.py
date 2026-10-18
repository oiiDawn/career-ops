"""Compare discovered posting URLs and company-role identities with retained SQLite facts."""

from __future__ import annotations

from datetime import date
import html
import re
import sqlite3
import unicodedata
from urllib.parse import parse_qsl, unquote, urlencode, urlsplit, urlunsplit


STRIP_PARAMS = frozenset("language lang locale utm_source utm_medium utm_campaign utm_term utm_content ref src source gh_src lever-origin lever-source rltr feedid".split())
LOCATION_SUFFIXES = frozenset([
    "amer", "americas", "amsterdam", "apac", "austin", "barcelona", "bay area", "belgium", "berlin", "boston",
    "brussels", "budapest", "canada", "chicago", "copenhagen", "dublin", "emea", "eu", "europe", "finland",
    "france", "frankfurt", "germany", "hamburg", "helsinki", "india", "ireland", "italy", "la", "latin america",
    "lisbon", "london", "los angeles", "madrid", "melbourne", "milan", "montreal", "munich", "netherlands",
    "new york", "north america", "nyc", "on site", "onsite", "oslo", "paris", "poland", "porto", "prague",
    "remote", "rome", "san francisco", "seattle", "sf", "singapore", "spain", "stockholm", "sydney", "tokyo",
    "toronto", "uk", "united kingdom", "united states", "us", "usa", "vancouver", "vienna", "warsaw", "zurich",
    "hong kong", "hk", "shanghai", "shenzhen", "hangzhou", "suzhou", "beijing", "in office",
])
REMOTE_SUFFIXES = frozenset(("distributed", "hybrid", "on site", "onsite", "remote", "wfh", "work from home"))


def _text_key(value: object, separator: str = "") -> str:
    text = unicodedata.normalize("NFKC", str(value or "")).lower().replace("\u0307", "")
    parts = []
    discarded = False
    for char in text:
        if unicodedata.category(char)[0] in {"L", "M", "N"}:
            if discarded and separator:
                parts.append(separator)
            parts.append(char)
            discarded = False
        else:
            discarded = True
    return "".join(parts).strip()


def _location_suffix(tag: str) -> bool:
    normalized = _text_key(tag, " ")
    if normalized in LOCATION_SUFFIXES:
        return True
    parts = [_text_key(part, " ") for part in re.split(r"[,/|;]+|\s+(?:and|or)\s+", tag.lower())]
    parts = [part for part in parts if part]
    if len(parts) > 1 and all(part in LOCATION_SUFFIXES for part in parts):
        return True
    return any(normalized.startswith(remote + " ") and normalized[len(remote) + 1:] in LOCATION_SUFFIXES
               for remote in REMOTE_SUFFIXES)


def role_key(role: object) -> str:
    title = unicodedata.normalize("NFKC", html.unescape(str(role or ""))).lower()
    while "|" in title and _location_suffix(title.rsplit("|", 1)[1]):
        title = title.rsplit("|", 1)[0].rstrip()
    while match := re.search(r"\s*[\[(]([^\[\]()]+)[\])]\s*$", title):
        if not _location_suffix(match.group(1)):
            break
        title = title[:match.start()].rstrip()
    return _text_key(title, " ")


def company_aliases(aliases: object) -> dict[str, str]:
    if not isinstance(aliases, dict):
        return {}
    canonical = {str(name).strip().lower() for name in aliases if str(name).strip()}
    resolved = {name: name for name in canonical}
    claims = {}
    for name, values in aliases.items():
        owner = str(name).strip().lower()
        if not owner:
            continue
        for alias in values if isinstance(values, list) else [values]:
            key = str(alias or "").strip().lower()
            if key and key not in canonical:
                claims.setdefault(key, set()).add(owner)
    for alias, owners in claims.items():
        if len(owners) == 1:
            resolved[alias] = next(iter(owners))
    return resolved


def company_role_key(company: object, role: object, aliases: dict[str, str] | None = None) -> str:
    name = str(company or "").strip().lower()
    return f"{(aliases or {}).get(name, name)}::{role_key(role)}"


def url_key(raw: object) -> object:
    """Compare source posting identities without changing retained evidence URLs."""
    if not isinstance(raw, str) or not raw:
        return raw
    try:
        parsed = urlsplit(raw)
        if not parsed.scheme or not parsed.netloc:
            return raw
        host = parsed.hostname or ""
        if re.fullmatch(r"(?:[\w-]+\.)*linkedin\.com", host.lower()):
            posting = re.fullmatch(r"/jobs/view/(?:.*-)?(\d+)/?", parsed.path)
            if posting:
                return f"https://www.linkedin.com/jobs/view/{posting[1]}"
        netloc = parsed.netloc.lower()
        query = [(key, value) for key, value in parse_qsl(parsed.query, keep_blank_values=True)
                 if key.lower() not in STRIP_PARAMS]
        if host.lower() == "app.mokahr.com":
            fragment = re.fullmatch(r"/job/([^/?#]+)(?:\?[^#]*)?", parsed.fragment)
            if fragment:
                job_id = unquote(fragment.group(1))
                query = [(key, value) for key, value in query if key != "mokahr_job_id"]
                query.append(("mokahr_job_id", job_id))
        path = parsed.path.rstrip("/").lower() or "/"
        return urlunsplit((parsed.scheme.lower(), netloc, path, urlencode(query), ""))
    except ValueError:
        return raw


def should_dedup(first_seen: str, status: str, *, today: date, recheck_after_days: int | None) -> bool:
    if status in {"skipped_invalid_url", "skipped_blocked_host"}:
        return True
    if status.startswith("cooldown:"):
        return today.isoformat() < status.rsplit(":", 1)[-1]
    if status != "added" or recheck_after_days is None:
        return True
    try:
        first = date.fromisoformat(first_seen)
    except (TypeError, ValueError):
        return True
    return (today - first).days < recheck_after_days


def database_snapshot(db: sqlite3.Connection, *, today: date, recheck_after_days: int | None = None) -> dict:
    """Skip known source identities; titles alone cannot establish duplicate openings."""
    rows = [dict(row) for row in db.execute(
        "SELECT url,CASE WHEN state='discovered' THEN 'added' ELSE 'processed' END status, "
        "substr(created_at,1,10) first_seen FROM opportunities")]
    rows.extend(dict(row) for row in db.execute(
        "SELECT url,status,substr(created_at,1,10) first_seen FROM scan_outcomes"))
    eligible = [row for row in rows if should_dedup(row["first_seen"], row["status"],
                                                    today=today, recheck_after_days=recheck_after_days)]
    seen = {url_key(row["url"]) for row in eligible}
    for row in db.execute("SELECT s.url,o.state,substr(o.created_at,1,10) first_seen "
                          "FROM scan_observations s JOIN opportunities o ON o.id=s.opportunity_id"):
        if should_dedup(row['first_seen'], 'added' if row['state'] == 'discovered' else 'processed',
                        today=today, recheck_after_days=recheck_after_days):
            seen.add(url_key(row['url']))
    fingerprints = [dict(row) for row in db.execute(
        "SELECT o.url,substr(r.first_seen,1,10) dateStr,o.company,o.role title,r.fingerprint "
        "FROM repost_inputs r JOIN opportunities o ON o.id=r.opportunity_id")]
    return {"seen": seen, "recheck_eligible": len(rows) - len(eligible),
            "fingerprint_history": fingerprints}
