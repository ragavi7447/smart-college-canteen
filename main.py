import os
import csv
import socket
import qrcode
from io import BytesIO
from datetime import datetime
from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse, Response, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from sqlalchemy.orm import Session
from sqlalchemy import func
from database import engine, Base, SessionLocal
from models import Product, Order, OrderItem

load_dotenv()

app = FastAPI(title="Smart College Canteen")

# Enable session support for cart isolation (compatible with HTTP and HTTPS)
app.add_middleware(
    SessionMiddleware,
    secret_key=os.environ.get("SESSION_SECRET_KEY", "smart-canteen-college-2026-secret-key"),
    same_site="lax",
    https_only=os.environ.get("HTTPS_ONLY", "false").lower() == "true"
)

# Automatic HTTP to HTTPS redirection (if behind proxy) & Production Security Headers
@app.middleware("http")
async def security_and_https_middleware(request: Request, call_next):
    forwarded_proto = request.headers.get("x-forwarded-proto")
    if forwarded_proto == "http":
        url = request.url.replace(scheme="https")
        return RedirectResponse(url=str(url), status_code=301)

    response = await call_next(request)

    # Security Headers (avoid setting HSTS on localhost/127.0.0.1 to allow both HTTP and HTTPS local dev)
    host = request.url.hostname or ""
    if request.url.scheme == "https" and host not in ("localhost", "127.0.0.1"):
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains; preload"
    response.headers["X-Frame-Options"] = "SAMEORIGIN"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    return response



# Connect CSS and JavaScript static assets
app.mount("/static", StaticFiles(directory="static"), name="static")

# Create database tables if not existing
Base.metadata.create_all(bind=engine)

# Auto-seed initial canteen products if table is newly created
def auto_seed_initial_products():
    try:
        db = SessionLocal()
        if db.query(Product).count() == 0:
            default_items = [
                ("Chicken Rice", "Rice", 80),
                ("Parota", "Main Course", 25),
                ("Sambar Rice", "Rice", 50),
                ("Chilli Chicken", "Chicken", 100),
                ("Cauliflower Pakoda", "Snacks", 40),
                ("Pani Puri", "Snacks", 30),
                ("Masal Puri", "Snacks", 30),
                ("Tea", "Snacks", 15),
            ]
            for name, category, price in default_items:
                product = Product(name=name, category=category, price=price, available=True, stock=20)
                db.add(product)
            db.commit()
        db.close()
    except Exception as e:
        print(f"Auto-seed notice: {e}")

auto_seed_initial_products()

# Connect Jinja2 HTML templates
templates = Jinja2Templates(directory="templates")

# Documents storage directory
DOCS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "documents")
BILLS_DIR = os.path.join(DOCS_DIR, "bills")
CSV_PATH = os.path.join(DOCS_DIR, "order_history.csv")

os.makedirs(BILLS_DIR, exist_ok=True)


# =========================================================
# FAVICON (Fixes 404 in logs)
# =========================================================

FAVICON_SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">
  <rect width="100" height="100" rx="20" fill="#2d6a4f"/>
  <text y="70" x="15" font-size="70">🍴</text>
</svg>"""

@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    return Response(content=FAVICON_SVG, media_type="image/svg+xml")


# =========================================================
# HELPER FUNCTIONS
# =========================================================

def get_local_ip():
    """Detects local LAN IP for mobile network access."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def ensure_ssl_certificates(cert_path="cert.pem", key_path="key.pem"):
    """Generates self-signed SSL certificate if missing, supporting localhost and LAN IP."""
    if os.path.exists(cert_path) and os.path.exists(key_path):
        return cert_path, key_path

    try:
        import datetime
        import ipaddress
        from cryptography import x509
        from cryptography.x509.oid import NameOID
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.asymmetric import rsa
        from cryptography.hazmat.primitives import serialization

        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        subject = issuer = x509.Name([
            x509.NameAttribute(NameOID.COMMON_NAME, "localhost"),
        ])

        ip = get_local_ip()
        san_list = [
            x509.DNSName("localhost"),
            x509.IPAddress(ipaddress.ip_address("127.0.0.1")),
        ]
        if ip and ip != "127.0.0.1":
            try:
                san_list.append(x509.IPAddress(ipaddress.ip_address(ip)))
            except Exception:
                pass

        cert = (
            x509.CertificateBuilder()
            .subject_name(subject)
            .issuer_name(issuer)
            .public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(datetime.datetime.now(datetime.timezone.utc))
            .not_valid_after(datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=365))
            .add_extension(x509.SubjectAlternativeName(san_list), critical=False)
            .sign(key, hashes.SHA256())
        )

        with open(key_path, "wb") as f:
            f.write(key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.TraditionalOpenSSL,
                encryption_algorithm=serialization.NoEncryption(),
            ))

        with open(cert_path, "wb") as f:
            f.write(cert.public_bytes(serialization.Encoding.PEM))

        return cert_path, key_path
    except Exception as e:
        print(f"Warning: Could not generate SSL certificate: {e}")
        return None, None


