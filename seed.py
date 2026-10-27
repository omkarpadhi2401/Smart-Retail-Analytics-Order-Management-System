"""
seed.py — business data generator
AI-Powered Business Finance and Inventory Analysis System

Generates 12 months of realistic business data (Oct 2025 – Sep 2026):
  34 products, 28 customers, 6 staff + payroll, 5,200 sales orders,
  10,400 order lines and 253 expenses across 8 categories.

Run `python seed.py` to (re)write database.sql for MySQL.
db.py also imports generate() to auto-seed an empty database.
"""
import random
import calendar
from datetime import date, datetime, timedelta

DB_NAME = "business_finance_db"
MONTHS = [(2025, 10), (2025, 11), (2025, 12)] + [(2026, m) for m in range(1, 10)]
N_ORDERS, N_LINES, N_EXPENSES = 5200, 10400, 253

# ── Schema (MySQL syntax; db.py adapts it for the SQLite fallback) ───────────
TABLES = ["customers", "staff", "salaries", "products", "orders", "order_items", "expenses"]
SCHEMA = {
    "customers": """CREATE TABLE IF NOT EXISTS customers (
    customer_id   INT AUTO_INCREMENT PRIMARY KEY,
    name          VARCHAR(100) NOT NULL,
    email         VARCHAR(100) NOT NULL UNIQUE,
    phone         VARCHAR(15),
    customer_type VARCHAR(20) DEFAULT 'Retail',
    city          VARCHAR(60),
    created_at    DATETIME,
    password      VARCHAR(255)
)""",
    "staff": """CREATE TABLE IF NOT EXISTS staff (
    staff_id   INT AUTO_INCREMENT PRIMARY KEY,
    name       VARCHAR(100) NOT NULL,
    email      VARCHAR(100) NOT NULL UNIQUE,
    password   VARCHAR(255) NOT NULL,
    phone      VARCHAR(15),
    role       VARCHAR(20) DEFAULT 'support',
    monthly_salary DECIMAL(10,2) DEFAULT 0,
    joined_at  DATETIME
)""",
    "salaries": """CREATE TABLE IF NOT EXISTS salaries (
    salary_id  INT AUTO_INCREMENT PRIMARY KEY,
    staff_id   INT NOT NULL,
    amount     DECIMAL(10,2) NOT NULL,
    month      VARCHAR(7) NOT NULL,
    paid_on    DATE,
    FOREIGN KEY (staff_id) REFERENCES staff(staff_id) ON DELETE CASCADE
)""",
    "products": """CREATE TABLE IF NOT EXISTS products (
    product_id  INT AUTO_INCREMENT PRIMARY KEY,
    sku         VARCHAR(20) NOT NULL UNIQUE,
    name        VARCHAR(150) NOT NULL,
    category    VARCHAR(80) NOT NULL,
    price       DECIMAL(10,2) NOT NULL,
    cost_price  DECIMAL(10,2) NOT NULL,
    stock       INT DEFAULT 0,
    min_stock   INT DEFAULT 10,
    supplier    VARCHAR(120),
    description VARCHAR(255),
    created_at  DATETIME
)""",
    "orders": """CREATE TABLE IF NOT EXISTS orders (
    order_id     INT AUTO_INCREMENT PRIMARY KEY,
    customer_id  INT NOT NULL,
    total_amount DECIMAL(12,2) NOT NULL,
    address      VARCHAR(255),
    status       VARCHAR(20) DEFAULT 'Pending',
    order_date   DATETIME NOT NULL,
    FOREIGN KEY (customer_id) REFERENCES customers(customer_id) ON DELETE CASCADE
)""",
    "order_items": """CREATE TABLE IF NOT EXISTS order_items (
    item_id     INT AUTO_INCREMENT PRIMARY KEY,
    order_id    INT NOT NULL,
    product_id  INT NOT NULL,
    quantity    INT NOT NULL,
    unit_price  DECIMAL(10,2) NOT NULL,
    unit_cost   DECIMAL(10,2) NOT NULL,
    FOREIGN KEY (order_id)   REFERENCES orders(order_id)     ON DELETE CASCADE,
    FOREIGN KEY (product_id) REFERENCES products(product_id) ON DELETE CASCADE
)""",
    "expenses": """CREATE TABLE IF NOT EXISTS expenses (
    expense_id     INT AUTO_INCREMENT PRIMARY KEY,
    expense_date   DATE NOT NULL,
    category       VARCHAR(40) NOT NULL,
    description    VARCHAR(200) NOT NULL,
    vendor         VARCHAR(120),
    amount         DECIMAL(12,2) NOT NULL,
    payment_method VARCHAR(30) DEFAULT 'Bank Transfer'
)""",
}
COLUMNS = {
    "customers": ["customer_id", "name", "email", "phone", "customer_type", "city", "created_at", "password"],
    "staff": ["staff_id", "name", "email", "password", "phone", "role", "monthly_salary", "joined_at"],
    "salaries": ["salary_id", "staff_id", "amount", "month", "paid_on"],
    "products": ["product_id", "sku", "name", "category", "price", "cost_price", "stock",
                 "min_stock", "supplier", "description", "created_at"],
    "orders": ["order_id", "customer_id", "total_amount", "address", "status", "order_date"],
    "order_items": ["item_id", "order_id", "product_id", "quantity", "unit_price", "unit_cost"],
    "expenses": ["expense_id", "expense_date", "category", "description", "vendor", "amount", "payment_method"],
}
EXPENSE_CATEGORIES = ["Rent", "Salaries", "Utilities", "Marketing", "Inventory Purchase",
                      "Transportation", "Operations", "Miscellaneous"]

