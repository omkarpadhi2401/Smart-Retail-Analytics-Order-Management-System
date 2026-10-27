import os
import pytest
os.environ["FORCE_SQLITE"] = "1"

import app as flask_app
import db
import analytics

@pytest.fixture
def client():
    flask_app.app.config["TESTING"] = True
    with flask_app.app.test_client() as c:
        yield c

def login_staff(client):
    return client.post("/login", data={"email": "admin@shop.com", "password": "admin123"}, follow_redirects=True)

def login_customer(client):
    return client.post("/shop/login", data={"email": "customer@shop.com", "password": "customer123"}, follow_redirects=True)

def test_auth_pages_rendering(client):
    res = client.get("/login")
    assert res.status_code == 200
    assert b"auth-wrap" in res.data
    assert b"auth-card" in res.data
    assert b"Staff Sign In" in res.data

    res_shop = client.get("/shop/login")
    assert res_shop.status_code == 200
    assert b"auth-wrap" in res_shop.data
    assert b"auth-card" in res_shop.data
    assert b"Customer Sign In" in res_shop.data

    res_reg = client.get("/shop/register")
    assert res_reg.status_code == 200
    assert b"auth-wrap" in res_reg.data
    assert b"Create Customer Account" in res_reg.data

def test_security_redirects(client):
    # Unauthenticated access should redirect to login
    for path in ["/", "/profit", "/cashflow", "/expenses", "/inventory", "/alerts", "/sales", "/forecast"]:
        r = client.get(path)
        assert r.status_code == 302
        assert "/login" in r.headers["Location"]

    for path in ["/shop", "/shop/cart", "/shop/orders"]:
        r = client.get(path)
        assert r.status_code == 302
        assert "/shop/login" in r.headers["Location"]

def test_expense_crud_and_analytics_consistency(client):
    login_staff(client)
    
    # 1. Baseline
    d_initial = analytics.load()
    initial_exp = d_initial["finance"]["total"]["expenses"]
    
    # 2. Add Expense
    res = client.post("/expenses", data={
        "expense_date": "2026-10-28",
        "category": "Utilities",
        "description": "Test Cloud Server Hosting",
        "vendor": "CloudHost Inc",
        "amount": "15000",
        "payment_method": "Credit Card"
    }, follow_redirects=True)
    assert res.status_code == 200
    assert b"Expense added" in res.data
    
    # Verify in DB and analytics
    rows = db.query("SELECT * FROM expenses WHERE description = 'Test Cloud Server Hosting'")
    assert len(rows) == 1
    eid = rows[0]["expense_id"]
    assert float(rows[0]["amount"]) == 15000.0
    
    d_after_add = analytics.load()
    assert d_after_add["finance"]["total"]["expenses"] == pytest.approx(initial_exp + 15000.0)

    # 3. Edit Expense
    res_edit = client.post(f"/expenses/edit/{eid}", data={
        "expense_date": "2026-10-28",
        "category": "Marketing",
        "description": "Test Digital Ad Campaign",
        "vendor": "AdNetwork",
        "amount": "25000",
        "payment_method": "Bank Transfer"
    }, follow_redirects=True)
    assert res_edit.status_code == 200
    assert b"Expense updated" in res_edit.data
    
    row_edited = db.query("SELECT * FROM expenses WHERE expense_id = %s", (eid,))[0]
    assert row_edited["category"] == "Marketing"
    assert row_edited["description"] == "Test Digital Ad Campaign"
    assert float(row_edited["amount"]) == 25000.0
    
    d_after_edit = analytics.load()
    assert d_after_edit["finance"]["total"]["expenses"] == pytest.approx(initial_exp + 25000.0)

    # 4. Invalid Amount Rejection
    res_invalid = client.post(f"/expenses/edit/{eid}", data={
        "expense_date": "2026-10-28",
        "category": "Marketing",
        "description": "Test Digital Ad Campaign",
        "vendor": "AdNetwork",
        "amount": "-500",
        "payment_method": "Bank Transfer"
    }, follow_redirects=True)
    assert b"Please enter a valid date, category and positive amount" in res_invalid.data

    # 5. Delete Expense
    res_del = client.post(f"/expenses/delete/{eid}", follow_redirects=True)
    assert res_del.status_code == 200
    assert b"Expense deleted" in res_del.data
    assert len(db.query("SELECT * FROM expenses WHERE expense_id = %s", (eid,))) == 0
    
    d_after_del = analytics.load()
    assert d_after_del["finance"]["total"]["expenses"] == pytest.approx(initial_exp)

