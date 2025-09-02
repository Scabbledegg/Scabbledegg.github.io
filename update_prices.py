update_prices.py
Leest Bulk.csv (met kolommen zoals Name, Set name, Quantity, eventueel Foil)
en schrijft data/prices.json met per-kaartprijzen (Scryfall 'eur' / 'eur_foil').

Gebruik:
  pip install requests
  python update_prices.py --csv Bulk.csv --out-json data/prices.json --out-csv data/cards_with_prices.csv
"""
import argparse, csv, json, time, os, sys
from datetime import datetime
import requests

SCRYFALL_SEARCH = "https://api.scryfall.com/cards/search"
SCRYFALL_NAMED = "https://api.scryfall.com/cards/named"

def find_field(headers, candidates):
    # headers: list of actual CSV headers
    # candidates: prioritized list of names to match (case-insensitive)
    hmap = {h.lower(): h for h in headers}
    for c in candidates:
        if c.lower() in hmap:
            return hmap[c.lower()]
    return None

def to_bool(val):
    if val is None:
        return False
    s = str(val).strip().lower()
    return s in ("1","true","yes","y","ja")

def scryfall_search_card(name):
    headers = {"User-Agent": "MTG-Price-Updater/1.0 (+github.com/yourname)"}
    params = {"q": f'!"{name}"', "unique": "prints"}
    try:
        r = requests.get(SCRYFALL_SEARCH, params=params, headers=headers, timeout=20)
        if r.status_code == 404:
            return None
        r.raise_for_status()
        return r.json()
    except Exception as e:
        print(f"[WARN] Scryfall search failed for {name}: {e}", file=sys.stderr)
        return None

def pick_card_from_search(res_json, target_setname):
    if not res_json or "data" not in res_json:
        return None
    items = res_json["data"]
    if not items:
        return None
    if not target_setname:
        return items[0]
    target_lower = target_setname.strip().lower()
    # try exact set_name match first
    for c in items:
        if c.get("set_name","").strip().lower() == target_lower:
            return c
    # try set code match (if target looks like a code)
    for c in items:
        if c.get("set","").strip().lower() == target_lower:
            return c
    # otherwise fallback to first
    return items[0]

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", required=True, help="Input CSV (Bulk.csv)")
    ap.add_argument("--out-json", default="data/prices.json", help="Output JSON")
    ap.add_argument("--out-csv", default=None, help="Optioneel: schrijf CSV met prijskolommen")
    ap.add_argument("--sleep", type=float, default=0.11, help="Pauze tussen requests (sec)")
    args = ap.parse_args()

    with open(args.csv, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        headers = reader.fieldnames or []

    # detect kolomnamen
    name_field = find_field(headers, ["Name","name","Card Name","card_name"])
    setname_field = find_field(headers, ["Set name","set_name","Set","set"])
    qty_field = find_field(headers, ["Quantity","Qty","quantity","qty"])
    foil_field = find_field(headers, ["Foil","Is foil","foil","is_foil"])

    if not name_field:
        print("CSV bevat geen kolom 'Name' (of alternatieven). Aborting.", file=sys.stderr)
        sys.exit(1)

    prices = {}
    ts = datetime.utcnow().isoformat()+"Z"

    for r in rows:
        name = r.get(name_field,"").strip()
        setname = (r.get(setname_field) or "").strip() if setname_field else ""
        is_foil = to_bool(r.get(foil_field)) if foil_field else False
        if not name:
            continue

        # try Scryfall search
        card_data = None
        res = scryfall_search_card(name)
        card = pick_card_from_search(res, setname) if res else None

        if not card:
            # try named endpoint (fallback)
            try:
                resp = requests.get(SCRYFALL_NAMED, params={"exact": name}, headers={"User-Agent":"MTG-Price-Updater/1.0"}, timeout=12)
                if resp.ok:
                    card = resp.json()
            except Exception:
                card = None

        p = card.get("prices", {}) if isinstance(card, dict) else {}
        price_eur = p.get("eur")
        price_eur_foil = p.get("eur_foil")
        chosen = price_eur_foil if is_foil and price_eur_foil else price_eur

        key = f"{name}|{setname}".strip("|")
        def parsef(x):
            try:
                return float(x) if x not in (None,"") else None
            except:
                return None

        prices[key] = {
            "name": name,
            "set_name": setname or None,
            "foil": bool(is_foil),
            "price_eur": parsef(price_eur),
            "price_eur_foil": parsef(price_eur_foil),
            "chosen_price_eur": parsef(chosen),
            "scryfall_id": card.get("id") if card else None,
            "updated_at": ts,
        }

        time.sleep(args.sleep)

    # schrijf JSON
    os.makedirs(os.path.dirname(args.out_json) or ".", exist_ok=True)
    with open(args.out_json, "w", encoding="utf-8") as f:
        json.dump({"updated_at": ts, "prices": prices}, f, ensure_ascii=False, indent=2)

    # optionele CSV output
    if args.out_csv:
        fieldnames = list(headers)
        for col in ("price_eur","price_eur_foil","chosen_price_eur"):
            if col not in fieldnames:
                fieldnames.append(col)
        with open(args.out_csv, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=fieldnames)
            w.writeheader()
            for r in rows:
                name = r.get(name_field,"").strip()
                setname = (r.get(setname_field) or "").strip() if setname_field else ""
                key = f"{name}|{setname}".strip("|")
                info = prices.get(key, {})
                r["price_eur"] = info.get("price_eur")
                r["price_eur_foil"] = info.get("price_eur_foil")
                r["chosen_price_eur"] = info.get("chosen_price_eur")
                w.writerow(r)

    print(f"OK: prijzen geüpdatet ({len(prices)} items) -> {args.out_json}")

if __name__ == "__main__":
    main()