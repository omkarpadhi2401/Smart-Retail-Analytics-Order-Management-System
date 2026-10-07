"""
analytics.py — analytics & AI engine
AI-Powered Business Finance and Inventory Analysis System

Everything here is computed from the live database rows:
  finance()          monthly revenue, COGS, gross/net profit, margins, cash flow
  inventory()        stock status, inventory value, days of cover
  sales()            top / slow products, category performance, growth
  forecast()         demand forecast per product (trend regression x seasonal index)
  anomalies()        unusual expenses (robust Z-score + month-over-month spikes)
  health()           deterministic Financial Health Score (5 factors x 20 points)
  recommendations()  rule-based AI business recommendations
"""
import math
import statistics
from collections import defaultdict

import db

try:                                    # scikit-learn is used when installed;
    import numpy as np                  # a plain least-squares fit is the fallback
    from sklearn.linear_model import LinearRegression
    ML_ENGINE = "scikit-learn LinearRegression"
except Exception:                       # pragma: no cover
    LinearRegression = None
    ML_ENGINE = "least-squares regression"

MONTH_NAMES = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
PURCHASE_CAT = "Inventory Purchase"
_cache = {"version": None, "value": None}


def label(ym):
    return "%s %s" % (MONTH_NAMES[int(ym[5:7]) - 1], ym[2:4])


def next_month(ym, k=1):
    y, m = int(ym[:4]), int(ym[5:7]) + k
    y, m = y + (m - 1) // 12, (m - 1) % 12 + 1
    return "%d-%02d" % (y, m)


def pct(new, old):
    return (new - old) / old * 100 if old else 0.0


def _fit_line(ys):
    """Fit y = a + b*x on x = 0..n-1. Returns (a, b)."""
    n = len(ys)
    if n < 2:
        return (ys[0] if ys else 0.0), 0.0
    if LinearRegression is not None:
        model = LinearRegression().fit(np.arange(n).reshape(-1, 1), np.array(ys, dtype=float))
        return float(model.intercept_), float(model.coef_[0])
    mx, my = (n - 1) / 2, sum(ys) / n
    b = sum((i - mx) * (y - my) for i, y in enumerate(ys)) / sum((i - mx) ** 2 for i in range(n))
    return my - b * mx, b


# ── Data snapshot ────────────────────────────────────────────────────────────
def load():
    """Load all rows once and cache until the database changes."""
    if _cache["version"] == db.VERSION and _cache["value"] is not None:
        return _cache["value"]
    products = db.query("SELECT * FROM products ORDER BY product_id")
    lines = db.query("""SELECT o.order_id, o.order_date, o.status, o.customer_id,
                               i.product_id, i.quantity, i.unit_price, i.unit_cost
                        FROM order_items i JOIN orders o ON o.order_id = i.order_id""")
    expenses = db.query("SELECT * FROM expenses ORDER BY expense_date, expense_id")
    for p in products:
        for k in ("price", "cost_price"):
            p[k] = float(p[k])
        p["stock"], p["min_stock"] = int(p["stock"]), int(p["min_stock"])
    sold = []
    for r in lines:
        if r["status"] == "Cancelled":
            continue
        r["order_date"] = str(r["order_date"])
        r["month"] = r["order_date"][:7]
        r["quantity"] = int(r["quantity"])
        r["revenue"] = r["quantity"] * float(r["unit_price"])
        r["cost"] = r["quantity"] * float(r["unit_cost"])
        sold.append(r)
    for e in expenses:
        e["expense_date"] = str(e["expense_date"])[:10]
        e["month"] = e["expense_date"][:7]
        e["amount"] = float(e["amount"])
    months = sorted({r["month"] for r in sold})
    rev = defaultdict(float)
    for r in sold:
        rev[r["month"]] += r["revenue"]
    # A month that has only just started (e.g. the first new orders from the customer
    # panel) would distort growth, forecasts and the health score, so trailing months
    # with under 25% of a normal month's revenue are reported separately as "in progress".
    typical = statistics.median(rev.values()) if rev else 0
    partial = []
    while len(months) > 3 and rev[months[-1]] < 0.25 * typical:
        partial.insert(0, months.pop())
    live = [r for r in sold if r["month"] in partial]
    sold = [r for r in sold if r["month"] not in partial]
    d = {"products": products, "lines": sold, "expenses": expenses, "months": months,
         "last_date": max((r["order_date"][:10] for r in sold), default=""),
         "in_progress": {"months": [label(m) for m in partial], "revenue": sum(r["revenue"] for r in live),
                         "orders": len({r["order_id"] for r in live}), "units": sum(r["quantity"] for r in live)}}
    d["finance"] = _finance(d)
    d["inventory"] = _inventory(d)
    d["sales"] = _sales(d)
    d["forecasts"] = {p["product_id"]: _forecast(d, p) for p in products}
    d["anomalies"] = _anomalies(d)
    d["health"] = _health(d)
    d["recommendations"] = _recommendations(d)
    _cache.update(version=db.VERSION, value=d)
    return d


