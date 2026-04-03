"""
seed_deploy.py — First-run deployment setup for Farm Supplies Price App.

Idempotent — safe to re-run, skips existing records.

Usage:
    python seed_deploy.py
"""
import os,secrets,sqlite3
from datetime import date

BASE_DIR=os.path.dirname(os.path.abspath(__file__))
DB_PATH=os.path.join(BASE_DIR,"prices.db")
ENV_PATH=os.path.join(BASE_DIR,"../.env")

# ── Category taxonomy ──────────────────────────────────────────────────────────
# (parent_name, [subcategories])
CATEGORIES=[
    ("Animal Feed",[
        "Cattle & Calf Feed","Horse & Pony Feed","Sheep & Goat Feed",
        "Pig Feed","Poultry & Game Feed","Rabbit & Small Animal",
    ]),
    ("Bedding & Forage",[
        "Straw & Hay","Wood Shavings & Hemp","Rubber Matting",
    ]),
    ("Fencing & Gates",[
        "Posts & Stakes","Wire & Netting","Electric Fencing",
        "Gates & Hurdles","Fencing Accessories",
    ]),
    ("Seeds & Grass",[
        "Grass & Pasture Mixes","Wildflower & Clover",
        "Crop & Fodder Seeds","Game Cover Seeds",
    ]),
    ("Fertilisers & Chemicals",[
        "Nitrogen Fertilisers","Compound Fertilisers","Organic Fertilisers",
        "Herbicides & Weedkillers","Lime & pH Adjustment",
    ]),
    ("Tools & Equipment",[
        "Hand Tools","Stable & Yard Equipment",
        "Sprayers & Applicators","Feeding & Watering Equipment",
    ]),
    ("Veterinary Supplies",[
        "Medicines & Treatments","Wound Care & First Aid",
        "Wormers & Parasiticides","Supplements & Vitamins","Tagging & ID",
    ]),
    ("Supplements & Minerals",[
        "Licks & Blocks","Liquid Supplements","Powders & Drenches",
    ]),
    ("Clothing & PPE",[
        "Waterproofs & Outerwear","Boots & Footwear","Gloves & Hand Protection",
    ]),
    ("Pest Control",[
        "Rodent Control","Fly & Insect Control",
    ]),
    ("Water & Irrigation",[
        "Troughs & Drinkers","Hose & Fittings",
    ]),
    ("Pet & Small Animal",[]),
    ("Other",[]),
]

# ── Training supplier ──────────────────────────────────────────────────────────
TRAIN_SUPPLIER=(
    "Wynnstay Group",
    "01691 828512",
    "sales@wynnstay.co.uk",
    "Major agricultural merchant — feeds, bedding, fencing & vet supplies. (Training record — update with your actual account details)",
)

# ── Training products: (name, category, unit, cost, markup, weight_kg, volume_litres, notes) ──
TRAIN_PRODUCTS=[
    ("Horse & Pony Cubes 20kg","Horse & Pony Feed","bag",8.50,30,20.0,None,
     "Training record — safe to delete when ready. Shows price-per-kg on label."),
    ("Sheep Nuts 25kg","Sheep & Goat Feed","bag",7.20,28,25.0,None,
     "Training record — safe to delete when ready. Shows price-per-kg on label."),
    ("Fly Repellent Spray 500ml","Veterinary Supplies","each",3.80,50,None,0.5,
     "Training record — safe to delete when ready. Shows price-per-100ml on label."),
]

# ── .env generation ────────────────────────────────────────────────────────────
def ensure_env():
    if os.path.exists(ENV_PATH):
        print(f"  .env already exists ({os.path.normpath(ENV_PATH)}) — skipping.")
        return False
    key=secrets.token_hex(32)
    with open(ENV_PATH,"w") as f:
        f.write(f"SECRET_KEY={key}\n# DB_PATH=prices.db\n# PORT=5000\n")
    print(f"  .env created with fresh SECRET_KEY at {os.path.normpath(ENV_PATH)}")
    return True

# ── Settings wizard ────────────────────────────────────────────────────────────
def _ask(prompt,default):
    v=input(f"  {prompt} [{default}]: ").strip()
    return v if v else default