def start_http_redirect_server(http_port=8080, target_port=8000):
    """Starts a background HTTP daemon that redirects any HTTP traffic to HTTPS."""
    from http.server import HTTPServer, BaseHTTPRequestHandler
    import threading

    class RedirectHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            host = self.headers.get("Host", "").split(":")[0] or "127.0.0.1"
            target_url = f"https://{host}:{target_port}{self.path}"
            self.send_response(301)
            self.send_header("Location", target_url)
            self.end_headers()

        def do_HEAD(self):
            self.do_GET()

        def log_message(self, format, *args):
            pass

    def run_server():
        try:
            server = HTTPServer(("0.0.0.0", http_port), RedirectHandler)
            server.serve_forever()
        except Exception:
            pass

    thread = threading.Thread(target=run_server, daemon=True)
    thread.start()


# Admin password protection (can be 'admin' or 'admin123')
ADMIN_PASSWORDS = {"admin", "admin123"}


def save_order_documents(order: Order, items: list):
    """Saves formatted receipt document in documents/bills/ and updates master CSV document."""
    try:
        # 1. Save individual .txt bill document
        bill_filename = f"{order.bill_no}.txt"
        bill_filepath = os.path.join(BILLS_DIR, bill_filename)

        # Extract date and time separately
        date_str = ""
        time_str = ""
        if order.order_date:
            parts = order.order_date.split(" ", 1)
            date_str = parts[0]
            time_str = parts[1] if len(parts) > 1 else ""
        if not date_str:
            date_str = datetime.now().strftime("%d-%m-%Y")
        if not time_str:
            time_str = datetime.now().strftime("%I:%M:%S %p")

        lines = [
            "=" * 60,
            "               SMART COLLEGE CANTEEN",
            "             Digital Bill Receipt Document",
            "=" * 60,
            f"Bill No        : {order.bill_no}",
            f"Date           : {date_str}",
            f"Time           : {time_str}",
            f"Customer Name  : {order.customer_name}",
            f"Payment Method : {order.payment_method}",
            f"Payment Status : {order.payment_status}",
            "-" * 60,
            f"{'ITEM NAME':<30} {'QTY':<8} {'PRICE (Rs)':<12} {'AMOUNT (Rs)':<10}",
            "-" * 60,
        ]

        item_summary_parts = []
        for item in items:
            item_name = getattr(item, "product_name", item.get("name") if isinstance(item, dict) else "")
            qty = getattr(item, "quantity", item.get("quantity") if isinstance(item, dict) else 1)
            price = getattr(item, "price", item.get("price") if isinstance(item, dict) else 0.0)
            amount = getattr(item, "amount", item.get("amount") if isinstance(item, dict) else 0.0)
            lines.append(f"{item_name:<30} {qty:<8} {price:<12.2f} {amount:<10.2f}")
            item_summary_parts.append(f"{item_name} (x{qty})")

        lines.extend([
            "-" * 60,
            f"{'TOTAL AMOUNT:':<50} Rs. {order.total:.2f}",
            "=" * 60,
            "         Thank you for ordering at College Canteen!",
            "             Please keep this receipt document.",
            "=" * 60,
        ])

        with open(bill_filepath, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))

        # 2. Append to master order_history.csv document
        file_exists = os.path.exists(CSV_PATH)
        with open(CSV_PATH, "a", newline="", encoding="utf-8") as csvfile:
            writer = csv.writer(csvfile)
            if not file_exists:
                writer.writerow([
                    "Bill No", "Customer Name", "Total (INR)",
                    "Payment Method", "Payment Status", "Order Date", "Items Purchased"
                ])
            writer.writerow([
                order.bill_no,
                order.customer_name,
                f"{order.total:.2f}",
                order.payment_method,
                order.payment_status,
                order.order_date,
                "; ".join(item_summary_parts)
            ])

    except Exception as e:
        print(f"Error saving order documents: {e}")


