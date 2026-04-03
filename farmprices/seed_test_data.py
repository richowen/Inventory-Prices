"""
seed_test_data.py — Insert 10 suppliers, subcategories, and 66 products for testing.
Safe to re-run: skips rows that already exist.

Usage:
    python seed_test_data.py
"""
import os, sqlite3
from datetime import date, timedelta

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH  = os.path.join(BASE_DIR, "prices.db")

SUPPLIERS = [
    ("Wynnstay Group",        "01691 828512", "sales@wynnstay.co.uk",    "Main feed supplier"),
    ("BOCM Pauls",            "01473 822222", "orders@bocmpauls.co.uk",  "Compound feeds"),
    ("Farmway",               "01677 422215", "info@farmway.co.uk",      "Bedding & feed"),
    ("Rumenco",               "01283 511211", "sales@rumenco.co.uk",     "Supplements & blocks"),
    ("Kelso Fencing",         "01573 225773", "info@kelsofencing.co.uk", "Fencing & posts"),
    ("Kings Seeds",           "01376 570000", "sales@kingsseeds.com",    "Seeds & grass mixes"),
    ("Hutchinsons",           "01354 696060", "hello@hutchinsons.co.uk", "Fertilisers & inputs"),
    ("NWF Agriculture",       "01829 261111", "orders@nwfag.co.uk",      "Bulk feed & bedding"),
    ("Norbrook Laboratories", "02825 631924", "vet@norbrook.com",        "Vet medicines"),
    ("Toolbank",              "01322 321321", "trade@toolbank.com",      "Hand & farm tools"),
]

# (subcategory_name, parent_category_name)
SUBCATEGORIES = [
    ("Cattle Feed",              "Animal Feed"),
    ("Horse Feed",               "Animal Feed"),
    ("Poultry & Small Animal",   "Animal Feed"),
    ("Wire & Netting",           "Fencing"),
    ("Electric Fencing",         "Fencing"),
    ("Stable & Yard Tools",      "Tools"),
    ("Medicines & Supplements",  "Vet Supplies"),
    ("Grass & Pasture",          "Seeds"),
]

today = date.today()