def configure_settings(db):
    print()
    print("─── Shop Settings ───────────────────────────────────────")
    print("  Press Enter to accept the default shown in [brackets].")
    print()
    shop_name=_ask("Shop name","My Farm Supplies")
    currency=_ask("Currency symbol","£")
    markup=_ask("Default markup %","30")
    rounding=_ask("Price rounding (none / 0.05 / 0.10 / 0.99)","none")
    review_days=_ask("'New/Updated' highlight window (days)","30")
    for k,v in [
        ("shop_name",shop_name),("currency",currency),
        ("default_markup",markup),("price_rounding",rounding),
        ("review_days",review_days),
    ]:
        db.execute("INSERT OR REPLACE INTO settings (key,value) VALUES (?,?)",(k,v))
    print()
    print(f"  ✓ Settings saved.")

# ── Category seeding ───────────────────────────────────────────────────────────
def seed_categories(db):
    added_p=added_s=0
    for parent_name,subs in CATEGORIES:
        if not db.execute("SELECT id FROM categories WHERE name=?",(parent_name,)).fetchone():
            db.execute("INSERT INTO categories (name) VALUES (?)",(parent_name,))
            added_p+=1
        parent_id=db.execute("SELECT id FROM categories WHERE name=?",(parent_name,)).fetchone()["id"]
        for sub in subs:
            if not db.execute("SELECT id FROM categories WHERE name=?",(sub,)).fetchone():
                db.execute("INSERT INTO categories (name,parent_id) VALUES (?,?)",(sub,parent_id))
                added_s+=1
    return added_p,added_s

# ── Training data ──────────────────────────────────────────────────────────────
def seed_training(db):
    name,tel,email,notes=TRAIN_SUPPLIER
    if not db.execute("SELECT id FROM suppliers WHERE name=?",(name,)).fetchone():
        db.execute("INSERT INTO suppliers (name,tel,email,notes) VALUES (?,?,?,?)",(name,tel,email,notes))
        print(f"  ✓ Training supplier added: {name}")
    else:
        print(f"  · Supplier already exists: {name}")

    today=date.today().isoformat()
    for pname,cat,unit,cost,markup,wkg,vlitres,pnotes in TRAIN_PRODUCTS:
        if db.execute("SELECT id FROM products WHERE name=? AND active=1",(pname,)).fetchone():
            print(f"  · Product already exists: {pname}")
            continue
        db.execute(
            """INSERT INTO products
               (name,category,unit,supplier_name,supplier_tel,cost_price,markup_pct,
                notes,barcode,quantity,reorder_threshold,weight_kg,volume_litres,last_updated)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (pname,cat,unit,name,tel,float(cost),float(markup),
             pnotes,"",10,2,wkg,vlitres,today)
        )
        print(f"  ✓ Training product added: {pname}")

# ── Checklist ──────────────────────────────────────────────────────────────────
def print_checklist():
    print()
    print("═"*58)
    print("  Setup complete — your next steps:")
    print("═"*58)
    print()
    print("  [ ] Start the app:  python app.py")
    print("  [ ] Log in:         username=admin  password=farm2024")
    print("  [ ] CHANGE PASSWORD immediately  (Admin → Users)")
    print("  [ ] Review settings              (Admin → Settings)")
    print("  [ ] Add your real suppliers      (Admin → Suppliers)")
    print("  [ ] Try the 3 training products — search, label, pricelist")
    print("  [ ] Delete training records when you are confident")
    print()
    print("  When ready to hand to the client:")
    print("  [ ] Run:  python reset_db.py   (wipes test data, keeps")
    print("            categories, settings & users)")
    print()

# ── Main ───────────────────────────────────────────────────────────────────────
def run():
    if not os.path.exists(DB_PATH):
        print("\nERROR: prices.db not found.")
        print("Start the app once first to create the database:\n  python app.py\n")
        return

    print()
    print("═"*58)
    print("  Farm Supplies App — Deployment Setup")
    print("═"*58)
    print()

    # .env
    print("─── Environment ─────────────────────────────────────────")
    ensure_env()

    # DB
    db=sqlite3.connect(DB_PATH)
    db.row_factory=sqlite3.Row
    db.execute("PRAGMA foreign_keys=ON")

    # Settings
    configure_settings(db)

    # Categories
    print()
    print("─── Categories ──────────────────────────────────────────")
    added_p,added_s=seed_categories(db)
    print(f"  ✓ {added_p} parent categor{'y' if added_p==1 else 'ies'} added,"
          f" {added_s} subcategor{'y' if added_s==1 else 'ies'} added.")

    # Training data
    print()
    print("─── Training Data ───────────────────────────────────────")
    seed_training(db)

    db.commit()
    db.close()

    print_checklist()

if __name__=="__main__":
    run()
