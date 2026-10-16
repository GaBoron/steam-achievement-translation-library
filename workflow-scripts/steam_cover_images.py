"""Resolve Steam header assets for the static website without browser API calls."""
from __future__ import annotations

import json
import re
import sys
from collections.abc import Iterable
from http.client import HTTPException
from urllib.parse import urlencode
from urllib.request import Request, urlopen


ASSET_ROOT = "https://shared.akamai.steamstatic.com/store_item_assets/"
STORE_API = "https://api.steampowered.com/IStoreBrowseService/GetItems/v1/"
BATCH_SIZE = 50


def valid_cover_url(app_id: str, value: object) -> bool:
    prefix = f"{ASSET_ROOT}steam/apps/{app_id}/"
    return isinstance(value, str) and value.startswith(prefix) and bool(re.fullmatch(
        r"(?:[a-f0-9]+/)?header[a-z0-9_-]*\.(?:jpg|jpeg|png|webp|avif)(?:\?t=\d+)?", value[len(prefix):],
    ))


def parse_cover_images(payload: object, app_ids: Iterable[str]) -> dict[str, str]:
    """Keep only image URLs belonging to the requested catalog games."""
    if not isinstance(payload, dict):
        raise ValueError("Steam cover metadata must be an object")
    return {app_id: payload[app_id] for app_id in app_ids if valid_cover_url(app_id, payload.get(app_id))}


def refresh_cover_images(app_ids: Iterable[str], existing: object) -> dict[str, str]:
    ids = sorted(set(app_ids), key=int)
    covers = parse_cover_images(existing, ids)
    for start in range(0, len(ids), BATCH_SIZE):
        batch = ids[start:start + BATCH_SIZE]
        query = urlencode({"input_json": json.dumps({
            "ids": [{"appid": int(app_id)} for app_id in batch],
            "context": {"language": "english", "country_code": "US"},
            "data_request": {"include_assets": True},
        }, separators=(",", ":"))})
        try:
            request = Request(f"{STORE_API}?{query}", headers={"User-Agent": "SATLI website build"})
            with urlopen(request, timeout=10) as response:
                payload = json.load(response)
            body = payload.get("response") if isinstance(payload, dict) else None
            items = body.get("store_items") if isinstance(body, dict) else None
            if not isinstance(items, list):
                raise ValueError("Steam response has no store_items list")
            for item in items:
                if not isinstance(item, dict) or item.get("success") != 1:
                    continue
                app_id = str(item.get("appid"))
                assets = item.get("assets")
                if app_id not in batch or not isinstance(assets, dict):
                    continue
                template, header = assets.get("asset_url_format"), assets.get("header")
                if not isinstance(template, str) or not isinstance(header, str):
                    continue
                url = ASSET_ROOT + template.replace("${FILENAME}", header)
                if valid_cover_url(app_id, url):
                    covers[app_id] = url
        except (OSError, HTTPException, ValueError) as exc:
            print(f"WARNING: Steam cover refresh failed for batch {start // BATCH_SIZE + 1}; "
                  f"keeping existing image URLs: {exc}", file=sys.stderr)
    return covers


def render_cover_images(covers: dict[str, str]) -> bytes:
    ordered = {app_id: covers[app_id] for app_id in sorted(covers, key=int)}
    return (json.dumps(ordered, indent=2) + "\n").encode("utf-8")