# name, category, price, cost, stock, min_stock, supplier, description, demand weight, monthly trend
PRODUCTS = [
    # Electronics (7)
    ("Wireless Earbuds", "Electronics", 1299, 810, 140, 40, "Shenzhen Audio Imports", "Bluetooth 5.0, 24hr battery, noise cancellation", 9.0, 0.010),
    ("Smart Watch Pro", "Electronics", 4999, 3350, 46, 15, "Shenzhen Audio Imports", "AMOLED display, heart rate monitor, GPS", 4.2, 0.035),
    ("Desk Lamp LED", "Electronics", 1199, 760, 310, 20, "BrightHome Electricals", "Touch control, 3 color modes, USB charging port", 3.2, -0.050),
    ("Wireless Mouse", "Electronics", 749, 450, 8, 25, "Shenzhen Audio Imports", "2.4GHz, silent click, 12-month battery", 7.0, 0.040),
    ("Mechanical Keyboard", "Electronics", 2899, 1900, 34, 12, "Shenzhen Audio Imports", "Blue switches, RGB backlight", 2.8, 0.015),
    ("Bluetooth Speaker", "Electronics", 1899, 1210, 52, 15, "Shenzhen Audio Imports", "20W, IPX7 waterproof", 3.6, 0.000),
    ("Power Bank 20000mAh", "Electronics", 1499, 960, 0, 20, "VoltEdge Power", "22.5W fast charging, dual output", 5.0, 0.020),
    # Footwear (4)
    ("Running Shoes", "Footwear", 2499, 1560, 12, 20, "Stride Footwear Co.", "Lightweight mesh upper, cushioned sole", 5.0, 0.000),
    ("Sports Sandals", "Footwear", 1299, 800, 58, 20, "Stride Footwear Co.", "Quick-dry straps, shock absorbent", 2.8, -0.020),
    ("Formal Leather Shoes", "Footwear", 2999, 1850, 18, 20, "Stride Footwear Co.", "Classic oxford derby, genuine leather, padded insole", 3.4, 0.005),
    ("Canvas Sneakers", "Footwear", 1599, 980, 72, 25, "Stride Footwear Co.", "Lightweight lace-up sneakers, vulcanized rubber sole", 4.2, 0.010),
    # Bags (4)
    ("Casual Backpack", "Bags", 1599, 990, 64, 20, "UrbanCarry Mfg.", "30L capacity, laptop compartment, waterproof", 4.0, 0.005),
    ("Leather Wallet", "Bags", 899, 520, 9, 15, "UrbanCarry Mfg.", "Genuine leather, RFID blocking", 3.0, 0.005),
    ("Laptop Sleeve 15\"", "Bags", 699, 390, 420, 15, "UrbanCarry Mfg.", "Shock-proof neoprene", 1.6, -0.060),
    ("Gym Duffel Bag", "Bags", 1299, 780, 36, 15, "UrbanCarry Mfg.", "Waterproof fabric, shoe tunnel, 35L capacity", 3.8, 0.010),
    # Clothing (4)
    ("Cotton T-Shirt", "Clothing", 599, 330, 260, 80, "Tirupur Textiles", "100% cotton, regular fit, multiple colors", 10.0, 0.000),
    ("Formal Shirt", "Clothing", 1199, 700, 88, 30, "Tirupur Textiles", "Wrinkle-free cotton blend", 4.4, 0.000),
    ("Denim Jeans", "Clothing", 1799, 1080, 70, 25, "Tirupur Textiles", "Slim fit, stretch denim", 4.0, -0.010),
    ("Classic Polo T-Shirt", "Clothing", 899, 520, 95, 30, "Tirupur Textiles", "100% combed cotton pique, bio-washed", 5.5, 0.005),
    # Beauty (4)
    ("Face Moisturizer", "Beauty", 899, 540, 95, 30, "GlowCare Labs", "SPF 30, hydrating, dermatologist tested", 5.0, 0.012),
    ("Vitamin C Serum", "Beauty", 649, 360, 110, 30, "GlowCare Labs", "20% vitamin C, 30ml", 4.6, 0.030),
    ("Hydrating Gel Sunscreen", "Beauty", 699, 410, 85, 30, "GlowCare Labs", "SPF 50 PA+++, non-sticky water gel, 100ml", 5.4, 0.025),
    ("Clarifying Charcoal Cleanser", "Beauty", 449, 250, 115, 35, "GlowCare Labs", "Activated charcoal, deep pore cleansing, 150ml", 4.8, 0.010),
    # Sports (4)
    ("Yoga Mat", "Sports", 799, 470, 0, 15, "FitGear India", "Anti-slip, 6mm thick, eco-friendly", 3.6, 0.008),
    ("Dumbbell Set 10kg", "Sports", 1999, 1300, 26, 10, "FitGear India", "Rubber-coated, pair", 2.2, 0.000),
    ("Adjustable Resistance Bands", "Sports", 749, 420, 65, 20, "FitGear India", "5 levels with door anchor, foam handles, ankle straps", 4.2, 0.020),
    ("Badminton Racket Carbon Pro", "Sports", 1499, 890, 10, 15, "FitGear India", "High modulus carbon fiber, includes full cover", 3.5, 0.005),
    # Kitchen (4)
    ("Stainless Steel Bottle", "Kitchen", 699, 400, 150, 40, "Moradabad Steelworks", "1L, double-walled, keeps cold 24hr / hot 12hr", 6.0, 0.000),
    ("Non-stick Frying Pan", "Kitchen", 1099, 690, 40, 15, "Moradabad Steelworks", "28cm, induction base", 3.0, 0.000),
    ("Electric Kettle", "Kitchen", 1349, 860, 14, 15, "BrightHome Electricals", "1.5L, auto shut-off", 3.2, 0.010),
    ("Stainless Steel Knife Set", "Kitchen", 1199, 720, 50, 20, "Moradabad Steelworks", "5-piece chef set with acrylic rotating block", 3.2, 0.000),
    # Health (4)
    ("Protein Powder", "Health", 2199, 1480, 18, 25, "NutriMax Wellness", "1kg, 24g protein per serving, chocolate flavor", 4.4, 0.045),
    ("Multivitamin Tablets", "Health", 549, 310, 130, 40, "NutriMax Wellness", "60 tablets, daily essentials", 5.0, 0.015),
    ("Omega-3 Triple Strength", "Health", 899, 520, 90, 30, "NutriMax Wellness", "1000mg fish oil, 60 enterically coated softgels", 4.6, 0.020),
    ("Electrolyte Energy Drink Mix", "Health", 499, 280, 140, 45, "NutriMax Wellness", "Orange burst flavour, 30 sachets with B-vitamins", 5.2, 0.015),
]
CAT_CODE = {"Electronics": "ELE", "Footwear": "FTW", "Bags": "BAG", "Clothing": "CLO",
            "Beauty": "BTY", "Sports": "SPT", "Kitchen": "KIT", "Health": "HLT"}

