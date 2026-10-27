"""
AI-Powered Business Finance and Inventory Analysis System
Omkar Padhi | Roll No 24101C0003 | INFT-C

Run:  python app.py   ->  http://127.0.0.1:5000
Login: admin@shop.com / admin123
"""
import csv
import io
import os
from datetime import date, datetime
from functools import wraps

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

from flask import (Flask, Response, flash, jsonify, redirect, render_template, request,
                   session, url_for)
from werkzeug.security import check_password_hash, generate_password_hash

import ai_service
import analytics
import db
import seed

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "bfi-demo-secret-key")
db.init()


# ── Formatting helpers ───────────────────────────────────────────────────────
def inr(v, decimals=0):
    """Indian-style number grouping: 1234567 -> 12,34,567"""
    try:
        v = float(v)
    except (TypeError, ValueError):
        return "0"
    neg, v = v < 0, abs(v)
    whole, frac = ("%.*f" % (decimals, v)).partition(".")[::2]
    if len(whole) > 3:
        head, tail = whole[:-3], whole[-3:]
        parts = []
        while len(head) > 2:
            parts.insert(0, head[-2:])
            head = head[:-2]
        if head:
            parts.insert(0, head)
        whole = ",".join(parts) + "," + tail
    return ("-" if neg else "") + whole + ("." + frac if decimals else "")


def money(v):
    """Compact rupee amount: Rs 1.52 L / Rs 2.05 Cr"""
    v = float(v or 0)
    sign, a = ("-" if v < 0 else ""), abs(v)
    if a >= 1e7:
        return "%s₹%.2f Cr" % (sign, a / 1e7)
    if a >= 1e5:
        return "%s₹%.2f L" % (sign, a / 1e5)
    return "%s₹%s" % (sign, inr(a))


app.jinja_env.filters.update(inr=inr, money=money, month_label=analytics.label)


def login_required(f):
    @wraps(f)
    def wrapped(*a, **k):
        if "user_id" not in session:
            return redirect(url_for("login"))
        return f(*a, **k)
    return wrapped


@app.context_processor
def inject_globals():
    ctx = dict(backend=db.BACKEND, backend_note=db.NOTE, ml_engine=analytics.ML_ENGINE)
    if "user_id" in session:
        d = analytics.load()
        ctx.update(alert_count=len(d["inventory"]["low"]) + len(d["inventory"]["out"]),
                   anomaly_count=len(d["anomalies"]["items"]),
                   period="%s – %s" % (analytics.label(d["months"][0]), analytics.label(d["months"][-1]))
                   if d["months"] else "No data")
    return ctx


# ── Auth ─────────────────────────────────────────────────────────────────────
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        pw = request.form.get("password", "")
        rows = db.query("SELECT * FROM staff WHERE email = %s", (email,))
        ok = False
        if rows:
            stored = rows[0]["password"]
            ok = check_password_hash(stored, pw) if stored.startswith(("pbkdf2:", "scrypt:")) else stored == pw
        if ok:
            session.update(user_id=rows[0]["staff_id"], name=rows[0]["name"], role=rows[0]["role"])
            return redirect(url_for("dashboard"))
        flash("Invalid email or password.", "bad")
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# ── Pages ────────────────────────────────────────────────────────────────────
@app.route("/")
@login_required
def dashboard():
    d = analytics.load()
    return render_template("dashboard.html", active="dashboard", f=d["finance"], inv=d["inventory"],
                           s=d["sales"], health=d["health"], recs=d["recommendations"][:3], live=d["in_progress"])


@app.route("/profit")
@login_required
def profit():
    d = analytics.load()
    return render_template("profit.html", active="profit", f=d["finance"], s=d["sales"])