# =========================================================
# DYNAMIC UPI QR GENERATOR
# =========================================================

@app.get("/upi_qr")
def generate_upi_qr(amount: float = 0.0, bill_no: str = "CANTEEN"):
    """Generates standard UPI QR Code with College Canteen VPA."""
    upi_uri = (
        f"upi://pay?pa=collegecanteen@okaxis"
        f"&pn=Smart+College+Canteen"
        f"&am={amount:.2f}"
        f"&cu=INR"
        f"&tn=Bill-{bill_no}"
    )

    qr = qrcode.QRCode(
        version=1,
        box_size=6,
        border=2,
    )
    qr.add_data(upi_uri)
    qr.make(fit=True)
    img = qr.make_image(fill_color="#1b4332", back_color="white")

    buf = BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return Response(content=buf.getvalue(), media_type="image/png")


# =========================================================
# HOME & MENU
# =========================================================

@app.get("/api/status")
@app.get("/health")
def api_status():
    return {
        "status": "Smart College Canteen Running",
        "database": "Connected"
    }


@app.get("/", response_class=HTMLResponse)
@app.get("/canteen", response_class=HTMLResponse)
@app.get("/home", response_class=HTMLResponse)
def canteen_home(request: Request):
    is_admin = bool(request.session.get("is_admin", False))
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "request": request,
            "is_admin": is_admin
        }
    )



@app.get("/menu", response_class=HTMLResponse)
def menu(request: Request):
    db: Session = SessionLocal()
    try:
        products = (
            db.query(Product)
            .filter(Product.available == True)
            .order_by(Product.category, Product.name)
            .all()
        )
        cart = dict(request.session.get("cart", {}))
        cart_count = sum(cart.values())

        return templates.TemplateResponse(
            request=request,
            name="menu.html",
            context={
                "request": request,
                "products": products,
                "cart_count": cart_count
            }
        )
    finally:
        db.close()


# =========================================================
# CART OPERATIONS
# =========================================================

@app.post("/add_to_cart/{product_id}")
def add_to_cart(product_id: int, request: Request):
    db: Session = SessionLocal()
    try:
        product = (
            db.query(Product)
            .filter(Product.id == product_id)
            .first()
        )

        if not product:
            return JSONResponse(
                {"success": False, "message": "Product not found"},
                status_code=404
            )

        if not product.available or product.stock <= 0:
            return JSONResponse(
                {"success": False, "message": f"{product.name} is out of stock"},
                status_code=400
            )

        cart = dict(request.session.get("cart", {}))
        str_id = str(product_id)
        current_quantity = cart.get(str_id, 0)

        if current_quantity >= product.stock:
            return JSONResponse({
                "success": False,
                "message": f"Maximum available stock ({product.stock}) reached for {product.name}",
                "cart_count": sum(cart.values())
            })

        cart[str_id] = current_quantity + 1
        request.session["cart"] = cart
        total_items = sum(cart.values())

        return {
            "success": True,
            "message": f"{product.name} added to cart",
            "cart_count": total_items,
            "product_name": product.name
        }
    finally:
        db.close()


@app.get("/cart", response_class=HTMLResponse)
def cart(request: Request):
    cart_dict = dict(request.session.get("cart", {}))
    db: Session = SessionLocal()

    try:
        cart_products = []
        total = 0.0

        for pid_str, quantity in list(cart_dict.items()):
            try:
                pid = int(pid_str)
            except ValueError:
                continue

            product = (
                db.query(Product)
                .filter(Product.id == pid)
                .first()
            )

            if not product:
                continue

            adjusted_qty = min(quantity, product.stock)
            if adjusted_qty <= 0:
                continue

            amount = product.price * adjusted_qty
            total += amount

            cart_products.append({
                "id": product.id,
                "name": product.name,
                "price": product.price,
                "stock": product.stock,
                "quantity": adjusted_qty,
                "amount": amount
            })

        return templates.TemplateResponse(
            request=request,
            name="cart.html",
            context={
                "request": request,
                "products": cart_products,
                "total": total
            }
        )
    finally:
        db.close()