CUSTOMERS = [  # name, type, city
    ("Aarav Sharma", "Retail", "Pune"), ("Priya Singh", "Retail", "Bengaluru"), ("Arjun Mehta", "Retail", "Mumbai"),
    ("Sneha Kulkarni", "Retail", "Pune"), ("Rahul Verma", "Retail", "Delhi"), ("Ananya Iyer", "Retail", "Chennai"),
    ("Vikram Desai", "Retail", "Ahmedabad"), ("Neha Joshi", "Retail", "Mumbai"), ("Karan Malhotra", "Retail", "Delhi"),
    ("Pooja Nair", "Retail", "Kochi"), ("Aditya Rao", "Retail", "Hyderabad"), ("Meera Shah", "Retail", "Surat"),
    ("Rohit Pawar", "Retail", "Nashik"), ("Isha Kapoor", "Retail", "Jaipur"), ("Sunil Chawla", "Retail", "Chandigarh"),
    ("Deepika Nambiar", "Retail", "Bengaluru"), ("Gaurav Singhania", "Retail", "Kolkata"), ("Tanvi Trivedi", "Retail", "Vadodara"),
    ("Rohan Banerjee", "Retail", "Kolkata"), ("Simran Batra", "Retail", "Lucknow"),
    ("Sunrise Retail Mart", "B2B", "Mumbai"), ("TechZone Distributors", "B2B", "Pune"),
    ("FitLife Gyms Pvt Ltd", "B2B", "Mumbai"), ("GreenLeaf Office Supplies", "B2B", "Thane"),
    ("Metro Corporate Gifting", "B2B", "Navi Mumbai"), ("Campus Store VJTI", "B2B", "Mumbai"),
    ("Apex Retail Chain", "B2B", "Bengaluru"), ("Zenith Health & Fitness", "B2B", "Delhi"),
]
STAFF = [  # name, email, password, role, salary
    ("Admin User", "admin@shop.com", "admin123", "admin", 55000),
    ("Riya Sharma", "riya@shop.com", "riya123", "manager", 42000),
    ("Suresh Gaikwad", "suresh@shop.com", "suresh123", "accounts", 30000),
    ("Kavita More", "kavita@shop.com", "kavita123", "sales", 24000),
    ("Imran Shaikh", "imran@shop.com", "imran123", "warehouse", 19000),
    ("Deepa Pillai", "deepa@shop.com", "deepa123", "support", 17000),
]
DEMO_CUSTOMER = ("customer@shop.com", "customer123")     # login for the customer panel
SEASON = [1.12, 1.13, 1.08, 0.94, 0.90, 0.96, 0.97, 1.00, 1.01, 0.97, 0.95, 1.01]
PURCHASE_FACTOR = [1.00, 1.01, 0.94, 0.90, 1.00, 1.00, 1.03, 0.98, 0.83, 1.00, 1.03, 1.27]