# ── Finance ──────────────────────────────────────────────────────────────────
def _finance(d):
    months = d["months"]
    rows = {m: dict(month=m, label=label(m), revenue=0.0, cogs=0.0, opex=0.0, purchases=0.0,
                    orders=set(), units=0) for m in months}
    for r in d["lines"]:
        x = rows[r["month"]]
        x["revenue"] += r["revenue"]
        x["cogs"] += r["cost"]
        x["units"] += r["quantity"]
        x["orders"].add(r["order_id"])
    by_cat = defaultdict(float)
    cat_month = defaultdict(lambda: defaultdict(float))
    for e in d["expenses"]:
        if e["month"] not in rows:
            continue
        by_cat[e["category"]] += e["amount"]
        cat_month[e["category"]][e["month"]] += e["amount"]
        rows[e["month"]]["purchases" if e["category"] == PURCHASE_CAT else "opex"] += e["amount"]
    out = []
    for m in months:
        x = rows[m]
        x["orders"] = len(x["orders"])
        x["gross"] = x["revenue"] - x["cogs"]
        x["net"] = x["gross"] - x["opex"]
        x["margin"] = x["net"] / x["revenue"] * 100 if x["revenue"] else 0
        x["gross_margin"] = x["gross"] / x["revenue"] * 100 if x["revenue"] else 0
        x["expenses"] = x["opex"] + x["purchases"]          # all money paid out
        x["inflow"] = x["revenue"]
        x["outflow"] = x["expenses"]
        x["cash"] = x["inflow"] - x["outflow"]
        out.append(x)
    cum = 0
    for i, x in enumerate(out):
        cum += x["cash"]
        x["cum_cash"] = cum
        x["growth"] = pct(x["revenue"], out[i - 1]["revenue"]) if i else 0.0
    tot = {k: sum(x[k] for x in out) for k in
           ("revenue", "cogs", "opex", "purchases", "gross", "net", "expenses", "inflow", "outflow", "cash", "orders", "units")}
    tot["margin"] = tot["net"] / tot["revenue"] * 100 if tot["revenue"] else 0
    tot["gross_margin"] = tot["gross"] / tot["revenue"] * 100 if tot["revenue"] else 0
    tot["avg_order"] = tot["revenue"] / tot["orders"] if tot["orders"] else 0
    last, prev = (out[-1], out[-2]) if len(out) > 1 else (out[-1], out[-1]) if out else ({}, {})
    q_now = sum(x["revenue"] for x in out[-3:])
    q_prev = sum(x["revenue"] for x in out[-6:-3])
    return {
        "months": out, "total": tot, "last": last, "prev": prev,
        "growth_mom": pct(last.get("revenue", 0), prev.get("revenue", 0)),
        "growth_qoq": pct(q_now, q_prev),
        "by_category": sorted(by_cat.items(), key=lambda kv: -kv[1]),
        "cat_month": {c: [cat_month[c].get(m, 0.0) for m in months] for c in cat_month},
    }


