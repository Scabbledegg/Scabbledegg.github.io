"""
update_prices.py

Leest Bulk.csv (met kolommen zoals Name, Set name, Quantity, eventueel Foil)
en schrijft data/prices.json met per-kaartprijzen (Scryfall 'eur' / 'eur_foil').

Gebruik:
  pip install requests
  python update_prices.py --csv Bulk.csv --out-json data/prices.json --out-csv data/cards_with_prices.csv
"""

import argparse, csv, json, time, os, sys, unicodedata
from datetime import datetime
import requests

SCRYFALL_SEARCH = "https://api.scryfall.com/cards/search"
SCRYFALL_NAMED = "https://api.scryfall.com/cards/named"


def normalize(s: str) -> str:
    """Maak strings case/space/accent-ongevoelig voor vergelijking."""
    return unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().strip().lower()


def find_field(headers, candidates):
    hmap = {h.lower(): h for h in headers}
    for c in candidates:
        if c.lower() in hmap:
            return hmap[c.lower()]
    return None


def to_bool(val):
    if val is None:
        return False
    s = str(val).strip().lower()
    return s in ("1", "true", "yes", "y", "ja")


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
    """Kies de juiste kaart uit de zoekresultaten."""
    if not res_json or "data" not in res_json:
        return None
    items = res_json["data"]
    if not items:
        return None

    tgt = normalize(target_setname) if target_setname else None

    # 1. Zoek exacte set match met prijs
    if tgt:
        for c in items:
            if normalize(c.get("set_name", "")) == tgt or normalize(c.get("set", "")) == tgt:
                if c.get("prices", {}).get("eur") or c.get("prices", {}).get("eur_foil"):
                    return c

    # 2. Zoek eerste kaart met geldige EUR prijs
    for c in items:
        if c.get("prices", {}).get("eur") or c.get("prices", {}).get("eur_foil"):
            return c

    # 3. Fallback naar eerste resultaat
    return items[0]


def parse_float(x):
    try:
        return float(x) if x not in (None, "") else None
    except:
        return None


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

    # Detect kolommen
    name_field = find_field(headers, ["Name", "Card Name"])
    setname_field = find_field(headers, ["Set name", "Set"])
    qty_field = find_field(headers, ["Quantity", "Qty"])
    foil_field = find_field(headers, ["Foil", "Is foil"])

    if not name_field:
        print("CSV bevat geen kolom 'Name'. Aborting.", file=sys.stderr)
        sys.exit(1)

    prices = {}
    ts = datetime.utcnow().isoformat() + "Z"

    for r in rows:
        name = r.get(name_field, "").strip()
        setname = (r.get(setname_field) or "").strip() if setname_field else ""
        is_foil = to_bool(r.get(foil_field)) if foil_field else False
        if not name:
            continue

        # Scryfall search
        card = None
        res = scryfall_search_card(name)
        card = pick_card_from_search(res, setname) if res else None

        if not card:
            # fallback named endpoint
            try:
                resp = requests.get(
                    SCRYFALL_NAMED,
                    params={"fuzzy": name},
                    headers={"User-Agent": "MTG-Price-Updater/1.0"},
                    timeout=12,
                )
                if resp.ok:
                    card = resp.json()
            except Exception:
                card = None

        p = card.get("prices", {}) if isinstance(card, dict) else {}
        price_eur = parse_float(p.get("eur"))
        price_eur_foil = parse_float(p.get("eur_foil"))

        # kies foil prijs indien gewenst
        chosen = None
        if is_foil and price_eur_foil is not None:
            chosen = price_eur_foil
        elif price_eur is not None:
            chosen = price_eur
        elif price_eur_foil is not None:
            chosen = price_eur_foil

        if chosen is None:
            print(f"[NO PRICE FOUND] {name} ({setname})", file=sys.stderr)

        key = f"{name.strip()}|{setname.strip()}".strip("|")
        prices[key] = {
            "name": name,
            "set_name": setname or None,
            "foil": bool(is_foil),
            "price_eur": price_eur,
            "price_eur_foil": price_eur_foil,
            "chosen_price_eur": chosen if chosen is not None else "N/A",
            "scryfall_id": card.get("id") if card else None,
            "updated_at": ts,
        }

        time.sleep(args.sleep)

    # Schrijf JSON
    os.makedirs(os.path.dirname(args.out_json) or ".", exist_ok=True)
    with open(args.out_json, "w", encoding="utf-8") as f:
        json.dump({"updated_at": ts, "prices": prices}, f, ensure_ascii=False, indent=2)

    # Optionele CSV output
    if args.out_csv:
        fieldnames = list(headers)
        for col in ("price_eur", "price_eur_foil", "chosen_price_eur"):
            if col not in fieldnames:
                fieldnames.append(col)
        with open(args.out_csv, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=fieldnames)
            w.writeheader()
            for r in rows:
                name = r.get(name_field, "").strip()
                setname = (r.get(setname_field) or "").strip() if setname_field else ""
                key = f"{name.strip()}|{setname.strip()}".strip("|")
                info = prices.get(key, {})
                r["price_eur"] = info.get("price_eur")
                r["price_eur_foil"] = info.get("price_eur_foil")
                r["chosen_price_eur"] = info.get("chosen_price_eur")
                w.writerow(r)

    print(f"OK: prijzen geüpdatet ({len(prices)} items) -> {args.out_json}")


if __name__ == "__main__":
    main()
