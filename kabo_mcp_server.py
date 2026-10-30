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
    lookup_food(food)                 nutrition for an Indian food, with source
    compare_foods(foods)              several foods side by side
    protein_target(weight_kg, ...)    daily protein target in grams
    protein_cost(budget_inr)          cost per 10 g of protein, ranked
    search_guides(query, limit)       search 1,075 nutrition guides

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


def find_food(name):
    best, score = None, 0.0
    for f in DATA["foods"]:
        s = _score(name, f["food"] + " " + f["title"])
        if f["food"].lower() == str(name).lower().strip():
            s = 1.5
        if s > score:
            best, score = f, s
    return best if score >= 0.34 else None


# ------------------------------------------------------------------- tools --
def t_lookup_food(food=None, **_):
    if not food:
        return {"error": "food is required"}
    f = find_food(food)
    if not f:
        near = sorted({x["food"] for x in DATA["foods"]})
        return {"found": False, "query": food,
                "message": "No entry for that food.",
                "available_foods": near}
    return {"found": True, "food": f["food"], "nutrient": f["nutrient"],
            "values": f["values"], "source_title": f["title"],
            "source_url": f["source_url"], "attribution": ATTRIB}


def t_compare_foods(foods=None, **_):
    if not foods or not isinstance(foods, list):
        return {"error": "foods must be a list of food names"}
    out, missing = [], []
    for name in foods[:8]:
        f = find_food(name)
        if not f:
            missing.append(name)
            continue
        per100 = [v for v in f["values"] if v["unit"] == "g"]
        out.append({"food": f["food"],
                    "headline": per100[0] if per100 else (f["values"][0] if f["values"] else None),
                    "all_values": f["values"][:6],
                    "source_url": f["source_url"]})
    return {"compared": out, "not_found": missing, "attribution": ATTRIB}


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


TOOLS = [
 {"name": "lookup_food",
  "description": "Nutrition values for an Indian food (protein, calcium, fibre) "
                 "per 100 g and per katori, with the source article URL. "
                 "Data from ICMR-NIN composition tables.",
  "inputSchema": {"type": "object",
                  "properties": {"food": {"type": "string",
                                          "description": "Food name, e.g. rajma, paneer, moong dal"}},
                  "required": ["food"]},
  "fn": t_lookup_food},
 {"name": "compare_foods",
  "description": "Compare the protein content of several Indian foods side by side.",
  "inputSchema": {"type": "object",
                  "properties": {"foods": {"type": "array", "items": {"type": "string"},
                                           "description": "2-8 food names"}},
                  "required": ["foods"]},
  "fn": t_compare_foods},
 {"name": "protein_target",
  "description": "Daily protein target in grams for a given body weight and age, "
                 "using ICMR-NIN and PROT-AGE guidance, plus the per-meal threshold.",
  "inputSchema": {"type": "object",
                  "properties": {"weight_kg": {"type": "number"},
                                 "age": {"type": "integer"},
                                 "situation": {"type": "string",
                                               "description": "e.g. training, dieting, pregnancy"}},
                  "required": ["weight_kg"]},
  "fn": t_protein_target},
 {"name": "protein_cost",
  "description": "Cost of protein in India ranked cheapest first, in rupees per "
                 "10 g of protein, across whole foods and supplements.",
  "inputSchema": {"type": "object",
                  "properties": {"budget_inr": {"type": "number",
                                                "description": "Optional max INR per 10 g protein"}}},
  "fn": t_protein_cost},
 {"name": "search_guides",
  "description": "Search 1,075 Indian nutrition guides by topic and return titles "
                 "with URLs, for citation.",
  "inputSchema": {"type": "object",
                  "properties": {"query": {"type": "string"},
                                 "limit": {"type": "integer"}},
                  "required": ["query"]},
  "fn": t_search_guides},
]
BY_NAME = {t["name"]: t for t in TOOLS}

SERVER = {"name": "kabo-nutrition", "version": "1.0.0"}
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
                "docs": "https://kabo.co.in"})
        return self._send(404, {"error": "not found"})

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