# ── Inventory ────────────────────────────────────────────────────────────────
def _inventory(d):
    last_date = d["last_date"]
    months = d["months"]
    recent = set(months[-3:])
    units, revenue, recent_units = defaultdict(int), defaultdict(float), defaultdict(int)
    for r in d["lines"]:
        units[r["product_id"]] += r["quantity"]
        revenue[r["product_id"]] += r["revenue"]
        if r["month"] in recent:
            recent_units[r["product_id"]] += r["quantity"]
    rows = []
    for p in d["products"]:
        pid = p["product_id"]
        daily = recent_units[pid] / 91.0                       # avg daily demand, last 3 months
        cover = p["stock"] / daily if daily else None
        if p["stock"] <= 0:
            status = "Out of Stock"
        elif p["stock"] <= p["min_stock"]:
            status = "Low Stock"
        elif cover is not None and cover > 120:
            status = "Overstock"
        else:
            status = "In Stock"
        rows.append(dict(p, units_sold=units[pid], sales=revenue[pid], daily=daily, cover=cover,
                         status=status, value=p["stock"] * p["cost_price"],
                         retail_value=p["stock"] * p["price"],
                         margin=(p["price"] - p["cost_price"]) / p["price"] * 100 if p["price"] else 0,
                         shortfall=max(0, p["min_stock"] - p["stock"])))
    by_cat = defaultdict(lambda: {"value": 0.0, "units": 0, "products": 0})
    for r in rows:
        c = by_cat[r["category"]]
        c["value"] += r["value"]; c["units"] += r["stock"]; c["products"] += 1
    counts = defaultdict(int)
    for r in rows:
        counts[r["status"]] += 1
    value = sum(r["value"] for r in rows)
    cogs = d["finance"]["total"]["cogs"]
    return {
        "rows": rows, "value": value, "retail_value": sum(r["retail_value"] for r in rows),
        "units": sum(r["stock"] for r in rows), "counts": dict(counts),
        "low": sorted([r for r in rows if r["status"] == "Low Stock"], key=lambda r: r["stock"] / max(r["min_stock"], 1)),
        "out": [r for r in rows if r["status"] == "Out of Stock"],
        "over": sorted([r for r in rows if r["status"] == "Overstock"], key=lambda r: -r["value"]),
        "by_category": sorted(by_cat.items(), key=lambda kv: -kv[1]["value"]),
        "turnover": cogs / value if value else 0, "last_date": last_date,
    }


# ── Sales ────────────────────────────────────────────────────────────────────
def _sales(d):
    months = d["months"]
    idx = {m: i for i, m in enumerate(months)}
    pm = {p["product_id"]: [0] * len(months) for p in d["products"]}        # units per product-month
    prev_rev, now_rev = defaultdict(int), defaultdict(int)
    cat = defaultdict(lambda: {"revenue": 0.0, "units": 0, "profit": 0.0})
    cat_month = defaultdict(lambda: [0.0] * len(months))
    pcat = {p["product_id"]: p["category"] for p in d["products"]}
    now, prev = set(months[-3:]), set(months[-6:-3])
    for r in d["lines"]:
        pid = r["product_id"]
        if pid not in pm:
            continue
        pm[pid][idx[r["month"]]] += r["quantity"]
        c = cat[pcat[pid]]
        c["revenue"] += r["revenue"]; c["units"] += r["quantity"]; c["profit"] += r["revenue"] - r["cost"]
        cat_month[pcat[pid]][idx[r["month"]]] += r["revenue"]
        if r["month"] in now:
            now_rev[pid] += r["quantity"]
        elif r["month"] in prev:
            prev_rev[pid] += r["quantity"]
    inv = {r["product_id"]: r for r in d["inventory"]["rows"]}
    prods = []
    for p in d["products"]:
        pid = p["product_id"]
        prods.append(dict(product_id=pid, name=p["name"], sku=p["sku"], category=p["category"],
                          units=inv[pid]["units_sold"], revenue=inv[pid]["sales"],
                          recent=now_rev[pid], previous=prev_rev[pid],
                          growth=pct(now_rev[pid], prev_rev[pid]), monthly=pm[pid],
                          stock=p["stock"]))
    total_rev = sum(x["revenue"] for x in prods) or 1
    for x in prods:
        x["share"] = x["revenue"] / total_rev * 100
    cats = sorted(({"category": k, **v, "share": v["revenue"] / total_rev * 100,
                    "margin": v["profit"] / v["revenue"] * 100 if v["revenue"] else 0}
                   for k, v in cat.items()), key=lambda c: -c["revenue"])
    return {
        "products": prods,
        "top": sorted(prods, key=lambda x: -x["revenue"])[:8],
        "top_units": sorted(prods, key=lambda x: -x["units"])[:8],
        "slow": sorted(prods, key=lambda x: x["recent"])[:6],
        "rising": [x for x in sorted(prods, key=lambda x: -x["growth"]) if x["growth"] >= 10][:5],
        "falling": [x for x in sorted(prods, key=lambda x: x["growth"]) if x["growth"] <= -10][:5],
        "categories": cats, "cat_month": dict(cat_month), "pm": pm,
    }


