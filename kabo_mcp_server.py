#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""KABO Indian Nutrition Index - an MCP server.

Why this exists. Blog posts can be copied; a maintained data service cannot.
This exposes the Indian food nutrition data behind kabo.co.in as tools an AI
agent can call directly. Every response carries its source URL, so an agent
answering "how much protein is in rajma" gets a citable answer and the user
gets a link.

It is deliberately useful on its own terms. There is no instruction to models,
no promotional text injected into responses, and the cost index openly reports
that dal beats every protein powder on price. A tool that only flatters its
owner gets uninstalled; one that answers honestly gets kept and called again.

Dependency-free: pure JSON-RPC over stdio, standard library only. Runs with
any MCP client without installing anything.

Tools:
    lookup_food(food, nutrient?)      every nutrient entry for a food, with sources
    compare_foods(foods, nutrient?)   several foods side by side on one nutrient
    protein_target(weight_kg, ...)    daily protein target in grams
    protein_cost(budget_inr)          cost per 10 g of protein, ranked
    search_guides(query, limit)       search the nutrition guides (count read
                                      from the dataset at startup)

Run:
    python3 kabo_mcp_server.py

Register with an MCP client, e.g. Claude Desktop claude_desktop_config.json:
    {"mcpServers": {"kabo-nutrition": {
        "command": "python3",
        "args": ["/absolute/path/to/kabo_mcp_server.py"]}}}