@app.post("/update_cart")
async def update_cart(request: Request):
    form = await request.form()
    product_ids = form.getlist("product_id[]")
    quantities = form.getlist("quantity[]")

    db: Session = SessionLocal()
    try:
        cart = {}
        for pid_raw, qty_raw in zip(product_ids, quantities):
            try:
                pid = int(pid_raw)
                qty = int(qty_raw)
            except ValueError:
                continue

            if qty <= 0:
                continue

            product = db.query(Product).filter(Product.id == pid).first()
            if product and product.stock > 0:
                cart[str(pid)] = min(qty, product.stock)

        request.session["cart"] = cart
        return RedirectResponse(url="/cart", status_code=303)
    finally:
        db.close()


@app.get("/remove_from_cart/{product_id}")
def remove_from_cart(product_id: int, request: Request):
    cart = dict(request.session.get("cart", {}))
    str_id = str(product_id)

    if str_id in cart:
        del cart[str_id]
        request.session["cart"] = cart

    return RedirectResponse(url="/cart", status_code=303)


@app.get("/clear_cart")
def clear_cart(request: Request):
    request.session["cart"] = {}
    return RedirectResponse(url="/cart", status_code=303)


# =========================================================
# CHECKOUT & BILL GENERATION
# =========================================================

@app.get("/checkout", response_class=HTMLResponse)
def checkout(request: Request):
    cart_dict = dict(request.session.get("cart", {}))

    if not cart_dict:
        return RedirectResponse(url="/menu", status_code=303)

    db: Session = SessionLocal()
    try:
        products = []
        total = 0.0

        for pid_str, quantity in cart_dict.items():
            try:
                pid = int(pid_str)
            except ValueError:
                continue

            product = db.query(Product).filter(Product.id == pid).first()
            if product:
                amount = product.price * quantity
                total += amount
                products.append({
                    "name": product.name,
                    "quantity": quantity,
                    "price": product.price,
                    "amount": amount
                })

        if not products:
            return RedirectResponse(url="/menu", status_code=303)

        return templates.TemplateResponse(
            request=request,
            name="checkout.html",
            context={
                "request": request,
                "products": products,
                "total": total
            }
        )
    finally:
        db.close()


@app.post("/generate_bill", response_class=HTMLResponse)
async def generate_bill(request: Request):
    form = await request.form()
    customer_name = form.get("customer_name", "College Student")
    payment_method = form.get("payment_method", "UPI")

    cart_dict = dict(request.session.get("cart", {}))
    if not cart_dict:
        return RedirectResponse(url="/menu", status_code=303)

    db: Session = SessionLocal()
    try:
        items = []
        total = 0.0

        for pid_str, quantity in cart_dict.items():
            try:
                pid = int(pid_str)
            except ValueError:
                continue

            product = db.query(Product).filter(Product.id == pid).first()
            if not product:
                return HTMLResponse(content="Product not found", status_code=404)

            if quantity > product.stock:
                return HTMLResponse(
                    content=f"Not enough stock for {product.name}. Available: {product.stock}",
                    status_code=400
                )

            amount = product.price * quantity
            total += amount
            items.append({
                "product": product,
                "name": product.name,
                "quantity": quantity,
                "price": product.price,
                "amount": amount
            })

        if not items:
            return RedirectResponse(url="/menu", status_code=303)

        # Generate unique bill identifier and timestamp
        now = datetime.now()
        timestamp = now.strftime("%Y%m%d%H%M%S")
        bill_no = f"CAN-{timestamp}"
        date_str = now.strftime("%d-%m-%Y")
        time_str = now.strftime("%I:%M:%S %p")
        order_date = f"{date_str} {time_str}"

        order = Order(
            bill_no=bill_no,
            customer_name=customer_name,
            total=total,
            payment_method=payment_method,
            payment_status="PAID",
            order_date=order_date
        )
        db.add(order)
        db.flush()

        created_items = []
        for item in items:
            order_item = OrderItem(
                order_id=order.id,
                product_name=item["name"],
                quantity=item["quantity"],
                price=item["price"],
                amount=item["amount"]
            )
            db.add(order_item)
            created_items.append(order_item)

            # Deduct stock
            item["product"].stock -= item["quantity"]
            if item["product"].stock <= 0:
                item["product"].available = False

        db.commit()

        # Save order document to documents/ folder (both .txt bill and CSV master)
        save_order_documents(order, created_items)

        # Clear session cart after successful order
        request.session["cart"] = {}

        return templates.TemplateResponse(
            request=request,
            name="bill.html",
            context={
                "request": request,
                "order": order,
                "items": created_items,
                "date_str": date_str,
                "time_str": time_str
            }
        )
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