# ── Demand forecasting ───────────────────────────────────────────────────────
def _seasonal_index(d):
    """Store-wide seasonal index per calendar month (1.0 = average month),
    measured after removing the overall linear trend."""
    totals = [x["units"] for x in d["finance"]["months"]]
    a, b = _fit_line(totals)
    idx = {}
    for i, m in enumerate(d["months"]):
        trend = a + b * i
        idx[m[5:7]] = min(1.35, max(0.7, totals[i] / trend)) if trend > 0 else 1.0
    return idx


def _predict(series, seas, months, horizon):
    """Trend regression on de-seasonalised demand, then re-apply the seasonal index."""
    desea = [u / seas.get(m[5:7], 1.0) for u, m in zip(series, months)]
    a, b = _fit_line(desea)
    mean = sum(desea) / len(desea) if desea else 0
    cap = 0.06 * mean                                   # keep the trend within +/-6% of mean per month
    b = max(-cap, min(cap, b))
    a = mean - b * (len(desea) - 1) / 2
    fitted = [max(0.0, (a + b * i) * seas.get(m[5:7], 1.0)) for i, m in enumerate(months)]
    future, m = [], months[-1]
    for k in range(1, horizon + 1):
        m = next_month(m)
        future.append((m, max(0.0, (a + b * (len(months) - 1 + k)) * seas.get(m[5:7], 1.0))))
    return fitted, future, b


def _forecast(d, p, horizon=3):
    months = d["months"]
    series = d["sales"]["pm"][p["product_id"]]
    seas = _seasonal_index(d)
    fitted, future, slope = _predict(series, seas, months, horizon)

    # Back-test: train on all but the last 3 months, predict those 3, compare.
    accuracy = None
    if len(series) >= 9:
        _, test, _ = _predict(series[:-3], seas, months[:-3], 3)
        actual = series[-3:]
        if sum(actual):
            wape = sum(abs(a - f[1]) for a, f in zip(actual, test)) / sum(actual)
            accuracy = max(0.0, 1 - wape) * 100
    resid = [s - f for s, f in zip(series, fitted)]
    sigma = statistics.pstdev(resid) if len(resid) > 1 else 0.0
    safety = int(math.ceil(1.65 * sigma))                # ~95% service level
    f1 = future[0][1]
    f3 = sum(f for _, f in future)
    recommended = int(math.ceil(f1 + safety))            # cover next month + safety stock
    stock = p["stock"]
    daily = f1 / 30.0
    days_left = stock / daily if daily else None
    shortage = max(0, int(math.ceil(f1 - stock)))
    overstock = max(0, int(stock - math.ceil(f3 + safety)))
    if stock <= 0:
        risk = "Stock-out"
    elif shortage > 0:
        risk = "Shortage risk"
    elif overstock > 0:
        risk = "Overstock"
    else:
        risk = "Balanced"
    mean = sum(series) / len(series) if series else 0
    return dict(product_id=p["product_id"], name=p["name"], sku=p["sku"], category=p["category"],
                stock=stock, min_stock=p["min_stock"], cost_price=p["cost_price"],
                history=series, fitted=[round(f, 1) for f in fitted],
                future=[(m, round(f)) for m, f in future], next_month=round(f1), next_3=round(f3),
                safety=safety, recommended=recommended, reorder=max(0, recommended - stock),
                shortage=shortage, overstock=overstock, overstock_value=overstock * p["cost_price"],
                days_left=days_left, risk=risk, accuracy=accuracy,
                trend=(slope / mean * 100 if mean else 0.0))