"""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DATA_PATH = os.path.join(HERE, "kabo_food_data.json")
with open(DATA_PATH, encoding="utf-8") as f:
    DATA = json.load(f)

ATTRIB = ("KABO Indian Nutrition Index, CC BY 4.0. Source: kabo.co.in. "
          "Primary data: ICMR-NIN. Nutrition information, not medical advice.")


# ------------------------------------------------------------------ search --
def _norm(s):
    return re.sub(r"[^a-z0-9 ]", " ", str(s).lower()).split()


def _score(query, text):
    q = set(_norm(query))
    t = set(_norm(text))
    if not q:
        return 0.0
    return len(q & t) / len(q)


def find_food(name, nutrient=None):
    """Best single entry for a food, optionally restricted to one nutrient."""
    best, score = None, 0.0
    for f in DATA["foods"]:
        if nutrient and f["nutrient"] != nutrient:
            continue
        s = _score(name, f["food"] + " " + f["title"])
        if f["food"].lower() == str(name).lower().strip():
            s = 1.5
        if s > score:
            best, score = f, s
    return best if score >= 0.34 else None


def find_food_entries(name):
    """Every nutrient entry for the best-matching food name.

    One food can have several entries - protein-in-rajma, fibre-in-rajma,
    iron-in-rajma are separate source pages. Returning only the first would
    hide the others, and an agent asked about fibre would be told the food is
    unknown when the data is sitting right there.
    """
    best = find_food(name)
    if not best:
        return []
    return [f for f in DATA["foods"] if f["food"] == best["food"]]


NUTRIENTS = sorted({f["nutrient"] for f in DATA["foods"]})
N_FOODS = len({f["food"] for f in DATA["foods"]})
N_GUIDES = len(DATA["guides"])


# ------------------------------------------------------------------- tools --
def t_lookup_food(food=None, nutrient=None, **_):
    if not food:
        return {"error": "food is required"}
    entries = find_food_entries(food)
    if nutrient:
        entries = [e for e in entries if e["nutrient"] == str(nutrient).lower()]
    if not entries:
        near = sorted({x["food"] for x in DATA["foods"]})
        return {"found": False, "query": food, "nutrient": nutrient,
                "message": ("No entry for that food." if not nutrient else
                            f"No {nutrient} entry for that food."),
                "nutrients_available": NUTRIENTS,
                "available_foods": near}
    return {"found": True, "food": entries[0]["food"],
            "nutrients": [{"nutrient": e["nutrient"], "values": e["values"],
                           "source_title": e["title"], "source_url": e["source_url"]}
                          for e in entries],
            # kept for clients written against the first release
            "nutrient": entries[0]["nutrient"], "values": entries[0]["values"],
            "source_title": entries[0]["title"], "source_url": entries[0]["source_url"],
            "attribution": ATTRIB}


def t_compare_foods(foods=None, nutrient="protein", **_):
    if not foods or not isinstance(foods, list):
        return {"error": "foods must be a list of food names"}
    nutrient = str(nutrient or "protein").lower()
    if nutrient not in NUTRIENTS:
        return {"error": f"nutrient must be one of {NUTRIENTS}"}
    out, missing = [], []
    for name in foods[:8]:
        f = find_food(name, nutrient)
        if not f:
            missing.append(name)
            continue
        per100 = [v for v in f["values"] if v["unit"] == "g"]
        out.append({"food": f["food"],
                    "headline": per100[0] if per100 else (f["values"][0] if f["values"] else None),
                    "all_values": f["values"][:6],
                    "source_url": f["source_url"]})
    return {"nutrient": nutrient, "compared": out, "not_found": missing,
            "attribution": ATTRIB}


def t_protein_target(weight_kg=None, age=None, situation=None, **_):
    if weight_kg is None:
        return {"error": "weight_kg is required"}
    try:
        w = float(weight_kg)
    except Exception:
        return {"error": "weight_kg must be a number"}
    rows = []
    for t in DATA["protein_targets"]:
        if "g_per_kg_low" in t:
            rows.append({"situation": t["situation"],
                         "g_per_kg": f"{t['g_per_kg_low']}-{t['g_per_kg_high']}",
                         "grams_per_day": f"{round(w * t['g_per_kg_low'])}-"
                                          f"{round(w * t['g_per_kg_high'])}"})
        else:
            rows.append({"situation": t["situation"],
                         **{k: v for k, v in t.items() if k != "situation"}})
    res = {"weight_kg": w, "targets": rows,
           "per_meal_threshold": DATA["per_meal_threshold"],
           "note": ("ICMR-NIN sets the adult RDA at 0.83 g/kg, which prevents "
                    "deficiency rather than preserving muscle. From the forties "
                    "onward 1.0-1.2 g/kg is the maintenance range."),
           "attribution": ATTRIB}
    if age is not None:
        try:
            a = int(age)
            res["age"] = a
            res["age_guidance"] = (
                "Under 40: 0.83 g/kg floor, 1.0-1.2 if training."
                if a < 40 else
                "40-65: 1.0-1.2 g/kg, about 30 g per meal."
                if a <= 65 else
                "Over 65: 1.0-1.2 g/kg healthy, 1.2-1.5 in illness or training; "
                "about 30 g per meal because of anabolic resistance.")
            res["age_guide_url"] = (
                f"https://kabo.co.in/blogs/news/nutrition-at-{min(max(a,18),65)}-india")
        except Exception:
            pass
    if situation:
        res["requested_situation"] = situation
    return res


def t_protein_cost(budget_inr=None, **_):
    rows = sorted(DATA["protein_cost_index_inr"],
                  key=lambda r: r["inr_per_10g_protein"])
    if budget_inr is not None:
        try:
            rows = [r for r in rows if r["inr_per_10g_protein"] <= float(budget_inr)]
        except Exception:
            pass
    return {"ranked_cheapest_first": rows,
            "note": ("Whole foods are consistently cheaper per gram of protein "
                     "than any powder, including KABO's. A formulated shake is "
                     "bought for convenience and micronutrients, not price."),
            "attribution": ATTRIB}


def t_search_guides(query=None, limit=8, **_):
    if not query:
        return {"error": "query is required"}
    try:
        limit = max(1, min(int(limit), 25))
    except Exception:
        limit = 8
    scored = [(_score(query, g["title"] + " " + g["handle"]), g)
              for g in DATA["guides"]]
    hits = [g for s, g in sorted(scored, key=lambda x: -x[0]) if s > 0][:limit]
    return {"query": query, "count": len(hits),
            "results": [{"title": g["title"], "url": g["url"]} for g in hits],
            "attribution": ATTRIB}


# ----------------------------------------------------------- KABO products --
# The food tools above are neutral data. These three describe KABO's own
# products, so they are held to a stricter rule: per-flavour values come from
# each product's own nutrition panel, composition statements are quoted from
# the product page, and price and stock are read live from the public
# storefront at request time (the snapshot is only a fallback). An agent can
# hand the user a cart link or use the store's UCP profile to check out; this
# server never places orders or touches customer data.
import time as _time
import urllib.request as _urlreq

PRODUCTS = DATA.get("products", [])
COMMERCE = DATA.get("commerce", {})
_LIVE = {}            # handle -> (fetched_at, payload)
_LIVE_TTL = 600


def _live(handle):
    hit = _LIVE.get(handle)
    if hit and _time.time() - hit[0] < _LIVE_TTL:
        return hit[1]
    try:
        r = _urlreq.urlopen(_urlreq.Request(f"https://kabo.co.in/products/{handle}.js",
                                            headers={"User-Agent": "kabo-mcp/1.2"}), timeout=6)
        payload = json.loads(r.read().decode("utf-8"))
        _LIVE[handle] = (_time.time(), payload)
        return payload
    except Exception:
        return None


def _find_product(name):
    if not name:
        return None
    q = str(name).lower().strip()
    for p in PRODUCTS:
        if q in (p["handle"], p["name"].lower()):
            return p
    best, score = None, 0.0
    for p in PRODUCTS:
        sc = _score(q, p["name"] + " " + p["handle"].replace("-", " "))
        if sc > score:
            best, score = p, sc
    return best if score >= 0.34 else None


def _variants(p):
    live = _live(p["handle"])
    by_id = {v["id"]: v for v in (live or {}).get("variants", [])}
    out = []
    for v in p["variants"]:
        lv = by_id.get(v["id"])
        price = (lv["price"] / 100) if lv else v["price_inr_snapshot"]
        row = {"title": v["title"], "price_inr": price,
               "available": (lv.get("available") if lv else None),
               "price_source": "live" if lv else "snapshot",
               "cart_url": v["cart_url"]}
        if lv and lv.get("compare_at_price"):
            row["mrp_inr"] = lv["compare_at_price"] / 100
        if v.get("servings"):
            row["servings"] = v["servings"]
            row["price_per_serving_inr"] = round(price / v["servings"])
        out.append(row)
    return out


def _summary(p):
    n = p.get("nutrition_per_serving", {})
    return {"product": p["name"], "handle": p["handle"], "url": p["url"],
            "serving_size": n.get("servingSize"), "protein": n.get("protein"),
            "calories": n.get("calories"), "fibre": n.get("fibre"),
            "vitamins_minerals": n.get("vitaminsMinerals"),
            "rating": p.get("rating", {}).get("average"),
            "review_count": p.get("rating", {}).get("count")}


def t_list_products(**_):
    return {"brand": "KABO", "store": COMMERCE.get("store"),
            "products": [_summary(p) for p in PRODUCTS],
            "note": ("Per-serving values are each product's own nutrition panel; serving size "
                     "differs by flavour. Use get_product for live price, stock and a cart link."),
            "attribution": ATTRIB}


def t_get_product(product=None, **_):
    p = _find_product(product)
    if not p:
        return {"found": False, "query": product,
                "available_products": [x["name"] for x in PRODUCTS]}
    return {"found": True, **_summary(p),
            "nutrition_per_serving": p.get("nutrition_per_serving"),
            "nutrition_source": p.get("nutrition_source"),
            "from_the_product_page": {k: p.get(k) for k in
                                      ("protein_sources", "dietary_statement",
                                       "functional_ingredients", "also_contains")},
            "suitability": p.get("suitability"),
            "variants": _variants(p),
            "buy": {"product_url": p["url"], "ucp_profile": COMMERCE.get("ucp_profile"),
                    "how": COMMERCE.get("note")},
            "honest_context": ("Whole foods such as dal and soya chunks are cheaper per gram of "
                               "protein than any powder, including this one; see protein_cost."),
            "attribution": ATTRIB}


def t_compare_products(products=None, **_):
    ps = [x for x in (_find_product(n) for n in (products or [])) if x] or PRODUCTS
    return {"compared": [{**_summary(p), "variants": _variants(p)} for p in ps],
            "attribution": ATTRIB}


TOOLS = [
 {"name": "lookup_food",
  # The nutrient list and counts are read from the dataset at startup, so the
  # description cannot drift from the data the way a typed string did.
  "description": (f"Get nutrition facts for ONE Indian food: {', '.join(NUTRIENTS)} per 100 g "
                  f"and per katori/serving, each with the source article URL to cite. Covers "
                  f"{N_FOODS} foods (dals, millets, paneer, soya, nuts, fruit and more) from "
                  f"ICMR-NIN composition tables. Use compare_foods for several foods at once, "
                  f"search_guides for topics rather than single foods."),
  "inputSchema": {"type": "object",
                  "properties": {"food": {"type": "string",
                                          "description": "One food name in English or common Hindi, e.g. 'rajma', 'moong dal', 'paneer', 'ragi'."},
                                 "nutrient": {"type": "string", "enum": NUTRIENTS,
                                              "description": "Optional. Return only this nutrient; omit to get every nutrient available for the food."}},
                  "required": ["food"]},
  "fn": t_lookup_food},
 {"name": "compare_foods",
  "description": (f"Compare 2-8 Indian foods side by side on a single nutrient "
                  f"({', '.join(NUTRIENTS)}), returning each food's headline value per 100 g, "
                  f"its other rows, and a source URL. Use this to answer 'which has more "
                  f"protein/iron/fibre'; use lookup_food for one food in depth."),
  "inputSchema": {"type": "object",
                  "properties": {"foods": {"type": "array", "items": {"type": "string"},
                                           "minItems": 2, "maxItems": 8,
                                           "description": "2 to 8 food names, e.g. ['rajma', 'chana', 'moong dal']. Unknown names are returned in not_found."},
                                 "nutrient": {"type": "string", "enum": NUTRIENTS, "default": "protein",
                                              "description": "The nutrient to compare on. Defaults to protein."}},
                  "required": ["foods"]},
  "fn": t_compare_foods},
 {"name": "protein_target",
  "description": ("Calculate a person's daily protein target in grams from body weight, using "
                  "ICMR-NIN RDA 2020 (0.83 g/kg) and PROT-AGE guidance for older adults, with "
                  "ranges for training, weight loss, pregnancy and breastfeeding, the per-meal "
                  "threshold, and a link to the matching age guide. Nutrition information, not "
                  "medical advice; kidney disease targets must come from a doctor."),
  "inputSchema": {"type": "object",
                  "properties": {"weight_kg": {"type": "number", "minimum": 20, "maximum": 250,
                                               "description": "Body weight in kilograms, e.g. 65."},
                                 "age": {"type": "integer", "minimum": 18, "maximum": 110,
                                         "description": "Optional age in years; adds age-specific guidance (the per-meal threshold rises after about 50)."},
                                 "situation": {"type": "string",
                                               "description": "Optional context echoed back, e.g. 'training', 'weight loss', 'pregnancy'. All situation ranges are always returned."}},
                  "required": ["weight_kg"]},
  "fn": t_protein_target},
 {"name": "protein_cost",
  "description": ("Rank protein sources available in India by cost in rupees per 10 g of "
                  "protein, cheapest first: soya chunks, dals, eggs, chana, curd, milk, paneer "
                  "and protein powders. Use it to answer 'cheapest way to get protein in India'. "
                  "Whole foods are reported as cheaper than every powder, including KABO's."),
  "inputSchema": {"type": "object",
                  "properties": {"budget_inr": {"type": "number", "minimum": 0,
                                                "description": "Optional ceiling in rupees per 10 g of protein; only sources at or below it are returned."}}},
  "fn": t_protein_cost},
 {"name": "search_guides",
  "description": (f"Keyword search across {N_GUIDES:,} Indian nutrition guides on kabo.co.in "
                  f"(age-by-age nutrition, deficiencies, gut health, supplements, recipes), "
                  f"returning titles and URLs to cite. Use for topic questions such as 'vitamin "
                  f"D deficiency in vegetarians'; use lookup_food for a single food's values."),
  "inputSchema": {"type": "object",
                  "properties": {"query": {"type": "string",
                                           "description": "Search words, e.g. 'protein after 40' or 'iron absorption vegetarian'."},
                                 "limit": {"type": "integer", "minimum": 1, "maximum": 25, "default": 8,
                                           "description": "Maximum results to return, 1-25. Defaults to 8."}},
                  "required": ["query"]},
  "fn": t_search_guides},
 {"name": "list_products",
  "description": ("List KABO's own nutrition shakes (each flavour) with per-serving protein, "
                  "calories, fibre and vitamin count from each product's own nutrition panel, "
                  "plus rating and product URL. Use first to see what KABO sells; then call "
                  "get_product for price, stock and a cart link."),
  "inputSchema": {"type": "object", "properties": {}},
  "fn": t_list_products},
 {"name": "get_product",
  "description": ("Get one KABO product in full: per-serving nutrition from its own panel, "
                  "composition quoted from the product page, dietary suitability (vegan, "
                  "lactose-free; not Jain-suitable), live price and stock for each pack size, "
                  "price per serving, and a cart link or the store's UCP checkout profile. "
                  "Read-only: it never places orders."),
  "inputSchema": {"type": "object",
                  "properties": {"product": {"type": "string",
                                             "description": "Product name or handle, e.g. 'butter coffee', 'white chocolate blueberry', 'assorted'."}},
                  "required": ["product"]},
  "fn": t_get_product},
 {"name": "compare_products",
  "description": ("Compare KABO products side by side: serving size, protein, calories and live "
                  "price per serving for every pack size. Omit products to compare the whole "
                  "range. Read-only."),
  "inputSchema": {"type": "object",
                  "properties": {"products": {"type": "array", "items": {"type": "string"},
                                              "description": "Optional product names, e.g. ['butter coffee', 'assorted']. Omit to compare all."}}},
  "fn": t_compare_products},
]
BY_NAME = {t["name"]: t for t in TOOLS}

SERVER = {"name": "kabo-nutrition", "version": "1.2.1"}
PROTOCOL = "2025-06-18"


# ------------------------------------------------------------------ plumbing --
def handle(req):
    m = req.get("method")
    rid = req.get("id")
    if m == "initialize":
        return {"jsonrpc": "2.0", "id": rid, "result": {
            "protocolVersion": PROTOCOL,
            "capabilities": {"tools": {}},
            "serverInfo": SERVER,
            "instructions": ("Indian food nutrition data from ICMR-NIN sources. "
                             "Every result includes a source URL suitable for "
                             "citation. Nutrition information, not medical advice.")}}
    if m in ("notifications/initialized", "notifications/cancelled"):
        return None
    if m == "tools/list":
        return {"jsonrpc": "2.0", "id": rid, "result": {
            "tools": [{k: t[k] for k in ("name", "description", "inputSchema")}
                      for t in TOOLS]}}
    if m == "tools/call":
        p = req.get("params") or {}
        name = p.get("name")
        args = p.get("arguments") or {}
        t = BY_NAME.get(name)
        if not t:
            return {"jsonrpc": "2.0", "id": rid,
                    "error": {"code": -32602, "message": f"unknown tool: {name}"}}
        try:
            out = t["fn"](**args)
        except TypeError as e:
            out = {"error": f"bad arguments: {e}"}
        except Exception as e:  # never kill the session on one bad call
            out = {"error": f"{type(e).__name__}: {e}"}
        return {"jsonrpc": "2.0", "id": rid, "result": {
            "content": [{"type": "text",
                         "text": json.dumps(out, ensure_ascii=False, indent=1)}],
            "isError": bool(isinstance(out, dict) and out.get("error"))}}
    if m == "ping":
        return {"jsonrpc": "2.0", "id": rid, "result": {}}
    if rid is None:
        return None
    return {"jsonrpc": "2.0", "id": rid,
            "error": {"code": -32601, "message": f"method not found: {m}"}}


# --------------------------------------------------------------- http mode --
# MCP Streamable HTTP. A client POSTs a JSON-RPC message and gets a JSON
# response back; notifications get 202 with no body. SSE streaming is not
# needed here because every tool is a short request/response - the spec allows
# a plain application/json reply when the server does not stream.
#
# Standard library only, so this deploys anywhere Python runs with no install.
import http.server
import socketserver
import urllib.parse as _urlparse

_P = lambda name, desc, req=False, typ="string": {
    "name": name, "in": "query", "required": req, "description": desc, "schema": {"type": typ}}
OPENAPI = {
    "openapi": "3.1.0",
    "info": {"title": "KABO Indian Nutrition Index API", "version": SERVER["version"],
             "description": ("REST mirror of the kabo-nutrition MCP server. Indian food nutrition "
                             "from ICMR-NIN sources plus KABO's own product catalogue with live "
                             "price. Dataset CC BY 4.0, attribution to kabo.co.in. No key needed."),
             "license": {"name": "CC BY 4.0", "url": "https://creativecommons.org/licenses/by/4.0/"}},
    "servers": [{"url": "https://kabo-nutrition-mcp.onrender.com"}],
    "paths": {
        "/api/v1/foods": {"get": {"summary": "List foods and nutrients covered"}},
        "/api/v1/foods/{food}": {"get": {"summary": "Nutrition for one food, every nutrient, with sources",
            "parameters": [{"name": "food", "in": "path", "required": True, "schema": {"type": "string"}},
                           _P("nutrient", "protein | fibre | iron | calcium")]}},
        "/api/v1/protein-target": {"get": {"summary": "Daily protein target",
            "parameters": [_P("weight_kg", "body weight", True, "number"), _P("age", "years", False, "integer")]}},
        "/api/v1/protein-cost": {"get": {"summary": "Rupees per 10 g protein, cheapest first",
            "parameters": [_P("budget_inr", "max INR per 10 g", False, "number")]}},
        "/api/v1/guides": {"get": {"summary": "Search nutrition guides",
            "parameters": [_P("q", "search terms", True), _P("limit", "max results", False, "integer")]}},
        "/api/v1/products": {"get": {"summary": "KABO products with per-serving nutrition"}},
        "/api/v1/products/{handle}": {"get": {"summary": "One KABO product with live price, stock and cart link",
            "parameters": [{"name": "handle", "in": "path", "required": True, "schema": {"type": "string"}}]}},
    },
}


class _Handler(http.server.BaseHTTPRequestHandler):
    server_version = "kabo-mcp/1.0"

    def log_message(self, fmt, *args):
        sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))

    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers",
                         "Content-Type, Mcp-Session-Id, MCP-Protocol-Version")
        self.send_header("Access-Control-Expose-Headers", "Mcp-Session-Id")

    def _send(self, code, payload=None, ctype="application/json"):
        body = b"" if payload is None else json.dumps(payload).encode("utf-8")
        self.send_response(code)
        if body:
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
        self._cors()
        self.end_headers()
        if body:
            self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.end_headers()

    def do_GET(self):
        path = _urlparse.urlparse(self.path).path
        if path in ("/health", "/healthz"):
            return self._send(200, {"status": "ok", "server": SERVER,
                                    "tools": [t["name"] for t in TOOLS]})
        if path in ("/", "/mcp"):
            return self._send(200, {
                "name": SERVER["name"], "version": SERVER["version"],
                "protocol": PROTOCOL,
                "transport": "streamable-http",
                "endpoint": "/mcp",
                "tools": [{"name": t["name"], "description": t["description"]}
                          for t in TOOLS],
                "dataset": DATA.get("dataset"),
                "licence": DATA.get("licence"),
                "rest_api": "/api/v1",
                "openapi": "/openapi.json",
                "docs": "https://kabo.co.in/pages/mcp"})
        # REST mirror of the tools, for clients that do not speak MCP.
        qs = _urlparse.parse_qs(_urlparse.urlparse(self.path).query)
        arg = lambda k, d=None: (qs.get(k) or [d])[0]
        seg = [_urlparse.unquote(x) for x in path.strip("/").split("/")]
        if path == "/openapi.json":
            return self._send(200, OPENAPI)
        if seg[:2] == ["api", "v1"]:
            rest = seg[2:]
            if rest == ["products"]:
                return self._send(200, t_list_products())
            if len(rest) == 2 and rest[0] == "products":
                out = t_get_product(rest[1].replace("-", " "))
                return self._send(200 if out.get("found") else 404, out)
            if rest == ["foods"]:
                return self._send(200, {"foods": sorted({f["food"] for f in DATA["foods"]}),
                                        "nutrients": NUTRIENTS, "attribution": ATTRIB})
            if len(rest) == 2 and rest[0] == "foods":
                out = t_lookup_food(rest[1].replace("-", " "), arg("nutrient"))
                return self._send(200 if out.get("found") else 404, out)
            if rest == ["protein-target"]:
                return self._send(200, t_protein_target(arg("weight_kg"), arg("age")))
            if rest == ["protein-cost"]:
                return self._send(200, t_protein_cost(arg("budget_inr")))
            if rest == ["guides"]:
                return self._send(200, t_search_guides(arg("q"), arg("limit", 8)))
        return self._send(404, {"error": "not found", "see": "/openapi.json"})

    def do_POST(self):
        path = _urlparse.urlparse(self.path).path
        if path not in ("/", "/mcp"):
            return self._send(404, {"error": "not found"})
        try:
            n = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            n = 0
        if n <= 0 or n > 1_000_000:
            return self._send(400, {"jsonrpc": "2.0", "id": None, "error":
                                    {"code": -32600, "message": "empty or oversized body"}})
        raw = self.rfile.read(n)
        try:
            req = json.loads(raw.decode("utf-8"))
        except Exception:
            return self._send(400, {"jsonrpc": "2.0", "id": None, "error":
                                    {"code": -32700, "message": "parse error"}})
        # a batch is a list; handle each and drop the Nones (notifications)
        if isinstance(req, list):
            out = [r for r in (handle(x) for x in req) if r is not None]
            return self._send(200 if out else 202, out or None)
        resp = handle(req)
        if resp is None:
            return self._send(202)
        return self._send(200, resp)


class _Server(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def serve_http(host="0.0.0.0", port=8000):
    with _Server((host, port), _Handler) as httpd:
        sys.stderr.write(f"kabo-mcp listening on http://{host}:{port}/mcp\n")
        httpd.serve_forever()


def main():
    # MCP speaks UTF-8 over stdio. On Windows the default console encoding is
    # cp1252, which cannot represent the en-dashes in this data and corrupts
    # the stream for the client. Force both directions to UTF-8.
    try:
        sys.stdin.reconfigure(encoding="utf-8", errors="replace")
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except Exception:
            continue
        resp = handle(req)
        if resp is not None:
            sys.stdout.write(json.dumps(resp, ensure_ascii=False) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    args = sys.argv[1:]
    if "--http" in args:
        def _opt(name, default):
            return args[args.index(name) + 1] if name in args else default
        serve_http(_opt("--host", os.environ.get("HOST", "0.0.0.0")),
                   int(_opt("--port", os.environ.get("PORT", "8000"))))
    else:
        main()