def test_order_lifecycle_and_atomic_transactions(client):
    login_customer(client)
    
    # Pick a product
    prod = db.query("SELECT * FROM products WHERE stock >= 10 ORDER BY product_id LIMIT 1")[0]
    pid = prod["product_id"]
    initial_stock = prod["stock"]
    
    # 1. Add to cart
    res_cart = client.post(f"/shop/cart/add/{pid}", data={"quantity": "3"}, follow_redirects=True)
    assert res_cart.status_code == 200
    
    # 2. Place Order
    res_order = client.post("/shop/cart", data={"address": "123 Test Street, Cyber City"}, follow_redirects=True)
    assert res_order.status_code == 200
    assert b"placed successfully" in res_order.data
    
    # Stock must be exactly initial_stock - 3
    updated_prod = db.query("SELECT stock FROM products WHERE product_id = %s", (pid,))[0]
    assert updated_prod["stock"] == initial_stock - 3
    
    # Find placed order
    order = db.query("SELECT * FROM orders WHERE customer_id = 1 ORDER BY order_id DESC LIMIT 1")[0]
    oid = order["order_id"]
    assert order["status"] == "Pending"
    assert float(order["total_amount"]) == pytest.approx(3 * float(prod["price"]))
    
    # 3. Test Insufficient Stock Rejection
    # Try ordering more than current available stock
    current_stock = updated_prod["stock"]
    client.post(f"/shop/cart/add/{pid}", data={"quantity": str(current_stock + 10)}, follow_redirects=True)
    # Even if session has manipulated quantity, checkout must verify atomically against DB
    with client.session_transaction() as sess:
        sess["cart"] = {str(pid): current_stock + 5}
    
    res_fail = client.post("/shop/cart", data={"address": "123 Test Street, Cyber City"}, follow_redirects=True)
    assert b"Insufficient stock" in res_fail.data
    
    # Stock must NOT have changed
    check_stock = db.query("SELECT stock FROM products WHERE product_id = %s", (pid,))[0]
    assert check_stock["stock"] == current_stock

    # 4. Cancel the placed order
    res_cancel = client.post(f"/shop/orders/cancel/{oid}", follow_redirects=True)
    assert res_cancel.status_code == 200
    assert b"has been cancelled and items returned to stock" in res_cancel.data
    
    # Verify order is Cancelled
    ord_check = db.query("SELECT status FROM orders WHERE order_id = %s", (oid,))[0]
    assert ord_check["status"] == "Cancelled"
    
    # Verify stock restored to initial_stock
    restored_prod = db.query("SELECT stock FROM products WHERE product_id = %s", (pid,))[0]
    assert restored_prod["stock"] == initial_stock

def test_product_management_and_delete_protection(client):
    login_staff(client)
    
    # 1. Add product
    res_add = client.post("/inventory/add", data={
        "sku": "TST-999",
        "name": "Audit Test Headphone",
        "category": "Electronics",
        "price": "2999.00",
        "cost_price": "1500.00",
        "stock": "25",
        "min_stock": "5",
        "supplier": "Test Audio Corp"
    }, follow_redirects=True)
    assert res_add.status_code == 200
    assert b"Product added" in res_add.data
    
    p = db.query("SELECT * FROM products WHERE sku = 'TST-999'")[0]
    pid = p["product_id"]
    
    # 2. Edit product
    res_edit = client.post(f"/inventory/edit/{pid}", data={
        "name": "Audit Test Headphone Pro",
        "category": "Electronics",
        "price": "3499.00",
        "cost_price": "1800.00",
        "stock": "30",
        "min_stock": "8",
        "supplier": "Test Audio Corp Ltd"
    }, follow_redirects=True)
    assert res_edit.status_code == 200
    assert b"updated" in res_edit.data
    
    p_edited = db.query("SELECT * FROM products WHERE product_id = %s", (pid,))[0]
    assert p_edited["name"] == "Audit Test Headphone Pro"
    assert float(p_edited["price"]) == 3499.00
    assert p_edited["stock"] == 30

    # 3. Delete product without orders -> succeeds
    res_del = client.post(f"/inventory/delete/{pid}", follow_redirects=True)
    assert b"deleted" in res_del.data
    assert len(db.query("SELECT * FROM products WHERE product_id = %s", (pid,))) == 0

    # 4. Attempt to delete existing product with order history -> blocked
    prod_with_orders = db.query("""SELECT p.product_id, p.name FROM products p 
                                   JOIN order_items i ON i.product_id = p.product_id 
                                   LIMIT 1""")[0]
    res_blocked = client.post(f"/inventory/delete/{prod_with_orders['product_id']}", follow_redirects=True)
    assert b"Cannot delete product" in res_blocked.data
    assert b"order history records" in res_blocked.data

def test_financial_reconciliation():
    d = analytics.load()
    fin = d["finance"]["total"]
    
    # Query database directly for non-cancelled orders
    orders_rev = db.query("""SELECT SUM(i.quantity * i.unit_price) AS rev,
                                    SUM(i.quantity * i.unit_cost) AS cogs
                             FROM order_items i 
                             JOIN orders o ON o.order_id = i.order_id
                             WHERE o.status != 'Cancelled'""")[0]
    
    db_rev = float(orders_rev["rev"] or 0)
    db_cogs = float(orders_rev["cogs"] or 0)
    
    assert fin["revenue"] == pytest.approx(db_rev, rel=1e-3)
    assert fin["cogs"] == pytest.approx(db_cogs, rel=1e-3)
    assert fin["gross"] == pytest.approx(fin["revenue"] - fin["cogs"], rel=1e-3)
    assert fin["net"] == pytest.approx(fin["gross"] - fin["opex"], rel=1e-3)
    assert fin["cash"] == pytest.approx(fin["inflow"] - fin["outflow"], rel=1e-3)