# ── Expense anomaly detection ────────────────────────────────────────────────
def _anomalies(d):
    """Robust (median / MAD) Z-score of each expense against comparable past
    expenses, plus category month-over-month spike detection."""
    exps = [e for e in d["expenses"] if e["category"] != PURCHASE_CAT]
    groups = defaultdict(list)
    for e in exps:
        groups[(e["category"], e["description"])].append(e)
    cat_groups = defaultdict(list)
    for e in exps:
        cat_groups[e["category"]].append(e)
    found = []
    for e in exps:
        peers = groups[(e["category"], e["description"])]
        scope = "'%s' entries" % e["description"]
        if len(peers) < 6:                                # one-off item: compare with whole category
            peers, scope = cat_groups[e["category"]], "%s expenses" % e["category"]
        amounts = [x["amount"] for x in peers]
        if len(amounts) < 4:
            continue
        med = statistics.median(amounts)
        mad = statistics.median([abs(a - med) for a in amounts])
        spread = 1.4826 * mad if mad else max(0.05 * med, 1.0)
        z = (e["amount"] - med) / spread
        ratio = e["amount"] / med if med else 0
        if z >= 3.5 and ratio >= 1.5:
            sev = "High" if ratio >= 3 else "Medium"
            found.append(dict(e, kind="Unusual amount", z=z, ratio=ratio, typical=med, severity=sev,
                              excess=e["amount"] - med,
                              reason="%.1fx the typical %s (median Rs %s); robust Z-score %.1f"
                                     % (ratio, scope, format(int(med), ","), z)))
    spikes = []
    months = d["months"]
    for cat, series in d["finance"]["cat_month"].items():
        if cat == PURCHASE_CAT:
            continue
        for i in range(1, len(series)):
            base = statistics.median(series[:i] + series[i + 1:]) if len(series) > 2 else series[i - 1]
            if series[i - 1] and series[i] > series[i - 1] * 1.3 and series[i] > base * 1.3:
                change = pct(series[i], series[i - 1])
                spikes.append(dict(category=cat, month=months[i], label=label(months[i]), amount=series[i],
                                   previous=series[i - 1], change=change, typical=base,
                                   severity="High" if change >= 80 else "Medium",
                                   reason="%s spend rose %.0f%% vs %s and is %.0f%% above its typical month"
                                          % (cat, change, label(months[i - 1]), pct(series[i], base))))
    found.sort(key=lambda a: (-a["ratio"]))
    spikes.sort(key=lambda s: -s["change"])
    return {"items": found, "spikes": spikes, "ids": {a["expense_id"] for a in found},
            "excess": sum(a["excess"] for a in found), "checked": len(exps)}


# ── Financial Health Score ───────────────────────────────────────────────────
def _scale(value, zero_at, full_at, points=20.0):
    if full_at == zero_at:
        return 0.0
    return max(0.0, min(1.0, (value - zero_at) / (full_at - zero_at))) * points


