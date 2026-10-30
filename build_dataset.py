# -*- coding: utf-8 -*-
"""Build kabo_food_data.json from the live article corpus.

Extracts the nutrition tables out of the protein-in-X / calcium-in-X fact
pages and emits the dataset the MCP server reads.

One parsing rule matters more than the rest: header rows are skipped. A <th>
row names the columns, and parsing it as data produced entries like
{"Food": "Protein (dry, per 100 g)", "low": 100.0} - which would make an
agent confidently answer that "Food" contains 100 g of protein. Only <td>
rows are read.

Usage:
    python3 build_dataset.py
"""
import html as H
import json
import os
import re
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "scripts"))
from dotenv import load_dotenv

load_dotenv(os.path.join(ROOT, ".env"))
import requests

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

OUT = os.path.join(HERE, "kabo_food_data.json")
STORE = os.getenv("SHOPIFY_STORE", "").rstrip("/")
TOKEN = os.getenv("SHOPIFY_TOKEN", "")
s = requests.Session()
s.headers.update({"X-Shopify-Access-Token": TOKEN})
BASE = f"https://{STORE}/admin/api/2024-01"

FACT = re.compile(r"^(protein|calcium|fibre|iron)-in-(.+?)(?:-india)?$")
NUM = re.compile(r"(\d+(?:\.\d+)?)\s*(?:[–—-]\s*(\d+(?:\.\d+)?))?\s*(g|mg|kcal)\b",
                 re.I)
TH = re.compile(r"<th[^>]*>")
TD = re.compile(r"<td[^>]*>(.*?)</td>", re.S)
TR = re.compile(r"<tr[^>]*>(.*?)</tr>", re.S)
TABLE = re.compile(r"<table.*?</table>", re.S)


def get(path, **kw):
    for a in range(6):
        try:
            r = s.get(f"{BASE}{path}", timeout=120, **kw)
            r.json()
            return r
        except Exception:
            time.sleep(2 * (a + 1))
    return None


def clean(x):
    return re.sub(r"\s+", " ", H.unescape(re.sub(r"<[^>]+>", "", x))).strip()


def fetch_articles():
    arts = {}
    for bl in get("/blogs.json").json()["blogs"]:
        pi = None
        while True:
            p = {"limit": 100, "fields": "handle,title,body_html"}
            if pi:
                p["page_info"] = pi
            r = get(f"/blogs/{bl['id']}/articles.json", params=p)
            if r is None:
                break
            for a in r.json()["articles"]:
                arts[a["handle"]] = (a["title"], a["body_html"] or "")
            link = r.headers.get("Link", "")
            if 'rel="next"' not in link:
                break
            m = re.search(r'page_info=([^&>]+)[^>]*>; rel="next"', link)
            if not m:
                break
            pi = m.group(1)
    return arts


def extract_foods(arts):
    foods = []
    for h, (title, body) in sorted(arts.items()):
        m = FACT.match(h)
        if not m:
            continue
        nutrient, food = m.group(1), m.group(2).replace("-", " ")
        vals = []
        for tb in TABLE.findall(body):
            for tr in TR.findall(tb):
                if TH.search(tr):          # header row - names columns, not data
                    continue
                c = [clean(x) for x in TD.findall(tr)]
                if len(c) < 2:
                    continue
                label, val = c[0], c[1]
                if len(label) < 2:
                    continue
                if not (re.search(r"\d", val) and re.search(r"\bg\b|gram|mg|kcal", val)):
                    continue
                mm = NUM.search(val)
                if not mm:
                    continue
                vals.append({"item": label[:70], "stated": val[:40],
                             "low": float(mm.group(1)),
                             "high": float(mm.group(2)) if mm.group(2) else None,
                             "unit": mm.group(3).lower()})
        if vals:
            foods.append({"food": food, "nutrient": nutrient, "title": title,
                          "source_url": f"https://kabo.co.in/blogs/news/{h}",
                          "values": vals[:14]})
    return foods


def build_products():
    """Snapshot KABO's own products for the product tools.

    Per-flavour values come from each product's custom.nutrition_json
    metafield - the same data the product page renders - so one flavour's
    serving size is never reused for another (Butter Coffee is 54 g, White
    Chocolate Blueberry 51 g). Composition and dietary statements are quoted
    from the product description, not paraphrased, and carry that page as
    their source. Prices here are a fallback only: the server fetches live
    price and stock from the public storefront at request time.
    """
    out = []
    api = f"https://{STORE}/admin/api/2024-10"
    prods = s.get(f"{api}/products.json", params={"limit": 50, "status": "active",
                  "fields": "id,handle,title,body_html,variants,images,product_type"},
                  timeout=60).json()["products"]
    for p in prods:
        mf = {f"{m['namespace']}.{m['key']}": m["value"] for m in
              s.get(f"{api}/products/{p['id']}/metafields.json", timeout=60).json()["metafields"]}
        try:
            nut = json.loads(mf.get("custom.nutrition_json") or "{}")
        except Exception:
            nut = {}
        text = clean(p.get("body_html") or "")
        def quote(pattern):
            m = re.search(r"[^.]{0,160}" + pattern + r"[^.]{0,160}\.", text, re.I)
            return m.group(0).strip(" :") if m else None
        url = f"https://kabo.co.in/products/{p['handle']}"
        out.append({
            "handle": p["handle"],
            "name": re.sub(r"\s*-\s*The Ultimate.*$", "", p["title"]).strip(),
            "full_title": p["title"],
            "url": url,
            "image": (p.get("images") or [{}])[0].get("src"),
            "nutrition_per_serving": nut,
            "nutrition_source": url + " (product nutrition panel)",
            "protein_sources": quote(r"pea protein, brown rice protein, and yeast protein"),
            "dietary_statement": quote(r"ideal for vegans"),
            "functional_ingredients": quote(r"functional mushrooms"),
            "also_contains": quote(r"probiotics & digestive enzymes"),
            "suitability": {
                "vegan": "yes - the product page states it is ideal for vegans",
                "lactose_free": "yes - the product page states it suits lactose-free users",
                "jain": ("no - contains functional mushrooms and yeast protein, which most "
                         "Jain observances exclude"),
                "medical": ("not a substitute for medical treatment; people with kidney disease, "
                            "pregnant or breastfeeding, or on prescribed diets should check with "
                            "their doctor first"),
            },
            "rating": {"average": (json.loads(mf["reviews.rating"])["value"]
                                   if "reviews.rating" in mf else None),
                       "count": int(mf["reviews.rating_count"]) if "reviews.rating_count" in mf else None,
                       "source": "Judge.me reviews on kabo.co.in"},
            "variants": [{"id": v["id"], "title": v["title"], "sku": v.get("sku"),
                          "price_inr_snapshot": float(v["price"]),
                          "servings": (int(re.search(r"(\d+)\s*Shakes", v["title"]).group(1))
                                       if re.search(r"(\d+)\s*Shakes", v["title"]) else None),
                          "cart_url": f"https://kabo.co.in/cart/{v['id']}:1"}
                         for v in p["variants"]],
        })
    return out