def _hash(pw):
    try:
        from werkzeug.security import generate_password_hash
        return generate_password_hash(pw, method="pbkdf2:sha256")
    except Exception:
        return pw


def generate():
    """Return {table: [row tuples]} — same output on every run (fixed seed)."""
    rng = random.Random(42)
    data = {t: [] for t in TABLES}

    for i, (n, t, c) in enumerate(CUSTOMERS, 1):
        email = n.lower().replace(" ", ".").replace(".pvt.ltd", "") + ("@gmail.com" if t == "Retail" else ".in")
        data["customers"].append((i, n, email, "90000%05d" % i, t, c, "2025-09-%02d 10:00:00" % (i % 28 + 1),
                                  _hash(DEMO_CUSTOMER[1]) if i == 1 else None))

    for i, (n, e, pw, role, sal) in enumerate(STAFF, 1):
        data["staff"].append((i, n, e, _hash(pw), "98765%05d" % i, role, sal, "2025-06-01 09:00:00"))

    counters = {}
    for i, p in enumerate(PRODUCTS, 1):
        code = CAT_CODE[p[1]]
        counters[code] = counters.get(code, 0) + 1
        data["products"].append((i, "%s-%03d" % (code, counters[code]), p[0], p[1], p[2], p[3],
                                 p[4], p[5], p[6], p[7], "2025-09-15 09:00:00"))

    # ── Orders: exact totals, festive seasonality, per-product trends ────────
    tot = sum(SEASON)
    per_month = [int(N_ORDERS * s / tot) for s in SEASON]
    per_month[0] += N_ORDERS - sum(per_month)

    slots = []                                     # (month index, datetime)
    for mi, (y, m) in enumerate(MONTHS):
        days = calendar.monthrange(y, m)[1]
        stamps = sorted(datetime(y, m, rng.randint(1, days), rng.randint(9, 20), rng.randint(0, 59))
                        for _ in range(per_month[mi]))
        slots += [(mi, s) for s in stamps]

    line_counts = [rng.choices([1, 2, 3, 4], [38, 36, 19, 7])[0] for _ in slots]
    while sum(line_counts) != N_LINES:             # nudge to the exact line total
        k = rng.randrange(len(line_counts))
        if sum(line_counts) < N_LINES and line_counts[k] < 4:
            line_counts[k] += 1
        elif sum(line_counts) > N_LINES and line_counts[k] > 1:
            line_counts[k] -= 1

    retail = [i for i, c in enumerate(CUSTOMERS, 1) if c[1] == "Retail"]
    b2b = [i for i, c in enumerate(CUSTOMERS, 1) if c[1] == "B2B"]
    item_id = 0
    cogs_month = [0.0] * 12
    for oid, ((mi, stamp), nlines) in enumerate(zip(slots, line_counts), 1):
        is_b2b = rng.random() < 0.08
        cust = rng.choice(b2b if is_b2b else retail)
        weights = [max(0.15, p[8] * (1 + p[9] * (mi - 5.5) * 2)) for p in PRODUCTS]
        chosen = set()
        while len(chosen) < nlines:
            chosen.add(rng.choices(range(len(PRODUCTS)), weights)[0])
        if stamp >= datetime(2026, 9, 27):
            status = rng.choice(["Pending", "Processing", "Shipped"])
        else:
            status = "Cancelled" if rng.random() < 0.02 else "Delivered"
        total = 0
        for pi in sorted(chosen):
            p = PRODUCTS[pi]
            qty = rng.randint(3, 7) if is_b2b else rng.choices([1, 2, 3], [70, 23, 7])[0]
            price = round(p[2] * (0.92 if is_b2b else 1.0))      # 8% trade discount for B2B
            item_id += 1
            data["order_items"].append((item_id, oid, pi + 1, qty, price, p[3]))
            total += qty * price
            if status != "Cancelled":
                cogs_month[mi] += qty * p[3]
        city = CUSTOMERS[cust - 1][2]
        data["orders"].append((oid, cust, total, "%d, Main Road, %s" % (rng.randint(1, 240), city),
                               status, stamp.strftime("%Y-%m-%d %H:%M:%S")))

    # ── Payroll + expenses ───────────────────────────────────────────────────
    exp = []                                        # (date, category, description, vendor, amount, method)
    sid = 0
    suppliers = sorted({p[6] for p in PRODUCTS})
    for mi, (y, m) in enumerate(MONTHS):
        d = lambda day: date(y, m, day).isoformat()
        festive = mi in (0, 1, 2)
        j = lambda base, pct=0.08: round(base * (1 + rng.uniform(-pct, pct)), -1)

        exp.append((d(3), "Rent", "Shop & warehouse rent", "Shree Properties", 85000, "Bank Transfer"))
        payroll = 0
        for si, s in enumerate(STAFF, 1):
            sid += 1
            data["salaries"].append((sid, si, s[4], "%d-%02d" % (y, m), d(28)))
            payroll += s[4]
        exp.append((d(28), "Salaries", "Monthly staff payroll (6 employees)", "Payroll", payroll, "Bank Transfer"))

        exp.append((d(10), "Utilities", "Electricity bill", "MSEDCL", j(19000, 0.10), "UPI"))
        exp.append((d(12), "Utilities", "Internet & phone", "Jio Business", 3499, "Auto Debit"))
        exp.append((d(14), "Utilities", "Water & housekeeping", "Society Office", j(4200), "Cash"))

        boost = 1.35 if festive else 1.0
        exp.append((d(5), "Marketing", "Social media ads", "Meta Ads", j(16000 * boost), "Credit Card"))
        exp.append((d(15), "Marketing", "Search ads", "Google Ads", j(14000 * boost), "Credit Card"))
        exp.append((d(22), "Marketing", "Flyers & local promotion", "PrintHub", j(7000), "Cash"))

        buy = cogs_month[mi] * PURCHASE_FACTOR[mi]
        shares = [0.34, 0.27, 0.22, 0.17]
        for k, day in enumerate((4, 11, 18, 25)):
            exp.append((d(day), "Inventory Purchase", "Stock replenishment PO", rng.choice(suppliers),
                        round(buy * shares[k], -2), "Bank Transfer"))
            exp.append((d(day + 1), "Transportation", "Courier & last-mile delivery" if k % 2 == 0 else "Inbound freight",
                        "BlueDart" if k % 2 == 0 else "VRL Logistics", j(7600 * SEASON[mi], 0.12), "Bank Transfer"))

        exp.append((d(8), "Operations", "Software subscriptions (billing, POS)", "Zoho", 6500, "Credit Card"))
        exp.append((d(20), "Operations", "Equipment maintenance", "CoolTech Services", j(9000, 0.15), "UPI"))
        if mi < 10:
            exp.append((d(17), "Operations", "Packaging material", "PackRight", j(5200, 0.12), "UPI"))
        exp.append((d(9), "Miscellaneous", "Office supplies & stationery", "Local vendor", j(3200, 0.15), "Cash"))
        exp.append((d(23), "Miscellaneous", "Staff refreshments", "Local vendor", j(3800, 0.15), "Cash"))

    # Planted unusual expenses for the anomaly detector
    exp.append(("2026-09-12", "Marketing", "Festive campaign - influencers & hoardings", "AdVantage Media", 96000, "Bank Transfer"))
    exp.append(("2026-07-16", "Operations", "Emergency AC compressor repair", "CoolTech Services", 48500, "UPI"))
    exp.append(("2026-02-19", "Miscellaneous", "GST late-filing penalty", "GST Department", 35000, "Bank Transfer"))
    exp = [(("2026-05-10", "Utilities", "Electricity bill", "MSEDCL", 52400, "UPI")
            if (e[0] == "2026-05-10" and e[2] == "Electricity bill") else e) for e in exp]

    exp.sort(key=lambda e: e[0])
    assert len(exp) == N_EXPENSES, len(exp)
    data["expenses"] = [(i,) + e for i, e in enumerate(exp, 1)]
    return data


