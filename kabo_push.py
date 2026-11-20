# -*- coding: utf-8 -*-
"""KABO web push subscriber service (20 Nov 2026). Standard library only.

Mounted by kabo_mcp_server.py under /push/*. Stores subscribers and clicks as
Shopify metaobjects (kabo_push_subscriber, kabo_push_click) so there is no
database to run, and the free host sleeping or restarting loses nothing.

  POST /push/subscribe     {"subscription": {...}, "path": "/", "browser": "Chrome Android"}
  POST /push/unsubscribe   {"endpoint": "..."}
  POST /push/click         {"campaign": "...", "subscriber": "<32 hex>"}
  GET  /push/health        {"configured": true|false}

Only browsers on kabo.co.in may call it (Origin check). No IP address is
stored or logged. Sending is NOT done here - the private VAPID key never
leaves the owner's machine (scripts/116_push_send.py).

Env (Render > Environment):
  SHOPIFY_STORE               1h2n1k-k2.myshopify.com
  SHOPIFY_PUSH_CLIENT_ID      Dev Dashboard app "KABO Push" (scopes: read/write_metaobjects,
  SHOPIFY_PUSH_CLIENT_SECRET    read/write_metaobject_definitions) - exchanged for a 24 h token
  or SHOPIFY_PUSH_TOKEN       a static Admin API token with the same scopes
"""
import hashlib
import json
import os
import threading
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone

API = "2025-07"
ORIGINS = {"https://kabo.co.in", "https://www.kabo.co.in"}
PUSH_HOSTS = ("fcm.googleapis.com", "updates.push.services.mozilla.com", "notify.windows.com",
              "web.push.apple.com", "push.services.mozilla.com")
_tok = {"value": None, "exp": 0}
_lock = threading.Lock()
_rate = {"t": 0.0, "n": 0}


def configured():
    return bool(os.environ.get("SHOPIFY_STORE") and (os.environ.get("SHOPIFY_PUSH_TOKEN") or
                (os.environ.get("SHOPIFY_PUSH_CLIENT_ID") and os.environ.get("SHOPIFY_PUSH_CLIENT_SECRET"))))


def _token():
    static = os.environ.get("SHOPIFY_PUSH_TOKEN")
    if static:
        return static
    with _lock:
        if _tok["value"] and time.time() < _tok["exp"] - 300:
            return _tok["value"]
        body = urllib.parse.urlencode({"grant_type": "client_credentials",
                                       "client_id": os.environ["SHOPIFY_PUSH_CLIENT_ID"],
                                       "client_secret": os.environ["SHOPIFY_PUSH_CLIENT_SECRET"]}).encode()
        req = urllib.request.Request(f"https://{os.environ['SHOPIFY_STORE']}/admin/oauth/access_token", data=body,
                                     headers={"Content-Type": "application/x-www-form-urlencoded"})
        d = json.loads(urllib.request.urlopen(req, timeout=20).read())
        _tok["value"], _tok["exp"] = d["access_token"], time.time() + int(d.get("expires_in", 86399))
        return _tok["value"]


def _gql(query, variables=None):
    req = urllib.request.Request(f"https://{os.environ['SHOPIFY_STORE']}/admin/api/{API}/graphql.json",
                                 data=json.dumps({"query": query, "variables": variables or {}}).encode(),
                                 headers={"Content-Type": "application/json", "X-Shopify-Access-Token": _token()})
    d = json.loads(urllib.request.urlopen(req, timeout=20).read())
    if d.get("errors"):
        raise RuntimeError(str(d["errors"])[:300])
    return d["data"]


def _now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def sub_handle(endpoint):
    return hashlib.sha256(endpoint.encode()).hexdigest()[:32]


def _clip(s, n):
    return str(s or "")[:n]


def _fields(d):
    return [{"key": k, "value": v} for k, v in d.items() if v not in (None, "")]


def _upsert_status(handle, fields):
    m = """mutation($h: MetaobjectHandleInput!, $m: MetaobjectUpsertInput!) { metaobjectUpsert(handle: $h, metaobject: $m) {
      metaobject { handle } userErrors { field message } } }"""
    r = _gql(m, {"h": {"type": "kabo_push_subscriber", "handle": handle}, "m": {"fields": _fields(fields)}})["metaobjectUpsert"]
    if r["userErrors"]:
        raise RuntimeError(str(r["userErrors"])[:300])


def subscribe(p):
    s = p.get("subscription") or {}
    ep, keys = _clip(s.get("endpoint"), 1000), s.get("keys") or {}
    host = urllib.parse.urlparse(ep).hostname or ""
    if not ep.startswith("https://") or not any(host == h or host.endswith("." + h) for h in PUSH_HOSTS):
        return 400, {"error": "unsupported push endpoint"}
    if not keys.get("p256dh") or not keys.get("auth"):
        return 400, {"error": "missing keys"}
    h = sub_handle(ep)
    q = 'query($h: MetaobjectHandleInput!) { metaobjectByHandle(handle: $h) { id } }'
    exists = _gql(q, {"h": {"type": "kabo_push_subscriber", "handle": h}})["metaobjectByHandle"]
    f = {"endpoint": ep, "p256dh": _clip(keys["p256dh"], 200), "auth": _clip(keys["auth"], 100),
         "status": "active", "browser": _clip(p.get("browser"), 40), "updated_at": _now()}
    if not exists:
        f.update({"first_path": _clip(p.get("path"), 200), "subscribed_at": _now()})
    _upsert_status(h, f)
    return 200, {"ok": True, "subscriber": h, "new": not exists}


def unsubscribe(p):
    ep = _clip(p.get("endpoint"), 1000)
    if not ep:
        return 400, {"error": "missing endpoint"}
    _upsert_status(sub_handle(ep), {"status": "unsubscribed", "updated_at": _now()})
    return 200, {"ok": True}


def click(p):
    camp, sub = _clip(p.get("campaign"), 80), _clip(p.get("subscriber"), 32)
    if not camp:
        return 400, {"error": "missing campaign"}
    m = """mutation($m: MetaobjectCreateInput!) { metaobjectCreate(metaobject: $m) { metaobject { id } userErrors { message } } }"""
    _gql(m, {"m": {"type": "kabo_push_click", "fields": _fields({"campaign": camp, "subscriber": sub, "clicked_at": _now()})}})
    return 200, {"ok": True}


ROUTES = {"/push/subscribe": subscribe, "/push/unsubscribe": unsubscribe, "/push/click": click}


def handle_post(path, origin, raw):
    """Returns (status, payload). Called by the HTTP handler for /push/* POSTs."""
    if origin not in ORIGINS:
        return 403, {"error": "origin not allowed"}
    if not configured():
        return 503, {"error": "push store not configured"}
    now = time.time()
    with _lock:  # crude global limit: 40 writes per second is far above real traffic
        if now - _rate["t"] > 1:
            _rate["t"], _rate["n"] = now, 0
        _rate["n"] += 1
        if _rate["n"] > 40:
            return 429, {"error": "slow down"}
    if len(raw) > 4096:
        return 413, {"error": "too large"}
    try:
        p = json.loads(raw.decode("utf-8") or "{}")
    except Exception:
        return 400, {"error": "bad json"}
    try:
        return ROUTES[path](p)
    except Exception as e:  # never echo Shopify errors to browsers in detail
        import sys
        sys.stderr.write(f"push {path} failed: {str(e)[:200]}\n")
        return 502, {"error": "store write failed"}
