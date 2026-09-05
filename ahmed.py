import os
import json
import requests
from datetime import datetime
from dotenv import load_dotenv
from flask import Flask, render_template_string, request, redirect, url_for, session, jsonify, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
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

# --- إعدادات Google OAuth ---
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

# --- نماذج قاعدة البيانات (Models) ---
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    first_name = db.Column(db.String(50), nullable=False)
    last_name = db.Column(db.String(50), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=True)
    phone = db.Column(db.String(20), nullable=True)
    address = db.Column(db.Text, nullable=True)
    birth_date = db.Column(db.String(20), nullable=True)
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

class Category(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)

class SiteSettings(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    header_color = db.Column(db.String(20), default='#131921')
    primary_color = db.Column(db.String(20), default='#ff9900')
    price_color = db.Column(db.String(20), default='#B12704')
    bg_color = db.Column(db.String(20), default='#eaeded')
    text_color = db.Column(db.String(20), default='#0f1111')
    icon_color = db.Column(db.String(20), default='#ffffff')
    card_bg_color = db.Column(db.String(20), default='#ffffff')
    font_size = db.Column(db.Integer, default=14)
    shipping_fee = db.Column(db.Float, default=50.0)
    logo_url = db.Column(db.String(500), nullable=True)

class Order(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    phone = db.Column(db.String(20), nullable=False)
    address = db.Column(db.Text, nullable=False)
    payment_method = db.Column(db.String(50), nullable=False)
    payment_status = db.Column(db.String(50), default='Pending')
    items_price = db.Column(db.Float, nullable=False)
    shipping_fee = db.Column(db.Float, nullable=False, default=50.0)
    total_price = db.Column(db.Float, nullable=False)
    items_json = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_read = db.Column(db.Boolean, default=False)

class SupportMessage(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    session_id = db.Column(db.String(255), nullable=False)
    sender_type = db.Column(db.String(20), nullable=False)
    message = db.Column(db.Text, nullable=False)
    client_email = db.Column(db.String(120), nullable=True)
    client_phone = db.Column(db.String(20), nullable=True)
    is_read = db.Column(db.Boolean, default=False)
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
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Anything Shop - متجر احترافي</title>
    <style>
        :root {
            --header-bg: {{ settings.header_color }};
            --primary-color: {{ settings.primary_color }};
            --price-color: {{ settings.price_color }};
            --bg-color: {{ settings.bg_color }};
            --text-color: {{ settings.text_color }};
            --icon-color: {{ settings.icon_color }};
            --card-bg: {{ settings.card_bg_color }};
            --font-size: {{ settings.font_size }}px;
        }
        * { box-sizing: border-box; }
        body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; margin:0; padding:0; background: var(--bg-color); color: var(--text-color); font-size: var(--font-size); text-align:right; overflow-x: hidden; }
        
        header { background: var(--header-bg); color:white; padding:10px 15px; display:flex; align-items:center; justify-content:space-between; position:sticky; top:0; z-index:100; gap:10px; flex-wrap: wrap; }
        .logo { font-size:20px; font-weight:bold; color: var(--primary-color); text-decoration:none; white-space:nowrap; display: flex; align-items: center; gap: 8px; }
        
        .logo-3d {
            width: 36px; height: 36px; display: inline-flex; align-items: center; justify-content: center;
            background: linear-gradient(135deg, #131921, #232f3e); border-radius: 8px;
            box-shadow: 0 3px 6px rgba(0,0,0,0.4), inset 0 1px 1px rgba(255,255,255,0.2);
            overflow: hidden; border: 1px solid #37475a;
        }
        .logo-3d img, .logo-3d svg { width: 100%; height: 100%; object-fit: cover; }
        
        .search-bar { flex-grow:1; max-width:500px; display:flex; min-width: 200px; }
        .search-bar input { width:100%; padding:8px 10px; border:none; border-radius:0 4px 4px 0; font-size:13px; outline:none; }
        .search-bar button { background: var(--primary-color); border:none; padding:8px 12px; border-radius:4px 0 0 4px; cursor:pointer; font-weight:bold; font-size: 13px; color: var(--text-color); }
        
        .nav-right { display:flex; align-items:center; gap:8px; white-space:nowrap; flex-wrap: wrap; }
        .nav-btn { background:#232f3e; color: var(--icon-color); padding:6px 12px; border-radius:4px; text-decoration:none; font-weight:bold; border:1px solid #d5d9d9; position: relative; font-size: 13px; }
        .admin-btn { background: var(--primary-color); color:black; }
        
        .badge-notification {
            position: absolute; top: -6px; right: -6px; background-color: #ff3b30; color: white;
            border-radius: 50%; padding: 2px 5px; font-size: 10px; font-weight: bold; min-width: 15px; text-align: center;
        }

        .nav-categories { background:#232f3e; padding:8px 15px; display:flex; gap:10px; overflow-x:auto; white-space: nowrap; }
        .nav-categories a { color: var(--icon-color); text-decoration:none; font-weight:500; font-size:13px; padding:4px 8px; border-radius:3px; }
        .nav-categories a:hover, .nav-categories a.active { background:#37475a; color: var(--primary-color); }
        
        .container { max-width:1300px; margin:15px auto; padding:0 10px; min-height:75vh; }
        .products-grid { display:grid; grid-template-columns: repeat(auto-fill, minmax(180px, 1fr)); gap:15px; }
        .card { background: var(--card-bg); border:1px solid #e7e7e7; border-radius:8px; padding:12px; display:flex; flex-direction:column; justify-content:space-between; }
        .card img { width:100%; height:140px; object-fit:cover; border-radius:4px; margin-bottom:8px; }
        .card-title { font-size:14px; font-weight:600; margin-bottom:5px; height:38px; overflow:hidden; }
        .card-price { font-size:16px; color: var(--price-color); font-weight:bold; margin-bottom:8px; }
        .btn-add { background:#ffd814; border:1px solid #FCD200; border-radius:20px; padding:7px; width:100%; font-weight:bold; cursor:pointer; font-size: 13px; }
        
        .cart-table, .orders-table, .admin-table { width:100%; background: var(--card-bg); border-collapse:collapse; margin-bottom:20px; border-radius:8px; overflow:hidden; font-size: 13px; }
        .cart-table th, .cart-table td, .orders-table th, .orders-table td, .admin-table th, .admin-table td { padding:10px; text-align:right; border-bottom:1px solid #ddd; }
        
        .checkout-form, .auth-form, .admin-card { background: var(--card-bg); padding:18px; border-radius:8px; margin-bottom:20px; border:1px solid #ddd; box-shadow:0 2px 5px rgba(0,0,0,0.1); }
        .form-group { margin-bottom:12px; }
        .form-group label { display:block; margin-bottom:4px; font-weight:bold; font-size: 13px; }
        .form-group input, .form-group textarea, .form-group select { width:100%; padding:9px; border:1px solid #ccc; border-radius:4px; font-size: 14px; }
        
        .btn-submit { background: var(--primary-color); color:black; border:none; padding:10px; border-radius:4px; font-weight:bold; width:100%; cursor:pointer; font-size:15px; }
        .btn-google { display:flex; align-items:center; justify-content:center; gap:10px; background:#4285F4; color:white; border:none; padding:10px; border-radius:4px; font-weight:bold; width:100%; text-decoration:none; margin-top:10px; font-size:14px; }
        .btn-danger { background:#dc3545; color:white; padding:5px 10px; border:none; border-radius:4px; cursor:pointer; text-decoration:none; font-size:11px; }
        .btn-edit { background:#ffc107; color:black; padding:5px 10px; border:none; border-radius:4px; cursor:pointer; text-decoration:none; font-size:11px; margin-left:4px; }
        
        .admin-section-box { background: var(--card-bg); border: 1px solid #ccc; border-radius: 8px; margin-bottom: 15px; overflow: hidden; box-shadow: 0 2px 4px rgba(0,0,0,0.05); }
        .admin-section-header { background: #232f3e; color: #fff; padding: 12px 18px; font-weight: bold; cursor: pointer; display: flex; justify-content: space-between; align-items: center; font-size: 14px; }
        .admin-section-header:hover { background: #37475a; }
        .admin-section-content { padding: 18px; display: none; border-top: 1px solid #ddd; }
        .admin-section-content.open { display: block; }

        .pagination-box { display: flex; justify-content: center; gap: 6px; margin: 25px 0; }
        .pagination-box a, .pagination-box span { padding: 8px 14px; border: 1px solid #ccc; background: #fff; color: #333; text-decoration: none; border-radius: 4px; font-size: 13px; font-weight: bold; }
        .pagination-box a.active, .pagination-box span.active { background: var(--primary-color); color: #000; border-color: #d4af37; }

        .live-chat-admin-container { display: flex; height: 450px; background: #fff; border: 1px solid #ddd; border-radius: 8px; overflow: hidden; margin-top: 10px; }
        .chat-sidebar { width: 280px; background: #f8f9fa; border-left: 1px solid #ddd; display: flex; flex-direction: column; }
        .chat-sidebar-list { flex: 1; overflow-y: auto; }
        .client-chat-item { padding: 10px 12px; border-bottom: 1px solid #eee; cursor: pointer; text-decoration: none; color: #333; display: flex; justify-content: space-between; align-items: center; font-size: 12px; }
        .client-chat-item:hover, .client-chat-item.active { background: #e9ecef; }
        .chat-main-area { flex: 1; display: flex; flex-direction: column; background: #fff; }
        .admin-messages-box { flex: 1; padding: 12px; overflow-y: auto; background: #f1f2f6; display: flex; flex-direction: column; gap: 6px; }
        .admin-msg-bubble { max-width: 75%; padding: 8px 12px; border-radius: 8px; font-size: 12px; }
        .admin-msg-bubble.client { background: #fff; align-self: flex-start; border: 1px solid #dcdde1; color: #333; }
        .admin-msg-bubble.admin { background: #0084ff; color: #fff; align-self: flex-end; }
        .admin-reply-box { padding: 10px; background: #fff; border-top: 1px solid #ddd; display: flex; gap: 6px; }
        .admin-reply-box input { flex: 1; padding: 7px; border: 1px solid #ccc; border-radius: 4px; outline: none; font-size: 12px; }
        .admin-reply-box button { padding: 7px 14px; background: #0084ff; color: #fff; border: none; border-radius: 4px; cursor: pointer; font-weight: bold; font-size: 12px; }

        .chat-widget-btn { position: fixed; bottom: 20px; left: 20px; background: var(--primary-color); color: #000; width: 52px; height: 52px; border-radius: 50%; display: flex; align-items: center; justify-content: center; box-shadow: 0 4px 10px rgba(0,0,0,0.3); cursor: pointer; z-index: 999; font-weight: bold; text-decoration: none; border: 2px solid white; font-size: 18px; }
        .chat-popup { position: fixed; bottom: 82px; left: 15px; width: 320px; max-width: calc(100vw - 30px); height: 400px; background: white; border-radius: 10px; box-shadow: 0 5px 20px rgba(0,0,0,0.2); z-index: 1000; display: none; flex-direction: column; overflow: hidden; border: 1px solid #ccc; }
        .chat-header { background: var(--header-bg); color: white; padding: 10px 12px; display: flex; justify-content: space-between; align-items: center; font-weight: bold; font-size: 13px; }
        .chat-header button { background: none; border: none; color: white; font-size: 15px; cursor: pointer; }
        .chat-messages-container { flex: 1; padding: 10px; overflow-y: auto; background: #f9f9f9; display: flex; flex-direction: column; gap: 6px; }
        .chat-msg { padding: 7px 10px; border-radius: 8px; max-width: 80%; font-size: 12px; }
        .chat-msg.client { background: #0084ff; color: #fff; align-self: flex-end; }
        .chat-msg.admin { background: #e4e6eb; color: #000; align-self: flex-start; }
        .chat-footer { padding: 8px; background: #fff; border-top: 1px solid #ddd; display: flex; flex-direction: column; gap: 5px; }
        .chat-footer-row { display: flex; gap: 5px; width: 100%; }
        .chat-footer input { flex: 1; padding: 7px; border: 1px solid #ccc; border-radius: 4px; font-size: 11px; }
        .chat-footer button { background: #0084ff; color: #fff; border: none; padding: 7px 10px; border-radius: 4px; cursor: pointer; font-size: 11px; }
        
        footer { background: var(--header-bg); color:white; padding:20px 15px; margin-top:30px; border-top:3px solid var(--primary-color); text-align:center; }
        .alert { background:#d4edda; color:#155724; padding:10px; border-radius:4px; margin-bottom:12px; font-size: 13px; }
    </style>
</head>
<body>

<header>
    <a href="/" class="logo">
        <div class="logo-3d">
            {% if settings.logo_url %}
                <img src="{{ settings.logo_url }}" alt="Logo">
            {% else %}
                <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">
                    <path d="M50 12 L82 78 L65 78 L50 45 L35 78 L18 78 Z" fill="%23ffd700"/>
                    <polygon points="50,28 60,56 40,56" fill="%231e3c72"/>
                </svg>
            {% endif %}
        </div>
        Anything Shop
    </a>
    
    <form action="/search" method="GET" class="search-bar">
        <input type="text" name="q" placeholder="ابحث عن منتج..." value="{{ search_query or '' }}">
        <button type="submit">بحث 🔍</button>
    </form>

    <div class="nav-right">
        {% if current_user.is_authenticated %}
            {% if current_user.is_admin %}
                <a href="/admin" class="nav-btn admin-btn">
                    ⚙️ لوحة الأدمن
                    <span id="global-admin-badge" class="badge-notification" style="display:none;">0</span>
                </a>
            {% endif %}
            <a href="/profile" class="nav-btn" style="background:#37475a;">👤 حسابي</a>
            <a href="/orders" class="nav-btn">📦 طلباتي</a>
            <a href="/logout" class="nav-btn">خروج</a>
        {% else %}
            <a href="/login" class="nav-btn">دخول</a>
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
        <h2>{{ 'نتائج البحث عن: ' ~ search_query if page == 'search' else ('منتجات قسم: ' ~ current_cat if page == 'category' else 'المنتجات المتاحة') }}</h2>
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

            {% if total_product_pages > 1 %}
            <div class="pagination-box">
                {% for p in range(1, total_product_pages + 1) %}
                    {% if page == 'home' %}
                        <a href="/?page={{ p }}" class="{% if current_product_page == p %}active{% endif %}">{{ p }}</a>
                    {% elif page == 'category' %}
                        <a href="/category/{{ current_cat }}?page={{ p }}" class="{% if current_product_page == p %}active{% endif %}">{{ p }}</a>
                    {% elif page == 'search' %}
                        <a href="/search?q={{ search_query }}&page={{ p }}" class="{% if current_product_page == p %}active{% endif %}">{{ p }}</a>
                    {% endif %}
                {% endfor %}
            </div>
            {% endif %}
        {% else %}
            <p>لم يتم العثور على منتجات.</p>
        {% endif %}

    {% elif page == 'register' %}
        <div class="auth-form" style="max-width:450px; margin:auto;">
            <h2>إنشاء حساب جديد</h2>
            <form action="/register" method="POST">
                <div class="form-group"><label>الاسم الأول</label><input type="text" name="first_name" required></div>
                <div class="form-group"><label>الاسم الأخير</label><input type="text" name="last_name" required></div>
                <div class="form-group"><label>البريد الإلكتروني</label><input type="email" name="email" required></div>
                <div class="form-group"><label>كلمة المرور</label><input type="password" name="password" required></div>
                <div class="form-group"><label>رقم الهاتف</label><input type="tel" name="phone" placeholder="01xxxxxxxxx" required></div>
                <div class="form-group"><label>العنوان بالكامل</label><textarea name="address" rows="2" required></textarea></div>
                <div class="form-group"><label>تاريخ الميلاد</label><input type="date" name="birth_date" required></div>
                <button type="submit" class="btn-submit">تسجيل الحساب</button>
            </form>
            <a href="/login/google" class="btn-google">🌐 التسجيل بواسطة جوجل</a>
        </div>

    {% elif page == 'profile' %}
        <div class="auth-form" style="max-width:500px; margin:auto;">
            <h2>👤 ملفي الشخصي وتعديل البيانات</h2>
            <form action="/profile" method="POST">
                <div class="form-group"><label>الاسم الأول</label><input type="text" name="first_name" value="{{ current_user.first_name }}" required></div>
                <div class="form-group"><label>الاسم الأخير</label><input type="text" name="last_name" value="{{ current_user.last_name }}" required></div>
                <div class="form-group"><label>البريد الإلكتروني</label><input type="email" value="{{ current_user.email }}" disabled style="background:#eee;"></div>
                <div class="form-group"><label>رقم الهاتف</label><input type="tel" name="phone" value="{{ current_user.phone or '' }}" required></div>
                <div class="form-group"><label>العنوان بالكامل</label><textarea name="address" rows="2" required>{{ current_user.address or '' }}</textarea></div>
                <div class="form-group"><label>تاريخ الميلاد</label><input type="date" name="birth_date" value="{{ current_user.birth_date or '' }}"></div>
                <button type="submit" class="btn-submit">حفظ وتحديث البيانات</button>
            </form>
        </div>

    {% elif page == 'cart' %}
        <h2>سلة التسوق</h2>
        {% if cart_items %}
            <table class="cart-table">
                <thead><tr><th>المنتج</th><th>السعر</th><th>الكمية</th><th>الإجمالي</th></tr></thead>
                <tbody>
                    {% for item in cart_items %}
                    <tr><td>{{ item.name }}</td><td>{{ item.price }} ج.م</td><td>{{ item.qty }}</td><td>{{ "%.2f"|format(item.price * item.qty) }} ج.م</td></tr>
                    {% endfor %}
                </tbody>
            </table>
            <div style="text-align:left; background:var(--card-bg); padding:12px; border-radius:8px; margin-bottom:15px;">
                <p>مصاريف الشحن: <strong>{{ "%.2f"|format(settings.shipping_fee) }} ج.م</strong></p>
                <h3 style="color: var(--price-color);">الإجمالي النهائي: {{ "%.2f"|format(final_total) }} ج.م</h3>
            </div>
            <div class="checkout-form">
                <h3>تفاصيل الشحن والتسليم</h3>
                <form action="/checkout" method="POST">
                    <div class="form-group"><label>رقم الهاتف للتواصل</label><input type="tel" name="phone" value="{{ current_user.phone or '' }}" required></div>
                    <div class="form-group"><label>عنوان التوصيل بالكامل</label><textarea name="address" rows="2" required>{{ current_user.address or '' }}</textarea></div>
                    <div class="form-group"><label>طريقة الدفع</label><select name="payment_method" required><option value="Cash">الدفع عند الاستلام (كاش)</option></select></div>
                    <button type="submit" class="btn-submit">تأكيد ومتابعة الطلب</button>
                </form>
            </div>
        {% else %}
            <p>سلة التسوق فارغة حالياً.</p>
        {% endif %}

    {% elif page == 'orders' %}
        <h2>طلباتي</h2>
        {% for order in orders %}
            <div style="background:var(--card-bg); padding:12px; border-radius:8px; margin-bottom:15px; border:1px solid #ccc;">
                <h4>طلب رقم #{{ order.id }} - {{ order.created_at.strftime('%Y-%m-%d %H:%M') }}</h4>
                <p><strong>حالة الدفع:</strong> {{ order.payment_status }}</p>
                <p><strong>العنوان:</strong> {{ order.address }}</p>
                <h3 style="color: var(--price-color);">المبلغ الإجمالي: {{ "%.2f"|format(order.total_price) }} ج.م</h3>
            </div>
        {% endfor %}

    {% elif page == 'admin' %}
        <h2>⚙️ لوحة تحكم الأدمن</h2>

        <div class="admin-section-box">
            <div class="admin-section-header" onclick="toggleSection('sec-chat')">
                <span>💬 المحادثات الحية والدعم الفني (للعملاء المسجلين فقط)</span>
                <span>▼</span>
            </div>
            <div id="sec-chat" class="admin-section-content {% if active_session %}open{% endif %}">
                <div class="live-chat-admin-container">
                    <div class="chat-sidebar">
                        <div class="chat-sidebar-list">
                            {% for conv in paged_chats %}
                                <a href="/admin?session={{ conv.session_id }}&chat_page={{ chat_page }}" class="client-chat-item {% if active_session == conv.session_id %}active{% endif %}">
                                    <div>
                                        <strong>{{ conv.email }}</strong><br>
                                        <small>{{ conv.last_time[:16] }}</small>
                                    </div>
                                    {% if conv.unread_count > 0 %}
                                        <span class="badge-notification" style="position:static;">{{ conv.unread_count }}</span>
                                    {% endif %}
                                </a>
                            {% endfor %}
                        </div>
                        {% if total_chat_pages > 1 %}
                        <div class="pagination-box" style="margin:5px 0;">
                            {% for p in range(1, total_chat_pages + 1) %}
                                <a href="/admin?chat_page={{ p }}{% if active_session %}&session={{ active_session }}{% endif %}" class="{% if chat_page == p %}active{% endif %}">{{ p }}</a>
                            {% endfor %}
                        </div>
                        {% endif %}
                    </div>
                    <div class="chat-main-area">
                        {% if active_session %}
                            <div class="admin-messages-box" id="adminMsgBox"></div>
                            <form class="admin-reply-box" id="adminReplyForm">
                                <input type="text" id="adminReplyInput" placeholder="اكتب ردك هنا..." required autocomplete="off">
                                <button type="submit">إرسال</button>
                            </form>
                        {% else %}
                            <div style="padding: 40px; text-align: center; color: #666;">اختر محادثة للبدء.</div>
                        {% endif %}
                    </div>
                </div>
            </div>
        </div>

        <div class="admin-section-box">
            <div class="admin-section-header" onclick="toggleSection('sec-orders')">
                <span>📦 إدارة الأوردرات (إجمالي: {{ total_orders_count }})</span>
                <span>▼</span>
            </div>
            <div id="sec-orders" class="admin-section-content">
                <table class="admin-table">
                    <thead><tr><th>رقم الطلب</th><th>العميل</th><th>الهاتف</th><th>العنوان</th><th>الإجمالي</th><th>الحالة</th><th>إجراء</th></tr></thead>
                    <tbody>
                        {% for ord in paged_orders %}
                        <tr {% if not ord.is_read %}style="background-color: #fff9db;"{% endif %}>
                            <td>#{{ ord.id }}</td>
                            <td>{{ ord.customer.first_name }} {{ ord.customer.last_name }}</td>
                            <td>{{ ord.phone }}</td>
                            <td>{{ ord.address }}</td>
                            <td>{{ "%.2f"|format(ord.total_price) }} ج.م</td>
                            <td>{{ ord.payment_status }}</td>
                            <td><a href="/admin/mark-order-read/{{ ord.id }}" style="color:#0084ff; text-decoration:none;">تحديد كمقروء</a></td>
                        </tr>
                        {% endfor %}
                    </tbody>
                </table>
            </div>
        </div>

        <div class="admin-section-box">
            <div class="admin-section-header" onclick="toggleSection('sec-categories')">
                <span>📂 إدارة أقسام الموقع</span>
                <span>▼</span>
            </div>
            <div id="sec-categories" class="admin-section-content">
                <form action="/admin/add-category" method="POST" style="display:flex; gap:10px; margin-bottom:15px;">
                    <input type="text" name="cat_name" placeholder="اسم القسم الجديد..." required style="flex:1; padding:8px; border:1px solid #ccc; border-radius:4px;">
                    <button type="submit" style="background:var(--primary-color); border:none; padding:8px 15px; border-radius:4px; font-weight:bold; cursor:pointer;">إضافة قسم</button>
                </form>
                <ul style="list-style:none; padding:0;">
                    {% for cat in custom_categories %}
                        <li style="display:flex; justify-content:space-between; align-items:center; padding:8px; border-bottom:1px solid #eee;">
                            <form action="/admin/edit-category/{{ cat.id }}" method="POST" style="display:flex; gap:8px; flex:1; align-items:center;">
                                <input type="text" name="new_name" value="{{ cat.name }}" required style="padding:5px; border:1px solid #ccc; border-radius:4px; width:200px;">
                                <button type="submit" class="btn-edit">تحديث الاسم</button>
                            </form>
                            <a href="/admin/delete-category/{{ cat.id }}" class="btn-danger" onclick="return confirm('حذف القسم؟')">حذف</a>
                        </li>
                    {% endfor %}
                </ul>
            </div>
        </div>

        <div class="admin-section-box">
            <div class="admin-section-header" onclick="toggleSection('sec-add-prod')">
                <span>➕ إضافة منتج جديد</span>
                <span>▼</span>
            </div>
            <div id="sec-add-prod" class="admin-section-content">
                <form action="/admin/add-product" method="POST" enctype="multipart/form-data">
                    <div class="form-group"><label>اسم المنتج</label><input type="text" name="name" required></div>
                    <div class="form-group"><label>السعر (ج.م)</label><input type="number" step="0.01" name="price" required></div>
                    <div class="form-group"><label>القسم</label>
                        <select name="category" required style="width:100%; padding:9px; border:1px solid #ccc; border-radius:4px;">
                            {% for cat in custom_categories %}<option value="{{ cat.name }}">{{ cat.name }}</option>{% endfor %}
                        </select>
                    </div>
                    <div class="form-group"><label>رفع صورة المنتج</label><input type="file" name="image_file" accept="image/*"></div>
                    <div class="form-group"><label>أو رابط صورة خارجي</label><input type="url" name="image_url"></div>
                    <button type="submit" class="btn-submit">حفظ المنتج</button>
                </form>
            </div>
        </div>

        <div class="admin-section-box">
            <div class="admin-section-header" onclick="toggleSection('sec-manage-prod')">
                <span>🛠️ إدارة وتعديل المنتجات</span>
                <span>▼</span>
            </div>
            <div id="sec-manage-prod" class="admin-section-content">
                <table class="admin-table">
                    <thead><tr><th>#</th><th>الاسم</th><th>القسم</th><th>السعر</th><th>إجراءات</th></tr></thead>
                    <tbody>
                        {% for p in all_products %}
                        <tr>
                            <td>{{ p.id }}</td>
                            <td><b>{{ p.name }}</b></td><td>{{ p.category }}</td><td>{{ p.price }} ج.م</td>
                            <td>
                                <a href="/admin/edit-product/{{ p.id }}" class="btn-edit">تعديل</a>
                                <a href="/admin/delete-product/{{ p.id }}" class="btn-danger" onclick="return confirm('تأكيد الحذف؟')">حذف</a>
                            </td>
                        </tr>
                        {% endfor %}
                    </tbody>
                </table>
            </div>
        </div>

        <!-- قسم التحكم الشامل في الألوان والأيقونات والديزاين -->
        <div class="admin-section-box">
            <div class="admin-section-header" onclick="toggleSection('sec-design')">
                <span>🎨 التحكم الكامل في ألوان الديزاين، الأيقونات، والشعار</span>
                <span>▼</span>
            </div>
            <div id="sec-design" class="admin-section-content">
                <form action="/admin/update-settings" method="POST" enctype="multipart/form-data">
                    <div class="form-group"><label>رفع شعار الموقع (Logo)</label><input type="file" name="logo_file" accept="image/*"></div>
                    <div class="form-group"><label>أو رابط الشعار (Logo URL)</label><input type="url" name="logo_url" value="{{ settings.logo_url or '' }}"></div>
                    
                    <div style="display:grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 10px;">
                        <div class="form-group"><label>لون الهيدر</label><input type="color" name="header_color" value="{{ settings.header_color }}"></div>
                        <div class="form-group"><label>اللون الرئيسي</label><input type="color" name="primary_color" value="{{ settings.primary_color }}"></div>
                        <div class="form-group"><label>لون الأسعار</label><input type="color" name="price_color" value="{{ settings.price_color }}"></div>
                        <div class="form-group"><label>لون خلفية الموقع العامة</label><input type="color" name="bg_color" value="{{ settings.bg_color }}"></div>
                        <div class="form-group"><label>لون النصوص</label><input type="color" name="text_color" value="{{ settings.text_color }}"></div>
                        <div class="form-group"><label>لون الأيقونات والروابط العلوية</label><input type="color" name="icon_color" value="{{ settings.icon_color }}"></div>
                        <div class="form-group"><label>لون خلفية البطاقات (Cards)</label><input type="color" name="card_bg_color" value="{{ settings.card_bg_color }}"></div>
                    </div>

                    <div class="form-group" style="margin-top:10px;"><label>مصاريف الشحن</label><input type="number" step="0.01" name="shipping_fee" value="{{ settings.shipping_fee }}" required></div>
                    <button type="submit" class="btn-submit">حفظ كافة تعديلات التصميم والألوان</button>
                </form>
            </div>
        </div>

    {% elif page == 'edit_product' %}
        <div class="admin-card" style="max-width:500px; margin:auto;">
            <h2>✏️ تعديل المنتج #{{ edit_prod.id }}</h2>
            <form action="/admin/edit-product/{{ edit_prod.id }}" method="POST" enctype="multipart/form-data">
                <div class="form-group"><label>الاسم</label><input type="text" name="name" value="{{ edit_prod.name }}" required></div>
                <div class="form-group"><label>السعر</label><input type="number" step="0.01" name="price" value="{{ edit_prod.price }}" required></div>
                <div class="form-group"><label>القسم</label>
                    <select name="category" required style="width:100%; padding:9px; border:1px solid #ccc; border-radius:4px;">
                        {% for cat in custom_categories %}
                            <option value="{{ cat.name }}" {% if edit_prod.category == cat.name %}selected{% endif %}>{{ cat.name }}</option>
                        {% endfor %}
                    </select>
                </div>
                <div class="form-group"><label>رفع صورة جديدة</label><input type="file" name="image_file" accept="image/*"></div>
                <div class="form-group"><label>رابط الصورة الحالي</label><input type="url" name="image_url" value="{{ edit_prod.image }}"></div>
                <button type="submit" class="btn-submit">حفظ التعديلات</button>
            </form>
        </div>

    {% elif page == 'login' %}
        <div class="auth-form" style="max-width:380px; margin:auto;">
            <h2>تسجيل الدخول</h2>
            <form action="/login" method="POST">
                <div class="form-group"><label>البريد الإلكتروني</label><input type="email" name="email" required></div>
                <div class="form-group"><label>كلمة المرور</label><input type="password" name="password" required></div>
                <button type="submit" class="btn-submit">تسجيل الدخول</button>
            </form>
            <a href="/login/google" class="btn-google">🌐 الدخول بواسطة جوجل</a>
        </div>
    {% endif %}
</div>

<!-- زر الشات العائم (متاح فقط للمسجلين) -->
{% if current_user.is_authenticated %}
<div id="support-chat-btn" class="chat-widget-btn">💬</div>
<div id="support-chat-window" class="chat-popup">
    <div class="chat-header"><span>الدعم الفني المباشر</span><button id="close-chat">✕</button></div>
    <div id="chat-messages" class="chat-messages-container"></div>
    <div class="chat-footer">
        <div class="chat-footer-row">
            <input type="text" id="chat-input" placeholder="اكتب رسالتك هنا..." autocomplete="off">
            <button id="chat-send">إرسال</button>
        </div>
    </div>
</div>
{% endif %}

<script>
function toggleSection(id) {
    const box = document.getElementById(id);
    if (box) { box.classList.toggle('open'); }
}

document.addEventListener("DOMContentLoaded", function() {
    {% if current_user.is_authenticated %}
    let sessionId = 'user_session_{{ current_user.id }}';
    const btn = document.getElementById('support-chat-btn');
    const win = document.getElementById('support-chat-window');
    const closeBtn = document.getElementById('close-chat');
    const sendBtn = document.getElementById('chat-send');
    const input = document.getElementById('chat-input');
    const msgContainer = document.getElementById('chat-messages');

    let isChatOpen = false;
    if (btn && win) {
        btn.onclick = () => { isChatOpen = !isChatOpen; win.style.display = isChatOpen ? 'flex' : 'none'; if(isChatOpen) fetchMsgs(); };
        closeBtn.onclick = () => { isChatOpen = false; win.style.display = 'none'; };
    }

    function fetchMsgs() {
        fetch('/api/chat/messages?session_id=' + sessionId).then(res => res.json()).then(data => {
            if (data.status === 'success') {
                msgContainer.innerHTML = '';
                data.messages.forEach(m => {
                    const div = document.createElement('div');
                    div.className = 'chat-msg ' + m.sender_type;
                    div.innerText = m.message;
                    msgContainer.appendChild(div);
                });
                msgContainer.scrollTop = msgContainer.scrollHeight;
            }
        });
    }

    if (sendBtn && input) {
        sendBtn.onclick = sendMsg;
        input.onkeypress = (e) => { if (e.key === 'Enter') sendMsg(); };
    }

    function sendMsg() {
        const text = input.value.trim();
        if (!text) return;
        const fd = new FormData();
        fd.append('action', 'client_send');
        fd.append('session_id', sessionId);
        fd.append('message', text);
        fd.append('client_email', '{{ current_user.email }}');
        fd.append('client_phone', '{{ current_user.phone or "غير محدد" }}');
        
        fetch('/api/chat/send', { method: 'POST', body: fd }).then(res => res.json()).then(data => {
            if (data.status === 'success') { input.value = ''; fetchMsgs(); }
        });
    }
    {% endif %}

    const adminMsgBox = document.getElementById('adminMsgBox');
    const adminReplyForm = document.getElementById('adminReplyForm');
    const adminReplyInput = document.getElementById('adminReplyInput');
    const urlParams = new URLSearchParams(window.location.search);
    const activeSession = urlParams.get('session');

    if (adminMsgBox && activeSession) {
        function fetchAdminMsgs() {
            fetch('/api/chat/messages?session_id=' + activeSession).then(res => res.json()).then(data => {
                if (data.status === 'success') {
                    adminMsgBox.innerHTML = '';
                    data.messages.forEach(m => {
                        const div = document.createElement('div');
                        div.className = 'admin-msg-bubble ' + m.sender_type;
                        div.innerText = m.message;
                        adminMsgBox.appendChild(div);
                    });
                    adminMsgBox.scrollTop = adminMsgBox.scrollHeight;
                }
            });
        }
        fetchAdminMsgs();
        setInterval(fetchAdminMsgs, 4000);

        if (adminReplyForm && adminReplyInput) {
            adminReplyForm.onsubmit = (e) => {
                e.preventDefault();
                const text = adminReplyInput.value.trim();
                if (!text) return;
                const fd = new FormData();
                fd.append('action', 'admin_send');
                fd.append('session_id', activeSession);
                fd.append('message', text);
                fetch('/api/chat/send', { method: 'POST', body: fd }).then(res => res.json()).then(data => {
                    if (data.status === 'success') { adminReplyInput.value = ''; fetchAdminMsgs(); }
                });
            };
        }
    }
});
</script>
<footer><small>©️ 2026 Anything Shop - جميع الحقوق محفوظة.</small></footer>
</body>
</html>
"""

# --- مساعد رفع الصور ---
UPLOAD_FOLDER = 'static/uploads'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

def save_uploaded_file(file_storage):
    if file_storage and file_storage.filename != '':
        if not os.path.exists(UPLOAD_FOLDER):
            os.makedirs(UPLOAD_FOLDER)
        filename = secure_filename(file_storage.filename)
        unique_filename = f"{datetime.utcnow().strftime('%Y%m%d%H%M%S')}_{filename}"
        filepath = os.path.join(UPLOAD_FOLDER, unique_filename)
        file_storage.save(filepath)
        return f"/{filepath}"
    return None

def get_cart_count():
    return sum(session.get('cart', {}).values())

def get_settings():
    settings = SiteSettings.query.first()
    if not settings:
        settings = SiteSettings()
        db.session.add(settings)
        db.session.commit()
    return settings

def get_categories_list():
    cats = Category.query.all()
    if not cats:
        default_cats = ["أحذية", "إلكترونيات", "مأكولات ومشروبات", "لبان وحلويات"]
        for name in default_cats:
            db.session.add(Category(name=name))
        db.session.commit()
        cats = Category.query.all()
    return [c.name for c in cats]

# --- المسارات الأساسية ---
@app.route("/")
def home():
    page_num = int(request.args.get('page', 1))
    per_page = 10
    query = Product.query
    total_count = query.count()
    total_pages = (total_count + per_page - 1) // per_page
    paged_products = query.offset((page_num - 1) * per_page).limit(per_page).all()
    
    return render_template_string(
        HTML_TEMPLATE, page='home', products=paged_products, 
        current_product_page=page_num, total_product_pages=total_pages,
        cart_count=get_cart_count(), categories_list=get_categories_list(), current_cat="All", settings=get_settings()
    )

@app.route("/category/<cat_name>")
def category_view(cat_name):
    page_num = int(request.args.get('page', 1))
    per_page = 10
    query = Product.query.filter_by(category=cat_name)
    total_count = query.count()
    total_pages = (total_count + per_page - 1) // per_page
    paged_products = query.offset((page_num - 1) * per_page).limit(per_page).all()

    return render_template_string(
        HTML_TEMPLATE, page='category', products=paged_products, 
        current_product_page=page_num, total_product_pages=total_pages,
        cart_count=get_cart_count(), categories_list=get_categories_list(), current_cat=cat_name, settings=get_settings()
    )

@app.route("/search")
def search():
    query_str = request.args.get("q", "").strip()
    if not query_str: return redirect(url_for('home'))
    
    page_num = int(request.args.get('page', 1))
    per_page = 10
    filters = [Product.name.ilike(f"%{w}%") for w in query_str.split()] + [Product.category.ilike(f"%{w}%") for w in query_str.split()]
    query = Product.query.filter(db.or_(*filters))
    
    total_count = query.count()
    total_pages = (total_count + per_page - 1) // per_page
    paged_products = query.offset((page_num - 1) * per_page).limit(per_page).all()

    return render_template_string(
        HTML_TEMPLATE, page='search', products=paged_products, search_query=query_str,
        current_product_page=page_num, total_product_pages=total_pages,
        cart_count=get_cart_count(), categories_list=get_categories_list(), current_cat="", settings=get_settings()
    )

# --- مسارات Google OAuth ---
@app.route('/login/google')
def google_login():
    redirect_uri = url_for('google_auth', _external=True)
    return google.authorize_redirect(redirect_uri)

@app.route('/login/google/callback')
def google_auth():
    token = google.authorize_access_token()
    user_info = token.get('userinfo')
    if not user_info:
        resp = google.get('userinfo')
        user_info = resp.json()
    
    email = user_info.get('email')
    first_name = user_info.get('given_name', 'Google')
    last_name = user_info.get('family_name', 'User')
    avatar = user_info.get('picture')

    user = User.query.filter_by(email=email).first()
    if not user:
        user = User(
            first_name=first_name, last_name=last_name, email=email,
            phone="01000000000", address="غير محدد", avatar_url=avatar, auth_provider='google'
        )
        db.session.add(user)
        db.session.commit()
    
    login_user(user)
    return redirect(url_for('home'))

# --- مسارات الشات (مخصصة للمسجلين فقط) ---
@app.route("/api/chat/send", methods=["POST"])
@login_required
def api_chat_send():
    action, session_id, message = request.form.get("action"), request.form.get("session_id"), request.form.get("message", "").strip()
    if not session_id or not message: return jsonify({"status": "error"})
    
    if action == "client_send":
        db.session.add(SupportMessage(
            user_id=current_user.id, session_id=session_id, sender_type="client", message=message, 
            client_email=current_user.email, client_phone=current_user.phone, is_read=False
        ))
        db.session.commit()
        return jsonify({"status": "success"})
    elif action == "admin_send" and current_user.is_admin:
        client_msg = SupportMessage.query.filter_by(session_id=session_id).first()
        u_id = client_msg.user_id if client_msg else current_user.id
        db.session.add(SupportMessage(user_id=u_id, session_id=session_id, sender_type="admin", message=message, is_read=True))
        db.session.commit()
        return jsonify({"status": "success"})
    return jsonify({"status": "error"})

@app.route("/api/chat/messages", methods=["GET"])
@login_required
def api_chat_messages():
    session_id = request.args.get("session_id")
    if not session_id: return jsonify({"status": "error", "messages": []})
    messages = SupportMessage.query.filter_by(session_id=session_id).order_by(SupportMessage.created_at.asc()).all()
    msgs_list = [{"sender_type": m.sender_type, "message": m.message} for m in messages]
    return jsonify({"status": "success", "messages": msgs_list})

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        f_name, l_name, email, password = request.form.get("first_name"), request.form.get("last_name"), request.form.get("email"), request.form.get("password")
        if User.query.filter_by(email=email).first():
            flash("البريد مسجل مسبقاً.")
            return redirect(url_for('register'))
        new_user = User(
            first_name=f_name, last_name=l_name, email=email,
            password_hash=generate_password_hash(password, method='scrypt'),
            phone=request.form.get("phone"), address=request.form.get("address"), birth_date=request.form.get("birth_date")
        )
        db.session.add(new_user)
        db.session.commit()
        login_user(new_user)
        return redirect(url_for('home'))
    return render_template_string(HTML_TEMPLATE, page='register', cart_count=get_cart_count(), categories_list=get_categories_list(), settings=get_settings())

@app.route("/profile", methods=["GET", "POST"])
@login_required
def profile():
    if request.method == "POST":
        current_user.first_name, current_user.last_name = request.form.get("first_name"), request.form.get("last_name")
        current_user.phone, current_user.address = request.form.get("phone"), request.form.get("address")
        db.session.commit()
        flash("تم التحديث بنجاح!")
        return redirect(url_for('profile'))
    return render_template_string(HTML_TEMPLATE, page='profile', cart_count=get_cart_count(), categories_list=get_categories_list(), settings=get_settings())

@app.route("/add-to-cart", methods=["POST"])
def add_to_cart():
    p_id = str(request.form.get("product_id"))
    cart = session.get('cart', {})
    cart[p_id] = cart.get(p_id, 0) + 1
    session['cart'] = cart
    flash("تمت الإضافة للسلة!")
    return redirect(request.referrer or url_for('home'))

@app.route("/cart")
def view_cart():
    cart = session.get('cart', {})
    cart_items, total_price = [], 0.0
    for p_id_str, qty in cart.items():
        product = Product.query.get(int(p_id_str))
        if product:
            total_price += product.price * qty
            cart_items.append({"name": product.name, "price": product.price, "qty": qty})
    settings = get_settings()
    final_total = total_price + settings.shipping_fee
    return render_template_string(HTML_TEMPLATE, page='cart', cart_items=cart_items, total_price=total_price, final_total=final_total, cart_count=get_cart_count(), categories_list=get_categories_list(), current_cat="Cart", settings=settings)

@app.route("/checkout", methods=["POST"])
@login_required
def checkout():
    cart = session.get('cart', {})
    if not cart: return redirect(url_for('home'))
    order_items, items_price = [], 0.0
    for p_id_str, qty in cart.items():
        product = Product.query.get(int(p_id_str))
        if product:
            items_price += product.price * qty
            order_items.append({"name": product.name, "price": product.price, "qty": qty})
    settings = get_settings()
    new_order = Order(
        user_id=current_user.id, phone=request.form.get("phone"), address=request.form.get("address"), 
        payment_method="Cash", items_price=items_price, shipping_fee=settings.shipping_fee, 
        total_price=items_price + settings.shipping_fee, items_json=json.dumps(order_items)
    )
    db.session.add(new_order)
    db.session.commit()
    session['cart'] = {}
    flash("تم تسجيل الطلب بنجاح!")
    return redirect(url_for('my_orders'))

@app.route("/orders")
@login_required
def my_orders():
    return render_template_string(HTML_TEMPLATE, page='orders', orders=Order.query.filter_by(user_id=current_user.id).all(), cart_count=get_cart_count(), categories_list=get_categories_list(), current_cat="Orders", settings=get_settings())

# --- لوحة تحكم الأدمن ---
@app.route("/admin")
@login_required
def admin_panel():
    if not current_user.is_admin: return redirect(url_for('home'))
    
    order_page = int(request.args.get('order_page', 1))
    orders_per_page = 10
    all_orders_query = Order.query.order_by(Order.created_at.desc())
    total_orders_count = all_orders_query.count()
    total_order_pages = (total_orders_count + orders_per_page - 1) // orders_per_page
    paged_orders = all_orders_query.offset((order_page - 1) * orders_per_page).limit(orders_per_page).all()

    chat_page = int(request.args.get('chat_page', 1))
    chats_per_page = 10
    subquery = db.session.query(SupportMessage.session_id, db.func.max(SupportMessage.created_at).label('max_time')).group_by(SupportMessage.session_id).subquery()
    raw_sessions = db.session.query(subquery.c.session_id, subquery.c.max_time.label('last_time')).order_by(subquery.c.max_time.desc()).all()
    
    chat_sessions = []
    for s in raw_sessions:
        unread_cnt = SupportMessage.query.filter_by(session_id=s.session_id, sender_type='client', is_read=False).count()
        first_msg = SupportMessage.query.filter_by(session_id=s.session_id, sender_type='client').first()
        chat_sessions.append({
            "session_id": s.session_id, "last_time": str(s.last_time), "unread_count": unread_cnt,
            "email": first_msg.client_email if first_msg else "عميل مسجل"
        })
    
    total_chat_pages = (len(chat_sessions) + chats_per_page - 1) // chats_per_page
    paged_chats = chat_sessions[(chat_page - 1) * chats_per_page : chat_page * chats_per_page]
    
    active_session = request.args.get("session")
    if not active_session and paged_chats: active_session = paged_chats[0]["session_id"]

    return render_template_string(
        HTML_TEMPLATE, page='admin', 
        paged_orders=paged_orders, total_orders_count=total_orders_count, total_order_pages=total_order_pages, order_page=order_page,
        paged_chats=paged_chats, total_chat_pages=total_chat_pages, chat_page=chat_page, active_session=active_session,
        custom_categories=Category.query.all(), all_products=Product.query.all(),
        cart_count=get_cart_count(), categories_list=get_categories_list(), current_cat="Admin", settings=get_settings()
    )

@app.route("/admin/mark-order-read/<int:order_id>")
@login_required
def mark_order_read(order_id):
    if not current_user.is_admin: return redirect(url_for('home'))
    ord = Order.query.get_or_404(order_id)
    ord.is_read = True
    db.session.commit()
    return redirect(url_for('admin_panel'))

@app.route("/admin/add-category", methods=["POST"])
@login_required
def admin_add_category():
    if not current_user.is_admin: return redirect(url_for('home'))
    name = request.form.get("cat_name", "").strip()
    if name and not Category.query.filter_by(name=name).first():
        db.session.add(Category(name=name))
        db.session.commit()
        flash("تم إضافة القسم بنجاح!")
    return redirect(url_for('admin_panel'))

@app.route("/admin/edit-category/<int:cat_id>", methods=["POST"])
@login_required
def admin_edit_category(cat_id):
    if not current_user.is_admin: return redirect(url_for('home'))
    cat = Category.query.get_or_404(cat_id)
    new_name = request.form.get("new_name", "").strip()
    if new_name:
        old_name = cat.name
        cat.name = new_name
        Product.query.filter_by(category=old_name).update({Product.category: new_name})
        db.session.commit()
        flash("تم تحديث اسم القسم بنجاح!")
    return redirect(url_for('admin_panel'))

@app.route("/admin/delete-category/<int:cat_id>")
@login_required
def admin_delete_category(cat_id):
    if not current_user.is_admin: return redirect(url_for('home'))
    db.session.delete(Category.query.get_or_404(cat_id))
    db.session.commit()
    flash("تم حذف القسم بنجاح.")
    return redirect(url_for('admin_panel'))

@app.route("/admin/add-product", methods=["POST"])
@login_required
def admin_add_product():
    if not current_user.is_admin: return redirect(url_for('home'))
    image_url = save_uploaded_file(request.files.get("image_file"))
    if not image_url:
        image_url = request.form.get("image_url", "https://via.placeholder.com/400")

    db.session.add(Product(
        name=request.form.get("name"), price=float(request.form.get("price")),
        category=request.form.get("category"), image=image_url
    ))
    db.session.commit()
    flash("تمت إضافة المنتج بنجاح!")
    return redirect(url_for('admin_panel'))

@app.route("/admin/edit-product/<int:prod_id>", methods=["GET", "POST"])
@login_required
def admin_edit_product(prod_id):
    if not current_user.is_admin: return redirect(url_for('home'))
    prod = Product.query.get_or_404(prod_id)
    if request.method == "POST":
        prod.name = request.form.get("name")
        prod.price = float(request.form.get("price"))
        prod.category = request.form.get("category")
        
        uploaded_img = save_uploaded_file(request.files.get("image_file"))
        if uploaded_img:
            prod.image = uploaded_img
        elif request.form.get("image_url"):
            prod.image = request.form.get("image_url")
            
        db.session.commit()
        flash("تم التعديل بنجاح!")
        return redirect(url_for('admin_panel'))
    return render_template_string(HTML_TEMPLATE, page='edit_product', edit_prod=prod, custom_categories=Category.query.all(), cart_count=get_cart_count(), categories_list=get_categories_list(), settings=get_settings())

@app.route("/admin/delete-product/<int:prod_id>")
@login_required
def admin_delete_product(prod_id):
    if not current_user.is_admin: return redirect(url_for('home'))
    db.session.delete(Product.query.get_or_404(prod_id))
    db.session.commit()
    flash("تم حذف المنتج.")
    return redirect(url_for('admin_panel'))

@app.route("/admin/update-settings", methods=["POST"])
@login_required
def admin_update_settings():
    if not current_user.is_admin: return redirect(url_for('home'))
    settings = get_settings()
    settings.header_color = request.form.get("header_color")
    settings.primary_color = request.form.get("primary_color")
    settings.price_color = request.form.get("price_color")
    settings.bg_color = request.form.get("bg_color")
    settings.text_color = request.form.get("text_color")
    settings.icon_color = request.form.get("icon_color")
    settings.card_bg_color = request.form.get("card_bg_color")
    settings.shipping_fee = float(request.form.get("shipping_fee"))
    
    uploaded_logo = save_uploaded_file(request.files.get("logo_file"))
    if uploaded_logo:
        settings.logo_url = uploaded_logo
    elif request.form.get("logo_url"):
        settings.logo_url = request.form.get("logo_url")
        
    db.session.commit()
    flash("تم تحديث إعدادات التصميم بالكامل بنجاح!")
    return redirect(url_for('admin_panel'))

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        user = User.query.filter_by(email=request.form.get("email")).first()
        if user and user.password_hash and check_password_hash(user.password_hash, request.form.get("password")):
            login_user(user)
            return redirect(url_for('admin_panel' if user.is_admin else 'home'))
        flash("خطأ في البيانات.")
    return render_template_string(HTML_TEMPLATE, page='login', cart_count=get_cart_count(), categories_list=get_categories_list(), settings=get_settings())

@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for('home'))

def seed_data():
    if Category.query.count() == 0:
        for c in ["أحذية", "إلكترونيات", "مأكولات ومشروبات", "لبان وحلويات"]:
            db.session.add(Category(name=c))
        db.session.commit()
    if Product.query.count() == 0:
        db.session.add_all([
            Product(name="حذاء رياضي أنيق", price=450.0, category="أحذية", image="https://images.unsplash.com/photo-1542291026-7eec264c27ff?w=400"),
            Product(name="سماعة بلوتوث لاسلكية", price=650.0, category="إلكترونيات", image="https://images.unsplash.com/photo-1505740420928-5e560c06d30e?w=400"),
            Product(name="لبان نعناع منعش", price=15.0, category="لبان وحلويات", image="https://images.unsplash.com/photo-1582058091505-f87a2e55a40f?w=400")
        ])
        db.session.commit()
    admin = User.query.filter_by(email="admin@shop.com").first()
    if not admin:
        db.session.add(User(
            first_name="أحمد", last_name="الأدمن", email="admin@shop.com", 
            password_hash=generate_password_hash("admin123", method='scrypt'), 
            is_admin=True, phone="01000000000", address="القاهرة"
        ))
        db.session.commit()
    else:
        admin.is_admin = True
        db.session.commit()

with app.app_context():
    db.create_all()
    seed_data()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