@app.route("/cashflow")
@login_required
def cashflow():
    d = analytics.load()
    f = d["finance"]
    ms = f["months"]
    recent = ms[-3:]
    avg_in = sum(x["inflow"] for x in recent) / len(recent)
    avg_out = sum(x["outflow"] for x in recent) / len(recent)
    seas = analytics._seasonal_index(d)
    proj, m, cum = [], ms[-1]["month"], ms[-1]["cum_cash"]
    for _ in range(3):                                   # simple run-rate projection
        m = analytics.next_month(m)
        inflow = avg_in * seas.get(m[5:7], 1.0)
        outflow = avg_out * (0.75 + 0.25 * seas.get(m[5:7], 1.0))
        cum += inflow - outflow
        proj.append(dict(label=analytics.label(m), inflow=inflow, outflow=outflow, cash=inflow - outflow, cum=cum))
    burn = sum(x["opex"] for x in recent) / len(recent)
    return render_template("cashflow.html", active="cashflow", f=f, proj=proj,
                           positive=sum(1 for x in ms if x["cash"] > 0), burn=burn,
                           runway=(ms[-1]["cum_cash"] / burn if burn else 0),
                           best=max(ms, key=lambda x: x["cash"]), worst=min(ms, key=lambda x: x["cash"]))


@app.route("/expenses", methods=["GET", "POST"])
@login_required
def expenses():
    if request.method == "POST":
        try:
            amount = float(request.form["amount"])
            if amount <= 0:
                raise ValueError
            db.execute("""INSERT INTO expenses (expense_date, category, description, vendor, amount, payment_method)
                          VALUES (%s, %s, %s, %s, %s, %s)""",
                       (request.form["expense_date"], request.form["category"],
                        request.form["description"].strip() or "Expense", request.form.get("vendor", "").strip(),
                        amount, request.form.get("payment_method", "Bank Transfer")))
            flash("Expense added. Analytics have been refreshed.", "good")
        except (KeyError, ValueError):
            flash("Please enter a valid date, category and amount.", "bad")
        return redirect(url_for("expenses"))
    d = analytics.load()
    cat, month = request.args.get("category", ""), request.args.get("month", "")
    q, flagged = request.args.get("q", "").strip().lower(), request.args.get("flagged", "")
    ids = d["anomalies"]["ids"]
    rows = [e for e in d["expenses"]
            if (not cat or e["category"] == cat) and (not month or e["month"] == month)
            and (not q or q in e["description"].lower() or q in (e["vendor"] or "").lower())
            and (not flagged or e["expense_id"] in ids)]
    rows = sorted(rows, key=lambda e: (e["expense_date"], e["expense_id"]), reverse=True)
    by_cat = {}
    for e in rows:
        by_cat[e["category"]] = by_cat.get(e["category"], 0) + e["amount"]
    return render_template("expenses.html", active="expenses", rows=rows, ids=ids, f=d["finance"],
                           total=sum(e["amount"] for e in rows),
                           by_cat=sorted(by_cat.items(), key=lambda kv: -kv[1]),
                           categories=seed.EXPENSE_CATEGORIES,
                           months=sorted({e["month"] for e in d["expenses"]}, reverse=True),
                           sel=dict(category=cat, month=month, q=request.args.get("q", ""), flagged=flagged),
                           an=d["anomalies"], default_date=d["last_date"] or date.today().isoformat())


@app.route("/expenses/delete/<int:eid>", methods=["POST"])
@login_required
def delete_expense(eid):
    db.execute("DELETE FROM expenses WHERE expense_id = %s", (eid,))
    flash("Expense deleted.", "good")
    return redirect(url_for("expenses"))


@app.route("/anomalies")
@login_required
def anomalies():
    d = analytics.load()
    return render_template("anomalies.html", active="anomalies", an=d["anomalies"], f=d["finance"])


@app.route("/inventory")
@login_required
def inventory():
    d = analytics.load()
    inv = d["inventory"]
    cat, status, q = request.args.get("category", ""), request.args.get("status", ""), request.args.get("q", "").strip().lower()
    rows = [r for r in inv["rows"]
            if (not cat or r["category"] == cat) and (not status or r["status"] == status)
            and (not q or q in r["name"].lower() or q in r["sku"].lower() or q in (r["supplier"] or "").lower())]
    return render_template("inventory.html", active="inventory", inv=inv, rows=rows,
                           categories=sorted({r["category"] for r in inv["rows"]}),
                           sel=dict(category=cat, status=status, q=request.args.get("q", "")))