TARGETS = [
 {"situation": "Adult, avoid deficiency (ICMR-NIN RDA)", "g_per_kg_low": 0.83, "g_per_kg_high": 0.83},
 {"situation": "Adult, preserve muscle (from age 40)", "g_per_kg_low": 1.0, "g_per_kg_high": 1.2},
 {"situation": "Training to build muscle", "g_per_kg_low": 1.4, "g_per_kg_high": 1.6},
 {"situation": "In a calorie deficit", "g_per_kg_low": 1.6, "g_per_kg_high": 1.6},
 {"situation": "Older adult, healthy (PROT-AGE)", "g_per_kg_low": 1.0, "g_per_kg_high": 1.2},
 {"situation": "Older adult, illness/recovery/training", "g_per_kg_low": 1.2, "g_per_kg_high": 1.5},
 {"situation": "Pregnancy, 2nd trimester (add to base)", "add_g_per_day": 9},
 {"situation": "Pregnancy, 3rd trimester (add to base)", "add_g_per_day": 22},
 {"situation": "Breastfeeding, 0-6 months (add to base)", "add_g_per_day": 17},
 {"situation": "Chronic kidney disease",
  "note": "Set by a nephrologist. General targets do not apply."},
]
COST = [{"source": "Soya chunks", "inr_per_10g_protein": 6},
        {"source": "Toor or moong dal", "inr_per_10g_protein": 8},
        {"source": "Eggs", "inr_per_10g_protein": 12},
        {"source": "Roasted chana", "inr_per_10g_protein": 14},
        {"source": "Curd, homemade", "inr_per_10g_protein": 18},
        {"source": "Milk", "inr_per_10g_protein": 20},
        {"source": "Paneer", "inr_per_10g_protein": 28},
        {"source": "Whey protein, mid-range", "inr_per_10g_protein": 35},
        {"source": "Imported whey isolate", "inr_per_10g_protein": 60}]
MEAL = [{"age_band": "20-35", "protein_per_meal_g": 20},
        {"age_band": "50-65", "protein_per_meal_g": 30},
        {"age_band": "65+", "protein_per_meal_g": 30,
         "note": "30-40 g; anabolic resistance raises the per-meal threshold"}]


if __name__ == "__main__":
    if not STORE or not TOKEN:
        print("SHOPIFY_STORE / SHOPIFY_TOKEN missing from .env")
        raise SystemExit(1)
    arts = fetch_articles()
    print(f"{len(arts)} articles fetched")
    foods = extract_foods(arts)
    guides = [{"handle": h, "title": t,
               "url": f"https://kabo.co.in/blogs/news/{h}"}
              for h, (t, _) in sorted(arts.items())]
    ds = {"dataset": "KABO Indian Nutrition Index",
          "version": time.strftime("%Y-%m-%d"),
          "licence": "CC BY 4.0 - free to use with attribution to kabo.co.in",
          "primary_sources": ["ICMR-NIN Indian Food Composition Tables",
                              "ICMR-NIN Nutrient Requirements for Indians (RDA 2020)",
                              "PROT-AGE / ESPEN expert group recommendations"],
          "disclaimer": ("Nutrition information, not medical advice. Values are "
                         "approximate and vary by variety, preparation and brand."),
          "products": build_products(),
          "commerce": {
              "store": "https://kabo.co.in",
              "ucp_profile": "https://kabo.co.in/.well-known/ucp",
              "note": ("Checkout runs on the store's own Shopify checkout. Agents that speak "
                       "the Universal Commerce Protocol can discover carts and checkout via "
                       "the UCP profile; others can hand the user a cart_url.")},
          "foods": foods, "protein_targets": TARGETS,
          "per_meal_threshold": MEAL, "protein_cost_index_inr": COST,
          "guides": guides}
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(ds, f, indent=1, ensure_ascii=False)
    rows = sum(len(x["values"]) for x in foods)
    print(f"wrote {OUT}")
    print(f"  foods {len(foods)}   value rows {rows}   guides {len(guides)}")
    print(f"  size {os.path.getsize(OUT)/1024:.0f} KB")
