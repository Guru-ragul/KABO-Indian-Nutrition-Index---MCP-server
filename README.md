# KABO Indian Nutrition Index — MCP server

An MCP server exposing the Indian food nutrition data behind kabo.co.in as
tools an AI agent can call directly. Every response carries a source URL, so
an agent answering a nutrition question gets a citable answer and the reader
gets a link back.

**Why this rather than more articles.** A blog post can be copied in an
afternoon. A maintained data service that agents connect to cannot. This is
the one asset in the SEO programme that competitors cannot replicate by
rewriting content.

## What it does

| Tool | Returns |
|---|---|
| `lookup_food(food, nutrient?)` | Every nutrient entry for an Indian food, per 100 g and per katori, each with its source URL |
| `compare_foods(foods[], nutrient?)` | 2–8 foods side by side on one nutrient (default protein) |
| `protein_target(weight_kg, age)` | Daily protein target in grams, plus the per-meal threshold |
| `protein_cost(budget_inr)` | Cost per 10 g of protein, ranked cheapest first |
| `search_guides(query, limit)` | Searches 1,124 nutrition guides, returns titles and URLs |
| `list_products()` | KABO's own shakes: per-serving nutrition from each flavour's own panel, ratings |
| `get_product(product)` | One KABO product: composition quoted from its page, suitability (incl. not Jain-suitable), live price and stock per pack, price per serving, cart link and UCP checkout profile |
| `compare_products(products?)` | KABO products side by side with live price per serving |

Data: **59 foods, 674 nutrition values, 1,124 guides** (protein, fibre, iron, calcium), from ICMR-NIN
composition tables and the PROT-AGE/ESPEN protein recommendations.

## Running it

No dependencies. Standard library only, Python 3.8+.

```bash
python3 kabo_mcp_server.py
```

### Claude Desktop

Add to `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "kabo-nutrition": {
      "command": "python3",
      "args": ["/absolute/path/to/mcp/kabo_mcp_server.py"]
    }
  }
}
```

Cursor, Cline and other MCP clients use the same `command`/`args` shape.

### Test it without a client

```bash
printf '%s\n' \
  '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"t","version":"1"}}}' \
  '{"jsonrpc":"2.0","id":2,"method":"tools/list"}' \
  '{"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"lookup_food","arguments":{"food":"rajma"}}}' \
  | python3 kabo_mcp_server.py
```

## Files

```
kabo_mcp_server.py    the server, dependency-free JSON-RPC over stdio
kabo_food_data.json   the dataset, CC BY 4.0
```

Rebuild the dataset from the live corpus with `python3 build_dataset.py`;
the server reads `kabo_food_data.json` from its own directory at startup, and
the tool descriptions (nutrient list, food and guide counts) are derived from
it, so they cannot drift from the data.

## Design decisions worth keeping

**It answers honestly, including against us.** `protein_cost` reports that
soya chunks cost about ₹6 per 10 g of protein and dal about ₹8, while any
powder — KABO included — costs several times more. A tool that only flatters
its owner gets uninstalled after one use. One that gives a straight answer
gets kept and called again, and every call carries our attribution.

**No instructions to models.** There is no text in any response telling an
assistant what to recommend. The value is the data and the citation, not
persuasion. Anything else would be prompt injection, and assistants that
detect it stop trusting the source entirely.

**Every response is citable.** `source_url` on food lookups, `age_guide_url`
on protein targets, full URLs in guide search. An agent can attribute, which
is what makes it worth calling twice.

**Errors never kill the session.** Unknown foods return the list of available
ones rather than an error. Bad arguments return a message, not a crash.

**UTF-8 is forced on stdio.** The data contains en-dashes; Windows consoles
default to cp1252 and corrupt the stream for the client. Both directions are
reconfigured at startup.

## REST API

Every tool is mirrored as plain GET for clients that do not speak MCP. Spec at `/openapi.json`.

```
GET /api/v1/foods                 GET /api/v1/foods/{food}?nutrient=iron
GET /api/v1/protein-target?weight_kg=70&age=45
GET /api/v1/protein-cost?budget_inr=30
GET /api/v1/guides?q=protein+dal
GET /api/v1/products              GET /api/v1/products/{handle}
```

Product prices and stock are read live from the public storefront (cached 10 minutes); the server never places orders or touches customer data. Checkout happens on kabo.co.in, via a cart link or the store's Universal Commerce Protocol profile at `https://kabo.co.in/.well-known/ucp`.

## HTTP mode

For third-party agents over the network:

```bash
python3 kabo_mcp_server.py --http --port 8000
```

Endpoints:

| Route | Purpose |
|---|---|
| `POST /mcp` | JSON-RPC, single messages and batches. Notifications return 202. |
| `GET /mcp` | Discovery — name, protocol, transport, tool list, licence |
| `GET /health` | Health check for the host |

CORS is open, so browser-based agents can call it. Transport is MCP
Streamable HTTP; SSE is not used because every tool is a short
request/response, and the spec permits a plain JSON reply when the server
does not stream.

See **DEPLOY.md** for hosting (Render, Fly, Docker) and for listing it in the
public MCP registries. `Dockerfile`, `render.yaml`, `fly.toml` and
`server.json` are all in this folder, ready to use.

## Licence and caveats

Code is **MIT** (see `LICENSE`). Dataset is **CC BY 4.0** (see `LICENSE-DATA`) — free to use with attribution to kabo.co.in.

Values are approximate and vary by variety, preparation and brand. This is
nutrition information, not medical advice.