@app.route("/inventory/restock/<int:pid>", methods=["POST"])
@login_required
def restock(pid):
    try:
        qty = int(request.form["quantity"])
        if qty <= 0:
            raise ValueError
        db.execute("UPDATE products SET stock = stock + %s WHERE product_id = %s", (qty, pid))
        flash("Stock updated: %d units received." % qty, "good")
    except (KeyError, ValueError):
        flash("Enter a positive quantity.", "bad")
    return redirect(request.referrer or url_for("inventory"))


@app.route("/inventory/add", methods=["POST"])
@login_required
def add_product():
    fm = request.form
    try:
        db.execute("""INSERT INTO products (sku, name, category, price, cost_price, stock, min_stock, supplier, description, created_at)
                      VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                   (fm["sku"].strip().upper(), fm["name"].strip(), fm["category"].strip(), float(fm["price"]),
                    float(fm["cost_price"]), int(fm["stock"]), int(fm["min_stock"]), fm.get("supplier", "").strip(),
                    "", date.today().isoformat() + " 09:00:00"))
        flash("Product added.", "good")
    except Exception:
        flash("Could not add product - check the values (SKU must be unique).", "bad")
    return redirect(url_for("inventory"))


@app.route("/alerts")
@login_required
def alerts():
    d = analytics.load()
    return render_template("alerts.html", active="alerts", inv=d["inventory"], fc=d["forecasts"])


@app.route("/sales")
@login_required
def sales():
    d = analytics.load()
    return render_template("sales.html", active="sales", s=d["sales"], f=d["finance"])


@app.route("/forecast")
@login_required
def forecast():
    d = analytics.load()
    fc = d["forecasts"]
    order = {"Stock-out": 0, "Shortage risk": 1, "Overstock": 2, "Balanced": 3}
    rows = sorted(fc.values(), key=lambda x: (order[x["risk"]], -x["next_month"]))
    pid = request.args.get("product", type=int)
    cur = fc.get(pid) or (rows[0] if rows else None)
    months = d["months"]
    labels = [analytics.label(m) for m in months] + [analytics.label(m) for m, _ in cur["future"]] if cur else []
    acc = [x["accuracy"] for x in rows if x["accuracy"] is not None]
    return render_template("forecast.html", active="forecast", rows=rows, cur=cur, labels=labels,
                           avg_acc=sum(acc) / len(acc) if acc else 0,
                           n_short=sum(1 for x in rows if x["risk"] in ("Stock-out", "Shortage risk")),
                           n_over=sum(1 for x in rows if x["risk"] == "Overstock"),
                           reorder_value=sum(x["reorder"] * x["cost_price"] for x in rows))


@app.route("/health-score")
@login_required
def health():
    d = analytics.load()
    return render_template("health.html", active="health", h=d["health"], f=d["finance"])


@app.route("/insights")
@login_required
def insights():
    d = analytics.load()
    recs = d["recommendations"]
    area = request.args.get("area", "")
    areas = sorted({r["area"] for r in recs})
    counts = {p: sum(1 for r in recs if r["priority"] == p) for p in ("High", "Medium", "Low")}
    return render_template("insights.html", active="insights", areas=areas, area=area, counts=counts,
                           recs=[r for r in recs if not area or r["area"] == area], h=d["health"],
                           ai_status=ai_service.status())


# ── AI Assistant Routes ─────────────────────────────────────────────────────
def _handle_ai(fn, *args, **kwargs):
    try:
        ai_service.check_rate(session["user_id"])
        res = fn(*args, **kwargs)
        return jsonify(res)
    except ai_service.AIError as e:
        return jsonify({"error": e.message, "code": e.code}), e.status
    except Exception as ex:
        app.logger.error("AI service error: %s", ai_service.mask(str(ex)))
        return jsonify({"error": "An unexpected error occurred. Please try again.", "code": "internal_error"}), 500


@app.route("/ai/chat", methods=["POST"])
@login_required
def ai_chat():
    data = request.get_json(silent=True) or request.form or {}
    question = data.get("question", "")
    history = data.get("history", [])
    return _handle_ai(ai_service.chat, question, history)


@app.route("/ai/summary", methods=["POST"])
@login_required
def ai_summary():
    return _handle_ai(ai_service.summary)


@app.route("/ai/recommendations", methods=["POST"])
@login_required
def ai_recommendations():
    return _handle_ai(ai_service.recommendations)


@app.route("/ai/explain/anomaly/<int:expense_id>", methods=["POST"])
@login_required
def ai_explain_anomaly(expense_id):
    return _handle_ai(ai_service.explain_anomaly, expense_id)


@app.route("/ai/explain/forecast/<int:product_id>", methods=["POST"])
@login_required
def ai_explain_forecast(product_id):
    return _handle_ai(ai_service.explain_forecast, product_id)


@app.route("/ai/explain/health", methods=["POST"])
@login_required
def ai_explain_health():
    return _handle_ai(ai_service.explain_health)


@app.route("/ai/status", methods=["GET"])
@login_required
def ai_status_route():
    try:
        return jsonify(ai_service.status())
    except ai_service.AIError as e:
        return jsonify({"error": e.message, "code": e.code}), e.status
    except Exception as ex:
        app.logger.error("AI status error: %s", ai_service.mask(str(ex)))
        return jsonify({"error": "An unexpected error occurred. Please try again.", "code": "internal_error"}), 500


@app.route("/staff")
@login_required
def staff():
    rows = db.query("SELECT staff_id, name, email, phone, role, monthly_salary, joined_at FROM staff ORDER BY staff_id")
    pay = db.query("SELECT month, SUM(amount) AS total, COUNT(*) AS n FROM salaries GROUP BY month ORDER BY month")
    return render_template("staff.html", active="staff", rows=rows, pay=pay,
                           monthly=sum(float(r["monthly_salary"]) for r in rows))



# ── Staff: customer orders ───────────────────────────────────────────────────
ORDER_STATUSES = ["Pending", "Processing", "Shipped", "Delivered", "Cancelled"]


@app.route("/orders")
@login_required
def orders():
    status = request.args.get("status", "")
    sql = """SELECT o.order_id, o.order_date, o.total_amount, o.status, o.address,
                    c.name AS customer, c.customer_type
             FROM orders o JOIN customers c ON c.customer_id = o.customer_id"""
    rows = db.query(sql + (" WHERE o.status = %s" if status else "") + " ORDER BY o.order_id DESC LIMIT 150",
                    (status,) if status else ())
    counts = {r["status"]: r["n"] for r in db.query("SELECT status, COUNT(*) AS n FROM orders GROUP BY status")}
    return render_template("orders.html", active="orders", rows=rows, counts=counts, status=status,
                           statuses=ORDER_STATUSES)


@app.route("/orders/update/<int:oid>", methods=["POST"])
@login_required
def update_order(oid):
    new = request.form.get("status")
    cur = db.query("SELECT status FROM orders WHERE order_id = %s", (oid,))
    if not cur or new not in ORDER_STATUSES:
        flash("Order not found.", "bad")
    elif cur[0]["status"] == "Cancelled":
        flash("A cancelled order cannot be reopened.", "bad")
    elif new != cur[0]["status"]:
        if new == "Cancelled":                           # put the stock back
            for it in db.query("SELECT product_id, quantity FROM order_items WHERE order_id = %s", (oid,)):
                db.execute("UPDATE products SET stock = stock + %s WHERE product_id = %s", (it["quantity"], it["product_id"]))
        db.execute("UPDATE orders SET status = %s WHERE order_id = %s", (new, oid))
        flash("Order #%d marked %s." % (oid, new), "good")
    return redirect(request.referrer or url_for("orders"))


# ── Customer panel (/shop) ───────────────────────────────────────────────────
def customer_required(f):
    @wraps(f)
    def wrapped(*a, **k):
        if "customer_id" not in session:
            return redirect(url_for("shop_login"))
        return f(*a, **k)
    return wrapped


def _cart_rows():
    cart = session.get("cart", {})
    if not cart:
        return [], 0.0
    prods = {str(p["product_id"]): p for p in db.query("SELECT * FROM products")}
    rows = []
    for pid, qty in cart.items():
        p = prods.get(pid)
        if p:
            rows.append(dict(p, qty=qty, line=qty * float(p["price"])))
    return rows, sum(r["line"] for r in rows)


@app.context_processor
def inject_cart():
    return dict(cart_count=sum(session.get("cart", {}).values()))


@app.route("/shop/login", methods=["GET", "POST"])
def shop_login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        rows = db.query("SELECT * FROM customers WHERE email = %s", (email,))
        if rows and rows[0].get("password") and check_password_hash(rows[0]["password"], request.form.get("password", "")):
            session.update(customer_id=rows[0]["customer_id"], customer_name=rows[0]["name"])
            return redirect(url_for("shop"))
        flash("Invalid email or password.", "bad")
    return render_template("shop_login.html", mode="login")


@app.route("/shop/register", methods=["GET", "POST"])
def shop_register():
    if request.method == "POST":
        fm = request.form
        name, email, pw = fm.get("name", "").strip(), fm.get("email", "").strip().lower(), fm.get("password", "")
        if not name or "@" not in email or len(pw) < 6:
            flash("Enter your name, a valid email and a password of at least 6 characters.", "bad")
        elif db.query("SELECT customer_id FROM customers WHERE email = %s", (email,)):
            flash("An account with this email already exists. Please sign in.", "bad")
        else:
            cid = db.execute("""INSERT INTO customers (name, email, phone, customer_type, city, created_at, password)
                                VALUES (%s, %s, %s, %s, %s, %s, %s)""",
                             (name, email, fm.get("phone", "").strip(), "Retail", fm.get("city", "").strip(),
                              datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                              generate_password_hash(pw, method="pbkdf2:sha256")))
            session.update(customer_id=cid, customer_name=name)
            flash("Welcome, %s! Your account is ready." % name, "good")
            return redirect(url_for("shop"))
    return render_template("shop_login.html", mode="register")


@app.route("/shop/logout")
def shop_logout():
    for k in ("customer_id", "customer_name", "cart"):
        session.pop(k, None)
    return redirect(url_for("shop_login"))


@app.route("/shop")
@customer_required
def shop():
    cat, q = request.args.get("category", ""), request.args.get("q", "").strip().lower()
    prods = db.query("SELECT * FROM products ORDER BY category, name")
    rows = [p for p in prods if (not cat or p["category"] == cat)
            and (not q or q in p["name"].lower() or q in (p["description"] or "").lower())]
    return render_template("shop.html", tab="shop", rows=rows, categories=sorted({p["category"] for p in prods}),
                           sel=dict(category=cat, q=request.args.get("q", "")))


@app.route("/shop/cart/add/<int:pid>", methods=["POST"])
@customer_required
def cart_add(pid):
    p = db.query("SELECT name, stock FROM products WHERE product_id = %s", (pid,))
    qty = max(1, request.form.get("quantity", 1, type=int) or 1)
    cart = session.get("cart", {})
    have = cart.get(str(pid), 0)
    if not p or int(p[0]["stock"]) <= 0:
        flash("That product is out of stock.", "bad")
    elif have + qty > int(p[0]["stock"]):
        flash("Only %d units of %s are available." % (int(p[0]["stock"]), p[0]["name"]), "bad")
    else:
        cart[str(pid)] = have + qty
        session["cart"] = cart
        flash("%s added to your cart." % p[0]["name"], "good")
    return redirect(request.referrer or url_for("shop"))


@app.route("/shop/cart/remove/<int:pid>", methods=["POST"])
@customer_required
def cart_remove(pid):
    cart = session.get("cart", {})
    cart.pop(str(pid), None)
    session["cart"] = cart
    return redirect(url_for("shop_cart"))


@app.route("/shop/cart", methods=["GET", "POST"])
@customer_required
def shop_cart():
    rows, total = _cart_rows()
    if request.method == "POST":
        address = request.form.get("address", "").strip()
        short = [r for r in rows if r["qty"] > int(r["stock"])]
        if not rows:
            flash("Your cart is empty.", "bad")
        elif not address:
            flash("Please enter a delivery address.", "bad")
        elif short:
            flash("Not enough stock for %s (only %d left)." % (short[0]["name"], int(short[0]["stock"])), "bad")
        else:
            oid = db.execute("""INSERT INTO orders (customer_id, total_amount, address, status, order_date)
                                VALUES (%s, %s, %s, %s, %s)""",
                             (session["customer_id"], total, address, "Pending",
                              datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
            for r in rows:
                db.execute("""INSERT INTO order_items (order_id, product_id, quantity, unit_price, unit_cost)
                              VALUES (%s, %s, %s, %s, %s)""",
                           (oid, r["product_id"], r["qty"], float(r["price"]), float(r["cost_price"])))
                db.execute("UPDATE products SET stock = stock - %s WHERE product_id = %s", (r["qty"], r["product_id"]))
            session["cart"] = {}
            flash("Order #%d placed. Thank you!" % oid, "good")
            return redirect(url_for("shop_orders"))
        return redirect(url_for("shop_cart"))
    return render_template("shop_cart.html", tab="cart", rows=rows, total=total)


@app.route("/shop/orders")
@customer_required
def shop_orders():
    orders_ = db.query("SELECT * FROM orders WHERE customer_id = %s ORDER BY order_id DESC LIMIT 50", (session["customer_id"],))
    items = {}
    if orders_:
        ids = [o["order_id"] for o in orders_]
        for it in db.query("""SELECT i.order_id, i.quantity, i.unit_price, p.name FROM order_items i
                              JOIN products p ON p.product_id = i.product_id
                              WHERE i.order_id IN (%s)""" % ", ".join(["%s"] * len(ids)), ids):
            items.setdefault(it["order_id"], []).append(it)
    return render_template("shop_orders.html", tab="orders", orders=orders_, items=items)


# ── CSV exports ──────────────────────────────────────────────────────────────
@app.route("/export/<name>.csv")
@login_required
def export(name):
    d = analytics.load()
    if name == "expenses":
        head = ["expense_id", "expense_date", "category", "description", "vendor", "amount", "payment_method"]
        rows = [[e[h] for h in head] for e in d["expenses"]]
    elif name == "inventory":
        head = ["sku", "name", "category", "stock", "min_stock", "price", "cost_price", "value", "units_sold", "sales", "supplier", "status"]
        rows = [[r[h] for h in head] for r in d["inventory"]["rows"]]
    elif name == "monthly":
        head = ["month", "revenue", "cogs", "gross", "opex", "net", "margin", "inflow", "outflow", "cash"]
        rows = [[round(x[h], 2) if isinstance(x[h], float) else x[h] for h in head] for x in d["finance"]["months"]]
    elif name == "forecast":
        head = ["sku", "name", "stock", "next_month", "next_3", "recommended", "reorder", "shortage", "overstock", "risk"]
        rows = [[x[h] for h in head] for x in d["forecasts"].values()]
    else:
        return "Unknown export", 404
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(head)
    w.writerows(rows)
    return Response(buf.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": "attachment; filename=%s.csv" % name})


@app.route("/health")
def health_check():
    return {"status": "ok", "database": db.BACKEND}


if __name__ == "__main__":
    print("\n  AI-Powered Business Finance and Inventory Analysis System")
    print("  Database: %s   |   Open http://127.0.0.1:5000" % db.BACKEND)
    print("  Staff login:    admin@shop.com / admin123")
    print("  Customer panel: http://127.0.0.1:5000/shop   (%s / %s)\n" % seed.DEMO_CUSTOMER)
    app.run(debug=os.getenv("FLASK_DEBUG") == "1", port=int(os.getenv("PORT", "5000")))
