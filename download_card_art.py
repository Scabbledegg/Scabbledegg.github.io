import os
import pandas as pd
import requests
import re

# Laad je CSV
df = pd.read_csv("Bulk.csv")

# Map voor afbeeldingen
os.makedirs("card_images", exist_ok=True)

def sanitize_file_name(name: str) -> str:
    # Zelfde als in HTML
    name = re.sub(r"[/:]", "-", name)           # vervang / en :
    name = re.sub(r"[^a-zA-Z0-9\s\-]", "", name) # haal rare tekens weg
    name = re.sub(r"\s+", " ", name).strip()     # dubbele spaties fixen
    return name

for i, row in df.iterrows():
    if pd.isna(row["Name"]) or pd.isna(row["Scryfall ID"]):
        continue

    card_name = sanitize_file_name(str(row["Name"]))
    scryfall_id = row["Scryfall ID"]

    filename = os.path.join("card_images", f"{card_name}.jpg")

    # Skip als het al bestaat
    if os.path.exists(filename):
        print(f"⏭️ Bestaat al: {card_name}")
        continue

    url = f"https://api.scryfall.com/cards/{scryfall_id}"
    response = requests.get(url)
    if response.status_code != 200:
        print(f"❌ Error bij {card_name}")
        continue

    data = response.json()

    if "image_uris" in data:
        img_url = data["image_uris"]["large"]
    elif "card_faces" in data:  # double-faced cards
        img_url = data["card_faces"][0]["image_uris"]["large"]
    else:
        print(f"⚠️ Geen afbeelding voor {card_name}")
        continue

    img_data = requests.get(img_url).content

    with open(filename, "wb") as f:
        f.write(img_data)

    print(f"✅ Nieuw gedownload: {card_name}")
