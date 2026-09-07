import os
import json
import hmac
import hashlib
import base64
import requests
from collections import defaultdict
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
# لو فيه DATABASE_URL (زي قاعدة بيانات Render PostgreSQL) بيستخدمها، وإلا بيرجع لملف SQLite محلي للتجربة فقط
_database_url = os.environ.get("DATABASE_URL", "sqlite:///shop_demo.db")
if _database_url.startswith("postgres://"):
    # SQLAlchemy الحديث محتاج postgresql:// مش postgres:// اللي بيديها Render
    _database_url = _database_url.replace("postgres://", "postgresql://", 1)
app.config['SQLALCHEMY_DATABASE_URI'] = _database_url
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
    used_coupon = db.Column(db.Boolean, default=False)
    login_count = db.Column(db.Integer, default=0)
    orders = db.relationship('Order', backref='customer', lazy=True)

class Product(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    price = db.Column(db.Float, nullable=False)
    category = db.Column(db.String(100), nullable=False)
    image = db.Column(db.Text, nullable=False)
    is_sold_out = db.Column(db.Boolean, default=False)
    description = db.Column(db.Text, nullable=True)

    @property
    def gallery(self):
        """كل صور المنتج: الصورة الرئيسية + الصور الإضافية، حد أقصى 10 صور"""
        imgs = [self.image] + [im.image_url for im in self.extra_images]
        return imgs[:10]

class ProductImage(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=False)
    image_url = db.Column(db.Text, nullable=False)
    product = db.relationship('Product', backref=db.backref('extra_images', lazy=True, cascade="all, delete-orphan"))

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
    logo_url = db.Column(db.Text, nullable=True)
    total_visits = db.Column(db.Integer, default=0)
    site_name = db.Column(db.String(150), default='Anything Shop')
    welcome_title = db.Column(db.String(200), default='أهلاً بك في متجرنا التجاري المتكامل!')
    welcome_text = db.Column(db.Text, default='استمتع بتجربة تسوق فريدة، عروض حصرية على أول طلب. استخدم كود الخصم (Anything 10) للحصول على خصم 10% على أول طلب.')
    banner_image_url = db.Column(db.Text, nullable=True)
    coupon_code = db.Column(db.String(100), default='Anything 10')
    usd_exchange_rate = db.Column(db.Float, default=50.0)

class Order(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    phone = db.Column(db.String(20), nullable=False)
    address = db.Column(db.Text, nullable=False)
    payment_method = db.Column(db.String(50), nullable=False)
    payment_status = db.Column(db.String(50), default='Pending')
    items_price = db.Column(db.Float, nullable=False)
    shipping_fee = db.Column(db.Float, nullable=False, default=50.0)
    discount_amount = db.Column(db.Float, nullable=False, default=0.0)
    total_price = db.Column(db.Float, nullable=False)
    items_json = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_read = db.Column(db.Boolean, default=False)
    paymob_order_id = db.Column(db.String(100), nullable=True)
    order_code = db.Column(db.String(100), nullable=True)
    admin_notes = db.Column(db.Text, nullable=True)
    paypal_order_id = db.Column(db.String(100), nullable=True)

    @property
    def items_list(self):
        try:
            return json.loads(self.items_json)
        except Exception:
            return []

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
    <title>{{ settings.site_name or 'Anything Shop' }} - متجر احترافي</title>
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
        
        .welcome-banner { background: linear-gradient(135deg, #232f3e, #37475a); color: white; padding: 15px 20px; border-radius: 8px; margin-bottom: 20px; display: flex; justify-content: space-between; align-items: center; box-shadow: 0 4px 6px rgba(0,0,0,0.1); }
        .welcome-banner h3 { margin: 0; color: var(--primary-color); font-size: 18px; }
        .welcome-banner p { margin: 5px 0 0; font-size: 13px; color: #ddd; }

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
        .payment-status-box { padding: 30px; text-align: center; border-radius: 8px; margin: 20px auto; max-width: 500px; }
        .payment-status-box.success { background: #d4edda; color: #155724; border: 1px solid #c3e6cb; }
        .payment-status-box.failed { background: #f8d7da; color: #721c24; border: 1px solid #f5c6cb; }
        .payment-status-box.pending { background: #fff3cd; color: #856404; border: 1px solid #ffeeba; }
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
        {{ settings.site_name or 'Anything Shop' }}
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
                    {% if admin_notif_count and admin_notif_count > 0 %}
                    <span id="global-admin-badge" class="badge-notification">{{ admin_notif_count }}</span>
                    {% endif %}
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
        {% if settings.banner_image_url %}
            <img src="{{ settings.banner_image_url }}" alt="عرض خاص" style="width:100%; max-height:280px; object-fit:cover; border-radius:8px; margin-bottom:20px;">
        {% endif %}
        <div class="welcome-banner">
            <div>
                <h3>{{ settings.welcome_title or ('أهلاً بك في متجر ' ~ (settings.site_name or 'Anything Shop') ~ '!') }}</h3>
                <p>{{ settings.welcome_text }}</p>
            </div>
        </div>

        <h2>{{ 'نتائج البحث عن: ' ~ search_query if page == 'search' else ('منتجات قسم: ' ~ current_cat if page == 'category' else 'المنتجات المتاحة') }}</h2>
        {% macro product_card(product) %}
        <div class="card" style="{% if product.is_sold_out %}opacity:0.6;{% endif %}position:relative;">
            {% if product.is_sold_out %}
            <div style="position:absolute; top:8px; left:8px; background:#dc3545; color:#fff; font-size:11px; font-weight:bold; padding:3px 8px; border-radius:4px; z-index:2;">نفذت الكمية</div>
            {% endif %}
            <div>
                <a href="/product/{{ product.id }}" style="text-decoration:none; color:inherit;">
                    <img src="{{ product.image }}" alt="{{ product.name }}">
                    <div class="card-title">{{ product.name }}</div>
                </a>
                <small style="color:#565959;">{{ product.category }}</small>
            </div>
            <div>
                <div class="card-price">{{ product.price }} ج.م</div>
                {% if product.is_sold_out %}
                    <button type="button" class="btn-add" disabled style="background:#ccc; border-color:#bbb; cursor:not-allowed;">نفذت الكمية</button>
                {% else %}
                <form action="/add-to-cart" method="POST" style="display:flex; gap:6px; align-items:center;">
                    <input type="hidden" name="product_id" value="{{ product.id }}">
                    <input type="number" name="qty" value="1" min="1" max="99" style="width:55px; padding:6px 4px; border:1px solid #ccc; border-radius:4px; text-align:center; font-size:13px;">
                    <button type="submit" class="btn-add" style="flex:1;">أضف إلى السلة</button>
                </form>
                {% endif %}
            </div>
        </div>
        {% endmacro %}
        {% if products %}
            {% if page == 'home' %}
                {% for cat_name, group_products in products|groupby('category') %}
                    <h3 style="margin:22px 0 10px; padding-bottom:6px; border-bottom:2px solid var(--primary-color); color: var(--header-bg);">{{ cat_name }}</h3>
                    <div class="products-grid">
                        {% for product in group_products %}
                            {{ product_card(product) }}
                        {% endfor %}
                    </div>
                {% endfor %}
            {% else %}
            <div class="products-grid">
                {% for product in products %}
                    {{ product_card(product) }}
                {% endfor %}
            </div>
            {% endif %}

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

            {% if current_user.auth_provider != 'google' %}
            <hr style="margin:20px 0; border:none; border-top:1px solid #ddd;">
            <h3>🔒 تغيير كلمة المرور</h3>
            <form action="/profile/change-password" method="POST">
                <div class="form-group"><label>كلمة المرور الحالية</label><input type="password" name="current_password" required></div>
                <div class="form-group"><label>كلمة المرور الجديدة</label><input type="password" name="new_password" required minlength="6"></div>
                <div class="form-group"><label>تأكيد كلمة المرور الجديدة</label><input type="password" name="confirm_password" required minlength="6"></div>
                <button type="submit" class="btn-submit">تحديث كلمة المرور</button>
            </form>
            {% else %}
            <p style="color:#888; font-size:12px; margin-top:15px;">حسابك مسجل عن طريق Google، فمفيش كلمة مرور لتغييرها هنا.</p>
            {% endif %}
        </div>

    {% elif page == 'cart' %}
        <h2>سلة التسوق</h2>
        {% if cart_items %}
            <table class="cart-table">
                <thead><tr><th>المنتج</th><th>السعر</th><th>الكمية</th><th>الإجمالي</th><th>إجراء</th></tr></thead>
                <tbody>
                    {% for item in cart_items %}
                    <tr>
                        <td>{{ item.name }}</td>
                        <td>{{ item.price }} ج.م</td>
                        <td>
                            <form action="/cart/update-qty" method="POST" style="display:flex; gap:5px; align-items:center;">
                                <input type="hidden" name="product_id" value="{{ item.id }}">
                                <input type="number" name="qty" value="{{ item.qty }}" min="1" max="99" style="width:55px; padding:5px; border:1px solid #ccc; border-radius:4px; text-align:center;">
                                <button type="submit" style="background:#232f3e; color:#fff; border:none; padding:5px 10px; border-radius:4px; cursor:pointer; font-size:11px;">تحديث</button>
                            </form>
                        </td>
                        <td>{{ "%.2f"|format(item.price * item.qty) }} ج.م</td>
                        <td>
                            <form action="/cart/remove-item" method="POST">
                                <input type="hidden" name="product_id" value="{{ item.id }}">
                                <button type="submit" class="btn-danger" onclick="return confirm('حذف المنتج من السلة؟')">حذف</button>
                            </form>
                        </td>
                    </tr>
                    {% endfor %}
                </tbody>
            </table>
            
            <div style="background:var(--card-bg); padding:15px; border-radius:8px; margin-bottom:15px; border:1px solid #ccc;">
                <form action="/apply-coupon" method="POST" style="display:flex; gap:10px; align-items:center;">
                    <input type="text" name="coupon_code" placeholder="أدخل كود الخصم (مثال: {{ settings.coupon_code or 'Anything 10' }})" value="{{ session.get('applied_coupon', '') }}" style="flex:1; padding:8px; border:1px solid #ccc; border-radius:4px;">
                    <button type="submit" style="background:#232f3e; color:#fff; border:none; padding:8px 15px; border-radius:4px; font-weight:bold; cursor:pointer;">تطبيق الكود</button>
                </form>
                {% if session.get('applied_coupon') == (settings.coupon_code or 'Anything 10') %}
                    <p style="color: green; margin-top: 8px; font-weight: bold; font-size: 13px;">✅ تم تطبيق خصم العرض الأول (10%) بنجاح!</p>
                {% endif %}
            </div>

            <div style="text-align:left; background:var(--card-bg); padding:12px; border-radius:8px; margin-bottom:15px;">
                <p>إجمالي المنتجات: {{ "%.2f"|format(total_price) }} ج.م</p>
                {% if discount_amount > 0 %}
                    <p style="color: green;">قيمة الخصم (10%): -{{ "%.2f"|format(discount_amount) }} ج.م</p>
                {% endif %}
                <p>مصاريف الشحن: <strong>{{ "%.2f"|format(settings.shipping_fee) }} ج.م</strong></p>
                <h3 style="color: var(--price-color);">الإجمالي النهائي: {{ "%.2f"|format(final_total) }} ج.م</h3>
            </div>
            
            <div class="checkout-form">
                <h3>تفاصيل الشحن والتسليم</h3>
                <form action="/checkout" method="POST">
                    <div class="form-group"><label>رقم الهاتف للتواصل</label><input type="tel" name="phone" value="{{ current_user.phone or '' }}" required></div>
                    <div class="form-group"><label>عنوان التوصيل بالكامل</label><textarea name="address" rows="2" required>{{ current_user.address or '' }}</textarea></div>
                    <div class="form-group">
                        <label>طريقة الدفع</label>
                        <select name="payment_method" required>
                            <option value="cod">الدفع عند الاستلام (كاش)</option>
                            <option value="card">بطاقة ائتمان (فيزا/ماستركارد) عبر Paymob</option>
                            <option value="paypal">الدفع عبر PayPal (بالدولار الأمريكي)</option>
                        </select>
                    </div>
                    <button type="submit" class="btn-submit">تأكيد ومتابعة الطلب</button>
                </form>
            </div>
        {% else %}
            <p>سلة التسوق فارغة حالياً.</p>
        {% endif %}

    {% elif page == 'product_detail' %}
        <div style="display:flex; gap:25px; flex-wrap:wrap; background:var(--card-bg); padding:20px; border-radius:8px; border:1px solid #ddd;">
            <div style="flex:1; min-width:280px; position:relative;">
                {% if product.is_sold_out %}
                <div style="position:absolute; top:8px; left:8px; background:#dc3545; color:#fff; font-size:12px; font-weight:bold; padding:4px 10px; border-radius:4px; z-index:2;">نفذت الكمية</div>
                {% endif %}
                <img id="mainProductImage" src="{{ product.gallery[0] }}" alt="{{ product.name }}" style="width:100%; max-height:400px; object-fit:cover; border-radius:8px;">
                {% if product.gallery|length > 1 %}
                <div style="display:flex; gap:8px; margin-top:10px; overflow-x:auto; padding-bottom:6px; -webkit-overflow-scrolling:touch;">
                    {% for img_url in product.gallery %}
                    <img src="{{ img_url }}" onclick="document.getElementById('mainProductImage').src='{{ img_url }}'" style="width:60px; height:60px; min-width:60px; object-fit:cover; border-radius:6px; border:2px solid #ddd; cursor:pointer;">
                    {% endfor %}
                </div>
                {% endif %}
            </div>
            <div style="flex:1; min-width:280px;">
                <h2>{{ product.name }}</h2>
                <p style="color:#565959;">القسم: {{ product.category }}</p>
                <h3 style="color: var(--price-color); font-size:26px;">{{ product.price }} ج.م</h3>
                {% if product.description %}
                    <p style="line-height:1.8; margin:15px 0;">{{ product.description }}</p>
                {% endif %}
                {% if product.is_sold_out %}
                    <button type="button" class="btn-add" disabled style="background:#ccc; border-color:#bbb; cursor:not-allowed; max-width:250px;">نفذت الكمية</button>
                {% else %}
                <form action="/add-to-cart" method="POST" style="display:flex; gap:8px; align-items:center; max-width:300px; margin-top:15px;">
                    <input type="hidden" name="product_id" value="{{ product.id }}">
                    <input type="number" name="qty" value="1" min="1" max="99" style="width:70px; padding:9px; border:1px solid #ccc; border-radius:4px; text-align:center;">
                    <button type="submit" class="btn-add" style="flex:1;">أضف إلى السلة</button>
                </form>
                {% endif %}
            </div>
        </div>

        {% if related_products %}
        <h3 style="margin:30px 0 15px;">🛍️ منتجات تانية ممكن تعجبك</h3>
        {% macro _rp_card(product) %}
        <div class="card" style="{% if product.is_sold_out %}opacity:0.6;{% endif %}">
            <div>
                <a href="/product/{{ product.id }}" style="text-decoration:none; color:inherit;">
                    <img src="{{ product.image }}" alt="{{ product.name }}">
                    <div class="card-title">{{ product.name }}</div>
                </a>
                <small style="color:#565959;">{{ product.category }}</small>
            </div>
            <div>
                <div class="card-price">{{ product.price }} ج.م</div>
                {% if not product.is_sold_out %}
                <form action="/add-to-cart" method="POST">
                    <input type="hidden" name="product_id" value="{{ product.id }}">
                    <input type="hidden" name="qty" value="1">
                    <button type="submit" class="btn-add">أضف إلى السلة</button>
                </form>
                {% else %}
                <button type="button" class="btn-add" disabled style="background:#ccc; cursor:not-allowed;">نفذت الكمية</button>
                {% endif %}
            </div>
        </div>
        {% endmacro %}
        <div class="products-grid">
            {% for rp in related_products %}
                {{ _rp_card(rp) }}
            {% endfor %}
        </div>
        {% endif %}

    {% elif page == 'payment_result' %}
        <div class="payment-status-box {{ 'success' if order.payment_status == 'Paid' else ('failed' if order.payment_status == 'Failed' else 'pending') }}">
            {% if order.payment_status == 'Paid' %}
                <h2>✅ تم الدفع بنجاح!</h2>
                <p>شكراً لك، تم تأكيد طلبك رقم #{{ order.id }} وسيتم تجهيزه للشحن.</p>
            {% elif order.payment_status == 'Failed' %}
                <h2>❌ فشلت عملية الدفع</h2>
                <p>لم تتم عملية الدفع بنجاح لطلبك رقم #{{ order.id }}. برجاء المحاولة مرة أخرى أو التواصل مع الدعم الفني.</p>
            {% else %}
                <h2>⏳ جاري تأكيد الدفع...</h2>
                <p>طلبك رقم #{{ order.id }} قيد المراجعة، سيتم تحديث الحالة تلقائياً خلال لحظات.</p>
            {% endif %}
            <a href="/orders" class="nav-btn" style="display:inline-block; margin-top:15px;">عرض طلباتي</a>
        </div>

    {% elif page == 'orders' %}
        <h2>طلباتي السابقة</h2>
        {% for order in orders %}
            <div style="background:var(--card-bg); padding:15px; border-radius:8px; margin-bottom:15px; border:1px solid #ccc;">
                <h4>طلب رقم #{{ order.id }} - {{ order.created_at.strftime('%Y-%m-%d %H:%M') }}</h4>
                {% if order.order_code %}<p><strong>كود الأوردر:</strong> {{ order.order_code }}</p>{% endif %}
                <p><strong>طريقة الدفع:</strong> {{ order.payment_method }}</p>
                <p><strong>حالة الدفع:</strong> {{ order.payment_status }}</p>
                <p><strong>رقم الهاتف:</strong> {{ order.phone }}</p>
                <p><strong>العنوان:</strong> {{ order.address }}</p>
                {% if order.discount_amount > 0 %}
                    <p><strong>الخصم المطبق:</strong> {{ "%.2f"|format(order.discount_amount) }} ج.م</p>
                {% endif %}
                <h3 style="color: var(--price-color);">المبلغ الإجمالي: {{ "%.2f"|format(order.total_price) }} ج.م</h3>
            </div>
        {% endfor %}

    {% elif page == 'admin' %}
        <h2>⚙️ لوحة تحكم الأدمن</h2>

        <div class="admin-section-box">
            <div class="admin-section-header" onclick="toggleSection('sec-stats')">
                <span>📊 إحصائيات الموقع</span>
                <span>▼</span>
            </div>
            <div id="sec-stats" class="admin-section-content">
                <div style="display:grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 15px; margin-bottom:20px;">
                    <div style="background:#f1f2f6; border-radius:8px; padding:18px; text-align:center;">
                        <div style="font-size:28px; font-weight:bold; color: var(--primary-color);">{{ total_visits }}</div>
                        <div style="font-size:13px; color:#555; margin-top:5px;">إجمالي عدد زيارات الموقع (كل الزوار)</div>
                    </div>
                    <div style="background:#f1f2f6; border-radius:8px; padding:18px; text-align:center;">
                        <div style="font-size:28px; font-weight:bold; color: var(--primary-color);">{{ total_registered_users }}</div>
                        <div style="font-size:13px; color:#555; margin-top:5px;">إجمالي عدد الحسابات المسجلة</div>
                    </div>
                    <div style="background:#f1f2f6; border-radius:8px; padding:18px; text-align:center;">
                        <div style="font-size:28px; font-weight:bold; color: var(--primary-color);">{{ total_logins }}</div>
                        <div style="font-size:13px; color:#555; margin-top:5px;">إجمالي عدد مرات تسجيل الدخول</div>
                    </div>
                </div>

                <h4 style="margin-bottom:10px;">📦 إجمالي الكمية المطلوبة لكل منتج (من كل الأوردرات)</h4>
                {% if product_totals_sorted %}
                <table class="admin-table">
                    <thead><tr><th>المنتج</th><th>إجمالي العدد المطلوب</th></tr></thead>
                    <tbody>
                        {% for name, qty in product_totals_sorted %}
                        <tr><td>{{ name }}</td><td>{{ qty }}</td></tr>
                        {% endfor %}
                    </tbody>
                </table>
                {% else %}
                <p style="color:#666;">لا يوجد طلبات مسجلة حتى الآن.</p>
                {% endif %}
            </div>
        </div>

        <div class="admin-section-box">
            <div class="admin-section-header" onclick="toggleSection('sec-customers')">
                <span>👥 كل الحسابات المسجلة (إجمالي: {{ total_registered_users }})</span>
                <span>▼</span>
            </div>
            <div id="sec-customers" class="admin-section-content">
                <form action="/admin/search-customer" method="GET" style="display:flex; gap:10px; margin-bottom:15px;">
                    <input type="text" name="q" placeholder="ابحث بالإيميل أو رقم الهاتف..." required style="flex:1; padding:9px; border:1px solid #ccc; border-radius:4px;">
                    <button type="submit" style="background:var(--primary-color); border:none; padding:9px 18px; border-radius:4px; font-weight:bold; cursor:pointer;">🔍 بحث</button>
                </form>
                <table class="admin-table">
                    <thead><tr><th>#</th><th>الاسم</th><th>البريد الإلكتروني</th><th>الهاتف</th><th>عدد مرات الدخول</th><th>نوع الحساب</th><th>إجراء</th></tr></thead>
                    <tbody>
                        {% for u in paged_customers %}
                        <tr>
                            <td>{{ u.id }}</td>
                            <td>{{ u.first_name }} {{ u.last_name }}</td>
                            <td>{{ u.email }}</td>
                            <td>{{ u.phone or '-' }}</td>
                            <td>{{ u.login_count or 0 }}</td>
                            <td>{{ 'أدمن' if u.is_admin else 'عميل' }}</td>
                            <td><a href="/admin/customer/{{ u.id }}" class="btn-edit">عرض البروفايل</a></td>
                        </tr>
                        {% endfor %}
                    </tbody>
                </table>
                {% if total_customer_pages > 1 %}
                <div class="pagination-box">
                    {% for p in range(1, total_customer_pages + 1) %}
                        <a href="/admin?customer_page={{ p }}" class="{% if customer_page == p %}active{% endif %}">{{ p }}</a>
                    {% endfor %}
                </div>
                {% endif %}
            </div>
        </div>


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
                                        <strong>{{ conv.display_name }}</strong><br>
                                        <small style="color:#888;">{{ conv.email }}</small><br>
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
                            {% if active_customer %}
                            <div style="background:#f1f2f6; padding:10px 14px; border-bottom:1px solid #ddd; font-size:12px; line-height:1.8;">
                                <strong>{{ active_customer.first_name }} {{ active_customer.last_name }}</strong>
                                <a href="/admin/customer/{{ active_customer.id }}" style="color:#0084ff; text-decoration:none; margin-right:8px;">(عرض البروفايل الكامل)</a><br>
                                📧 {{ active_customer.email }} &nbsp;|&nbsp; 📱 {{ active_customer.phone or '-' }}<br>
                                📍 {{ active_customer.address or '-' }}
                            </div>
                            {% endif %}
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
                <span>📦 إدارة الأوردرات وتفاصيل الدفع (إجمالي: {{ total_orders_count }})</span>
                <span>▼</span>
            </div>
            <div id="sec-orders" class="admin-section-content">
                <table class="admin-table">
                    <thead><tr><th>رقم الطلب</th><th>الكود</th><th>العميل</th><th>الهاتف</th><th>المنتجات المطلوبة</th><th>طريقة الدفع</th><th>العنوان</th><th>الإجمالي</th><th>الحالة</th><th>إجراء</th></tr></thead>
                    <tbody>
                        {% for ord in paged_orders %}
                        <tr {% if not ord.is_read %}style="background-color: #fff9db;"{% endif %}>
                            <td>#{{ ord.id }}</td>
                            <td>{{ ord.order_code or '-' }}</td>
                            <td>{{ ord.customer.first_name }} {{ ord.customer.last_name }}</td>
                            <td>{{ ord.phone }}</td>
                            <td>
                                <ul style="margin:0; padding-right:16px; list-style:disc;">
                                {% for it in ord.items_list %}
                                    <li>{{ it.name }} × {{ it.qty }}</li>
                                {% endfor %}
                                </ul>
                            </td>
                            <td><span style="background: #e2e8f0; padding: 3px 6px; border-radius: 4px; font-weight: bold;">{{ ord.payment_method }}</span></td>
                            <td>{{ ord.address }}</td>
                            <td>{{ "%.2f"|format(ord.total_price) }} ج.م</td>
                            <td>{{ ord.payment_status }}</td>
                            <td>
                                <a href="/admin/order/{{ ord.id }}" class="btn-edit">تفاصيل / تعديل</a>
                                {% if not ord.is_read %}<a href="/admin/mark-order-read/{{ ord.id }}" style="color:#0084ff; text-decoration:none; display:block; margin-top:4px; font-size:11px;">تحديد كمقروء</a>{% endif %}
                            </td>
                        </tr>
                        {% endfor %}
                    </tbody>
                </table>
                {% if total_order_pages > 1 %}
                <div class="pagination-box">
                    {% for p in range(1, total_order_pages + 1) %}
                        <a href="/admin?order_page={{ p }}{% if active_session %}&session={{ active_session }}&chat_page={{ chat_page }}{% endif %}" class="{% if order_page == p %}active{% endif %}">{{ p }}</a>
                    {% endfor %}
                </div>
                {% endif %}
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
                    <div class="form-group"><label>وصف المنتج (هيظهر في صفحة تفاصيل المنتج)</label><textarea name="description" rows="3" placeholder="اكتب وصف المنتج هنا..."></textarea></div>
                    <div class="form-group"><label>رفع صورة المنتج الرئيسية</label><input type="file" name="image_file" accept="image/*"></div>
                    <div class="form-group"><label>أو رابط صورة خارجي</label><input type="url" name="image_url"></div>
                    <div class="form-group"><label>صور إضافية للمنتج (اختياري، لحد 9 صور زيادة عن الرئيسية)</label><input type="file" name="extra_images" accept="image/*" multiple></div>
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
                    <thead><tr><th>#</th><th>الاسم</th><th>القسم</th><th>السعر</th><th>الحالة</th><th>إجراءات</th></tr></thead>
                    <tbody>
                        {% for p in all_products %}
                        <tr>
                            <td>{{ p.id }}</td>
                            <td><b>{{ p.name }}</b></td><td>{{ p.category }}</td><td>{{ p.price }} ج.م</td>
                            <td>
                                {% if p.is_sold_out %}
                                    <span style="background:#f8d7da; color:#721c24; padding:3px 8px; border-radius:4px; font-size:11px; font-weight:bold;">نفذت الكمية</span>
                                {% else %}
                                    <span style="background:#d4edda; color:#155724; padding:3px 8px; border-radius:4px; font-size:11px; font-weight:bold;">متاح</span>
                                {% endif %}
                            </td>
                            <td>
                                <a href="/admin/edit-product/{{ p.id }}" class="btn-edit">تعديل</a>
                                <a href="/admin/toggle-sold-out/{{ p.id }}" class="btn-edit" style="background:{{ '#28a745' if p.is_sold_out else '#dc3545' }}; color:#fff;">{{ 'إعادة التفعيل' if p.is_sold_out else 'نفذت الكمية' }}</a>
                                <a href="/admin/delete-product/{{ p.id }}" class="btn-danger" onclick="return confirm('تأكيد الحذف؟')">حذف</a>
                            </td>
                        </tr>
                        {% endfor %}
                    </tbody>
                </table>
            </div>
        </div>

        <div class="admin-section-box">
            <div class="admin-section-header" onclick="toggleSection('sec-homepage')">
                <span>🏠 محتوى الصفحة الرئيسية، العروض، وكود الخصم</span>
                <span>▼</span>
            </div>
            <div id="sec-homepage" class="admin-section-content">
                <form action="/admin/update-settings" method="POST" enctype="multipart/form-data">
                    <div class="form-group"><label>عنوان الترحيب في الصفحة الرئيسية</label><input type="text" name="welcome_title" value="{{ settings.welcome_title or '' }}"></div>
                    <div class="form-group"><label>نص الترحيب / الوصف تحت العنوان (السطر ده كله قابل للتعديل، تقدر تحذف أو تعدل ذكر كود الخصم منه براحتك)</label><textarea name="welcome_text" rows="3">{{ settings.welcome_text or '' }}</textarea></div>
                    <div class="form-group"><label>رفع صورة إعلان/عرض (بانر) للصفحة الرئيسية</label><input type="file" name="banner_image_file" accept="image/*"></div>
                    <div class="form-group"><label>أو رابط صورة الإعلان</label><input type="url" name="banner_image_url" value="{{ settings.banner_image_url or '' }}" placeholder="اتركه فارغاً لو عايز تشيل الإعلان"></div>
                    <div class="form-group"><label>كود الخصم الحالي (10% لأول طلب لكل عميل)</label><input type="text" name="coupon_code" value="{{ settings.coupon_code or 'Anything 10' }}" required></div>
                    <p style="color:#888; font-size:12px; margin-top:-5px;">لو غيّرت الكود، الكود القديم هيبقى مش شغال فوراً، والكود الجديد هيشتغل لكل العملاء من نفس اللحظة.</p>
                    <div class="form-group"><label>سعر صرف الدولار (لتحويل مبلغ الأوردر لدولار عند الدفع بـ PayPal)</label><input type="number" step="0.01" name="usd_exchange_rate" value="{{ settings.usd_exchange_rate or 50 }}" required></div>
                    <p style="color:#888; font-size:12px; margin-top:-5px;">PayPal مش بيدعم الجنيه المصري مباشرة، فالمبلغ بيتحول لدولار بالسعر ده وقت الدفع. حدّثه من وقت للتاني حسب سعر السوق.</p>
                    <button type="submit" class="btn-submit">حفظ محتوى الصفحة الرئيسية</button>
                </form>
            </div>
        </div>

        <div class="admin-section-box">
            <div class="admin-section-header" onclick="toggleSection('sec-design')">
                <span>🎨 التحكم الكامل في ألوان الديزاين، الأيقونات، والشعار</span>
                <span>▼</span>
            </div>
            <div id="sec-design" class="admin-section-content">
                <form action="/admin/update-settings" method="POST" enctype="multipart/form-data">
                    <div class="form-group"><label>اسم الموقع</label><input type="text" name="site_name" value="{{ settings.site_name or 'Anything Shop' }}" required></div>
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

    {% elif page == 'order_detail' %}
        <div class="admin-card" style="max-width:650px; margin:auto;">
            <h2>📦 تفاصيل الأوردر #{{ order.id }}</h2>
            <table class="admin-table">
                <tbody>
                    <tr><td><strong>العميل</strong></td><td>{{ order.customer.first_name }} {{ order.customer.last_name }} — <a href="/admin/customer/{{ order.customer.id }}" style="color:#0084ff;">عرض البروفايل</a></td></tr>
                    <tr><td><strong>التاريخ</strong></td><td>{{ order.created_at.strftime('%Y-%m-%d %H:%M') }}</td></tr>
                    <tr><td><strong>الهاتف</strong></td><td>{{ order.phone }}</td></tr>
                    <tr><td><strong>العنوان</strong></td><td>{{ order.address }}</td></tr>
                    <tr><td><strong>طريقة الدفع</strong></td><td>{{ order.payment_method }}</td></tr>
                    <tr><td><strong>حالة الدفع</strong></td><td>{{ order.payment_status }}</td></tr>
                    <tr><td><strong>الإجمالي</strong></td><td>{{ "%.2f"|format(order.total_price) }} ج.م</td></tr>
                </tbody>
            </table>
            <h4>المنتجات المطلوبة</h4>
            <ul>
                {% for it in order.items_list %}
                    <li>{{ it.name }} × {{ it.qty }}</li>
                {% endfor %}
            </ul>

            <form action="/admin/order/{{ order.id }}" method="POST" style="margin-top:20px;">
                <div class="form-group"><label>كود الأوردر (تحطه إنت براحتك، مثلاً لربط الأوردر بنظام شحن خارجي)</label><input type="text" name="order_code" value="{{ order.order_code or '' }}" placeholder="مثال: ORD-1024"></div>
                <div class="form-group"><label>ملاحظات الأدمن الداخلية على الأوردر</label><textarea name="admin_notes" rows="4" placeholder="أي تفاصيل أو وصف تحب تسجله على الأوردر ده...">{{ order.admin_notes or '' }}</textarea></div>
                <button type="submit" class="btn-submit">حفظ كود الأوردر والملاحظات</button>
            </form>
            <a href="/admin" class="nav-btn" style="display:inline-block; margin-top:10px;">⬅ رجوع للوحة الأدمن</a>
        </div>

    {% elif page == 'customer_profile' %}
        <div class="admin-card" style="max-width:650px; margin:auto;">
            <h2>👤 بروفايل العميل #{{ customer.id }}</h2>
            <table class="admin-table">
                <tbody>
                    <tr><td><strong>الاسم الكامل</strong></td><td>{{ customer.first_name }} {{ customer.last_name }}</td></tr>
                    <tr><td><strong>البريد الإلكتروني</strong></td><td>{{ customer.email }}</td></tr>
                    <tr><td><strong>رقم الهاتف</strong></td><td>{{ customer.phone or '-' }}</td></tr>
                    <tr><td><strong>العنوان</strong></td><td>{{ customer.address or '-' }}</td></tr>
                    <tr><td><strong>تاريخ الميلاد</strong></td><td>{{ customer.birth_date or '-' }}</td></tr>
                    <tr><td><strong>طريقة إنشاء الحساب</strong></td><td>{{ 'Google' if customer.auth_provider == 'google' else 'تسجيل مباشر' }}</td></tr>
                    <tr><td><strong>نوع الحساب</strong></td><td>{{ 'أدمن' if customer.is_admin else 'عميل عادي' }}</td></tr>
                    <tr><td><strong>عدد مرات تسجيل الدخول</strong></td><td>{{ customer.login_count or 0 }}</td></tr>
                    <tr><td><strong>استخدم كود الخصم؟</strong></td><td>{{ 'نعم' if customer.used_coupon else 'لا' }}</td></tr>
                </tbody>
            </table>
            <p style="color:#888; font-size:12px; margin-top:10px;">🔒 كلمة المرور مشفّرة (hashed) ولا يمكن عرضها لأي طرف، حتى الأدمن، لأسباب أمان.</p>

            <h3 style="margin-top:25px;">📦 طلبات هذا العميل ({{ customer_orders|length }})</h3>
            {% if customer_orders %}
                {% for order in customer_orders %}
                    <div style="background:var(--card-bg); padding:15px; border-radius:8px; margin-bottom:15px; border:1px solid #ccc;">
                        <h4>طلب رقم #{{ order.id }} - {{ order.created_at.strftime('%Y-%m-%d %H:%M') }}</h4>
                        <p><strong>طريقة الدفع:</strong> {{ order.payment_method }}</p>
                        <p><strong>حالة الدفع:</strong> {{ order.payment_status }}</p>
                        <ul style="margin:0; padding-right:16px;">
                            {% for it in order.items_list %}
                                <li>{{ it.name }} × {{ it.qty }}</li>
                            {% endfor %}
                        </ul>
                        <h4 style="color: var(--price-color); margin-top:8px;">الإجمالي: {{ "%.2f"|format(order.total_price) }} ج.م</h4>
                    </div>
                {% endfor %}
            {% else %}
                <p>لا يوجد طلبات لهذا العميل حتى الآن.</p>
            {% endif %}

            <a href="/admin" class="nav-btn" style="display:inline-block; margin-top:10px;">⬅ رجوع للوحة الأدمن</a>
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
                <div class="form-group"><label>وصف المنتج</label><textarea name="description" rows="3">{{ edit_prod.description or '' }}</textarea></div>
                <div class="form-group"><label>رفع صورة رئيسية جديدة (تستبدل الحالية)</label><input type="file" name="image_file" accept="image/*"></div>
                <div class="form-group"><label>رابط الصورة الرئيسية الحالي</label><input type="url" name="image_url" value="{{ edit_prod.image }}"></div>
                <div class="form-group"><label>إضافة صور إضافية جديدة للمعرض (لحد {{ 9 - (edit_prod.extra_images|length) }} صورة زيادة)</label><input type="file" name="extra_images" accept="image/*" multiple></div>
                <button type="submit" class="btn-submit">حفظ التعديلات</button>
            </form>

            {% if edit_prod.extra_images %}
            <h4 style="margin-top:20px;">🖼️ الصور الإضافية الحالية</h4>
            <div style="display:flex; gap:10px; flex-wrap:wrap;">
                {% for img in edit_prod.extra_images %}
                <div style="text-align:center;">
                    <img src="{{ img.image_url }}" style="width:80px; height:80px; object-fit:cover; border-radius:6px; border:1px solid #ccc;">
                    <br>
                    <a href="/admin/delete-product-image/{{ img.id }}" class="btn-danger" style="display:inline-block; margin-top:4px;" onclick="return confirm('حذف الصورة دي؟')">حذف</a>
                </div>
                {% endfor %}
            </div>
            {% endif %}
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

{% if current_user.is_authenticated %}
<div id="support-chat-btn" class="chat-widget-btn" style="position:fixed;">
    💬
    {% if customer_notif_count and customer_notif_count > 0 %}
    <span class="badge-notification">{{ customer_notif_count }}</span>
    {% endif %}
</div>
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
<footer><small>©️ 2026 {{ settings.site_name or 'Anything Shop' }} - جميع الحقوق محفوظة.</small></footer>
</body>
</html>
"""

# ============================================================
# ===================  تكامل Paymob الحقيقي (Intention API) ==================
# ============================================================
# ملحوظة: Paymob ألغوا الطريقة القديمة (auth token -> order -> payment key -> iframe)
# والمفروض تستخدم Intention API الجديدة (خطوة واحدة بس + Unified Checkout).
PAYMOB_SECRET_KEY = os.environ.get("PAYMOB_SECRET_KEY")   # مفتاح جديد لازم تجيبه من Paymob (مختلف عن الـ API Key القديم)
PAYMOB_PUBLIC_KEY = os.environ.get("PAYMOB_PUBLIC_KEY")
PAYMOB_INTEGRATION_ID = os.environ.get("PAYMOB_INTEGRATION_ID")  # استخدم 3867824 وقت التجربة حسب إيميل Paymob
PAYMOB_HMAC_KEY = os.environ.get("PAYMOB_HMAC_KEY")

PAYMOB_INTENTION_URL = "https://accept.paymob.com/v1/intention/"
PAYMOB_CHECKOUT_URL = "https://accept.paymob.com/unifiedcheckout/"


class PaymobError(Exception):
    pass


def paymob_create_intention(order, user):
    """
    بينشئ Intention واحدة على Paymob (الطريقة الحديثة المطلوبة بدل الطريقة القديمة الملغاة)
    ويرجع client_secret اللي بنستخدمه لبناء رابط Unified Checkout.
    """
    if not (PAYMOB_SECRET_KEY and PAYMOB_PUBLIC_KEY and PAYMOB_INTEGRATION_ID):
        raise PaymobError(
            "إعدادات Paymob غير مكتملة في .env "
            "(محتاج PAYMOB_SECRET_KEY, PAYMOB_PUBLIC_KEY, PAYMOB_INTEGRATION_ID)."
        )

    amount_cents = int(round(order.total_price * 100))
    items_json = json.loads(order.items_json)
    paymob_items = [
        {
            "name": it["name"][:255],
            "amount": int(round(it["price"] * 100)),
            "description": it["name"][:255],
            "quantity": it["qty"],
        }
        for it in items_json
    ]

    first_name = user.first_name or "Customer"
    last_name = user.last_name or "Shop"

    billing_data = {
        "apartment": "NA",
        "email": user.email,
        "floor": "NA",
        "first_name": first_name,
        "street": (order.address or "NA")[:255],
        "building": "NA",
        "phone_number": order.phone or "01000000000",
        "city": "Cairo",
        "country": "EGY",
        "last_name": last_name,
        "state": "NA",
    }

    payload = {
        "amount": amount_cents,
        "currency": "EGP",
        "payment_methods": [int(PAYMOB_INTEGRATION_ID)],
        "items": paymob_items,
        "billing_data": billing_data,
        "special_reference": str(order.id),
        "notification_url": url_for('paymob_webhook', _external=True),
        "redirection_url": url_for('paymob_callback', _external=True),
    }

    try:
        resp = requests.post(
            PAYMOB_INTENTION_URL,
            json=payload,
            headers={"Authorization": f"Token {PAYMOB_SECRET_KEY}", "Content-Type": "application/json"},
            timeout=20
        )
        resp.raise_for_status()
        return resp.json()["client_secret"]
    except Exception as e:
        raise PaymobError(f"فشل إنشاء عملية الدفع على Paymob: {e}")


def paymob_start_payment(order, user):
    """بينشئ الـ Intention ويرجع رابط Unified Checkout اللي نوجّه له العميل."""
    client_secret = paymob_create_intention(order, user)
    order.paymob_order_id = client_secret
    db.session.commit()
    return f"{PAYMOB_CHECKOUT_URL}?publicKey={PAYMOB_PUBLIC_KEY}&clientSecret={client_secret}"


def verify_paymob_hmac(data, received_hmac):
    """
    التحقق من الـ HMAC اللي بيبعته Paymob مع كل نداء webhook/callback
    للتأكد إن الرسالة فعلاً جايه من Paymob ومحدش تلاعب فيها.
    ترتيب الحقول ده محدد من توثيق Paymob (Transaction Processed Callback).
    """
    ordered_keys = [
        "amount_cents", "created_at", "currency", "error_occured",
        "has_parent_transaction", "id", "integration_id", "is_3d_secure",
        "is_auth", "is_capture", "is_refunded", "is_standalone_payment",
        "is_voided", "order.id", "owner", "pending", "source_data.pan",
        "source_data.sub_type", "source_data.type", "success",
    ]

    def get_nested(d, dotted_key):
        parts = dotted_key.split(".")
        val = d
        for p in parts:
            if val is None:
                return ""
            val = val.get(p) if isinstance(val, dict) else None
        return val

    concatenated = ""
    for key in ordered_keys:
        val = get_nested(data, key)
        if val is None:
            val = ""
        if isinstance(val, bool):
            val = "true" if val else "false"
        concatenated += str(val)

    calculated_hmac = hmac.new(
        PAYMOB_HMAC_KEY.encode("utf-8"),
        concatenated.encode("utf-8"),
        hashlib.sha512
    ).hexdigest()

    return hmac.compare_digest(calculated_hmac, received_hmac or "")


# ============================================================
# ===================  تكامل PayPal الحقيقي  ==================
# ============================================================
PAYPAL_CLIENT_ID = os.environ.get("PAYPAL_CLIENT_ID")
PAYPAL_CLIENT_SECRET = os.environ.get("PAYPAL_CLIENT_SECRET")
PAYPAL_MODE = os.environ.get("PAYPAL_MODE", "sandbox")  # "sandbox" للتجربة أو "live" للحساب الحقيقي
PAYPAL_BASE_URL = "https://api-m.sandbox.paypal.com" if PAYPAL_MODE == "sandbox" else "https://api-m.paypal.com"


class PaypalError(Exception):
    pass


def paypal_get_access_token():
    if not (PAYPAL_CLIENT_ID and PAYPAL_CLIENT_SECRET):
        raise PaypalError("إعدادات PayPal غير مكتملة (محتاج PAYPAL_CLIENT_ID و PAYPAL_CLIENT_SECRET في .env).")
    try:
        resp = requests.post(
            f"{PAYPAL_BASE_URL}/v1/oauth2/token",
            auth=(PAYPAL_CLIENT_ID, PAYPAL_CLIENT_SECRET),
            data={"grant_type": "client_credentials"},
            timeout=15
        )
        resp.raise_for_status()
        return resp.json()["access_token"]
    except PaypalError:
        raise
    except Exception as e:
        raise PaypalError(f"فشل الحصول على توكن PayPal: {e}")


def paypal_create_order(order, usd_amount):
    """
    بينشئ أوردر على PayPal ويرجع (paypal_order_id, رابط الموافقة اللي نوجه له العميل).
    """
    access_token = paypal_get_access_token()
    payload = {
        "intent": "CAPTURE",
        "purchase_units": [{
            "reference_id": str(order.id),
            "amount": {"currency_code": "USD", "value": f"{usd_amount:.2f}"}
        }],
        "application_context": {
            "return_url": url_for('paypal_return', _external=True),
            "cancel_url": url_for('paypal_cancel', _external=True),
            "brand_name": get_settings().site_name or "Anything Shop",
            "user_action": "PAY_NOW"
        }
    }
    try:
        resp = requests.post(
            f"{PAYPAL_BASE_URL}/v2/checkout/orders",
            json=payload,
            headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"},
            timeout=15
        )
        resp.raise_for_status()
        data = resp.json()
        approve_link = next((l["href"] for l in data.get("links", []) if l.get("rel") == "approve"), None)
        if not approve_link:
            raise PaypalError("لم يتم العثور على رابط الموافقة من PayPal.")
        return data["id"], approve_link
    except PaypalError:
        raise
    except Exception as e:
        raise PaypalError(f"فشل إنشاء الطلب على PayPal: {e}")


def paypal_capture_order(paypal_order_id):
    """بيأكد تحصيل المبلغ فعلياً بعد ما العميل يوافق على PayPal، ويرجع True/False."""
    access_token = paypal_get_access_token()
    try:
        resp = requests.post(
            f"{PAYPAL_BASE_URL}/v2/checkout/orders/{paypal_order_id}/capture",
            headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"},
            timeout=15
        )
        resp.raise_for_status()
        data = resp.json()
        return data.get("status") == "COMPLETED"
    except PaypalError:
        raise
    except Exception as e:
        raise PaypalError(f"فشل تأكيد تحصيل المبلغ من PayPal: {e}")


# --- مساعد رفع الصور ---
UPLOAD_FOLDER = 'static/uploads'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

CLOUDINARY_CLOUD_NAME = os.environ.get("CLOUDINARY_CLOUD_NAME")
CLOUDINARY_API_KEY = os.environ.get("CLOUDINARY_API_KEY")
CLOUDINARY_API_SECRET = os.environ.get("CLOUDINARY_API_SECRET")


def upload_to_cloudinary(file_storage):
    """
    بيرفع الصورة لـ Cloudinary عشان تفضل محفوظة دايماً (مش زي ملفات Render اللي بتتمسح).
    لو المتغيرات مش متظبطة في .env، بيرجع None عشان الكود يرجع تلقائياً لطريقة الحفظ المحلية.
    """
    if not (CLOUDINARY_CLOUD_NAME and CLOUDINARY_API_KEY and CLOUDINARY_API_SECRET):
        return None
    try:
        import time as _time
        timestamp = str(int(_time.time()))
        signature = hashlib.sha1(f"timestamp={timestamp}{CLOUDINARY_API_SECRET}".encode("utf-8")).hexdigest()
        resp = requests.post(
            f"https://api.cloudinary.com/v1_1/{CLOUDINARY_CLOUD_NAME}/image/upload",
            files={"file": (file_storage.filename, file_storage.stream, file_storage.mimetype)},
            data={"api_key": CLOUDINARY_API_KEY, "timestamp": timestamp, "signature": signature},
            timeout=30
        )
        resp.raise_for_status()
        return resp.json().get("secure_url")
    except Exception as e:
        print(f"[cloudinary] فشل رفع الصورة: {e}")
        return None


def save_uploaded_file(file_storage):
    if not file_storage or file_storage.filename == '':
        return None

    # المحاولة الأولى: Cloudinary لو متظبط (اختياري، مش إجباري)
    cloud_url = upload_to_cloudinary(file_storage)
    if cloud_url:
        return cloud_url

    # الطريقة الافتراضية: تخزين الصورة كـ Base64 جوه قاعدة البيانات نفسها (مش على ملفات السيرفر)
    # عشان تفضل موجودة دايماً حتى لو السيرفر اتعمله Deploy جديد أو اتقفل شوية وفتح تاني.
    try:
        file_storage.stream.seek(0)
        raw = file_storage.stream.read()
        if not raw:
            return None
        if len(raw) > 2 * 1024 * 1024:  # حد أقصى 2 ميجابايت للصورة الواحدة
            flash("الصورة كبيرة جداً (أكبر من 2 ميجا) — من فضلك ارفع صورة أصغر.")
            return None
        b64 = base64.b64encode(raw).decode('utf-8')
        mimetype = file_storage.mimetype or 'image/jpeg'
        return f"data:{mimetype};base64,{b64}"
    except Exception as e:
        print(f"[upload] فشل حفظ الصورة: {e}")
        return None

def get_cart_count():
    return sum(session.get('cart', {}).values())

def get_settings():
    settings = SiteSettings.query.first()
    if not settings:
        settings = SiteSettings()
        db.session.add(settings)
        db.session.commit()

    # لو الأعمدة الجديدة اتضافت فاضية (NULL) في قاعدة بيانات قديمة، نملاها بقيم افتراضية
    # عشان تظهر جاهزة للتعديل في لوحة الأدمن بدل ما تكون فاضية
    changed = False
    if not settings.site_name:
        settings.site_name = "Anything Shop"
        changed = True
    if not settings.welcome_title:
        settings.welcome_title = f"أهلاً بك في متجر {settings.site_name}!"
        changed = True
    if not settings.coupon_code:
        settings.coupon_code = "Anything 10"
        changed = True
    if not settings.welcome_text:
        settings.welcome_text = f"استمتع بتجربة تسوق فريدة، عروض حصرية على أول طلب. استخدم كود الخصم ({settings.coupon_code}) للحصول على خصم 10% على أول طلب."
        changed = True
    if not settings.usd_exchange_rate:
        settings.usd_exchange_rate = 50.0
        changed = True
    if changed:
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

# --- عداد زيارات الموقع (بيحسب كل زيارة فعلية لصفحة، بصرف النظر لو المستخدم مسجل دخول أو لأ) ---
@app.before_request
def track_site_visits():
    if request.method != "GET":
        return
    if request.path.startswith('/static') or request.path.startswith('/api') or request.path.startswith('/admin'):
        return
    if request.path in ('/payment/webhook',):
        return
    try:
        settings = get_settings()
        settings.total_visits = (settings.total_visits or 0) + 1
        db.session.commit()
    except Exception:
        db.session.rollback()

# --- الإشعارات: عدد الحاجات الجديدة اللي محتاجة انتباه الأدمن أو العميل ---
@app.context_processor
def inject_notification_counts():
    admin_notif_count = 0
    customer_notif_count = 0
    try:
        if current_user.is_authenticated:
            if current_user.is_admin:
                unread_orders = Order.query.filter_by(is_read=False).count()
                unread_chats = SupportMessage.query.filter_by(sender_type='client', is_read=False).count()
                admin_notif_count = unread_orders + unread_chats
            else:
                customer_notif_count = SupportMessage.query.filter_by(
                    session_id=f'user_session_{current_user.id}', sender_type='admin', is_read=False
                ).count()
    except Exception:
        pass
    return dict(admin_notif_count=admin_notif_count, customer_notif_count=customer_notif_count)

# --- المسارات الأساسية ---
@app.route("/")
def home():
    page_num = int(request.args.get('page', 1))
    per_page = 20
    # الترتيب حسب القسم أولاً عشان منتجات نفس القسم تفضل مع بعض ومتتفرقش بين الصفحات
    query = Product.query.order_by(Product.category.asc(), Product.id.asc())
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
    per_page = 20
    query = Product.query.filter_by(category=cat_name).order_by(Product.id.asc())
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
    per_page = 20
    filters = [Product.name.ilike(f"%{w}%") for w in query_str.split()] + [Product.category.ilike(f"%{w}%") for w in query_str.split()]
    query = Product.query.filter(db.or_(*filters)).order_by(Product.category.asc(), Product.id.asc())
    
    total_count = query.count()
    total_pages = (total_count + per_page - 1) // per_page
    paged_products = query.offset((page_num - 1) * per_page).limit(per_page).all()

    return render_template_string(
        HTML_TEMPLATE, page='search', products=paged_products, search_query=query_str,
        current_product_page=page_num, total_product_pages=total_pages,
        cart_count=get_cart_count(), categories_list=get_categories_list(), current_cat="", settings=get_settings()
    )

@app.route("/product/<int:product_id>")
def product_detail(product_id):
    product = Product.query.get_or_404(product_id)
    related_products = Product.query.filter(
        Product.category == product.category, Product.id != product.id
    ).order_by(db.func.random()).limit(6).all()

    return render_template_string(
        HTML_TEMPLATE, page='product_detail', product=product, related_products=related_products,
        cart_count=get_cart_count(), categories_list=get_categories_list(), current_cat=product.category, settings=get_settings()
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

    user.login_count = (user.login_count or 0) + 1
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
        db.session.add(SupportMessage(user_id=u_id, session_id=session_id, sender_type="admin", message=message, is_read=False))
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

    # لو الأدمن هو اللي بيفتح المحادثة دي، نعتبر رسايل العميل "مقروءة" فوراً عشان تختفي العلامة الحمراء
    if current_user.is_admin:
        SupportMessage.query.filter_by(session_id=session_id, sender_type='client', is_read=False).update({SupportMessage.is_read: True})
        db.session.commit()
    elif session_id == f'user_session_{current_user.id}':
        # العميل بيفتح شاته هو نفسه، يبقى رد الأدمن بقى مقروء
        SupportMessage.query.filter_by(session_id=session_id, sender_type='admin', is_read=False).update({SupportMessage.is_read: True})
        db.session.commit()

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
            phone=request.form.get("phone"), address=request.form.get("address"), birth_date=request.form.get("birth_date"),
            login_count=1
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

@app.route("/profile/change-password", methods=["POST"])
@login_required
def change_password():
    if current_user.auth_provider == 'google' or not current_user.password_hash:
        flash("حسابك مسجل عن طريق Google، مفيش كلمة مرور تتغير.")
        return redirect(url_for('profile'))

    current_password = request.form.get("current_password", "")
    new_password = request.form.get("new_password", "")
    confirm_password = request.form.get("confirm_password", "")

    if not check_password_hash(current_user.password_hash, current_password):
        flash("كلمة المرور الحالية غير صحيحة.")
        return redirect(url_for('profile'))
    if new_password != confirm_password:
        flash("كلمة المرور الجديدة وتأكيدها غير متطابقين.")
        return redirect(url_for('profile'))
    if len(new_password) < 6:
        flash("كلمة المرور الجديدة لازم تكون 6 حروف/أرقام على الأقل.")
        return redirect(url_for('profile'))

    current_user.password_hash = generate_password_hash(new_password, method='scrypt')
    db.session.commit()
    flash("تم تحديث كلمة المرور بنجاح!")
    return redirect(url_for('profile'))

@app.route("/add-to-cart", methods=["POST"])
def add_to_cart():
    p_id = str(request.form.get("product_id"))
    product = Product.query.get(int(p_id))
    if not product:
        flash("المنتج غير موجود.")
        return redirect(request.referrer or url_for('home'))
    if product.is_sold_out:
        flash("عذراً، هذا المنتج نفذت كميته حالياً.")
        return redirect(request.referrer or url_for('home'))

    try:
        qty = int(request.form.get("qty", 1))
    except (TypeError, ValueError):
        qty = 1
    qty = max(1, min(qty, 99))  # حد أدنى 1 وحد أقصى 99 لكل طلبية إضافة

    cart = session.get('cart', {})
    cart[p_id] = cart.get(p_id, 0) + qty
    session['cart'] = cart
    flash(f"تمت إضافة {qty} من \"{product.name}\" للسلة!")
    return redirect(request.referrer or url_for('home'))

@app.route("/apply-coupon", methods=["POST"])
@login_required
def apply_coupon():
    code = request.form.get("coupon_code", "").strip()
    active_coupon = get_settings().coupon_code or "Anything 10"
    if code == active_coupon:
        if current_user.used_coupon:
            session.pop('applied_coupon', None)
            flash(f"عذراً، لقد استخدمت كود الخصم ({active_coupon}) من قبل. الكود يُستخدم مرة واحدة فقط لكل عميل.")
        else:
            session['applied_coupon'] = active_coupon
            flash(f"تم تطبيق كود الخصم ({active_coupon}) بنجاح!")
    else:
        session.pop('applied_coupon', None)
        flash("كود الخصم غير صحيح.")
    return redirect(url_for('view_cart'))


@app.route("/cart")
def view_cart():
    cart = session.get('cart', {})
    cart_items, total_price = [], 0.0
    for p_id_str, qty in cart.items():
        product = Product.query.get(int(p_id_str))
        if product:
            total_price += product.price * qty
            cart_items.append({"id": product.id, "name": product.name, "price": product.price, "qty": qty})
    
    settings = get_settings()
    discount_amount = 0.0
    if session.get('applied_coupon') == (settings.coupon_code or "Anything 10") and current_user.is_authenticated and not current_user.used_coupon:
        discount_amount = total_price * 0.10
    
    final_total = (total_price - discount_amount) + settings.shipping_fee
    if final_total < 0: final_total = 0.0

    return render_template_string(
        HTML_TEMPLATE, page='cart', cart_items=cart_items, total_price=total_price, 
        discount_amount=discount_amount, final_total=final_total, 
        cart_count=get_cart_count(), categories_list=get_categories_list(), current_cat="Cart", settings=settings
    )

@app.route("/cart/update-qty", methods=["POST"])
def update_cart_qty():
    p_id = str(request.form.get("product_id"))
    try:
        qty = int(request.form.get("qty", 1))
    except (TypeError, ValueError):
        qty = 1
    cart = session.get('cart', {})
    if p_id in cart:
        if qty <= 0:
            cart.pop(p_id, None)
        else:
            cart[p_id] = min(qty, 99)
        session['cart'] = cart
    return redirect(url_for('view_cart'))

@app.route("/cart/remove-item", methods=["POST"])
def remove_cart_item():
    p_id = str(request.form.get("product_id"))
    cart = session.get('cart', {})
    cart.pop(p_id, None)
    session['cart'] = cart
    flash("تم حذف المنتج من السلة.")
    return redirect(url_for('view_cart'))

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
    discount_amount = 0.0
    coupon_used_this_order = False
    if session.get('applied_coupon') == (settings.coupon_code or "Anything 10") and not current_user.used_coupon:
        discount_amount = items_price * 0.10
        coupon_used_this_order = True

    total_price = (items_price - discount_amount) + settings.shipping_fee
    if total_price < 0: total_price = 0.0

    payment_method = request.form.get("payment_method", "cod")

    new_order = Order(
        user_id=current_user.id, phone=request.form.get("phone"), address=request.form.get("address"), 
        payment_method=payment_method if payment_method in ("card", "paypal") else "cod",
        payment_status='Pending',
        items_price=items_price, shipping_fee=settings.shipping_fee, discount_amount=discount_amount,
        total_price=total_price, items_json=json.dumps(order_items)
    )
    db.session.add(new_order)

    if coupon_used_this_order:
        current_user.used_coupon = True

    db.session.commit()

    # الكارت والكوبون بيتفضّوا سواء دفع كاش أو كارت، عشان الأوردر اتسجل بالفعل
    session['cart'] = {}
    session.pop('applied_coupon', None)

    if payment_method == "card":
        try:
            iframe_url = paymob_start_payment(new_order, current_user)
            return redirect(iframe_url)
        except PaymobError as e:
            new_order.payment_status = "Failed"
            db.session.commit()
            flash(f"تعذر بدء عملية الدفع الإلكتروني: {e}")
            return redirect(url_for('my_orders'))

    if payment_method == "paypal":
        try:
            usd_rate = settings.usd_exchange_rate or 50.0
            usd_amount = round(total_price / usd_rate, 2)
            paypal_order_id, approve_link = paypal_create_order(new_order, usd_amount)
            new_order.paypal_order_id = paypal_order_id
            db.session.commit()
            return redirect(approve_link)
        except PaypalError as e:
            new_order.payment_status = "Failed"
            db.session.commit()
            flash(f"تعذر بدء عملية الدفع عبر PayPal: {e}")
            return redirect(url_for('my_orders'))

    new_order.payment_status = "Cash on Delivery"
    db.session.commit()
    flash("تم تسجيل الطلب بنجاح!")
    return redirect(url_for('my_orders'))


@app.route("/payment/paypal/return")
@login_required
def paypal_return():
    paypal_order_id = request.args.get("token")
    order = Order.query.filter_by(paypal_order_id=paypal_order_id).first()
    if not order:
        flash("لم يتم العثور على الطلب.")
        return redirect(url_for('my_orders'))
    try:
        success = paypal_capture_order(paypal_order_id)
        order.payment_status = "Paid" if success else "Failed"
    except PaypalError as e:
        order.payment_status = "Failed"
        flash(f"حصل خطأ أثناء تأكيد الدفع: {e}")
    db.session.commit()
    return render_template_string(
        HTML_TEMPLATE, page='payment_result', order=order,
        cart_count=get_cart_count(), categories_list=get_categories_list(), current_cat="", settings=get_settings()
    )

@app.route("/payment/paypal/cancel")
@login_required
def paypal_cancel():
    paypal_order_id = request.args.get("token")
    order = Order.query.filter_by(paypal_order_id=paypal_order_id).first()
    if order:
        order.payment_status = "Failed"
        db.session.commit()
        flash("تم إلغاء عملية الدفع عبر PayPal.")
    return redirect(url_for('my_orders'))


@app.route("/payment/callback")
def paymob_callback():
    """
    الصفحة اللي المتصفح بيرجّع لها العميل بعد الدفع (Transaction Response Callback).
    دي بس لعرض النتيجة للعميل - التحديث الفعلي للحالة بيحصل في /payment/webhook
    (السيرفر لسيرفر) لأنه الوحيد اللي مينفعش يتزوّر من غير الـ HMAC السليم.
    """
    data = request.args.to_dict()
    received_hmac = data.get("hmac")

    order_id = data.get("merchant_order_id")
    order = Order.query.get(int(order_id)) if order_id and order_id.isdigit() else None

    if order and verify_paymob_hmac(data, received_hmac):
        success = data.get("success") == "true"
        order.payment_status = "Paid" if success else "Failed"
        db.session.commit()
    
    if not order:
        flash("لم يتم العثور على الطلب.")
        return redirect(url_for('home'))

    return render_template_string(
        HTML_TEMPLATE, page='payment_result', order=order,
        cart_count=get_cart_count(), categories_list=get_categories_list(), current_cat="", settings=get_settings()
    )


@app.route("/payment/webhook", methods=["POST"])
def paymob_webhook():
    """
    نداء سيرفر-لسيرفر من Paymob (Transaction Processed Callback) - ده المصدر
    الموثوق فيه لتحديث حالة الدفع، لأنه بيحمل HMAC بيتحقق منه السيرفر مباشرة.
    """
    payload = request.get_json(silent=True) or {}
    obj = payload.get("obj", payload)
    received_hmac = request.args.get("hmac")

    if not verify_paymob_hmac(obj, received_hmac):
        return jsonify({"status": "error", "message": "invalid hmac"}), 401

    merchant_order_id = (obj.get("order") or {}).get("merchant_order_id")
    if not merchant_order_id:
        return jsonify({"status": "error", "message": "no order id"}), 400

    order = Order.query.get(int(merchant_order_id))
    if not order:
        return jsonify({"status": "error", "message": "order not found"}), 404

    order.payment_status = "Paid" if obj.get("success") else "Failed"
    db.session.commit()
    return jsonify({"status": "success"})


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
        chat_customer = User.query.get(first_msg.user_id) if first_msg else None
        chat_sessions.append({
            "session_id": s.session_id, "last_time": str(s.last_time), "unread_count": unread_cnt,
            "email": first_msg.client_email if first_msg else "عميل مسجل",
            "display_name": f"{chat_customer.first_name} {chat_customer.last_name}" if chat_customer else "عميل"
        })
    
    total_chat_pages = (len(chat_sessions) + chats_per_page - 1) // chats_per_page
    paged_chats = chat_sessions[(chat_page - 1) * chats_per_page : chat_page * chats_per_page]
    
    active_session = request.args.get("session")
    if not active_session and paged_chats: active_session = paged_chats[0]["session_id"]

    active_customer = None
    if active_session:
        # نعتبر رسايل العميل مقروءة أول ما الأدمن يفتح المحادثة (حتى من غير ما ينتظر الـ AJAX)
        SupportMessage.query.filter_by(session_id=active_session, sender_type='client', is_read=False).update({SupportMessage.is_read: True})
        db.session.commit()
        active_first_msg = SupportMessage.query.filter_by(session_id=active_session, sender_type='client').first()
        if active_first_msg:
            active_customer = User.query.get(active_first_msg.user_id)

    total_registered_users = User.query.count()
    total_logins = db.session.query(db.func.coalesce(db.func.sum(User.login_count), 0)).scalar()
    total_visits = get_settings().total_visits or 0

    product_totals = defaultdict(int)
    for o in Order.query.all():
        for it in o.items_list:
            product_totals[it.get("name", "غير معروف")] += it.get("qty", 0)
    product_totals_sorted = sorted(product_totals.items(), key=lambda x: -x[1])

    customer_page = int(request.args.get('customer_page', 1))
    customers_per_page = 10
    all_customers_query = User.query.order_by(User.id.asc())
    total_customers_count = all_customers_query.count()
    total_customer_pages = (total_customers_count + customers_per_page - 1) // customers_per_page
    paged_customers = all_customers_query.offset((customer_page - 1) * customers_per_page).limit(customers_per_page).all()

    return render_template_string(
        HTML_TEMPLATE, page='admin', 
        paged_orders=paged_orders, total_orders_count=total_orders_count, total_order_pages=total_order_pages, order_page=order_page,
        paged_chats=paged_chats, total_chat_pages=total_chat_pages, chat_page=chat_page, active_session=active_session, active_customer=active_customer,
        custom_categories=Category.query.all(), all_products=Product.query.all(),
        total_registered_users=total_registered_users, total_logins=total_logins, total_visits=total_visits,
        paged_customers=paged_customers, total_customer_pages=total_customer_pages, customer_page=customer_page,
        product_totals_sorted=product_totals_sorted,
        cart_count=get_cart_count(), categories_list=get_categories_list(), current_cat="Admin", settings=get_settings()
    )

@app.route("/admin/search-customer", methods=["GET"])
@login_required
def admin_search_customer():
    if not current_user.is_admin: return redirect(url_for('home'))
    query_str = request.args.get("q", "").strip()
    if not query_str:
        flash("من فضلك اكتب إيميل أو رقم هاتف للبحث.")
        return redirect(url_for('admin_panel'))
    user = User.query.filter(
        db.or_(User.email.ilike(f"%{query_str}%"), User.phone.ilike(f"%{query_str}%"))
    ).first()
    if user:
        return redirect(url_for('admin_view_customer', user_id=user.id))
    flash(f"لم يتم العثور على أي عميل بالإيميل أو الرقم: {query_str}")
    return redirect(url_for('admin_panel'))

@app.route("/admin/customer/<int:user_id>")
@login_required
def admin_view_customer(user_id):
    if not current_user.is_admin: return redirect(url_for('home'))
    customer = User.query.get_or_404(user_id)
    customer_orders = Order.query.filter_by(user_id=customer.id).order_by(Order.created_at.desc()).all()
    return render_template_string(
        HTML_TEMPLATE, page='customer_profile', customer=customer, customer_orders=customer_orders,
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

@app.route("/admin/order/<int:order_id>", methods=["GET", "POST"])
@login_required
def admin_order_detail(order_id):
    if not current_user.is_admin: return redirect(url_for('home'))
    ord = Order.query.get_or_404(order_id)
    if request.method == "POST":
        ord.order_code = request.form.get("order_code", "").strip() or None
        ord.admin_notes = request.form.get("admin_notes", "").strip() or None
        ord.is_read = True
        db.session.commit()
        flash("تم حفظ التعديلات على الأوردر بنجاح!")
        return redirect(url_for('admin_order_detail', order_id=ord.id))
    return render_template_string(
        HTML_TEMPLATE, page='order_detail', order=ord,
        cart_count=get_cart_count(), categories_list=get_categories_list(), current_cat="Admin", settings=get_settings()
    )

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

    new_product = Product(
        name=request.form.get("name"), price=float(request.form.get("price")),
        category=request.form.get("category"), image=image_url,
        description=request.form.get("description", "").strip() or None
    )
    db.session.add(new_product)
    db.session.commit()

    # الصور الإضافية (حد أقصى 9 زيادة عن الرئيسية = 10 إجمالي)
    extra_files = request.files.getlist("extra_images")[:9]
    for f in extra_files:
        url = save_uploaded_file(f)
        if url:
            db.session.add(ProductImage(product_id=new_product.id, image_url=url))
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
        prod.description = request.form.get("description", "").strip() or None
        
        uploaded_img = save_uploaded_file(request.files.get("image_file"))
        if uploaded_img:
            prod.image = uploaded_img
        elif request.form.get("image_url"):
            prod.image = request.form.get("image_url")

        db.session.commit()

        # إضافة صور جديدة للمعرض من غير ما نتخطى حد الـ 9 صور إضافية
        remaining_slots = max(0, 9 - len(prod.extra_images))
        extra_files = request.files.getlist("extra_images")[:remaining_slots]
        for f in extra_files:
            url = save_uploaded_file(f)
            if url:
                db.session.add(ProductImage(product_id=prod.id, image_url=url))
        db.session.commit()

        flash("تم التعديل بنجاح!")
        return redirect(url_for('admin_panel'))
    return render_template_string(HTML_TEMPLATE, page='edit_product', edit_prod=prod, custom_categories=Category.query.all(), cart_count=get_cart_count(), categories_list=get_categories_list(), settings=get_settings())

@app.route("/admin/delete-product-image/<int:image_id>")
@login_required
def admin_delete_product_image(image_id):
    if not current_user.is_admin: return redirect(url_for('home'))
    img = ProductImage.query.get_or_404(image_id)
    prod_id = img.product_id
    db.session.delete(img)
    db.session.commit()
    flash("تم حذف الصورة.")
    return redirect(url_for('admin_edit_product', prod_id=prod_id))

@app.route("/admin/delete-product/<int:prod_id>")
@login_required
def admin_delete_product(prod_id):
    if not current_user.is_admin: return redirect(url_for('home'))
    db.session.delete(Product.query.get_or_404(prod_id))
    db.session.commit()
    flash("تم حذف المنتج.")
    return redirect(url_for('admin_panel'))

@app.route("/admin/toggle-sold-out/<int:prod_id>")
@login_required
def admin_toggle_sold_out(prod_id):
    if not current_user.is_admin: return redirect(url_for('home'))
    prod = Product.query.get_or_404(prod_id)
    prod.is_sold_out = not prod.is_sold_out
    db.session.commit()
    flash(f"تم تحديد \"{prod.name}\" كـ {'نفذت الكمية (Sold Out)' if prod.is_sold_out else 'متاح للبيع'}.")
    return redirect(url_for('admin_panel'))

@app.route("/admin/update-settings", methods=["POST"])
@login_required
def admin_update_settings():
    if not current_user.is_admin: return redirect(url_for('home'))
    settings = get_settings()

    if request.form.get("site_name", "").strip():
        settings.site_name = request.form.get("site_name").strip()

    if "header_color" in request.form:
        settings.header_color = request.form.get("header_color")
    if "primary_color" in request.form:
        settings.primary_color = request.form.get("primary_color")
    if "price_color" in request.form:
        settings.price_color = request.form.get("price_color")
    if "bg_color" in request.form:
        settings.bg_color = request.form.get("bg_color")
    if "text_color" in request.form:
        settings.text_color = request.form.get("text_color")
    if "icon_color" in request.form:
        settings.icon_color = request.form.get("icon_color")
    if "card_bg_color" in request.form:
        settings.card_bg_color = request.form.get("card_bg_color")
    if request.form.get("shipping_fee"):
        settings.shipping_fee = float(request.form.get("shipping_fee"))

    uploaded_logo = save_uploaded_file(request.files.get("logo_file"))
    if uploaded_logo:
        settings.logo_url = uploaded_logo
    elif request.form.get("logo_url"):
        settings.logo_url = request.form.get("logo_url")

    # --- محتوى الصفحة الرئيسية والعروض وكود الخصم ---
    if "welcome_title" in request.form:
        settings.welcome_title = request.form.get("welcome_title", "").strip() or settings.welcome_title
    if "welcome_text" in request.form:
        settings.welcome_text = request.form.get("welcome_text", "").strip() or settings.welcome_text

    uploaded_banner = save_uploaded_file(request.files.get("banner_image_file"))
    if uploaded_banner:
        settings.banner_image_url = uploaded_banner
    elif "banner_image_url" in request.form:
        settings.banner_image_url = request.form.get("banner_image_url", "").strip() or None

    if request.form.get("coupon_code", "").strip():
        settings.coupon_code = request.form.get("coupon_code").strip()

    if request.form.get("usd_exchange_rate"):
        try:
            settings.usd_exchange_rate = float(request.form.get("usd_exchange_rate"))
        except ValueError:
            pass

    db.session.commit()
    flash("تم تحديث الإعدادات بنجاح!")
    return redirect(url_for('admin_panel'))

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        user = User.query.filter_by(email=request.form.get("email")).first()
        if user and user.password_hash and check_password_hash(user.password_hash, request.form.get("password")):
            user.login_count = (user.login_count or 0) + 1
            db.session.commit()
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

def run_lightweight_migrations():
    """
    بيتأكد إن كل الأعمدة الموجودة في الـ Models (زي site_name, total_visits, login_count...)
    فعلاً موجودة في قاعدة البيانات الحقيقية، ولو أي عمود جديد ناقص بيضيفه تلقائياً بـ ALTER TABLE
    من غير ما يمسح أي بيانات موجودة. ده مهم جداً لما نستخدم قاعدة بيانات حقيقية زي Postgres،
    لأن db.create_all() بينشئ الجداول الناقصة بس ومش بيعدل جدول موجود بالفعل.
    """
    from sqlalchemy import inspect, text
    inspector = inspect(db.engine)
    for table in db.metadata.tables.values():
        if not inspector.has_table(table.name):
            continue
        existing_columns = {col['name'] for col in inspector.get_columns(table.name)}
        for column in table.columns:
            if column.name in existing_columns:
                continue
            try:
                col_type = column.type.compile(db.engine.dialect)
                with db.engine.connect() as conn:
                    conn.execute(text(f'ALTER TABLE "{table.name}" ADD COLUMN "{column.name}" {col_type}'))
                    conn.commit()
                print(f"[migration] تمت إضافة العمود '{column.name}' لجدول '{table.name}'")
            except Exception as e:
                print(f"[migration] فشل إضافة العمود '{column.name}' لجدول '{table.name}': {e}")

    # توسيع أعمدة الصور من VARCHAR(500) لـ TEXT عشان تستحمل الصور المخزّنة Base64 جوه قاعدة البيانات
    image_columns = [
        ("product", "image"),
        ("product_image", "image_url"),
        ("site_settings", "logo_url"),
        ("site_settings", "banner_image_url"),
    ]
    for table_name, col_name in image_columns:
        if not inspector.has_table(table_name):
            continue
        try:
            with db.engine.connect() as conn:
                conn.execute(text(f'ALTER TABLE "{table_name}" ALTER COLUMN "{col_name}" TYPE TEXT'))
                conn.commit()
        except Exception:
            # SQLite مش محتاج تحويل نوع العمود أصلاً، وPostgres لو العمود TEXT بالفعل بيتخطاها بأمان
            db.session.rollback()

with app.app_context():
    db.create_all()
    run_lightweight_migrations()
    seed_data()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
