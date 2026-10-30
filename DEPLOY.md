# Registering the KABO nutrition MCP server

Five steps, in order. Each one has to work before the next makes sense:
**repo → host → verify → register → verify again.**

The one thing worth understanding before you start: **the registry stores
metadata, not code.** It is a card catalogue. The card points at your running
server, so the server has to be live and reachable *before* you register. That
is why hosting comes first and why there is no way to shortcut it.

---

## Step 1 — Put this folder on GitHub as its own repo

The repo root must be **this `mcp/` folder's contents**, not the whole
kabo-new-store project. `render.yaml` and `Dockerfile` both assume that.

```bash
cd "C:/Users/QC/Documents/KABO SEO/gdrive_download/kabo-new-store/mcp"
git init
git add .
git commit -m "KABO Indian Nutrition Index - MCP server"
```

Then create an empty public repo on github.com named
**`kabo-nutrition-mcp`** (no README, no .gitignore - this folder has one), and:

```bash
git remote add origin https://github.com/<your-username>/kabo-nutrition-mcp.git
git branch -M main
git push -u origin main
```

It has to be **public**. Several registries require it, and the official one
uses your GitHub identity to prove you own the namespace.

---

## Step 2 — Host it

### Render (recommended - free tier is enough)

1. render.com → **New → Blueprint**
2. Point it at the repo. `render.yaml` is already there and sets the
   Dockerfile, the health check and the port - you should not have to type
   any settings.
3. Deploy. You get `https://kabo-nutrition-mcp.onrender.com`.

The free tier sleeps when idle and takes a few seconds to wake. For a server
agents call occasionally that is fine. If you later want it always warm, that
is Render's paid tier or Fly.

### Fly.io (alternative - Mumbai region, no cold starts on a paid machine)

```bash
cd mcp
fly launch --no-deploy     # accept the existing fly.toml
fly deploy
```

`fly.toml` is set to `bom` (Mumbai), closest to your audience.

---

## Step 3 — Verify it is actually live

Replace the host and run all three. Do not move on until they pass.

```bash
HOST=https://kabo-nutrition-mcp.onrender.com

curl -s $HOST/health
# {"status":"ok","server":{...},"tools":[...]}

curl -s $HOST/mcp
# discovery: name, protocol, transport, tool list, licence

curl -s -X POST $HOST/mcp -H 'Content-Type: application/json' -d '{
  "jsonrpc":"2.0","id":1,"method":"tools/call",
  "params":{"name":"lookup_food","arguments":{"food":"rajma"}}}'
# rajma, with a source_url back to kabo.co.in
```

If the third one returns a `source_url`, the server works. That is the whole
test.

### Optional: put it on your own domain

In Cloudflare, CNAME `mcp.kabo.co.in` to the host, proxied. Worth doing before
registering, because the URL you register is the one that ends up in every
listing and every agent's config, and changing it later means re-publishing.

---

## Step 4 — Register it in the official MCP registry

**First edit `server.json`** and replace the three placeholders:

| Placeholder | Replace with |
|---|---|
| `REPLACE-GITHUB-USERNAME` (twice) | your GitHub username, exactly |
| `REPLACE-WITH-YOUR-HOST` | your live host from step 3 |

The `name` field must be `io.github.<your-username>/kabo-nutrition`. The
registry checks that the GitHub account you log in with owns that namespace,
so the username has to match or publishing is rejected.

This `server.json` registers a **remote** server only - no npm, PyPI or Docker
package. That is deliberate: the registry refuses to publish a server whose
declared package does not already exist in a package registry, and we are not
publishing a package. Remote-only has no such precondition, and a hosted HTTP
endpoint is what third-party agents actually want anyway.

Then:

```bash
# install the CLI (macOS/Linux)
brew install mcp-publisher
# Windows: download the binary from
# https://github.com/modelcontextprotocol/registry/releases

mcp-publisher validate          # checks server.json, publishes nothing
mcp-publisher login github      # opens a browser, proves you own the namespace
mcp-publisher publish
```

If you see *"Invalid or expired Registry JWT token"*, run
`mcp-publisher login github` again - the token is short-lived.

The registry is still in preview, so flags and schema versions move. If a
command here is rejected, check the current quickstart:
https://modelcontextprotocol.io/registry/quickstart

---

## Step 5 — Confirm the listing, then do the other registries

```bash
curl "https://registry.modelcontextprotocol.io/v0.1/servers?search=kabo-nutrition"
```

Once that returns your server, submit to the rest. These are all web forms or
a pull request, and all of them want the public repo URL from step 1:

| Registry | How |
|---|---|
| **mcp.so** | Web submission form |
| **Glama** | Submit the repo; it indexes public MCP servers |
| **Smithery** | Web submission, hosted-server friendly |
| **`modelcontextprotocol/servers`** | PR adding one line to the community list |

### What to write in the listing

Lead with the data, not the brand. The people curating these lists install
tools that solve a problem:

> Indian food nutrition data from ICMR-NIN sources. Protein, calcium and fibre
> per 100 g and per katori for 52 Indian foods; compare foods; protein targets
> by age and weight; protein cost ranking in INR; search across 1,095
> nutrition guides. Every response includes a source URL.

That is accurate and it is also the strongest pitch available. "Sells protein
powder" is not a reason for anyone to install anything.

---

## Keeping it current

```bash
python3 build_dataset.py     # re-reads the live articles, rewrites the dataset
git commit -am "dataset refresh"
git push                     # Render and Fly redeploy on push
```

Run it after publishing a batch of articles. If you change the tool list or
the description, bump `version` in `server.json` and run `mcp-publisher
publish` again.

---

## What needs you, not me

- **GitHub account** for the repo and for namespace auth.
- **Render or Fly account** for hosting.
- **Cloudflare access** if you want `mcp.kabo.co.in`.

Everything upstream is finished and tested: both transports, the Dockerfile,
the Render and Fly configs, the registry manifest and the dataset builder.

---

## One honest caveat

Listing an MCP server will not move traffic next week. The registries are
small and discovery through them is slow and compounding rather than sudden.

The reason to do it is different: it is the only asset in this programme that
a competitor cannot replicate by rewriting your content. An article can be
copied in an afternoon. A maintained data service that agents have configured
and call repeatedly is a position, and every call carries your attribution
back to kabo.co.in.

Treat it as infrastructure with a long payback, not a campaign.
