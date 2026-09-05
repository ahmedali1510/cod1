import os
import json
import requests
import hmac
import hashlib
from datetime import datetime
from dotenv import load_dotenv
from flask import Flask, render_template_string, request, redirect, url_for, session, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from authlib.integrations.flask_client import OAuth

# تحميل متغيرات البيئة من ملف .env
load_dotenv()

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "ahmed_shop_demo_secret_key_2026")

# --- إعدادات قاعدة البيانات ---
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///shop_demo.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

# --- إعدادات Google OAuth من ملف .env ---
app.config['GOOGLE_CLIENT_ID'] = os.environ.get("GOOGLE_CLIENT_ID")
app.config['GOOGLE_CLIENT_SECRET'] = os.environ.get("GOOGLE_CLIENT_SECRET")

oauth = OAuth(app)
google = oauth.register(
    name='google',
    client_id=app.config['GOOGLE_CLIENT_ID'],
    client_secret=app.config['GOOGLE_CLIENT_SECRET'],
    server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
    client_kwargs={'scope': 'openid email profile'}
)

# --- إعدادات Paymob من ملف .env ---
PAYMOB_API_KEY = os.environ.get("PAYMOB_API_KEY")
PAYMOB_INTEGRATION_ID = os.environ.get("PAYMOB_INTEGRATION_ID")
PAYMOB_IFRAME_ID = os.environ.get("PAYMOB_IFRAME_ID")
PAYMOB_HMAC_KEY = os.environ.get("PAYMOB_HMAC_KEY")

# --- نماذج قاعدة البيانات (Models) ---
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=True)
    phone = db.Column(db.String(20), nullable=True)
    age = db.Column(db.Integer, nullable=True)
    avatar_url = db.Column(db.String(500), nullable=True, default="https://via.placeholder.com/150")
    is_admin = db.Column(db.Boolean, default=False)
    auth_provider = db.Column(db.String(50), default='local')
    orders = db.relationship('Order', backref='customer', lazy=True)