# =========================================================
# DOCUMENT DOWNLOADS & EXPORT
# =========================================================

@app.get("/download_bill_document/{bill_no}")
def download_bill_document(bill_no: str):
    """Downloads the order receipt as a .txt document."""
    bill_filepath = os.path.join(BILLS_DIR, f"{bill_no}.txt")

    if not os.path.exists(bill_filepath):
        db: Session = SessionLocal()
        try:
            order = db.query(Order).filter(Order.bill_no == bill_no).first()
            if not order:
                return HTMLResponse("Bill document not found", status_code=404)
            items = db.query(OrderItem).filter(OrderItem.order_id == order.id).all()
            save_order_documents(order, items)
        finally:
            db.close()

    return FileResponse(
        path=bill_filepath,
        filename=f"Bill_{bill_no}.txt",
        media_type="text/plain"
    )


@app.get("/download_orders_csv")
def download_orders_csv():
    """Exports and downloads the complete order history as a CSV document."""
    if not os.path.exists(CSV_PATH):
        db: Session = SessionLocal()
        try:
            orders = db.query(Order).order_by(Order.id.asc()).all()
            with open(CSV_PATH, "w", newline="", encoding="utf-8") as csvfile:
                writer = csv.writer(csvfile)
                writer.writerow([
                    "Bill No", "Customer Name", "Total (INR)",
                    "Payment Method", "Payment Status", "Order Date", "Items Purchased"
                ])
                for ord in orders:
                    items = db.query(OrderItem).filter(OrderItem.order_id == ord.id).all()
                    item_str = "; ".join([f"{it.product_name} (x{it.quantity})" for it in items])
                    writer.writerow([
                        ord.bill_no, ord.customer_name, f"{ord.total:.2f}",
                        ord.payment_method, ord.payment_status, ord.order_date, item_str
                    ])
        finally:
            db.close()

    return FileResponse(
        path=CSV_PATH,
        filename="college_canteen_orders.csv",
        media_type="text/csv"
    )


# =========================================================
# ADMIN AUTHENTICATION
# =========================================================

@app.post("/api/verify_admin")
async def verify_admin(request: Request):
    password = ""
    try:
        body = await request.json()
        password = str(body.get("password", "")).strip()
    except Exception:
        try:
            form = await request.form()
            password = str(form.get("password", "")).strip()
        except Exception:
            password = ""

    if password in ADMIN_PASSWORDS:
        request.session["is_admin"] = True
        return {"success": True, "message": "Admin authorized successfully"}
    else:
        return JSONResponse(
            status_code=401,
            content={"success": False, "message": "Incorrect password. Please try again."}
        )


@app.get("/admin/logout")
def admin_logout(request: Request):
    request.session["is_admin"] = False
    return RedirectResponse(url="/", status_code=303)


# =========================================================
# ORDERS HISTORY
# =========================================================

@app.get("/orders", response_class=HTMLResponse)
def orders(request: Request):
    if not request.session.get("is_admin"):
        return RedirectResponse(url="/?auth_required=orders", status_code=303)

    db: Session = SessionLocal()
    try:
        order_list = db.query(Order).order_by(Order.id.desc()).all()

        return templates.TemplateResponse(
            request=request,
            name="orders.html",
            context={
                "request": request,
                "orders": order_list
            }
        )
    finally:
        db.close()


# =========================================================
# ADMIN DASHBOARD & INVENTORY
# =========================================================