# (name, category, unit, supplier, cost, markup%, barcode, qty, reorder, weight_kg, volume_litres)
PRODUCTS = [
    # ── Animal Feed (top-level) ──────────────────────────────────────────────
    ("Rabbit Pellets 5kg",          "Animal Feed",          "bag",  "Farmway",               2.10, 40, "8901234500006", 60, 12, 5.0,  None),
    ("Goat Mix 20kg",               "Animal Feed",          "bag",  "Wynnstay Group",         6.80, 30, "8901234500007", 15, 3,  20.0, None),
    # ── Cattle Feed (sub of Animal Feed) ────────────────────────────────────
    ("Cattle Cake 25kg",            "Cattle Feed",          "bag",  "Wynnstay Group",         8.40, 30, "8901234500004", 25, 5,  25.0, None),
    ("Calf Creep Pellets 25kg",     "Cattle Feed",          "bag",  "BOCM Pauls",             9.20, 28, "8901234500008", 18, 4,  25.0, None),
    ("Mineralised Lamb Creep 25kg", "Cattle Feed",          "bag",  "Rumenco",               11.50, 25, "8901234500009", 12, 3,  25.0, None),
    ("Cattle Finisher Blend 25kg",  "Cattle Feed",          "bag",  "BOCM Pauls",            10.20, 28, "8901234500051", 15, 3,  25.0, None),
    ("Beef Blend Nuts 25kg",        "Cattle Feed",          "bag",  "Wynnstay Group",         9.80, 28, "8901234500052", 18, 4,  25.0, None),
    ("Dairy Nuts 25kg",             "Cattle Feed",          "bag",  "BOCM Pauls",            11.00, 25, "8901234500053", 20, 5,  25.0, None),
    # ── Horse Feed (sub of Animal Feed) ─────────────────────────────────────
    ("Horse & Pony Cubes 20kg",     "Horse Feed",           "bag",  "Wynnstay Group",         5.20, 35, "8901234500001", 48, 10, 20.0, None),
    ("Equine Senior Mix 20kg",      "Horse Feed",           "bag",  "Wynnstay Group",        12.30, 30, "8901234500010", 20, 5,  20.0, None),
    ("Competition Horse Cubes 20kg","Horse Feed",           "bag",  "Wynnstay Group",        14.50, 30, "8901234500054", 15, 3,  20.0, None),
    ("Stud Mix 20kg",               "Horse Feed",           "bag",  "Wynnstay Group",        13.80, 30, "8901234500055", 10, 2,  20.0, None),
    # ── Poultry & Small Animal (sub of Animal Feed) ──────────────────────────
    ("Poultry Layers Mash 20kg",    "Poultry & Small Animal","bag", "Farmway",                4.90, 32, "8901234500005", 40, 8,  20.0, None),
    ("Pig Finisher Pellets 25kg",   "Poultry & Small Animal","bag", "BOCM Pauls",             7.80, 28, "8901234500003", 20, 4,  25.0, None),
    ("Sheep Nuts 25kg",             "Poultry & Small Animal","bag", "BOCM Pauls",             6.10, 30, "8901234500002", 30, 5,  25.0, None),
    ("Chick Crumb 5kg",             "Poultry & Small Animal","bag", "Farmway",                2.80, 40, "8901234500056", 30, 6,  5.0,  None),
    ("Guinea Pig Pellets 2kg",      "Poultry & Small Animal","bag", "Farmway",                1.90, 45, "8901234500057", 25, 5,  2.0,  None),
    # ── Bedding ──────────────────────────────────────────────────────────────
    ("Straw Bale Large Square",     "Bedding",              "each", "NWF Agriculture",        3.50, 40, "8901234500011", 80, 20, 20.0, None),
    ("Wood Shavings 20kg Bale",     "Bedding",              "each", "Farmway",                4.20, 35, "8901234500012", 50, 10, 20.0, None),
    ("Hemp Bedding 20kg",           "Bedding",              "bag",  "Farmway",                7.80, 30, "8901234500013", 30, 6,  20.0, None),
    ("Miscanthus Bedding 20kg",     "Bedding",              "bag",  "NWF Agriculture",        6.50, 30, "8901234500014", 25, 5,  20.0, None),
    ("Rubber Stable Mat 2x1m",      "Bedding",              "each", "Toolbank",              18.00, 45, "8901234500015", 10, 2,  None, None),
    ("Dust-Free Shavings 25L",      "Bedding",              "each", "Farmway",                3.10, 35, "8901234500016", 40, 8,  None, None),
    # ── Fencing (top-level) ───────────────────────────────────────────────────
    ("Round Stake 1.8m",            "Fencing",              "each", "Kelso Fencing",          1.20, 50, "8901234500017", 200,40, 4.5,  None),
    ("Corner Post 2.4m",            "Fencing",              "each", "Kelso Fencing",          4.50, 40, "8901234500021", 40, 8,  10.0, None),
    ("Staples 1kg",                 "Fencing",              "bag",  "Kelso Fencing",          2.80, 50, "8901234500020", 30, 5,  1.0,  None),
    # ── Wire & Netting (sub of Fencing) ──────────────────────────────────────
    ("Stock Netting 50m Roll",      "Wire & Netting",       "roll", "Kelso Fencing",         38.00, 40, "8901234500018", 20, 4,  None, None),
    ("Barbed Wire 200m",            "Wire & Netting",       "roll", "Kelso Fencing",         14.00, 40, "8901234500022", 10, 2,  None, None),
    ("Chicken Wire 50m Roll",       "Wire & Netting",       "roll", "Kelso Fencing",         16.50, 40, "8901234500058", 12, 2,  None, None),
    ("Mild Steel Wire 200m",        "Wire & Netting",       "roll", "Kelso Fencing",         11.00, 40, "8901234500059", 8,  2,  None, None),
    # ── Electric Fencing (sub of Fencing) ────────────────────────────────────
    ("Electric Fence Wire 400m",    "Electric Fencing",     "roll", "Kelso Fencing",         12.50, 45, "8901234500019", 15, 3,  None, None),
    ("Electric Strainer Post",      "Electric Fencing",     "each", "Kelso Fencing",          3.80, 45, "8901234500060", 30, 6,  None, None),
    ("Energiser 2J Mains",          "Electric Fencing",     "each", "Kelso Fencing",         52.00, 40, "8901234500061", 5,  1,  None, None),
    # ── Seeds (top-level) ─────────────────────────────────────────────────────
    ("White Clover 2kg",            "Seeds",                "bag",  "Kings Seeds",            9.50, 35, "8901234500024", 20, 4,  2.0,  None),
    ("Chicory Mix 1kg",             "Seeds",                "bag",  "Kings Seeds",            8.20, 35, "8901234500027", 10, 2,  1.0,  None),
    # ── Grass & Pasture (sub of Seeds) ───────────────────────────────────────
    ("Ryegrass Mixture 20kg",       "Grass & Pasture",      "bag",  "Kings Seeds",           22.00, 30, "8901234500023", 25, 5,  20.0, None),
    ("Fodder Rape 5kg",             "Grass & Pasture",      "bag",  "Kings Seeds",            6.80, 30, "8901234500025", 15, 3,  5.0,  None),
    ("Grass Mix Amenity 10kg",      "Grass & Pasture",      "bag",  "Kings Seeds",           14.50, 32, "8901234500026", 18, 4,  10.0, None),
    ("AberDart Ryegrass 14kg",      "Grass & Pasture",      "bag",  "Kings Seeds",           18.00, 30, "8901234500062", 12, 3,  14.0, None),
    ("Amenity Pro Mix 5kg",         "Grass & Pasture",      "bag",  "Kings Seeds",            9.80, 32, "8901234500063", 10, 2,  5.0,  None),
    # ── Fertiliser ────────────────────────────────────────────────────────────
    ("NPK 20-10-10 25kg",           "Fertiliser",           "bag",  "Hutchinsons",           14.00, 28, "8901234500028", 30, 6,  25.0, None),
    ("Ammonium Nitrate 25kg",       "Fertiliser",           "bag",  "Hutchinsons",           12.50, 25, "8901234500029", 20, 4,  25.0, None),
    ("Liquid Urea 1000L IBC",       "Fertiliser",           "each", "Hutchinsons",          280.00, 20, "8901234500030", 2,  1,  None, 1000.0),
    ("Trace Element Mix 25kg",      "Fertiliser",           "bag",  "Hutchinsons",           18.00, 30, "8901234500031", 12, 3,  25.0, None),
    ("Lime Granules 25kg",          "Fertiliser",           "bag",  "Hutchinsons",            4.80, 30, "8901234500032", 40, 8,  25.0, None),
    # ── Tools (top-level) ─────────────────────────────────────────────────────
    ("Wheelbarrow 90L",             "Tools",                "each", "Toolbank",              28.00, 45, "8901234500035", 6,  1,  None, None),
    ("Hoof Pick Stainless",         "Tools",                "each", "Toolbank",               1.80, 60, "8901234500036", 20, 4,  None, None),
    ("Feed Scoop 2L",               "Tools",                "each", "Toolbank",               2.40, 55, "8901234500037", 25, 5,  None, None),
    # ── Stable & Yard Tools (sub of Tools) ───────────────────────────────────
    ("Hay Fork",                    "Stable & Yard Tools",  "each", "Toolbank",               8.50, 50, "8901234500033", 12, 2,  None, None),
    ("Muck Fork",                   "Stable & Yard Tools",  "each", "Toolbank",               9.20, 50, "8901234500034", 10, 2,  None, None),
    ("Water Brush",                 "Stable & Yard Tools",  "each", "Toolbank",               3.10, 50, "8901234500038", 15, 3,  None, None),
    ("Stable Broom",                "Stable & Yard Tools",  "each", "Toolbank",               4.50, 50, "8901234500064", 10, 2,  None, None),
    ("Skip / Dung Fork",            "Stable & Yard Tools",  "each", "Toolbank",               9.80, 50, "8901234500065", 8,  2,  None, None),
    # ── Vet Supplies (top-level) ──────────────────────────────────────────────
    ("Fly Repellent Spray 500ml",   "Vet Supplies",         "each", "Norbrook Laboratories",  4.80, 50, "8901234500040", 25, 5,  None, 0.5),
    ("Iodine Spray 500ml",          "Vet Supplies",         "each", "Norbrook Laboratories",  3.60, 50, "8901234500041", 20, 4,  None, 0.5),
    ("Wound Powder 200g",           "Vet Supplies",         "each", "Norbrook Laboratories",  4.10, 50, "8901234500042", 18, 3,  0.2,  None),
    # ── Medicines & Supplements (sub of Vet Supplies) ─────────────────────────
    ("Worming Paste 7.74g",         "Medicines & Supplements","each","Norbrook Laboratories", 3.20, 55, "8901234500039", 30, 6,  None, None),
    ("Vitamin E & Selenium 1L",     "Medicines & Supplements","each","Norbrook Laboratories",12.50, 45, "8901234500043", 10, 2,  None, 1.0),
    ("Cattle Bolus 6-pack",         "Medicines & Supplements","pack","Norbrook Laboratories",18.00, 40, "8901234500044", 8,  1,  None, None),
    ("Ivermectin Pour-On 500ml",    "Medicines & Supplements","each","Norbrook Laboratories",14.50, 45, "8901234500066", 8,  2,  None, 0.5),
    ("Copper Sulphate 1kg",         "Medicines & Supplements","each","Norbrook Laboratories", 6.80, 45, "8901234500067", 12, 2,  1.0,  None),
    # ── Other ─────────────────────────────────────────────────────────────────
    ("Galvanised Bucket 12L",       "Other",                "each", "Toolbank",               3.50, 50, "8901234500045", 20, 4,  None, None),
    ("Rope Headcollar",             "Other",                "each", "Toolbank",               4.20, 45, "8901234500046", 15, 3,  None, None),
    ("Baler Twine 500m",            "Other",                "roll", "NWF Agriculture",        6.80, 40, "8901234500047", 25, 5,  None, None),
    ("Livestock Spray Marker 500ml","Other",                "each", "Toolbank",               3.90, 50, "8901234500048", 12, 2,  None, 0.5),
    ("Salt Lick Block 10kg",        "Other",                "each", "Rumenco",                4.20, 45, "8901234500049", 30, 6,  10.0, None),
    ("Feed Barrier Net 3x3m",       "Other",                "each", "NWF Agriculture",       14.50, 40, "8901234500050", 8,  2,  None, None),
]


