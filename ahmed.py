import os
from flask import Flask, render_template_string, request, redirect, url_for, session, flash
from flask_mail import Mail, Message

app = Flask(__name__)
app.secret_key = "ahmed_shop_secret_key"

# --- إعدادات البريد الإلكتروني ---
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = 'aa6884981510@gmail.com'
app.config['MAIL_PASSWORD'] = 'tkca xjzc nbsh mbfj'  # كلمة مرور التطبيق الخاصة بك

mail = Mail(app)

# --- قائمة المنتجات مقسمة بالتفصيل (100 منتج) ---
CATEGORIES_DATA = {
    "Shoes": ["Running Shoes", "Casual Sneakers", "Leather Boots", "Sports Cleats", "Loafers", "Formal Shoes", "High Tops", "Slippers", "Hiking Boots", "Walking Shoes"],
    "Headphones": ["Wireless Headphones", "In-Ear Earbuds", "Noise Canceling Headset", "Gaming Headset", "Studio Headphones", "Bluetooth Earphones", "Sports Earbuds", "Neckband Earphones", "Over-Ear Headphones", "DJ Headphones"],
    "Eyewear": ["Classic Sunglasses", "Blue Light Glasses", "Aviator Sunglasses", "Polarized Glasses", "Wayfarer Frames", "Sports Sunglasses", "Round Eyeglasses", "Cat Eye Glasses", "Reading Glasses", "Vintage Frames"],
    "Watches": ["Smartwatch Series 7", "Classic Analog Watch", "Digital Chronograph", "Leather Strap Watch", "Stainless Steel Watch", "Fitness Tracker", "Luxury Diver Watch", "Minimalist Watch", "Quartz Watch", "Sports Watch"],
    "Electronics": ["Mechanical Keyboard", "Gaming Mouse", "4K Monitor", "USB-C Hub", "HD Webcam", "Power Bank 20k", "Bluetooth Speaker", "Desk Lamp", "Electric Kettle", "Smart Bulb"]
}

images_pool = [
    "https://images.unsplash.com/photo-1542291026-7eec264c27ff?w=400",
    "https://images.unsplash.com/photo-1505740420928-5e560c06d30e?w=400",
    "https://images.unsplash.com/photo-1572635196237-14b3f281503f?w=400",
    "https://images.unsplash.com/photo-1523275335684-37898b6baf30?w=400",
    "https://images.unsplash.com/photo-1583394838336-acd977736f90?w=400",
    "https://images.unsplash.com/photo-1560343090-f0409e92791a?w=400",
    "https://images.unsplash.com/photo-1526170375885-4d8ecf77b99f?w=400"
]

PRODUCTS = []
p_id = 1
for cat_name, items in CATEGORIES_DATA.items():
    for i in range(20):  # 20 منتج لكل قسم = 100 منتج
        base_item = items[i % len(items)]
        name = f"{base_item} Pro v{i+1}" if i >= len(items) else base_item
        price = round(20.0 + (p_id * 4.2) % 300, 2)
        img = images_pool[p_id % len(images_pool)]
        PRODUCTS.append({
            "id": p_id,
            "name": name,
            "price": price,
            "category": cat_name,
            "image": img
        })
        p_id += 1

