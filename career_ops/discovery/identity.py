"""Resolve posting aliases and conservative cross-source identities against current business facts."""

from __future__ import annotations

import html
import json
import re
from urllib.parse import urlsplit

from career_ops.discovery.dedup import _text_key, company_role_key, url_key


BOARD_HOSTS = ('linkedin.com', 'jobsdb.com', 'efinancialcareers.hk', 'hkstp.org')
CITY_NAMES = {
    'beijing': ('beijing', '北京'), 'shanghai': ('shanghai', '上海'),
    'shenzhen': ('shenzhen', '深圳'), 'hangzhou': ('hangzhou', '杭州'),
    'suzhou': ('suzhou', '苏州'), 'hongkong': ('hong kong', 'hongkong', '香港'),
}


def requisition(offer: dict) -> str | None:
    """Use employer requisitions, never a job board's advertisement number."""
    parsed = urlsplit(offer['url'])
    host = (parsed.hostname or '').lower()
    path = parsed.path
    if host.endswith('.myworkdayjobs.com'):
        match = re.search(r'_((?:JR-?\d+|R-\d+))(?:-\d+)?$', path)
        if match:
            return match[1]
    for domain, pattern in (
        ('jobs.siemens.com', r'/JobDetail/(\d+)/?$'),
        ('apply.careers.microsoft.com', r'/job/(\d+)/?$'),
        ('jobs.smartrecruiters.com', r'/[^/]+/(\d+)(?:-|$)'),
    ):
        if host == domain and (match := re.search(pattern, path)):
            return f'{domain}:{match[1]}'
    if any(host == board or host.endswith('.' + board) for board in BOARD_HOSTS):
        text = (offer.get('scan_jd') or {}).get('text') or offer.get('description') or ''
        ids = set(re.findall(r'(?im)(?:^[\s,]*|\bjob(?: requisition)? id\s*:?\s*)((?:JR-?\d+|R-\d+))\s*$', text))
        if len(ids) == 1:
            return ids.pop()
    return None


def _board(url: str) -> bool:
    host = (urlsplit(url).hostname or '').lower()
    return any(host == board or host.endswith('.' + board) for board in BOARD_HOSTS)


def _same_location(left: object, right: object) -> bool:
    if not left or not right:
        return False
    a, b = str(left).lower(), str(right).lower()
    cities_a = {city for city, names in CITY_NAMES.items() if any(name in a for name in names)}
    cities_b = {city for city, names in CITY_NAMES.items() if any(name in b for name in names)}
    if cities_a or cities_b:
        return bool(cities_a) and cities_a == cities_b
    return _text_key(a) == _text_key(b)


def _body(text: object) -> str:
    """Compare complete substantive text, retaining numbers and rejecting empty heading captures."""
    text = html.unescape(str(text or ''))
    text = re.sub(r'(?m)^\s*\d+[.)、]\s+', '', text)
    start = re.search(r'岗位职责|job description\s*:?|job responsibilities|about the role|we rely on you to|^role\b', text, re.I)
    if not start:
        return ''
    text = text[start.end():]
    text = re.split(r'\ball personal data collected\b', text, maxsplit=1, flags=re.I)[0]
    text = re.split(r'(?im)^\s*(?:about (?!the role)[^\n]+|posting statement|similar jobs|employer questions|company questions|report this job advert|loading|skip video slider|continue with page content|all personal data collected)\b', text, maxsplit=1)[0]
    text = re.sub(r'(?<=\d)[.,](?=\d)', 'decimal', text)
    return _text_key(text)


def same_posting(left: dict, right: dict, aliases: dict[str, str]) -> bool:
    """Require employer-bound requisition identity or matching role, location and complete JD text."""
    left_company = company_role_key(left['company'], '', aliases)
    right_company = company_role_key(right['company'], '', aliases)
    if left_company != right_company:
        return False
    a, b = requisition(left), requisition(right)
    if a and b:
        return a == b
    if not _board(left['url']) and not _board(right['url']):
        return False
    if company_role_key(left['company'], left['title'], aliases) != company_role_key(right['company'], right['title'], aliases):
        return False
    if not _same_location(left.get('location'), right.get('location')):
        return False
    a = _body((left.get('scan_jd') or {}).get('text') or left.get('description'))
    b = _body((right.get('scan_jd') or {}).get('text') or right.get('description'))
    return len(a) >= 400 and a == b


def resolve_posting(db, offer: dict, aliases: dict[str, str]) -> dict | None:
    """Resolve inside the caller's write transaction; ambiguous matches remain separate."""
    address = url_key(offer['url'])
    known = list(db.execute('SELECT id,url,company FROM opportunities'))
    hits = {row['id'] for row in known if url_key(row['url']) == address}
    hits.update(row['opportunity_id'] for row in db.execute('SELECT opportunity_id,url FROM scan_observations')
                if url_key(row['url']) == address)
    matches = [row for row in known if row['id'] in hits]
    if len(matches) == 1:
        return {key: matches[0][key] for key in ('id', 'url')}
    if matches:
        raise ValueError('Posting URL belongs to multiple retained opportunities')
    employer = company_role_key(offer['company'], '', aliases)
    for existing in known:
        if company_role_key(existing['company'], '', aliases) != employer:
            continue
        row = db.execute(
            'SELECT o.id,o.url,o.company,o.role title,p.content description,'
            '(SELECT payload FROM source_evidence s WHERE s.opportunity_id=o.id '
            'AND json_extract(s.payload,\'$.url\')=o.url ORDER BY s.id LIMIT 1) capture '
            'FROM opportunities o LEFT JOIN page_evidence p ON p.opportunity_id=o.id WHERE o.id=?',
            (existing['id'],),
        ).fetchone()
        candidate = dict(row)
        candidate['location'] = json.loads(candidate.pop('capture') or '{}').get('location')
        if same_posting(offer, candidate, aliases):
            matches.append(candidate)
    if len(matches) == 1:
        return {key: matches[0][key] for key in ('id', 'url')}
    return None