def run():
    if not os.path.exists(DB_PATH):
        print("ERROR: prices.db not found. Start the app first to create the database.")
        return

    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys=ON")

    # ── Suppliers ─────────────────────────────────────────────────────────────
    added_sup = 0
    for name, tel, email, notes in SUPPLIERS:
        if not db.execute("SELECT id FROM suppliers WHERE name=?", (name,)).fetchone():
            db.execute("INSERT INTO suppliers (name,tel,email,notes) VALUES (?,?,?,?)",
                       (name, tel, email, notes))
            added_sup += 1

    # ── Subcategories ─────────────────────────────────────────────────────────
    added_cat = 0
    for sub_name, parent_name in SUBCATEGORIES:
        parent = db.execute("SELECT id FROM categories WHERE name=?", (parent_name,)).fetchone()
        if not parent:
            print(f"  WARNING: parent category {parent_name!r} not found — skipping {sub_name!r}")
            continue
        if not db.execute("SELECT id FROM categories WHERE name=?", (sub_name,)).fetchone():
            db.execute("INSERT INTO categories (name, parent_id) VALUES (?,?)",
                       (sub_name, parent["id"]))
            added_cat += 1

    # ── Products ──────────────────────────────────────────────────────────────
    # Refresh category list after inserts
    all_cats = {r["name"] for r in db.execute("SELECT name FROM categories").fetchall()}

    added_prod = 0
    for i, row in enumerate(PRODUCTS):
        name, category, unit, supplier, cost, markup, barcode, qty, reorder, weight_kg, volume_litres = row
        if db.execute("SELECT id FROM products WHERE name=? AND active=1", (name,)).fetchone():
            continue
        if category not in all_cats:
            print(f"  WARNING: category {category!r} not found for {name!r} — skipping")
            continue
        days_back = (i % 45) + 1
        last_upd  = (today - timedelta(days=days_back)).isoformat()
        sup_row   = db.execute("SELECT tel FROM suppliers WHERE name=?", (supplier,)).fetchone()
        tel       = sup_row["tel"] if sup_row else ""
        db.execute(
            """INSERT INTO products
               (name,category,unit,supplier_name,supplier_tel,cost_price,markup_pct,
                notes,barcode,quantity,reorder_threshold,weight_kg,volume_litres,last_updated)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (name, category, unit, supplier, tel, float(cost), float(markup),
             "", barcode, float(qty), float(reorder), weight_kg, volume_litres, last_upd)
        )
        added_prod += 1

    db.commit()
    db.close()

    print(f"Seed complete: {added_sup} supplier(s), {added_cat} subcategory(ies), {added_prod} product(s) added.")
    if added_sup == 0 and added_cat == 0 and added_prod == 0:
        print("(All rows already present — nothing to do.)")


if __name__ == "__main__":
    run()