def _lit(v):
    if v is None:
        return "NULL"
    if isinstance(v, (int, float)):
        return str(v)
    return "'" + str(v).replace("\\", "\\\\").replace("'", "''") + "'"


def write_sql(path="database.sql"):
    data = generate()
    out = ["-- ============================================================",
           "--  AI-Powered Business Finance and Inventory Analysis System",
           "--  MySQL 8 schema + 12 months of demo data (generated by seed.py)",
           "--  Import:  mysql -u root -p < database.sql   (or phpMyAdmin > Import)",
           "-- ============================================================", "",
           "CREATE DATABASE IF NOT EXISTS %s CHARACTER SET utf8mb4;" % DB_NAME,
           "USE %s;" % DB_NAME, "", "SET FOREIGN_KEY_CHECKS = 0;"]
    out += ["DROP TABLE IF EXISTS %s;" % t for t in reversed(TABLES)]
    out += ["SET FOREIGN_KEY_CHECKS = 1;", ""]
    for t in TABLES:
        out += [SCHEMA[t] + ";", ""]
    for t in TABLES:
        rows = data[t]
        cols = ", ".join(COLUMNS[t])
        for i in range(0, len(rows), 400):
            chunk = rows[i:i + 400]
            out.append("INSERT INTO %s (%s) VALUES\n%s;" % (
                t, cols, ",\n".join("(" + ", ".join(_lit(v) for v in r) + ")" for r in chunk)))
        out.append("")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(out))
    return {t: len(data[t]) for t in TABLES}


if __name__ == "__main__":
    print("database.sql written:", write_sql())
