"""Derive searchable city labels and display text without changing retained location evidence."""

from __future__ import annotations

import json
import re


CITIES = {
    "香港": ("hong kong", "hongkong", "hk", "香港"),
    "北京": ("beijing", "北京"), "上海": ("shanghai", "上海"),
    "深圳": ("shenzhen", "深圳"), "广州": ("guangzhou", "广州"),
    "杭州": ("hangzhou", "杭州"), "苏州": ("suzhou", "苏州"),
    "南京": ("nanjing", "南京"), "成都": ("chengdu", "成都"),
    "重庆": ("chongqing", "重庆"), "西安": ("xi'an", "xian", "西安"),
}
HK_AREAS = {
    "central and western district": "中西区", "kowloon city district": "九龙城区",
    "kwun tong district": "观塘区", "eastern district": "东区",
    "southern district": "南区", "tai po district": "大埔区",
    "sha tin district": "沙田区", "kwai tsing district": "葵青区",
    "hong kong island": "香港岛", "new territories": "新界", "kowloon": "九龙",
    "kowloon bay": "九龙湾", "kowloon city": "九龙城", "admiralty": "金钟",
    "kai tak": "启德", "ngau tau kok": "牛头角", "north point": "北角",
    "pok fu lam": "薄扶林", "quarry bay": "鲗鱼涌", "science park": "科学园",
    "tin hau": "天后", "tsing yi": "青衣",
}
COUNTRIES = {"china", "cn", "chn", "prc", "中国", "中华人民共和国"}


def _pattern(alias: str) -> str:
    return rf"(?<![a-z]){re.escape(alias)}(?![a-z])" if alias.isascii() else re.escape(alias) + "市?"


def _texts(value: object) -> list[str]:
    """Read strings and schema.org Place/PostalAddress shapes; keep unfamiliar objects visible."""
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [text for item in value for text in _texts(item)]
    if isinstance(value, dict):
        parts = [text for key in ("name", "address", "addressLocality", "addressRegion", "addressCountry")
                 if key in value for text in _texts(value[key])]
        return [", ".join(dict.fromkeys(parts))] if parts else [json.dumps(value, ensure_ascii=False)]
    return [] if value is None else [str(value)]


def location_fields(raw: object) -> dict:
    """Normalize known aliases conservatively; unmatched text remains available in the display and search."""
    displays, cities = [], []
    for text in _texts(raw):
        for place in re.split(r"[;；/|\n]+", text):
            place = place.strip()
            if not place:
                continue
            tokens = [token.strip() for token in re.split(r"[,，]+", place) if token.strip()]
            # shortcut: bare area aliases are limited to observed Hong Kong locations; extend with verified examples.
            found = [city for city, aliases in CITIES.items()
                     if any(re.search(_pattern(alias), place, re.I) for alias in aliases)]
            if not found and any(token.lower() in HK_AREAS and token.lower() not in {
                    "science park", "eastern district", "southern district", "north point"} for token in tokens):
                found.append("香港")
            cities.extend(found)
            if not found:
                displays.append("中国（城市未明确）" if place.lower() in COUNTRIES else place)
                continue
            details = []
            for token in tokens:
                if token.lower() in COUNTRIES:
                    continue
                if "香港" in found and token.lower() in HK_AREAS:
                    details.append(HK_AREAS[token.lower()])
                    continue
                remainder = token
                for city in found:
                    for alias in CITIES[city]:
                        remainder = re.sub(_pattern(alias), "", remainder, flags=re.I)
                remainder = re.sub(r"\bSAR\b", "", remainder, flags=re.I).strip(" -·")
                if remainder:
                    details.append(remainder)
            if "香港" in found:
                details.reverse()
            displays.append(" · ".join(dict.fromkeys(found + details)))
    cities = list(dict.fromkeys(cities))
    original = raw if isinstance(raw, str) else json.dumps(raw, ensure_ascii=False)
    return {
        "location": "；".join(dict.fromkeys(displays)) or "地点未提供",
        "location_raw": raw,
        "location_cities": cities,
        "location_search": " ".join([original, *displays, *cities,
                                     *(alias for city in cities for alias in CITIES[city])]),
    }