@app.get("/admin", response_class=HTMLResponse)
def admin(request: Request):
    if not request.session.get("is_admin"):
        return RedirectResponse(url="/?auth_required=admin", status_code=303)

    db: Session = SessionLocal()
    try:
        products = (
            db.query(Product)
            .order_by(Product.category, Product.name)
            .all()
        )

        total_sales = (
            db.query(func.coalesce(func.sum(Order.total), 0.0))
            .filter(Order.payment_status == "PAID")
            .scalar() or 0.0
        )

        total_orders = (
            db.query(func.count(Order.id))
            .scalar() or 0
        )

        return templates.TemplateResponse(
            request=request,
            name="admin.html",
            context={
                "request": request,
                "products": products,
                "total_sales": total_sales,
                "total_orders": total_orders
            }
        )
    finally:
        db.close()


@app.post("/admin/add_product")
async def add_product(request: Request):
    if not request.session.get("is_admin"):
        return RedirectResponse(url="/?auth_required=admin", status_code=303)

    form = await request.form()
    name = form.get("name")
    category = form.get("category")
    price = float(form.get("price", 0))
    stock = int(form.get("stock", 0))

    db: Session = SessionLocal()
    try:
        product = Product(
            name=name,
            category=category,
            price=price,
            stock=stock,
            available=(stock > 0)
        )
        db.add(product)
        db.commit()
    finally:
        db.close()

    return RedirectResponse(url="/admin", status_code=303)


@app.post("/admin/update_stock/{product_id}")
async def update_stock(product_id: int, request: Request):
    if not request.session.get("is_admin"):
        return RedirectResponse(url="/?auth_required=admin", status_code=303)

    form = await request.form()
    try:
        stock = int(form.get("stock", 0))
    except ValueError:
        stock = 0

    db: Session = SessionLocal()
    try:
        product = db.query(Product).filter(Product.id == product_id).first()
        if product:
            product.stock = max(0, stock)
            product.available = product.stock > 0
            db.commit()
    finally:
        db.close()

    return RedirectResponse(url="/admin", status_code=303)


@app.get("/admin/delete_product/{product_id}")
def delete_product(product_id: int, request: Request):
    if not request.session.get("is_admin"):
        return RedirectResponse(url="/?auth_required=admin", status_code=303)

    db: Session = SessionLocal()
    try:
        product = db.query(Product).filter(Product.id == product_id).first()
        if product:
            db.delete(product)
            db.commit()
    finally:
        db.close()

    return RedirectResponse(url="/admin", status_code=303)


# =========================================================
# API - PRODUCT LIST
# =========================================================

@app.get("/api/products")
def api_products():
    db: Session = SessionLocal()
    try:
        products = db.query(Product).filter(Product.available == True).all()
        return [
            {
                "id": p.id,
                "name": p.name,
                "category": p.category,
                "price": p.price,
                "stock": p.stock,
                "available": p.available
            }
            for p in products
        ]
    finally:
        db.close()


# =========================================================
# MAIN EXECUTION
# =========================================================

if __name__ == "__main__":
    import uvicorn

    ip = get_local_ip()
    cert_file, key_file = ensure_ssl_certificates()

    # Start automatic HTTP redirect daemon on port 8080 (redirects to https://...:8000)
    start_http_redirect_server(http_port=8080, target_port=8000)

    ssl_kwargs = {}
    if cert_file and key_file and os.path.exists(cert_file) and os.path.exists(key_file):
        ssl_kwargs = {
            "ssl_certfile": cert_file,
            "ssl_keyfile": key_file,
        }
        scheme = "https"
    else:
        scheme = "http"

    print("")
    print("=" * 60)
    print(f"       SMART COLLEGE CANTEEN SYSTEM ({scheme.upper()})")
    print("=" * 60)
    print("")
    print(f"Secure URL (HTTPS):  {scheme}://127.0.0.1:8000")
    print(f"Localhost (HTTPS):   {scheme}://localhost:8000")
    print(f"Mobile / Wi-Fi URL:  {scheme}://{ip}:8000")
    print(f"HTTP Redirect URL:   http://127.0.0.1:8080  --> Auto redirects to HTTPS")
    print(f"Interactive Docs:    {scheme}://127.0.0.1:8000/docs")
    print("=" * 60)
    print("")

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        **ssl_kwargs
    )