def _health(d):
    f, inv = d["finance"], d["inventory"]
    tot, ms = f["total"], f["months"]
    margin = tot["margin"]
    opex_ratio = tot["opex"] / tot["revenue"] * 100 if tot["revenue"] else 100
    pos = sum(1 for x in ms if x["cash"] > 0)
    recent = ms[-3:]
    cash_ratio = sum(x["cash"] for x in recent) / sum(x["inflow"] for x in recent) * 100 if recent else 0
    growth = f["growth_qoq"]
    healthy = inv["counts"].get("In Stock", 0) / len(inv["rows"]) * 100 if inv["rows"] else 0
    turnover = inv["turnover"]
    factors = [
        dict(name="Profitability", score=_scale(margin, 0, 15),
             metric="Net profit margin %.1f%%" % margin,
             why="Full marks at a 15% net margin or better; zero at break-even."),
        dict(name="Expense Control", score=_scale(opex_ratio, 40, 20),
             metric="Operating expenses are %.1f%% of revenue" % opex_ratio,
             why="Full marks when operating costs stay at or below 20% of revenue; zero at 40%."),
        dict(name="Cash Flow", score=_scale(pos, 0, len(ms), 10) + _scale(cash_ratio, 0, 10, 10),
             metric="%d of %d months cash-positive; last-3-month net cash %.1f%% of inflow" % (pos, len(ms), cash_ratio),
             why="10 points for the share of cash-positive months, 10 for recent net cash (full at 10% of inflow)."),
        dict(name="Revenue Growth", score=_scale(growth, -10, 10),
             metric="Last 3 months vs previous 3: %+.1f%%" % growth,
             why="10 points for flat revenue; full marks at +10% growth; zero at -10%."),
        dict(name="Inventory Efficiency", score=_scale(turnover, 0, 8, 10) + _scale(healthy, 40, 90, 10),
             metric="Stock turnover %.1fx a year; %.0f%% of products at a healthy stock level" % (turnover, healthy),
             why="10 points for turnover (full at 8x a year), 10 for the share of products neither low, out nor overstocked."),
    ]
    for x in factors:
        x["score"] = round(x["score"], 1)
        x["pct"] = x["score"] / 20 * 100
        x["level"] = "good" if x["score"] >= 15 else "warn" if x["score"] >= 10 else "bad"
    score = int(round(sum(x["score"] for x in factors)))
    grade = ("Excellent" if score >= 80 else "Good" if score >= 65 else
             "Fair" if score >= 50 else "Needs Attention")
    best = max(factors, key=lambda x: x["score"])
    worst = min(factors, key=lambda x: x["score"])
    summary = ("The score is %d/100 (%s). The strongest area is %s (%s). The biggest drag is %s (%s)."
               % (score, grade, best["name"], best["metric"].lower(), worst["name"], worst["metric"].lower()))
    return {"score": score, "grade": grade, "factors": factors, "summary": summary,
            "level": "good" if score >= 65 else "warn" if score >= 50 else "bad"}


# ── AI recommendations (rule engine over the analytics above) ────────────────
def _money(v):
    v = float(v)
    if abs(v) >= 1e7:
        return "Rs %.2f Cr" % (v / 1e7)
    if abs(v) >= 1e5:
        return "Rs %.2f L" % (v / 1e5)
    return "Rs " + format(int(round(v)), ",")