class Product(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    price = db.Column(db.Float, nullable=False)
    category = db.Column(db.String(100), nullable=False)
    image = db.Column(db.String(500), nullable=False)

class SiteSettings(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    header_color = db.Column(db.String(20), default='#131921')
    primary_color = db.Column(db.String(20), default='#ff9900')
    price_color = db.Column(db.String(20), default='#B12704')
    bg_color = db.Column(db.String(20), default='#eaeded')
    text_color = db.Column(db.String(20), default='#0f1111')
    font_size = db.Column(db.Integer, default=14)
    shipping_fee = db.Column(db.Float, default=50.0)

class Order(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    phone = db.Column(db.String(20), nullable=False)
    address = db.Column(db.Text, nullable=False)
    payment_method = db.Column(db.String(50), nullable=False)
    payment_status = db.Column(db.String(50), default='Pending') # Pending, Paid, Failed
    paymob_order_id = db.Column(db.String(100), nullable=True)
    
    items_price = db.Column(db.Float, nullable=False)
    shipping_fee = db.Column(db.Float, nullable=False, default=50.0)
    total_price = db.Column(db.Float, nullable=False)
    items_json = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# --- HTML / CSS Template ---
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
    <meta charset="UTF-8">
    <title>Anything Shop - متجر احترافي</title>
    <style>
        :root {
            --header-bg: {{ settings.header_color }};
            --primary-color: {{ settings.primary_color }};
            --price-color: {{ settings.price_color }};
            --bg-color: {{ settings.bg_color }};
            --text-color: {{ settings.text_color }};
            --font-size: {{ settings.font_size }}px;
        }
        body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; margin:0; padding:0; background: var(--bg-color); color: var(--text-color); font-size: var(--font-size); text-align:right; }
        header { background: var(--header-bg); color:white; padding:12px 20px; display:flex; align-items:center; justify-content:space-between; position:sticky; top:0; z-index:100; gap:15px; }
        .logo { font-size:24px; font-weight:bold; color: var(--primary-color); text-decoration:none; white-space:nowrap; }
        .search-bar { flex-grow:1; max-width:600px; display:flex; }
        .search-bar input { width:100%; padding:9px 12px; border:none; border-radius:0 4px 4px 0; font-size:14px; outline:none; }
        .search-bar button { background: var(--primary-color); border:none; padding:9px 15px; border-radius:4px 0 0 4px; cursor:pointer; font-weight:bold; }
        .nav-right { display:flex; align-items:center; gap:12px; white-space:nowrap; }
        .nav-btn { background:#232f3e; color:white; padding:8px 15px; border-radius:4px; text-decoration:none; font-weight:bold; border:1px solid #d5d9d9; }
        .admin-btn { background: var(--primary-color); color:black; }
        .nav-categories { background:#232f3e; padding:10px 20px; display:flex; gap:15px; overflow-x:auto; }
        .nav-categories a { color:white; text-decoration:none; font-weight:500; font-size:14px; padding:5px 10px; border-radius:3px; }
        .nav-categories a:hover, .nav-categories a.active { background:#37475a; color: var(--primary-color); }
        .container { max-width:1300px; margin:20px auto; padding:0 15px; min-height:80vh; }
        .products-grid { display:grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap:20px; }
        .card { background:white; border:1px solid #e7e7e7; border-radius:8px; padding:15px; display:flex; flex-direction:column; justify-content:space-between; color: #0f1111; }
        .card img { width:100%; height:160px; object-fit:cover; border-radius:4px; margin-bottom:10px; }
        .card-title { font-size:15px; font-weight:600; margin-bottom:5px; height:40px; overflow:hidden; }
        .card-price { font-size:18px; color: var(--price-color); font-weight:bold; margin-bottom:10px; }
        .btn-add { background:#ffd814; border:1px solid #FCD200; border-radius:20px; padding:8px; width:100%; font-weight:bold; cursor:pointer; }
        .btn-add:hover { background:#f7ca00; }
        
        .cart-table, .orders-table, .admin-table { width:100%; background:white; color:#333; border-collapse:collapse; margin-bottom:20px; border-radius:8px; overflow:hidden; }
        .cart-table th, .cart-table td, .orders-table th, .orders-table td, .admin-table th, .admin-table td { padding:12px; text-align:right; border-bottom:1px solid #ddd; }
        .checkout-form, .auth-form, .admin-card { background:white; color:#333; padding:25px; border-radius:8px; margin-bottom:25px; border:1px solid #ddd; box-shadow:0 2px 5px rgba(0,0,0,0.1); }
        .form-group { margin-bottom:15px; }
        .form-group label { display:block; margin-bottom:5px; font-weight:bold; }
        .form-group input, .form-group textarea, .form-group select { width:100%; padding:10px; border:1px solid #ccc; border-radius:4px; box-sizing:border-box; }
        .btn-submit { background: var(--primary-color); color:black; border:none; padding:10px 20px; border-radius:4px; font-weight:bold; width:100%; cursor:pointer; font-size:16px; }
        .btn-danger { background:#dc3545; color:white; padding:6px 12px; border:none; border-radius:4px; cursor:pointer; text-decoration:none; font-size:12px; }
        .btn-edit { background:#ffc107; color:black; padding:6px 12px; border:none; border-radius:4px; cursor:pointer; text-decoration:none; font-size:12px; margin-left:5px; }
        
        .btn-social { display:flex; align-items:center; justify-content:center; gap:10px; padding:10px; border-radius:4px; text-decoration:none; font-weight:bold; margin-top:10px; border:1px solid #ccc; background:white; color:#333; }
        .btn-social img { width:20px; height:20px; }
        .alert { background:#d4edda; color:#155724; padding:10px; border-radius:4px; margin-bottom:15px; }
        .status-paid { color:green; font-weight:bold; }
        .status-pending { color:orange; font-weight:bold; }
        .admin-grid { display:grid; grid-template-columns: 1fr 1fr; gap:20px; }
        @media(max-width: 768px) { .admin-grid { grid-template-columns: 1fr; } }
        footer { background: var(--header-bg); color:white; text-align:center; padding:20px; margin-top:40px; border-top:3px solid var(--primary-color); }
    </style>
</head>
<body>

<header>
    <a href="/" class="logo">Anything Shop</a>
    
    <form action="/search" method="GET" class="search-bar">
        <input type="text" name="q" placeholder="ابحث عن منتج (مثلاً: لبانة، إيربودز...)" value="{{ search_query or '' }}">
        <button type="submit">بحث 🔍</button>
    </form>

    <div class="nav-right">
        {% if current_user.is_authenticated %}
            {% if current_user.is_admin %}
                <a href="/admin" class="nav-btn admin-btn">⚙️ لوحة الأدمن</a>
            {% endif %}
            <span>أهلاً، <strong>{{ current_user.name }}</strong></span>
            <a href="/orders" class="nav-btn">📦 طلباتي</a>
            <a href="/logout" class="nav-btn">تسجيل خروج</a>
        {% else %}
            <a href="/login" class="nav-btn">تسجيل الدخول</a>
            <a href="/register" class="nav-btn">حساب جديد</a>
        {% endif %}
        <a href="/cart" class="nav-btn">🛒 السلة ({{ cart_count }})</a>
    </div>
</header>

<div class="nav-categories">
    <a href="/" class="{% if current_cat == 'All' %}active{% endif %}">كل المنتجات</a>
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

    {% if page == 'home' or page == 'search' or page == 'category' %}
        {% if page == 'search' %}
            <h2>نتائج البحث عن: "{{ search_query }}"</h2>
        {% elif page == 'category' %}
            <h2>منتجات قسم: {{ current_cat }}</h2>
        {% else %}
            <h2>المنتجات المتاحة</h2>
        {% endif %}
        
        {% if products %}
            <div class="products-grid">
                {% for product in products %}
                <div class="card">
                    <div>
                        <img src="{{ product.image }}" alt="{{ product.name }}">
                        <div class="card-title">{{ product.name }}</div>
                        <small style="color:#565959;">{{ product.category }}</small>
                    </div>
                    <div>
                        <div class="card-price">{{ product.price }} ج.م</div>
                        <form action="/add-to-cart" method="POST">
                            <input type="hidden" name="product_id" value="{{ product.id }}">
                            <button type="submit" class="btn-add">أضف إلى السلة</button>
                        </form>
                    </div>
                </div>
                {% endfor %}
            </div>
        {% else %}
            <p style="font-size:18px;">لم يتم العثور على منتجات.</p>
        {% endif %}

    {% elif page == 'cart' %}
        <h2>سلة التسوق</h2>
        {% if cart_items %}
            <table class="cart-table">
                <thead>
                    <tr><th>المنتج</th><th>السعر</th><th>الكمية</th><th>الإجمالي</th></tr>
                </thead>
                <tbody>
                    {% for item in cart_items %}
                    <tr>
                        <td>{{ item.name }}</td>
                        <td>{{ item.price }} ج.م</td>
                        <td>{{ item.qty }}</td>
                        <td>{{ "%.2f"|format(item.price * item.qty) }} ج.م</td>
                    </tr>
                    {% endfor %}
                </tbody>
            </table>
            <div style="text-align:left; background:white; color:#333; padding:15px; border-radius:8px; margin-bottom:20px;">
                <p>إجمالي المنتجات: <strong>{{ "%.2f"|format(total_price) }} ج.م</strong></p>
                <p>مصاريف الشحن: <strong>{{ "%.2f"|format(settings.shipping_fee) }} ج.م</strong></p>
                <h3 style="color: var(--price-color);">الإجمالي: {{ "%.2f"|format(total_price + settings.shipping_fee) }} ج.م</h3>
            </div>
            
            <div class="checkout-form">
                <h3>تفاصيل الشحن والتسليم</h3>
                <form action="/checkout" method="POST">
                    <div class="form-group">
                        <label>رقم الهاتف للتواصل</label>
                        <input type="tel" name="phone" value="{{ current_user.phone or '' }}" required placeholder="01xxxxxxxxx">
                    </div>
                    <div class="form-group">
                        <label>عنوان التوصيل بالكامل</label>
                        <textarea name="address" rows="2" required placeholder="المحافظة - المدينة - الشارع"></textarea>
                    </div>
                    
                    <div class="form-group">
                        <label>طريقة الدفع</label>
                        <select name="payment_method" required>
                            <option value="Cash">الدفع عند الاستلام (كاش)</option>
                            <option value="Paymob">الدفع الإلكتروني الآمن عبر Paymob (فيزا / محفظة إلكترونية)</option>
                        </select>
                    </div>

                    <button type="submit" class="btn-submit">تأكيد ومتابعة الطلب</button>
                </form>
            </div>
        {% else %}
            <p>سلة التسوق فارغة حالياً.</p>
        {% endif %}

    {% elif page == 'orders' %}
        <h2>طلباتي</h2>
        {% for order in orders %}
            <div style="background:white; color:#333; padding:15px; border-radius:8px; margin-bottom:20px; border:1px solid #ccc;">
                <h4>طلب رقم #{{ order.id }} - {{ order.created_at.strftime('%Y-%m-%d %H:%M') }}</h4>
                <p><strong>حالة الدفع:</strong> <span class="{% if order.payment_status == 'Paid' %}status-paid{% else %}status-pending{% endif %}">{{ order.payment_status }}</span></p>
                <p><strong>طريقة الدفع:</strong> {{ order.payment_method }}</p>
                <p><strong>العنوان:</strong> {{ order.address }}</p>
                <h3 style="color: var(--price-color);">المبلغ: {{ "%.2f"|format(order.total_price) }} ج.م</h3>
            </div>
        {% endfor %}

    {% elif page == 'admin' %}
        <h2>⚙️ لوحة تحكم الأدمن</h2>

        <div class="admin-grid">
            <div class="admin-card">
                <h3>➕ إضافة منتج جديد</h3>
                <form action="/admin/add-product" method="POST">
                    <div class="form-group">
                        <label>اسم المنتج</label>
                        <input type="text" name="name" required>
                    </div>
                    <div class="form-group">
                        <label>السعر (ج.م)</label>
                        <input type="number" step="0.01" name="price" required>
                    </div>
                    <div class="form-group">
                        <label>القسم (Category)</label>
                        <input type="text" name="category" placeholder="مثال: مأكولات ومشروبات، إلكترونيات" required>
                    </div>
                    <div class="form-group">
                        <label>رابط صورة المنتج (URL)</label>
                        <input type="url" name="image" required>
                    </div>
                    <button type="submit" class="btn-submit">حفظ المنتج</button>
                </form>
            </div>

            <div class="admin-card">
                <h3>🎨 التحكم الشامل بستايل وتصميم الموقع</h3>
                <form action="/admin/update-settings" method="POST">
                    <div class="form-group">
                        <label>لون الهيدر (Header)</label>
                        <input type="color" name="header_color" value="{{ settings.header_color }}">
                    </div>
                    <div class="form-group">
                        <label>اللون الرئيسي (Primary Accent)</label>
                        <input type="color" name="primary_color" value="{{ settings.primary_color }}">
                    </div>
                    <div class="form-group">
                        <label>لون الأسعار (Price Color)</label>
                        <input type="color" name="price_color" value="{{ settings.price_color }}">
                    </div>
                    <div class="form-group">
                        <label>لون خلفية الموقع (Background)</label>
                        <input type="color" name="bg_color" value="{{ settings.bg_color }}">
                    </div>
                    <div class="form-group">
                        <label>لون النصوص الأساسي (Text Color)</label>
                        <input type="color" name="text_color" value="{{ settings.text_color }}">
                    </div>
                    <div class="form-group">
                        <label>حجم الخط (Font Size - px)</label>
                        <input type="number" name="font_size" value="{{ settings.font_size }}" required>
                    </div>
                    <div class="form-group">
                        <label>مصاريف الشحن (ج.م)</label>
                        <input type="number" step="0.01" name="shipping_fee" value="{{ settings.shipping_fee }}" required>
                    </div>
                    <button type="submit" class="btn-submit">حفظ وتطبيق التصميم</button>
                </form>
            </div>
        </div>

        <h3>📦 إدارة المنتجات الحالية</h3>
        <table class="admin-table">
            <thead>
                <tr><th>#</th><th>الصورة</th><th>اسم المنتج</th><th>القسم</th><th>السعر</th><th>إجراءات</th></tr>
            </thead>
            <tbody>
                {% for p in all_products %}
                <tr>
                    <td>{{ p.id }}</td>
                    <td><img src="{{ p.image }}" style="width:40px; height:40px; object-fit:cover; border-radius:4px;"></td>
                    <td><b>{{ p.name }}</b></td>
                    <td>{{ p.category }}</td>
                    <td>{{ p.price }} ج.م</td>
                    <td>
                        <a href="/admin/edit-product/{{ p.id }}" class="btn-edit">تعديل</a>
                        <a href="/admin/delete-product/{{ p.id }}" class="btn-danger" onclick="return confirm('تأكيد الحذف؟')">حذف</a>
                    </td>
                </tr>
                {% endfor %}
            </tbody>
        </table>

        <h3>👥 العملاء المسجلون بالنظام (إجمالي: {{ total_users }})</h3>
        <table class="admin-table">
            <thead>
                <tr><th>#</th><th>اسم العميل</th><th>البريد الإلكتروني</th><th>رقم الهاتف</th><th>العمر</th><th>طريقة التسجيل</th></tr>
            </thead>
            <tbody>
                {% for u in all_users %}
                <tr>
                    <td>{{ u.id }}</td>
                    <td><b>{{ u.name }}</b> {% if u.is_admin %}<small style="color:red;">(أدمن)</small>{% endif %}</td>
                    <td>{{ u.email }}</td>
                    <td>{{ u.phone or 'غير محدد' }}</td>
                    <td>{{ u.age or 'غير محدد' }}</td>
                    <td>{{ u.auth_provider }}</td>
                </tr>
                {% endfor %}
            </tbody>
        </table>

        <h3>🛒 جميع الأوردرات والطلبات الواردة</h3>
        <table class="admin-table">
            <thead>
                <tr><th>#</th><th>العميل</th><th>الهاتف والعنوان</th><th>المنتجات المطلوبة</th><th>طريقة الدفع</th><th>الحالة</th><th>المبلغ</th><th>التاريخ</th></tr>
            </thead>
            <tbody>
                {% for o in all_orders %}
                <tr>
                    <td>#{{ o.id }}</td>
                    <td><b>{{ o.customer.name }}</b><br><small>{{ o.customer.email }}</small></td>
                    <td><b>هاتف:</b> {{ o.phone }}<br><b>عنوان:</b> {{ o.address }}</td>
                    <td>
                        <small>
                            {% set items = json.loads(o.items_json) %}
                            {% for item in items %}
                                • {{ item.name }} ({{ item.qty }})<br>
                            {% endfor %}
                        </small>
                    </td>
                    <td>{{ o.payment_method }}</td>
                    <td><span class="{% if o.payment_status == 'Paid' %}status-paid{% else %}status-pending{% endif %}">{{ o.payment_status }}</span></td>
                    <td><strong>{{ "%.2f"|format(o.total_price) }} ج.م</strong></td>
                    <td>{{ o.created_at.strftime('%Y-%m-%d %H:%M') }}</td>
                </tr>
                {% endfor %}
            </tbody>
        </table>

    {% elif page == 'edit_product' %}
        <div class="admin-card" style="max-width:600px; margin:auto;">
            <h2>✏️ تعديل المنتج #{{ edit_prod.id }}</h2>
            <form action="/admin/edit-product/{{ edit_prod.id }}" method="POST">
                <div class="form-group">
                    <label>اسم المنتج</label>
                    <input type="text" name="name" value="{{ edit_prod.name }}" required>
                </div>
                <div class="form-group">
                    <label>السعر (ج.م)</label>
                    <input type="number" step="0.01" name="price" value="{{ edit_prod.price }}" required>
                </div>
                <div class="form-group">
                    <label>القسم</label>
                    <input type="text" name="category" value="{{ edit_prod.category }}" required>
                </div>
                <div class="form-group">
                    <label>رابط الصورة</label>
                    <input type="url" name="image" value="{{ edit_prod.image }}" required>
                </div>
                <button type="submit" class="btn-submit">حفظ التعديلات</button>
            </form>
        </div>

    {% elif page == 'login' %}
        <div class="auth-form" style="max-width:400px; margin:auto;">
            <h2>تسجيل الدخول</h2>
            <form action="/login" method="POST">
                <div class="form-group">
                    <label>البريد الإلكتروني</label>
                    <input type="email" name="email" required>
                </div>
                <div class="form-group">
                    <label>كلمة المرور</label>
                    <input type="password" name="password" required>
                </div>
                <button type="submit" class="btn-submit">تسجيل الدخول</button>
            </form>
            <a href="/login/google" class="btn-social">
                <img src="https://upload.wikimedia.org/wikipedia/commons/5/53/Google_%22G%22_Logo.svg" alt="Google">
                تسجيل الدخول الفعلي بواسطة Google
            </a>
        </div>
    {% endif %}
</div>

<footer>
    <small>© 2026 Anything Shop - جميع الحقوق محفوظة.</small>
</footer>

</body>
</html>
"""

# --- Helpers ---
def get_cart_count():
    cart = session.get('cart', {})
    return sum(cart.values())

def get_settings():
    settings = SiteSettings.query.first()
    if not settings:
        settings = SiteSettings()
        db.session.add(settings)
        db.session.commit()
    return settings

def get_categories():
    categories = db.session.query(Product.category).distinct().all()
    return [c[0] for c in categories]

# --- Routes ---
@app.route("/")
def home():
    products = Product.query.all()
    return render_template_string(
        HTML_TEMPLATE, page='home', products=products, 
        cart_count=get_cart_count(), categories_list=get_categories(),
        current_cat="All", settings=get_settings()
    )

@app.route("/category/<cat_name>")
def category_view(cat_name):
    products = Product.query.filter_by(category=cat_name).all()
    return render_template_string(
        HTML_TEMPLATE, page='category', products=products,
        cart_count=get_cart_count(), categories_list=get_categories(),
        current_cat=cat_name, settings=get_settings()
    )

@app.route("/search")
def search():
    query = request.args.get("q", "").strip()
    if not query:
        return redirect(url_for('home'))

    keywords = query.split()
    filters = []
    for word in keywords:
        filters.append(Product.name.ilike(f"%{word}%"))
        filters.append(Product.category.ilike(f"%{word}%"))

    results = Product.query.filter(db.or_(*filters)).all()

    return render_template_string(
        HTML_TEMPLATE, page='search', products=results, search_query=query,
        cart_count=get_cart_count(), categories_list=get_categories(),
        current_cat="", settings=get_settings()
    )

@app.route("/add-to-cart", methods=["POST"])
def add_to_cart():
    p_id = str(request.form.get("product_id"))
    cart = session.get('cart', {})
    cart[p_id] = cart.get(p_id, 0) + 1
    session['cart'] = cart
    flash("تمت إضافة المنتج للسلة بنجاح!")
    return redirect(request.referrer or url_for('home'))

@app.route("/cart")
def view_cart():
    cart = session.get('cart', {})
    cart_items = []
    total_price = 0.0
    for p_id_str, qty in cart.items():
        product = Product.query.get(int(p_id_str))
        if product:
            total_price += product.price * qty
            cart_items.append({"name": product.name, "price": product.price, "qty": qty})
            
    return render_template_string(
        HTML_TEMPLATE, page='cart', cart_items=cart_items, 
        total_price=total_price, cart_count=get_cart_count(),
        categories_list=get_categories(), current_cat="Cart", settings=get_settings()
    )

@app.route("/checkout", methods=["POST"])
@login_required
def checkout():
    phone = request.form.get("phone")
    address = request.form.get("address")
    payment_method = request.form.get("payment_method")
    
    cart = session.get('cart', {})
    if not cart:
        return redirect(url_for('home'))

    order_items = []
    items_price = 0.0
    for p_id_str, qty in cart.items():
        product = Product.query.get(int(p_id_str))
        if product:
            items_price += product.price * qty
            order_items.append({"name": product.name, "price": product.price, "qty": qty})

    settings = get_settings()
    total_price = items_price + settings.shipping_fee

    new_order = Order(
        user_id=current_user.id,
        phone=phone,
        address=address,
        payment_method=payment_method,
        payment_status='Pending' if payment_method == 'Paymob' else 'Cash on Delivery',
        items_price=items_price,
        shipping_fee=settings.shipping_fee,
        total_price=total_price,
        items_json=json.dumps(order_items)
    )
    db.session.add(new_order)
    db.session.commit()
    session['cart'] = {}

    if payment_method == 'Paymob':
        try:
            auth_res = requests.post("https://accept.paymob.com/api/auth/tokens", json={"api_key": PAYMOB_API_KEY}).json()
            token = auth_res.get("token")

            amount_in_cents = int(round(total_price * 100))

            order_res = requests.post("https://accept.paymob.com/api/ecommerce/orders", json={
                "auth_token": token,
                "delivery_needed": "false",
                "amount_cents": amount_in_cents,
                "currency": "EGP",
                "merchant_order_id": str(new_order.id),
                "items": []
            }).json()
            paymob_order_id = order_res.get("id")

            payment_key_res = requests.post("https://accept.paymob.com/api/acceptance/payment_keys", json={
                "auth_token": token,
                "amount_cents": amount_in_cents,
                "expiration": 3600,
                "order_id": paymob_order_id,
                "billing_data": {
                    "first_name": current_user.name or "Customer",
                    "last_name": "NA",
                    "email": current_user.email,
                    "phone_number": phone,
                    "apartment": "NA", "floor": "NA", "street": address, "building": "NA",
                    "shipping_method": "PKG", "postal_code": "NA", "city": "Cairo", "country": "EG"
                },
                "currency": "EGP",
                "integration_id": int(PAYMOB_INTEGRATION_ID)
            }).json()

            payment_token = payment_key_res.get("token")
            return redirect(f"https://accept.paymob.com/api/acceptance/iframes/{PAYMOB_IFRAME_ID}?payment_token={payment_token}")
        except Exception as e:
            flash(f"حدث خطأ أثناء الاتصال بـ Paymob: {str(e)}")
            return redirect(url_for('my_orders'))

    flash("تم تسجيل طلبك بنجاح!")
    return redirect(url_for('my_orders'))

@app.route("/paymob/callback")
def paymob_callback():
    hmac_fields = [
        "amount_cents", "created_at", "currency", "error_occured",
        "has_parent_transaction", "id", "integration_id", "is_3d_secure",
        "is_auth", "is_capture", "is_standalone_payment", "is_voided",
        "order", "owner", "pending", "source_data.pan", "source_data.sub_type",
        "source_data.type", "success"
    ]
    
    concatenated_string = ""
    for field in hmac_fields:
        val = request.args.get(field, "")
        concatenated_string += str(val)

    if PAYMOB_HMAC_KEY:
        calculated_hmac = hmac.new(
            PAYMOB_HMAC_KEY.encode('utf-8'),
            concatenated_string.encode('utf-8'),
            hashlib.sha512
        ).hexdigest()

        received_hmac = request.args.get("hmac")

        if calculated_hmac != received_hmac:
            flash("فشلت عملية التحقق من صحة المعاملة (HMAC Mismatch).")
            return redirect(url_for('my_orders'))

    success = request.args.get("success")
    merchant_order_id = request.args.get("merchant_order_id")

    if merchant_order_id:
        order = Order.query.get(int(merchant_order_id))
        if order:
            if success == "true":
                order.payment_status = "Paid"
                flash("تمت عملية الدفع بنجاح!")
            else:
                order.payment_status = "Failed"
                flash("فشلت عملية الدفع، يرجى المحاولة مرة أخرى.")
            db.session.commit()

    return redirect(url_for('my_orders'))

@app.route("/login/google")
def login_google():
    redirect_uri = url_for('google_callback', _external=True)
    return google.authorize_redirect(redirect_uri)

@app.route("/login/google/callback")
def google_callback():
    token = google.authorize_access_token()
    user_info = token.get('userinfo')
    if user_info:
        email = user_info['email']
        name = user_info.get('name', 'مستخدم جوجل')
        picture = user_info.get('picture', '')

        user = User.query.filter_by(email=email).first()
        if not user:
            user = User(
                name=name,
                email=email,
                auth_provider='google',
                avatar_url=picture,
                is_admin=(email == "admin@shop.com")
            )
            db.session.add(user)
            db.session.commit()

        login_user(user)
        flash("تم تسجيل الدخول بواسطة Google بنجاح!")
    return redirect(url_for('home'))

@app.route("/orders")
@login_required
def my_orders():
    user_orders = Order.query.filter_by(user_id=current_user.id).order_by(Order.created_at.desc()).all()
    return render_template_string(
        HTML_TEMPLATE, page='orders', orders=user_orders, 
        cart_count=get_cart_count(), categories_list=get_categories(),
        current_cat="Orders", settings=get_settings()
    )

# --- مسارات الأدمن ---
@app.route("/admin")
@login_required
def admin_panel():
    if not current_user.is_admin:
        flash("عذراً، هذه الصفحة مخصصة للأدمن فقط.")
        return redirect(url_for('home'))

    all_orders = Order.query.order_by(Order.created_at.desc()).all()
    all_products = Product.query.order_by(Product.id.desc()).all()
    all_users = User.query.all()
    
    return render_template_string(
        HTML_TEMPLATE, page='admin', all_orders=all_orders, all_products=all_products,
        all_users=all_users, total_users=len(all_users), json=json,
        cart_count=get_cart_count(), categories_list=get_categories(),
        current_cat="Admin", settings=get_settings()
    )

@app.route("/admin/add-product", methods=["POST"])
@login_required
def admin_add_product():
    if not current_user.is_admin:
        return redirect(url_for('home'))
        
    name = request.form.get("name")
    price = float(request.form.get("price"))
    category = request.form.get("category")
    image = request.form.get("image")

    new_prod = Product(name=name, price=price, category=category, image=image)
    db.session.add(new_prod)
    db.session.commit()
    flash("تمت إضافة المنتج بنجاح!")
    return redirect(url_for('admin_panel'))

@app.route("/admin/edit-product/<int:prod_id>", methods=["GET", "POST"])
@login_required
def admin_edit_product(prod_id):
    if not current_user.is_admin:
        return redirect(url_for('home'))

    prod = Product.query.get_or_404(prod_id)
    if request.method == "POST":
        prod.name = request.form.get("name")
        prod.price = float(request.form.get("price"))
        prod.category = request.form.get("category")
        prod.image = request.form.get("image")
        db.session.commit()
        flash("تم تعديل بيانات المنتج بنجاح!")
        return redirect(url_for('admin_panel'))

    return render_template_string(
        HTML_TEMPLATE, page='edit_product', edit_prod=prod,
        cart_count=get_cart_count(), categories_list=get_categories(),
        settings=get_settings()
    )

@app.route("/admin/delete-product/<int:prod_id>")
@login_required
def admin_delete_product(prod_id):
    if not current_user.is_admin:
        return redirect(url_for('home'))

    prod = Product.query.get_or_404(prod_id)
    db.session.delete(prod)
    db.session.commit()
    flash("تم حذف المنتج بنجاح.")
    return redirect(url_for('admin_panel'))

@app.route("/admin/update-settings", methods=["POST"])
@login_required
def admin_update_settings():
    if not current_user.is_admin:
        return redirect(url_for('home'))

    settings = get_settings()
    settings.header_color = request.form.get("header_color")
    settings.primary_color = request.form.get("primary_color")
    settings.price_color = request.form.get("price_color")
    settings.bg_color = request.form.get("bg_color")
    settings.text_color = request.form.get("text_color")
    settings.font_size = int(request.form.get("font_size"))
    settings.shipping_fee = float(request.form.get("shipping_fee"))

    db.session.commit()
    flash("تم تحديث إعدادات وتصميم الموقع بنجاح!")
    return redirect(url_for('admin_panel'))

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email")
        password = request.form.get("password")
        user = User.query.filter_by(email=email).first()
        if user and check_password_hash(user.password_hash, password):
            login_user(user)
            return redirect(url_for('admin_panel' if user.is_admin else 'home'))
        flash("بيانات الدخول غير صحيحة.")
    return render_template_string(HTML_TEMPLATE, page='login', cart_count=get_cart_count(), categories_list=get_categories(), settings=get_settings())

@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for('home'))

# --- تهيئة الحسابات الرئيسية والبيانات ---
def seed_data():
    if Product.query.count() == 0:
        db.session.add_all([
            Product(name="لبانة نعناع نكهة ممتازة", price=0.50, category="مأكولات ومشروبات", image="https://images.unsplash.com/photo-1582058091505-f87a2e55a40f?w=400"),
            Product(name="حذاء رياضي Pro", price=450.0, category="أحذية", image="https://images.unsplash.com/photo-1542291026-7eec264c27ff?w=400"),
            Product(name="سماعة لاسلكية Bluetooth", price=650.0, category="إلكترونيات", image="https://images.unsplash.com/photo-1505740420928-5e560c06d30e?w=400"),
            Product(name="سماعة أذن إيربودز AirPods", price=1200.0, category="إلكترونيات", image="https://images.unsplash.com/photo-1600294037681-c80b4cb5b434?w=400")
        ])
        db.session.commit()

    admin_email = "admin@shop.com"
    if not User.query.filter_by(email=admin_email).first():
        admin = User(
            name="أحمد الأدمن",
            email=admin_email,
            password_hash=generate_password_hash("admin123", method='scrypt'),
            is_admin=True
        )
        db.session.add(admin)
        db.session.commit()

# --- إنشاء الجداول والبيانات عند بداية التشغيل ---
with app.app_context():
    db.create_all()
    seed_data()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
app.run(host="0.0.0.0", port=port)
