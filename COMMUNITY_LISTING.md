# Listing copy for the remaining directories

Everything below is ready to paste. The official registry is done
(`io.github.Guru-ragul/kabo-nutrition`, active). Glama is submitted and
`glama.json` claims the listing. Smithery's publish endpoint returns 403 on its
own form - emailed support, nothing more to do there until they reply.

---

## 1. `modelcontextprotocol/servers` community list (one-line PR)

Repo: https://github.com/modelcontextprotocol/servers
File: `README.md`, section **Community Servers** (alphabetical by name).

Fork the repo on github.com (Fork button), then on the fork edit README.md and
insert this line in alphabetical position under Community Servers:

```
- **[KABO Indian Nutrition Index](https://github.com/Guru-ragul/KABO-Indian-Nutrition-Index---MCP-server)** - Indian food nutrition from ICMR-NIN: protein, calcium, fibre and iron per 100 g and per katori for Indian foods, protein targets by age and weight, protein cost in rupees, and search across 1,000+ nutrition guides. Every response cites its source. Hosted Streamable HTTP endpoint, no auth.
```

(Adjust the nutrient list to whatever the dataset carries at the time - the
server's own `GET /mcp` discovery lists it.)

PR title:
```
Add KABO Indian Nutrition Index (Indian food nutrition data, ICMR-NIN)
```

PR body:
```
Adds the KABO Indian Nutrition Index to Community Servers.

- Data: ICMR-NIN Indian Food Composition Tables and RDA 2020; PROT-AGE/ESPEN protein guidance
- Tools: lookup_food, compare_foods, protein_target, protein_cost, search_guides
- Transport: Streamable HTTP (hosted, no auth) and stdio (dependency-free Python)
- Licence: CC BY 4.0 for the dataset
- Registry: io.github.Guru-ragul/kabo-nutrition (official MCP registry, active)
- Every response carries a source URL

🤖 Generated with [Claude Code](https://claude.com/claude-code)
```

---

## 2. mcp.so

URL: https://mcp.so (Submit)

- Name: KABO Indian Nutrition Index
- Repo: https://github.com/Guru-ragul/KABO-Indian-Nutrition-Index---MCP-server
- Server URL: https://kabo-nutrition-mcp.onrender.com/mcp
- Category: Data / Health
- Description (long form):

```
Indian food nutrition data from ICMR-NIN sources, served as an MCP server. Look up protein, calcium, fibre and iron per 100 g and per katori for Indian foods; compare foods on one nutrient; calculate daily protein targets by age and body weight (ICMR-NIN RDA 2020, PROT-AGE); rank protein sources by cost per 10 g in rupees; and search across 1,000+ Indian nutrition guides. Every response includes a source URL. Free, no API key, dataset licensed CC BY 4.0.
```

---

## 3. PulseMCP

URL: https://www.pulsemcp.com/submit

Same fields as mcp.so. PulseMCP reads the official registry, so it may already
have picked the server up - search for "kabo" first.

---

## 4. Cursor directory / other "awesome-mcp" lists

Most of these are PRs to a README with the same one-liner as section 1.
Worth a search for `awesome-mcp-servers` on GitHub and adding to the top two
or three by stars, under a Health / Data heading.

---

## Short description (<= 100 chars, for anything with a cap)

```
ICMR-NIN nutrition for Indian foods: protein, targets by age, cost ranking. Every answer cited.
```

## Tags

```
nutrition, india, food, protein, icmr-nin, health, dataset, open-data, cc-by
```