# --- HTML / CSS Template ---
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Anything Shop - Amazon Style</title>
    <style>
        body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; margin:0; padding:0; background:#eaeded; }
        header { background:#131921; color:white; padding:12px 20px; display:flex; align-items:center; justify-content:space-between; position:sticky; top:0; z-index:100; }
        .logo { font-size:24px; font-weight:bold; color:#ff9900; text-decoration:none; }
        .cart-btn { background:#232f3e; color:white; padding:8px 15px; border-radius:4px; text-decoration:none; font-weight:bold; border:1px solid #d5d9d9; }
        .nav-categories { background:#232f3e; padding:10px 20px; display:flex; gap:15px; overflow-x:auto; }
        .nav-categories a { color:white; text-decoration:none; font-weight:500; font-size:14px; padding:5px 10px; border-radius:3px; }
        .nav-categories a:hover, .nav-categories a.active { background:#37475a; color:#ff9900; }
        .container { max-width:1300px; margin:20px auto; padding:0 15px; min-height:80vh; }
        .products-grid { display:grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap:20px; }
        .card { background:white; border:1px solid #e7e7e7; border-radius:8px; padding:15px; display:flex; flex-direction:column; justify-content:space-between; }
        .card img { width:100%; height:160px; object-fit:cover; border-radius:4px; margin-bottom:10px; }
        .card-title { font-size:15px; font-weight:600; color:#0f1111; margin-bottom:5px; height:40px; overflow:hidden; }
        .card-price { font-size:18px; color:#B12704; font-weight:bold; margin-bottom:10px; }
        .btn-add { background:#ffd814; border:1px solid #FCD200; border-radius:20px; padding:8px; width:100%; font-weight:bold; cursor:pointer; }
        .btn-add:hover { background:#f7ca00; }
        
        .cart-table { width:100%; background:white; border-collapse:collapse; margin-bottom:20px; border-radius:8px; overflow:hidden; }
        .cart-table th, .cart-table td { padding:12px; text-align:left; border-bottom:1px solid #ddd; }
        .checkout-form { background:white; padding:20px; border-radius:8px; max-width:500px; margin:auto; border:1px solid #ddd; }
        .form-group { margin-bottom:15px; }
        .form-group label { display:block; margin-bottom:5px; font-weight:bold; }
        .form-group input, .form-group textarea { width:100%; padding:8px; border:1px solid #ccc; border-radius:4px; box-sizing:border-box; }
        .btn-submit { background:#FF9900; color:white; border:none; padding:10px 20px; border-radius:4px; font-weight:bold; width:100%; cursor:pointer; font-size:16px; }
        .alert { background:#d4edda; color:#155724; padding:10px; border-radius:4px; margin-bottom:15px; }

        footer { background:#131921; color:white; text-align:center; padding:20px; margin-top:40px; border-top:3px solid #ff9900; }
        footer a { color:#ff9900; text-decoration:none; }
    </style>
</head>
<body>

<header>
    <a href="/" class="logo">Anything Shop</a>
    <a href="/cart" class="cart-btn">🛒 Cart ({{ cart_count }})</a>
</header>

<div class="nav-categories">
    <a href="/" class="{% if current_cat == 'All' %}active{% endif %}">All Products</a>
    {% for cat in categories_list %}
        <a href="/category/{{ cat }}" class="{% if current_cat == cat %}active{% endif %}">{{ cat }}</a>
    {% endfor %}
</div>

<div class="container">
    {% with messages = get_flashed_messages() %}
      {% if messages %}
        {% for message in messages %}
          <div class="alert">{{ message }}</div>
        {% endfor %}
      {% endif %}
    {% endwith %}

    {% if page == 'home' %}
        <h2>Category: {{ current_cat }} ({{ products|length }} Items)</h2>
        <div class="products-grid">
            {% for product in products %}
            <div class="card">
                <div>
                    <img src="{{ product.image }}" alt="{{ product.name }}">
                    <div class="card-title">{{ product.name }}</div>
                    <small style="color:#565959;">{{ product.category }}</small>
                </div>
                <div>
                    <div class="card-price">${{ product.price }}</div>
                    <form action="/add-to-cart" method="POST">
                        <input type="hidden" name="product_id" value="{{ product.id }}">
                        <button type="submit" class="btn-add">Add to Cart</button>
                    </form>
                </div>
            </div>
            {% endfor %}
        </div>

    {% elif page == 'cart' %}
        <h2>Your Shopping Cart</h2>
        {% if cart_items %}
            <table class="cart-table">
                <thead>
                    <tr><th>Product</th><th>Price</th><th>Quantity</th><th>Total</th></tr>
                </thead>
                <tbody>
                    {% for item in cart_items %}
                    <tr>
                        <td>{{ item.name }}</td>
                        <td>${{ item.price }}</td>
                        <td>{{ item.qty }}</td>
                        <td>${{ "%.2f"|format(item.price * item.qty) }}</td>
                    </tr>
                    {% endfor %}
                </tbody>
            </table>
            <h3>Total Amount: ${{ "%.2f"|format(total_price) }}</h3>
            <hr><br>
            
            <div class="checkout-form">
                <h3>Customer & Shipping Details</h3>
                <form action="/checkout" method="POST">
                    <div class="form-group">
                        <label>Full Name</label>
                        <input type="text" name="name" required>
                    </div>
                    <div class="form-group">
                        <label>Your Email (for Order Confirmation)</label>
                        <input type="email" name="customer_email" required>
                    </div>
                    <div class="form-group">
                        <label>Phone Number</label>
                        <input type="tel" name="phone" required>
                    </div>
                    <div class="form-group">
                        <label>Shipping Address</label>
                        <textarea name="address" rows="3" required></textarea>
                    </div>
                    <button type="submit" class="btn-submit">Place Order</button>
                </form>
            </div>
        {% else %}
            <p>Your cart is empty. <a href="/">Continue shopping</a></p>
        {% endif %}
    {% endif %}
</div>

<footer>
    <p>Need Support or Have Inquiries? Contact us at: <a href="mailto:aa6884981510@gmail.com">aa6884981510@gmail.com</a></p>
    <small>© 2026 Anything Shop. All rights reserved.</small>
</footer>

</body>
</html>
"""

# --- Routes ---

def get_cart_count():
    cart = session.get('cart', {})
    return sum(cart.values())

@app.route("/")
def home():
    return render_template_string(
        HTML_TEMPLATE, 
        page='home', 
        products=PRODUCTS, 
        cart_count=get_cart_count(),
        categories_list=list(CATEGORIES_DATA.keys()),
        current_cat="All"
    )

@app.route("/category/<cat_name>")
def category_view(cat_name):
    filtered_products = [p for p in PRODUCTS if p["category"] == cat_name]
    return render_template_string(
        HTML_TEMPLATE, 
        page='home', 
        products=filtered_products, 
        cart_count=get_cart_count(),
        categories_list=list(CATEGORIES_DATA.keys()),
        current_cat=cat_name
    )

@app.route("/add-to-cart", methods=["POST"])
def add_to_cart():
    p_id = str(request.form.get("product_id"))
    cart = session.get('cart', {})
    cart[p_id] = cart.get(p_id, 0) + 1
    session['cart'] = cart
    flash("Item added to cart!")
    return redirect(request.referrer or url_for('home'))

@app.route("/cart")
def view_cart():
    cart = session.get('cart', {})
    cart_items = []
    total_price = 0.0
    
    for p_id_str, qty in cart.items():
        p_id = int(p_id_str)
        product = next((p for p in PRODUCTS if p["id"] == p_id), None)
        if product:
            item_total = product["price"] * qty
            total_price += item_total
            cart_items.append({
                "name": product["name"],
                "price": product["price"],
                "qty": qty
            })
            
    return render_template_string(
        HTML_TEMPLATE, 
        page='cart', 
        cart_items=cart_items, 
        total_price=total_price, 
        cart_count=get_cart_count(),
        categories_list=list(CATEGORIES_DATA.keys()),
        current_cat="Cart"
    )

@app.route("/checkout", methods=["POST"])
def checkout():
    name = request.form.get("name")
    customer_email = request.form.get("customer_email")
    phone = request.form.get("phone")
    address = request.form.get("address")
    
    cart = session.get('cart', {})
    if not cart:
        return redirect(url_for('home'))

    # تجهيز تفاصيل الطلب
    order_details = ""
    total_amount = 0.0
    for p_id_str, qty in cart.items():
        p_id = int(p_id_str)
        product = next((p for p in PRODUCTS if p["id"] == p_id), None)
        if product:
            item_total = product["price"] * qty
            total_amount += item_total
            order_details += f"- {product['name']} (x{qty}) : ${item_total:.2f}\n"

    # 1. إيميل المتجر (لك)
    admin_body = f"""
    NEW ORDER RECEIVED!
    -------------------
    Customer Name: {name}
    Customer Email: {customer_email}
    Phone: {phone}
    Address: {address}
    
    Order Summary:
    {order_details}
    
    Total Amount: ${total_amount:.2f}
    """

    # 2. إيميل العميل (تأكيد الطلب)
    customer_body = f"""
    Hello {name},
    
    Thank you for shopping with Anything Shop!
    We have received your order and it is being processed.
    
    Your Order Details:
    {order_details}
    
    Total Paid: ${total_amount:.2f}
    Shipping Address: {address}
    
    If you have any questions, contact us at aa6884981510@gmail.com.
    """

    try:
        # إرسال إيميل لك (الأدمن)
        admin_msg = Message(
            subject=f"New Order #{session.get('cart_count', 1)} from {name}",
            sender=app.config['MAIL_USERNAME'],
            recipients=['aa6884981510@gmail.com'],
            body=admin_body
        )
        mail.send(admin_msg)

        # إرسال إيميل للعميل
        customer_msg = Message(
            subject="Order Confirmation - Anything Shop",
            sender=app.config['MAIL_USERNAME'],
            recipients=[customer_email],
            body=customer_body
        )
        mail.send(customer_msg)

        flash("Order placed successfully! Confirmation emails sent to you and the customer.")
    except Exception as e:
        flash(f"Order saved, but email failed to send: {str(e)}")

    session['cart'] = {}
    return redirect(url_for('home'))

if __name__ == "__main__":
    # تعديل الـ Port والـ Host ليتمكن Render من قراءة التطبيق بنجاح
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