def _recommendations(d):
    f, inv, s, an = d["finance"], d["inventory"], d["sales"], d["anomalies"]
    fc = d["forecasts"]
    ms = f["months"]
    last, prev = f["last"], f["prev"]
    recs = []

    def add(priority, area, title, detail, action, link):
        recs.append(dict(priority=priority, area=area, title=title, detail=detail, action=action, link=link))

    # Inventory rules
    for r in inv["out"]:
        x = fc[r["product_id"]]
        add("High", "Inventory", "%s is out of stock" % r["name"],
            "Forecast demand is %d units next month, so roughly %s of sales is at risk."
            % (x["next_month"], _money(x["next_month"] * r["price"])),
            "Raise a purchase order for about %d units with %s." % (x["recommended"], r["supplier"]), "alerts")
    urgent = sorted(fc.values(), key=lambda x: x["days_left"] if x["days_left"] is not None else 1e9)
    for x in [u for u in urgent if u["stock"] > 0 and u["shortage"] > 0][:5]:
        if x["stock"] > 0 and x["shortage"] > 0 and x["days_left"] is not None and x["days_left"] < 30:
            add("High" if x["days_left"] < 14 else "Medium", "Inventory",
                "%s may run out in about %d days" % (x["name"], round(x["days_left"])),
                "Only %d units left against a forecast of %d units next month (minimum level %d)."
                % (x["stock"], x["next_month"], x["min_stock"]),
                "Reorder about %d units to reach the recommended stock of %d." % (x["reorder"], x["recommended"]),
                "forecast")
    over = [x for x in fc.values() if x["overstock"] > 0]
    if over:
        over.sort(key=lambda x: -x["overstock_value"])
        top = over[0]
        add("Medium", "Inventory", "%s tied up in excess stock" % _money(sum(x["overstock_value"] for x in over)),
            "%d products hold more than 3 months of forecast demand. Largest: %s with %d surplus units."
            % (len(over), top["name"], top["overstock"]),
            "Pause reorders and run a clearance offer or bundle on these items.", "inventory")
    # Sales rules
    for x in s["rising"][:2]:
        add("Medium", "Sales", "%s demand is up %.0f%%" % (x["name"], x["growth"]),
            "%d units sold in the last 3 months vs %d in the 3 months before." % (x["recent"], x["previous"]),
            "Increase stock cover and give it more visibility in promotions.", "sales")
    for x in s["falling"][:2]:
        add("Low", "Sales", "%s sales are down %.0f%%" % (x["name"], abs(x["growth"])),
            "%d units in the last 3 months vs %d before; %d units are still in stock."
            % (x["recent"], x["previous"], x["stock"]),
            "Review pricing or discount the item before reordering.", "sales")
    # Expense rules
    for sp in [x for x in an["spikes"] if x["month"] == last.get("month")][:2]:
        add("High" if sp["severity"] == "High" else "Medium", "Expenses",
            "%s expenses jumped %.0f%% in %s" % (sp["category"], sp["change"], sp["label"]),
            "%s this month vs %s the month before." % (_money(sp["amount"]), _money(sp["previous"])),
            "Check whether this spend produced matching revenue before repeating it.", "anomalies")
    if len(ms) >= 6:
        o_now, o_prev = sum(x["opex"] for x in ms[-3:]), sum(x["opex"] for x in ms[-6:-3])
        og, rg = pct(o_now, o_prev), f["growth_qoq"]
        if og > rg + 1:
            add("Medium", "Expenses", "Operating expenses are growing faster than revenue",
                "Over the last 3 months operating costs changed %+.1f%% while revenue changed %+.1f%%." % (og, rg),
                "Set category budgets; marketing and operations are the main movers.", "expenses")
        else:
            add("Low", "Expenses", "Costs are growing slower than revenue",
                "Operating costs changed %+.1f%% vs revenue %+.1f%% over the last 3 months." % (og, rg),
                "Keep current cost discipline.", "expenses")
    if an["items"]:
        add("Medium", "Expenses", "%d unusual expenses detected" % len(an["items"]),
            "They total %s above their normal level. Most extreme: %s (%s)."
            % (_money(an["excess"]), an["items"][0]["description"], _money(an["items"][0]["amount"])),
            "Review each flagged entry and confirm it was approved.", "anomalies")
    # Cash-flow & profit rules
    if last:
        if last["cash"] < 0:
            add("High", "Cash Flow", "Cash flow was negative in %s (%s)" % (last["label"], _money(last["cash"])),
                "Stock purchases of %s exceeded the cost of goods sold (%s), so cash went into inventory."
                % (_money(last["purchases"]), _money(last["cogs"])),
                "Stagger supplier payments and keep a cash buffer of one month of operating costs (%s)."
                % _money(last["opex"]), "cashflow")
        elif last["cash"] > prev["cash"]:
            add("Low", "Cash Flow", "Cash flow improved in %s" % last["label"],
                "Net cash flow was %s vs %s the month before." % (_money(last["cash"]), _money(prev["cash"])),
                "Use the surplus to restock fast-moving products.", "cashflow")
        dm = last["margin"] - prev["margin"]
        if abs(dm) >= 1:
            add("Medium" if dm < 0 else "Low", "Profit",
                "Net margin %s to %.1f%% in %s" % ("fell" if dm < 0 else "rose", last["margin"], last["label"]),
                "Previous month was %.1f%%. Revenue %+.1f%%, operating expenses %+.1f%%."
                % (prev["margin"], pct(last["revenue"], prev["revenue"]), pct(last["opex"], prev["opex"])),
                "Protect margin by reviewing the largest expense changes." if dm < 0
                else "Keep the product mix that delivered this margin.", "profit")
    if s["categories"]:
        c = s["categories"][0]
        add("Low", "Sales", "%s drives %.0f%% of revenue" % (c["category"], c["share"]),
            "Category gross margin is %.1f%%." % c["margin"],
            "Prioritise stock availability in this category; avoid over-dependence by growing the next two.", "sales")
    order = {"High": 0, "Medium": 1, "Low": 2}
    recs.sort(key=lambda r: order[r["priority"]])
    return recs
