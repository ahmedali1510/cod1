import os
import json
import requests
import hmac
import hashlib
from datetime import datetime
from dotenv import load_dotenv
from flask import Flask, render_template_string, request, redirect, url_for, session, jsonify, flash
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
    payment_status = db.Column(db.String(50), default='Pending')
    items_price = db.Column(db.Float, nullable=False)
    discount_amount = db.Column(db.Float, nullable=False, default=0.0)
    shipping_fee = db.Column(db.Float, nullable=False, default=50.0)
    total_price = db.Column(db.Float, nullable=False)
    items_json = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_read = db.Column(db.Boolean, default=False)

# نموذج رسائل الشات الحي الفوري
class SupportMessage(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.String(255), nullable=False)
    sender_type = db.Column(db.String(20), nullable=False)
    message = db.Column(db.Text, nullable=False)
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
    <!-- أيقونة الموقع 3D أصفر في أزرق -->
    <link rel="icon" type="image/svg+xml" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><defs><linearGradient id='yg' x1='0%' y1='0%' x2='100%' y2='100%'><stop offset='0%' stop-color='%23fff200'/><stop offset='100%' stop-color='%23ff9900'/></linearGradient><linearGradient id='bg' x1='0%' y1='0%' x2='100%' y2='100%'><stop offset='0%' stop-color='%23131921'/><stop offset='100%' stop-color='%23232f3e'/></linearGradient></defs><rect width='100' height='100' rx='20' fill='url(%23bg)'/><path d='M50 18 L78 75 L63 75 L50 42 L37 75 L22 75 Z' fill='url(%23yg)' filter='drop-shadow(2px 4px 6px rgba(0,0,0,0.5))'/><polygon points='50,30 58,55 42,55' fill='%23131921'/></svg>">
    <style>
        :root {
            --header-bg: {{ settings.header_color }};
            --primary-color: {{ settings.primary_color }};
            --price-color: {{ settings.price_color }};
            --bg-color: {{ settings.bg_color }};
            --text-color: {{ settings.text_color }};
            --font-size: {{ settings.font_size }}px;
        }
        * { box-sizing: border-box; }
        body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; margin:0; padding:0; background: var(--bg-color); color: var(--text-color); font-size: var(--font-size); text-align:right; overflow-x: hidden; }
        
        header { background: var(--header-bg); color:white; padding:10px 15px; display:flex; align-items:center; justify-content:space-between; position:sticky; top:0; z-index:100; gap:10px; flex-wrap: wrap; }
        .logo { font-size:20px; font-weight:bold; color: var(--primary-color); text-decoration:none; white-space:nowrap; display: flex; align-items: center; gap: 8px; }
        
        /* تصميم شعار حرف A ثلاثي الأبعاد أصفر في أزرق */
        .logo-3d {
            width: 36px;
            height: 36px;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            background: linear-gradient(135deg, #131921, #232f3e);
            border-radius: 8px;
            box-shadow: 0 3px 6px rgba(0,0,0,0.4), inset 0 1px 1px rgba(255,255,255,0.2);
            position: relative;
            overflow: hidden;
            border: 1px solid #37475a;
        }
        .logo-3d svg {
            width: 28px;
            height: 28px;
            filter: drop-shadow(1px 2px 2px rgba(0,0,0,0.6));
        }
        
        .search-bar { flex-grow:1; max-width:500px; display:flex; min-width: 200px; }
        .search-bar input { width:100%; padding:8px 10px; border:none; border-radius:0 4px 4px 0; font-size:13px; outline:none; }
        .search-bar button { background: var(--primary-color); border:none; padding:8px 12px; border-radius:4px 0 0 4px; cursor:pointer; font-weight:bold; font-size: 13px; }
        
        .nav-right { display:flex; align-items:center; gap:8px; white-space:nowrap; flex-wrap: wrap; }
        .nav-btn { background:#232f3e; color:white; padding:6px 12px; border-radius:4px; text-decoration:none; font-weight:bold; border:1px solid #d5d9d9; position: relative; font-size: 13px; }
        .admin-btn { background: var(--primary-color); color:black; }
        
        .badge-notification {
            position: absolute;
            top: -6px;
            right: -6px;
            background-color: #ff3b30;
            color: white;
            border-radius: 50%;
            padding: 2px 5px;
            font-size: 10px;
            font-weight: bold;
            display: inline-block;
            min-width: 15px;
            text-align: center;
            box-shadow: 0 2px 5px rgba(0,0,0,0.3);
        }

        .nav-categories { background:#232f3e; padding:8px 15px; display:flex; gap:10px; overflow-x:auto; white-space: nowrap; }
        .nav-categories::-webkit-scrollbar { height: 4px; }
        .nav-categories::-webkit-scrollbar-thumb { background: #37475a; border-radius: 2px; }
        .nav-categories a { color:white; text-decoration:none; font-weight:500; font-size:13px; padding:4px 8px; border-radius:3px; }
        .nav-categories a:hover, .nav-categories a.active { background:#37475a; color: var(--primary-color); }
        
        .container { max-width:1300px; margin:15px auto; padding:0 10px; min-height:75vh; }
        .products-grid { display:grid; grid-template-columns: repeat(auto-fill, minmax(180px, 1fr)); gap:15px; }
        .card { background:white; border:1px solid #e7e7e7; border-radius:8px; padding:12px; display:flex; flex-direction:column; justify-content:space-between; color: #0f1111; }
        .card img { width:100%; height:140px; object-fit:cover; border-radius:4px; margin-bottom:8px; }
        .card-title { font-size:14px; font-weight:600; margin-bottom:5px; height:38px; overflow:hidden; }
        .card-price { font-size:16px; color: var(--price-color); font-weight:bold; margin-bottom:8px; }
        .btn-add { background:#ffd814; border:1px solid #FCD200; border-radius:20px; padding:7px; width:100%; font-weight:bold; cursor:pointer; font-size: 13px; }
        .btn-add:hover { background:#f7ca00; }
        
        .cart-table, .orders-table, .admin-table { width:100%; background:white; color:#333; border-collapse:collapse; margin-bottom:20px; border-radius:8px; overflow:hidden; font-size: 13px; }
        .cart-table th, .cart-table td, .orders-table th, .orders-table td, .admin-table th, .admin-table td { padding:10px; text-align:right; border-bottom:1px solid #ddd; }
        
        .checkout-form, .auth-form, .admin-card { background:white; color:#333; padding:18px; border-radius:8px; margin-bottom:20px; border:1px solid #ddd; box-shadow:0 2px 5px rgba(0,0,0,0.1); }
        .form-group { margin-bottom:12px; }
        .form-group label { display:block; margin-bottom:4px; font-weight:bold; font-size: 13px; }
        .form-group input, .form-group textarea, .form-group select { width:100%; padding:9px; border:1px solid #ccc; border-radius:4px; box-sizing:border-box; font-size: 14px; }
        
        .btn-submit { background: var(--primary-color); color:black; border:none; padding:10px; border-radius:4px; font-weight:bold; width:100%; cursor:pointer; font-size:15px; }
        .btn-danger { background:#dc3545; color:white; padding:5px 10px; border:none; border-radius:4px; cursor:pointer; text-decoration:none; font-size:11px; }
        .btn-edit { background:#ffc107; color:black; padding:5px 10px; border:none; border-radius:4px; cursor:pointer; text-decoration:none; font-size:11px; margin-left:4px; }
        
        .btn-social { display:flex; align-items:center; justify-content:center; gap:8px; padding:9px; border-radius:4px; text-decoration:none; font-weight:bold; margin-top:10px; border:1px solid #ccc; background:white; color:#333; font-size: 13px; }
        .btn-social img { width:18px; height:18px; }
        
        .alert { background:#d4edda; color:#155724; padding:10px; border-radius:4px; margin-bottom:12px; font-size: 13px; }
        .promo-banner { background: #fff8e1; border: 2px dashed #ff9900; padding: 12px; border-radius: 8px; margin-bottom: 15px; text-align: center; }
        .promo-code-box { display: inline-block; background: #232f3e; color: #ffd814; padding: 7px 12px; font-weight: bold; border-radius: 4px; margin: 5px 0; cursor: pointer; letter-spacing: 1px; font-size: 13px; }
        
        .status-paid { color:green; font-weight:bold; }
        .status-pending { color:orange; font-weight:bold; }
        
        .admin-grid { display:grid; grid-template-columns: 1fr 1fr; gap:15px; }
        
        /* لوحة التحكم والتشات */
        .live-chat-admin-container { display: flex; height: 500px; background: #fff; border: 1px solid #ddd; border-radius: 8px; overflow: hidden; margin-top: 15px; margin-bottom: 20px; }
        .chat-sidebar { width: 240px; background: #f8f9fa; border-left: 1px solid #ddd; overflow-y: auto; }
        .chat-sidebar h4 { padding: 12px; margin: 0; background: #232f3e; color: #fff; font-size: 13px; }
        .client-chat-item { padding: 10px 12px; border-bottom: 1px solid #eee; cursor: pointer; text-decoration: none; color: #333; display: flex; justify-content: space-between; align-items: center; font-size: 12px; }
        .client-chat-item:hover, .client-chat-item.active { background: #e9ecef; }
        .chat-main-area { flex: 1; display: flex; flex-direction: column; background: #fff; }
        .admin-messages-box { flex: 1; padding: 12px; overflow-y: auto; background: #f1f2f6; display: flex; flex-direction: column; gap: 6px; }
        .admin-msg-bubble { max-width: 75%; padding: 8px 12px; border-radius: 8px; font-size: 12px; line-height: 1.4; }
        .admin-msg-bubble.client { background: #fff; align-self: flex-start; border: 1px solid #dcdde1; color: #333; }
        .admin-msg-bubble.admin { background: #0084ff; color: #fff; align-self: flex-end; }
        .admin-reply-box { padding: 10px; background: #fff; border-top: 1px solid #ddd; display: flex; gap: 6px; }
        .admin-reply-box input { flex: 1; padding: 7px; border: 1px solid #ccc; border-radius: 4px; outline: none; font-size: 12px; }
        .admin-reply-box button { padding: 7px 14px; background: #0084ff; color: #fff; border: none; border-radius: 4px; cursor: pointer; font-weight: bold; font-size: 12px; }

        /* زر الشات العائم للعميل */
        .chat-widget-btn { position: fixed; bottom: 20px; left: 20px; background: var(--primary-color); color: #000; width: 52px; height: 52px; border-radius: 50%; display: flex; flex-direction: column; align-items: center; justify-content: center; box-shadow: 0 4px 10px rgba(0,0,0,0.3); cursor: pointer; z-index: 999; font-weight: bold; text-decoration: none; border: 2px solid white; transition: transform 0.2s; font-size: 18px; }
        .chat-widget-btn:hover { transform: scale(1.08); }
        .chat-widget-btn span { font-size: 9px; margin-top: 1px; }
        
        /* نافذة الشات المنبثقة للعميل */
        .chat-popup { position: fixed; bottom: 82px; left: 15px; width: 300px; max-width: calc(100vw - 30px); height: 380px; background: white; border-radius: 10px; box-shadow: 0 5px 20px rgba(0,0,0,0.2); z-index: 1000; display: none; flex-direction: column; overflow: hidden; border: 1px solid #ccc; }
        .chat-header { background: var(--header-bg); color: white; padding: 10px 12px; display: flex; justify-content: space-between; align-items: center; font-weight: bold; font-size: 13px; }
        .chat-header button { background: none; border: none; color: white; font-size: 15px; cursor: pointer; }
        .chat-notice { background: #fff3cd; color: #856404; padding: 6px 8px; font-size: 10px; text-align: center; border-bottom: 1px solid #ffeeba; }
        .chat-messages-container { flex: 1; padding: 10px; overflow-y: auto; background: #f9f9f9; display: flex; flex-direction: column; gap: 6px; }
        .chat-msg { padding: 7px 10px; border-radius: 8px; max-width: 80%; font-size: 12px; line-height: 1.4; }
        .chat-msg.client { background: #0084ff; color: #fff; align-self: flex-end; }
        .chat-msg.admin { background: #e4e6eb; color: #000; align-self: flex-start; }
        .chat-footer { padding: 8px; background: #fff; border-top: 1px solid #ddd; display: flex; gap: 5px; }
        .chat-footer input { flex: 1; padding: 7px; border: 1px solid #ccc; border-radius: 4px; outline: none; font-size: 11px; }
        .chat-footer button { background: #0084ff; color: #fff; border: none; padding: 7px 10px; border-radius: 4px; cursor: pointer; font-weight: bold; font-size: 11px; }
        
        /* الفوتر */
        footer { background: var(--header-bg); color:white; padding:20px 15px; margin-top:30px; border-top:3px solid var(--primary-color); text-align:center; }
        .footer-content { max-width: 800px; margin: 0 auto; display: flex; flex-direction: column; gap: 12px; align-items: center; }
        .footer-support { background: #232f3e; border: 1px solid #37475a; padding: 12px 20px; border-radius: 8px; width: 100%; box-sizing: border-box; }
        .footer-support h4 { color: var(--primary-color); margin-top: 0; margin-bottom: 8px; font-size: 14px; }
        .footer-support p { margin: 4px 0; font-size: 13px; }
        .footer-support a { color: #ffd814; text-decoration: none; }
        .footer-support a:hover { text-decoration: underline; }
        
        /* التجاوب الدقيق مع شاشات الهواتف المحمولة */
        @media(max-width: 768px) {
            header { padding: 8px 10px; justify-content: center; }
            .logo { font-size: 18px; margin-bottom: 4px; }
            .search-bar { order: 3; width: 100%; max-width: 100%; margin-top: 4px; }
            .nav-right { order: 2; width: 100%; justify-content: center; gap: 5px; }
            .nav-btn { padding: 5px 8px; font-size: 11px; }
            .products-grid { grid-template-columns: repeat(2, 1fr); gap: 10px; }
            .card { padding: 8px; }
            .card img { height: 110px; }
            .card-title { font-size: 12px; height: 32px; }
            .card-price { font-size: 14px; }
            .btn-add { padding: 5px; font-size: 11px; }
            .admin-grid { grid-template-columns: 1fr; }
            .live-chat-admin-container { flex-direction: column; height: 400px; }
            .chat-sidebar { width: 100%; height: 120px; }
        }
    </style>
</head>
<body>

<header>
    <a href="/" class="logo">
        <div class="logo-3d">
            <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">
                <defs>
                    <linearGradient id="mainYellow" x1="0%" y1="0%" x2="100%" y2="100%">
                        <stop offset="0%" stop-color="#fff565"/>
                        <stop offset="50%" stop-color="#ffd700"/>
                        <stop offset="100%" stop-color="#ff9900"/>
                    </linearGradient>
                    <linearGradient id="blueShade" x1="0%" y1="0%" x2="100%" y2="100%">
                        <stop offset="0%" stop-color="#1e3c72"/>
                        <stop offset="100%" stop-color="#2a5298"/>
                    </linearGradient>
                </defs>
                <!-- خلفية حرف A ثلاثية الأبعاد -->
                <path d="M50 12 L82 78 L65 78 L50 45 L35 78 L18 78 Z" fill="url(#mainYellow)" stroke="#d4af37" stroke-width="2"/>
                <!-- الفراغ الداخلي لحرف A بلون أزرق غامق 3D -->
                <polygon points="50,28 60,56 40,56" fill="url(#blueShade)"/>
                <!-- خط العرض السفلي لحرف A -->
                <polygon points="37,58 63,58 60,67 40,67" fill="#e68a00"/>
            </svg>
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
        {% else %}
            <p style="font-size:16px;">لم يتم العثور على منتجات.</p>
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
                <div class="form-group"><label>العنوان بالكامل</label><textarea name="address" rows="2" placeholder="المحافظة - المدينة - الشارع" required></textarea></div>
                <div class="form-group"><label>تاريخ الميلاد</label><input type="date" name="birth_date" required></div>
                <button type="submit" class="btn-submit">تسجيل الحساب</button>
            </form>
            <a href="/login/google" class="btn-social">
                <img src="https://upload.wikimedia.org/wikipedia/commons/5/53/Google_%22G%22_Logo.svg" alt="Google">
                أو التسجيل السريع بواسطة Google
            </a>
        </div>

    {% elif page == 'profile' %}
        <div class="auth-form" style="max-width:500px; margin:auto;">
            <h2>👤 ملفي الشخصي وتعديل البيانات</h2>
            <form action="/profile" method="POST">
                <div class="form-group"><label>الاسم الأول</label><input type="text" name="first_name" value="{{ current_user.first_name }}" required></div>
                <div class="form-group"><label>الاسم الأخير</label><input type="text" name="last_name" value="{{ current_user.last_name }}" required></div>
                <div class="form-group"><label>البريد الإلكتروني (لا يمكن تعديله)</label><input type="email" value="{{ current_user.email }}" disabled style="background:#eee;"></div>
                <div class="form-group"><label>رقم الهاتف</label><input type="tel" name="phone" value="{{ current_user.phone or '' }}" required></div>
                <div class="form-group"><label>العنوان بالكامل</label><textarea name="address" rows="2" required>{{ current_user.address or '' }}</textarea></div>
                <div class="form-group"><label>تاريخ الميلاد</label><input type="date" name="birth_date" value="{{ current_user.birth_date or '' }}"></div>
                <button type="submit" class="btn-submit">حفظ وتحديث البيانات</button>
            </form>
        </div>

    {% elif page == 'cart' %}
        <h2>سلة التسوق</h2>
        {% if is_first_order and cart_items %}
        <div class="promo-banner">
            <h3>🎉 مبروك! لديك خصم ترحيبي 10% على أول أوردر لك</h3>
            <p>انقر على الكود أدناه لتفعيله مباشرة في سلة التسوق:</p>
            <form action="/apply-coupon" method="POST" style="display:inline;">
                <input type="hidden" name="coupon_code" value="Anything Shop 10">
                <button type="submit" class="promo-code-box" style="border:none; cursor:pointer;">Anything Shop 10</button>
            </form>
        </div>
        {% endif %}

        {% if cart_items %}
            <div style="overflow-x: auto;">
                <table class="cart-table">
                    <thead><tr><th>المنتج</th><th>السعر</th><th>الكمية</th><th>الإجمالي</th></tr></thead>
                    <tbody>
                        {% for item in cart_items %}
                        <tr><td>{{ item.name }}</td><td>{{ item.price }} ج.م</td><td>{{ item.qty }}</td><td>{{ "%.2f"|format(item.price * item.qty) }} ج.م</td></tr>
                        {% endfor %}
                    </tbody>
                </table>
            </div>

            <div style="background:white; color:#333; padding:12px; border-radius:8px; margin-bottom:15px; border:1px solid #ccc;">
                <form action="/apply-coupon" method="POST" style="display:flex; gap:8px; flex-wrap: wrap;">
                    <input type="text" name="coupon_code" placeholder="أدخل كود الخصم هنا" value="{{ session.get('applied_coupon', '') }}" style="flex-grow:1; padding:8px; border:1px solid #ccc; border-radius:4px; font-size: 13px;">
                    <button type="submit" style="background:#232f3e; color:white; border:none; padding:8px 15px; border-radius:4px; font-weight:bold; cursor:pointer; font-size: 13px;">تطبيق الكود</button>
                </form>
                {% if session.get('applied_coupon') %}
                    <p style="color:green; margin-top:6px; font-size: 12px;">✅ تم تفعيل الكود بنجاح (خصم 10%) <a href="/remove-coupon" style="color:red; text-decoration:none; margin-right:8px;">[إلغاء]</a></p>
                {% endif %}
            </div>

            <div style="text-align:left; background:white; color:#333; padding:12px; border-radius:8px; margin-bottom:15px;">
                <p>إجمالي المنتجات: <strong>{{ "%.2f"|format(total_price) }} ج.م</strong></p>
                {% if discount_amount > 0 %}
                    <p style="color:green;">قيمة الخصم: <strong>- {{ "%.2f"|format(discount_amount) }} ج.م</strong></p>
                {% endif %}
                <p>مصاريف الشحن: <strong>{{ "%.2f"|format(settings.shipping_fee) }} ج.م</strong></p>
                <h3 style="color: var(--price-color);">الإجمالي النهائي: {{ "%.2f"|format(final_total) }} ج.م</h3>
            </div>
            
            <div class="checkout-form">
                <h3>تفاصيل الشحن والتسليم</h3>
                <form action="/checkout" method="POST">
                    <div class="form-group"><label>رقم الهاتف للتواصل</label><input type="tel" name="phone" value="{{ current_user.phone or '' }}" required></div>
                    <div class="form-group"><label>عنوان التوصيل بالكامل</label><textarea name="address" rows="2" required>{{ current_user.address or '' }}</textarea></div>
                    <div class="form-group"><label>طريقة الدفع</label><select name="payment_method" required><option value="Cash">الدفع عند الاستلام (كاش)</option><option value="Paymob">الدفع الإلكتروني الآمن عبر Paymob</option></select></div>
                    <button type="submit" class="btn-submit">تأكيد ومتابعة الطلب</button>
                </form>
            </div>
        {% else %}
            <p>سلة التسوق فارغة حالياً.</p>
        {% endif %}

    {% elif page == 'orders' %}
        <h2>طلباتي</h2>
        {% for order in orders %}
            <div style="background:white; color:#333; padding:12px; border-radius:8px; margin-bottom:15px; border:1px solid #ccc; font-size: 13px;">
                <h4>طلب رقم #{{ order.id }} - {{ order.created_at.strftime('%Y-%m-%d %H:%M') }}</h4>
                <p><strong>حالة الدفع:</strong> <span class="{% if order.payment_status == 'Paid' %}status-paid{% else %}status-pending{% endif %}">{{ order.payment_status }}</span></p>
                <p><strong>طريقة الدفع:</strong> {{ order.payment_method }}</p>
                <p><strong>العنوان:</strong> {{ order.address }}</p>
                {% if order.discount_amount > 0 %}
                    <p><strong>الخصم المطبق:</strong> - {{ "%.2f"|format(order.discount_amount) }} ج.م</p>
                {% endif %}
                <h3 style="color: var(--price-color);">المبلغ الإجمالي: {{ "%.2f"|format(order.total_price) }} ج.م</h3>
            </div>
        {% endfor %}

    {% elif page == 'admin' %}
        <h2>⚙️ لوحة تحكم الأدمن</h2>
        
        <h3>💬 نظام الدعم الفني والمحادثات الحية مع العملاء</h3>
        <div class="live-chat-admin-container">
            <div class="chat-sidebar">
                <h4>قائمة المحادثات</h4>
                {% if not chat_sessions %}
                    <div style="padding: 10px; color: #777; text-align: center; font-size: 11px;">لا توجد محادثات نشطة.</div>
                {% endif %}
                {% for conv in chat_sessions %}
                    <a href="/admin?session={{ conv.session_id }}" class="client-chat-item {% if active_session == conv.session_id %}active{% endif %}">
                        <div>
                            <strong>جلسة:</strong> {{ conv.session_id[:8] }}...<br>
                            <small style="color: #666;">{{ conv.last_time[:16] }}</small>
                        </div>
                        {% if conv.unread_count > 0 %}
                            <span class="badge-notification" style="position: static;">{{ conv.unread_count }}</span>
                        {% endif %}
                    </a>
                {% endfor %}
            </div>
            <div class="chat-main-area">
                {% if active_session %}
                    <div class="admin-messages-box" id="adminMsgBox"></div>
                    <form class="admin-reply-box" id="adminReplyForm">
                        <input type="text" id="adminReplyInput" placeholder="اكتب ردك كأدمن هنا..." required autocomplete="off">
                        <button type="submit">إرسال</button>
                    </form>
                {% else %}
                    <div style="padding: 30px; text-align: center; color: #666; margin-top: 50px; font-size: 13px;">
                        <h4>اختر محادثة من القائمة الجانبية للبدء بالرد الفوري.</h4>
                    </div>
                {% endif %}
            </div>
        </div>

        <h3>📦 إدارة الأوردرات الجديدة</h3>
        <div style="overflow-x: auto;">
            <table class="admin-table">
                <thead><tr><th>رقم الطلب</th><th>العميل</th><th>الهاتف</th><th>العنوان</th><th>الإجمالي</th><th>الحالة</th><th>إجراء</th></tr></thead>
                <tbody>
                    {% for ord in all_orders %}
                    <tr {% if not ord.is_read %}style="background-color: #fff9db;"{% endif %}>
                        <td>#{{ ord.id }} {% if not ord.is_read %}<span style="background:red; color:white; font-size:9px; padding:2px 4px; border-radius:4px;">جديد</span>{% endif %}</td>
                        <td>{{ ord.customer.first_name }} {{ ord.customer.last_name }}</td>
                        <td>{{ ord.phone }}</td>
                        <td>{{ ord.address }}</td>
                        <td>{{ "%.2f"|format(ord.total_price) }} ج.م</td>
                        <td><span class="status-pending">{{ ord.payment_status }}</span></td>
                        <td><a href="/admin/mark-order-read/{{ ord.id }}" style="font-size:11px; color:#0084ff; text-decoration:none;">تحديد كمقروء</a></td>
                    </tr>
                    {% endfor %}
                </tbody>
            </table>
        </div>

        <div class="admin-grid">
            <div class="admin-card">
                <h3>➕ إضافة منتج جديد</h3>
                <form action="/admin/add-product" method="POST" enctype="multipart/form-data">
                    <div class="form-group"><label>اسم المنتج</label><input type="text" name="name" required></div>
                    <div class="form-group"><label>السعر (ج.م)</label><input type="number" step="0.01" name="price" required></div>
                    <div class="form-group"><label>القسم</label><input type="text" name="category" required></div>
                    <div class="form-group">
                        <label>صورة المنتج</label>
                        <input type="file" name="image_file" accept="image/*" style="margin-bottom:6px; font-size: 12px;">
                        <input type="url" name="image" placeholder="أو أدخل رابط صورة مباشر (URL)">
                    </div>
                    <button type="submit" class="btn-submit">حفظ المنتج</button>
                </form>
            </div>
            <div class="admin-card">
                <h3>🎨 تصميم الموقع</h3>
                <form action="/admin/update-settings" method="POST">
                    <div class="form-group"><label>لون الهيدر</label><input type="color" name="header_color" value="{{ settings.header_color }}"></div>
                    <div class="form-group"><label>اللون الرئيسي</label><input type="color" name="primary_color" value="{{ settings.primary_color }}"></div>
                    <div class="form-group"><label>لون الأسعار</label><input type="color" name="price_color" value="{{ settings.price_color }}"></div>
                    <div class="form-group"><label>لون الخلفية</label><input type="color" name="bg_color" value="{{ settings.bg_color }}"></div>
                    <div class="form-group"><label>حجم الخط</label><input type="number" name="font_size" value="{{ settings.font_size }}" required></div>
                    <div class="form-group"><label>مصاريف الشحن</label><input type="number" step="0.01" name="shipping_fee" value="{{ settings.shipping_fee }}" required></div>
                    <button type="submit" class="btn-submit">حفظ التصميم</button>
                </form>
            </div>
        </div>

        <h3>🛠️ إدارة المنتجات</h3>
        <div style="overflow-x: auto;">
            <table class="admin-table">
                <thead><tr><th>#</th><th>الصورة</th><th>الاسم</th><th>القسم</th><th>السعر</th><th>إجراءات</th></tr></thead>
                <tbody>
                    {% for p in all_products %}
                    <tr>
                        <td>{{ p.id }}</td>
                        <td><img src="{{ p.image }}" style="width:35px; height:35px; object-fit:cover; border-radius:4px;"></td>
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

    {% elif page == 'edit_product' %}
        <div class="admin-card" style="max-width:500px; margin:auto;">
            <h2>✏️ تعديل المنتج #{{ edit_prod.id }}</h2>
            <form action="/admin/edit-product/{{ edit_prod.id }}" method="POST" enctype="multipart/form-data">
                <div class="form-group"><label>الاسم</label><input type="text" name="name" value="{{ edit_prod.name }}" required></div>
                <div class="form-group"><label>السعر</label><input type="number" step="0.01" name="price" value="{{ edit_prod.price }}" required></div>
                <div class="form-group"><label>القسم</label><input type="text" name="category" value="{{ edit_prod.category }}" required></div>
                <div class="form-group">
                    <label>تحديث الصورة</label>
                    <input type="file" name="image_file" accept="image/*" style="margin-bottom:6px; font-size: 12px;">
                    <input type="url" name="image" value="{{ edit_prod.image }}" required>
                </div>
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
            <a href="/login/google" class="btn-social">
                <img src="https://upload.wikimedia.org/wikipedia/commons/5/53/Google_%22G%22_Logo.svg" alt="Google">
                تسجيل الدخول بواسطة Google
            </a>
        </div>
    {% endif %}
</div>

<!-- زر الشات العائم للعميل -->
<div id="support-chat-btn" class="chat-widget-btn">
    💬
    <span>الدعم</span>
</div>

<!-- نافذة محادثة ودعم العملاء المنبثقة -->
<div id="support-chat-window" class="chat-popup">
    <div class="chat-header">
        <span>الدعم الفني المباشر</span>
        <button id="close-chat">✕</button>
    </div>
    <div class="chat-notice">
        ⏰ سيتم الرد عليك في أقرب وقت.
    </div>
    <div id="chat-messages" class="chat-messages-container"></div>
    <div class="chat-footer">
        <input type="text" id="chat-input" placeholder="اكتب رسالتك هنا..." autocomplete="off">
        <button id="chat-send">إرسال</button>
    </div>
</div>

<script>
document.addEventListener("DOMContentLoaded", function() {
    {% if current_user.is_authenticated and current_user.is_admin %}
    function checkAdminNotifications() {
        fetch('/api/admin/notifications')
            .then(res => res.json())
            .then(data => {
                const totalUnread = data.unread_messages + data.unread_orders;
                const badge = document.getElementById('global-admin-badge');
                if (badge) {
                    if (totalUnread > 0) {
                        badge.innerText = totalUnread;
                        badge.style.display = 'inline-block';
                    } else {
                        badge.style.display = 'none';
                    }
                }
            });
    }
    setInterval(checkAdminNotifications, 5000);
    checkAdminNotifications();
    {% endif %}

    let sessionId = localStorage.getItem('support_session_id');
    if (!sessionId) {
        sessionId = 'session_' + Math.random().toString(36).substring(2) + Date.now();
        localStorage.setItem('support_session_id', sessionId);
    }

    const btn = document.getElementById('support-chat-btn');
    const win = document.getElementById('support-chat-window');
    const closeBtn = document.getElementById('close-chat');
    const sendBtn = document.getElementById('chat-send');
    const input = document.getElementById('chat-input');
    const msgContainer = document.getElementById('chat-messages');

    let isChatOpen = false;

    if (btn && win) {
        btn.onclick = () => {
            isChatOpen = !isChatOpen;
            win.style.display = isChatOpen ? 'flex' : 'none';
            if (isChatOpen) fetchClientMessages();
        };
        closeBtn.onclick = () => {
            isChatOpen = false;
            win.style.display = 'none';
        };
    }

    function fetchClientMessages() {
        fetch('/api/chat/messages?session_id=' + sessionId)
            .then(res => res.json())
            .then(data => {
                if (data.status === 'success') {
                    msgContainer.innerHTML = '';
                    if (data.messages.length === 0) {
                        msgContainer.innerHTML = '<div style="text-align:center; color:#888; font-size:11px; margin-top:15px;">أهلاً بك! اكتب رسالتك وسنرد عليك.</div>';
                    }
                    data.messages.forEach(msg => {
                        const div = document.createElement('div');
                        div.className = 'chat-msg ' + msg.sender_type;
                        div.innerText = msg.message;
                        msgContainer.appendChild(div);
                    });
                    msgContainer.scrollTop = msgContainer.scrollHeight;
                }
            });
    }

    if (sendBtn && input) {
        sendBtn.onclick = sendClientMessage;
        input.onkeypress = (e) => { if (e.key === 'Enter') sendClientMessage(); };
    }

    function sendClientMessage() {
        const text = input.value.trim();
        if (!text) return;

        const formData = new FormData();
        formData.append('action', 'client_send');
        formData.append('session_id', sessionId);
        formData.append('message', text);

        fetch('/api/chat/send', { method: 'POST', body: formData })
            .then(res => res.json())
            .then(data => {
                if (data.status === 'success') {
                    input.value = '';
                    fetchClientMessages();
                }
            });
    }

    setInterval(() => {
        if (isChatOpen) fetchClientMessages();
    }, 4000);

    const adminMsgBox = document.getElementById('adminMsgBox');
    const adminReplyForm = document.getElementById('adminReplyForm');
    const adminReplyInput = document.getElementById('adminReplyInput');
    const urlParams = new URLSearchParams(window.location.search);
    const activeSession = urlParams.get('session');

    if (adminMsgBox && activeSession) {
        function fetchAdminMessages() {
            fetch('/api/chat/messages?session_id=' + activeSession)
                .then(res => res.json())
                .then(data => {
                    if (data.status === 'success') {
                        adminMsgBox.innerHTML = '';
                        data.messages.forEach(msg => {
                            const div = document.createElement('div');
                            div.className = 'admin-msg-bubble ' + msg.sender_type;
                            div.innerHTML = msg.message.replace(/\\n/g, '<br>') + 
                                            `<div style="font-size:9px; opacity:0.7; margin-top:2px; text-align:left;">${msg.created_at}</div>`;
                            adminMsgBox.appendChild(div);
                        });
                        adminMsgBox.scrollTop = adminMsgBox.scrollHeight;
                    }
                });
        }

        fetchAdminMessages();
        setInterval(fetchAdminMessages, 4000);

        if (adminReplyForm && adminReplyInput) {
            adminReplyForm.onsubmit = (e) => {
                e.preventDefault();
                const text = adminReplyInput.value.trim();
                if (!text) return;

                const formData = new FormData();
                formData.append('action', 'admin_send');
                formData.append('session_id', activeSession);
                formData.append('message', text);

                fetch('/api/chat/send', { method: 'POST', body: formData })
                    .then(res => res.json())
                    .then(data => {
                        if (data.status === 'success') {
                            adminReplyInput.value = '';
                            fetchAdminMessages();
                        }
                    });
            };
        }
    }
});
</script>

<footer>
    <div class="footer-content">
        <div class="footer-support">
            <h4>مركز المساعدة والدعم الفني</h4>
            <p>هل تحتاج إلى المساعدة أو استفسار بخصوص طلبك؟ استخدم زر <strong>الدعم الفوري</strong> العائم أسفل الشاشة للتحدث معنا مباشرة في أي وقت.</p>
        </div>
        <small>©️ 2026 Anything Shop - جميع الحقوق محفوظة.</small>
    </div>
</footer>
</body>
</html>
"""

# --- Helpers ---
UPLOAD_FOLDER = 'static/uploads'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

def get_cart_count():
    return sum(session.get('cart', {}).values())

def get_settings():
    settings = SiteSettings.query.first()
    if not settings:
        settings = SiteSettings()
        db.session.add(settings)
        db.session.commit()
    return settings

def get_categories():
    return [c[0] for c in db.session.query(Product.category).distinct().all()]

# --- Routes ---
@app.route("/")
def home():
    return render_template_string(HTML_TEMPLATE, page='home', products=Product.query.all(), cart_count=get_cart_count(), categories_list=get_categories(), current_cat="All", settings=get_settings())

@app.route("/category/<cat_name>")
def category_view(cat_name):
    return render_template_string(HTML_TEMPLATE, page='category', products=Product.query.filter_by(category=cat_name).all(), cart_count=get_cart_count(), categories_list=get_categories(), current_cat=cat_name, settings=get_settings())

@app.route("/search")
def search():
    query = request.args.get("q", "").strip()
    if not query: return redirect(url_for('home'))
    filters = [Product.name.ilike(f"%{w}%") for w in query.split()] + [Product.category.ilike(f"%{w}%") for w in query.split()]
    return render_template_string(HTML_TEMPLATE, page='search', products=Product.query.filter(db.or_(*filters)).all(), search_query=query, cart_count=get_cart_count(), categories_list=get_categories(), current_cat="", settings=get_settings())

@app.route("/api/admin/notifications", methods=["GET"])
def api_admin_notifications():
    if not current_user.is_authenticated or not current_user.is_admin:
        return jsonify({"unread_messages": 0, "unread_orders": 0})
    
    unread_messages = SupportMessage.query.filter_by(sender_type='client', is_read=False).count()
    unread_orders = Order.query.filter_by(is_read=False).count()
    return jsonify({"unread_messages": unread_messages, "unread_orders": unread_orders})

@app.route("/api/chat/send", methods=["POST"])
def api_chat_send():
    action = request.form.get("action")
    session_id = request.form.get("session_id")
    message = request.form.get("message", "").strip()

    if not session_id or not message:
        return jsonify({"status": "error", "message": "بيانات غير صالحة"})

    if action == "client_send":
        msg = SupportMessage(session_id=session_id, sender_type="client", message=message, is_read=False)
        db.session.add(msg)
        db.session.commit()
        return jsonify({"status": "success"})

    elif action == "admin_send" and current_user.is_authenticated and current_user.is_admin:
        msg = SupportMessage(session_id=session_id, sender_type="admin", message=message, is_read=True)
        db.session.add(msg)
        db.session.commit()
        return jsonify({"status": "success"})

    return jsonify({"status": "error", "message": "صلاحيات غير مرفوعة"})

@app.route("/api/chat/messages", methods=["GET"])
def api_chat_messages():
    session_id = request.args.get("session_id")
    if not session_id:
        return jsonify({"status": "error", "messages": []})
    
    if current_user.is_authenticated and current_user.is_admin:
        SupportMessage.query.filter_by(session_id=session_id, sender_type='client').update({SupportMessage.is_read: True})
        db.session.commit()

    messages = SupportMessage.query.filter_by(session_id=session_id).order_by(SupportMessage.created_at.asc()).all()
    msgs_list = [{
        "sender_type": m.sender_type,
        "message": m.message,
        "created_at": m.created_at.strftime('%Y-%m-%d %H:%M')
    } for m in messages]

    return jsonify({"status": "success", "messages": msgs_list})

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        first_name, last_name, email, password = request.form.get("first_name"), request.form.get("last_name"), request.form.get("email"), request.form.get("password")
        phone, address, birth_date = request.form.get("phone"), request.form.get("address"), request.form.get("birth_date")

        if User.query.filter_by(email=email).first():
            flash("البريد الإلكتروني مسجل مسبقاً.")
            return redirect(url_for('register'))

        new_user = User(
            first_name=first_name, last_name=last_name, email=email,
            password_hash=generate_password_hash(password, method='scrypt'),
            phone=phone, address=address, birth_date=birth_date, auth_provider='local'
        )
        db.session.add(new_user)
        db.session.commit()
        login_user(new_user)
        flash("تم إنشاء الحساب وتسجيل الدخول بنجاح! مبروك كود الخصم الترحيبي Anything Shop 10")
        return redirect(url_for('home'))

    return render_template_string(HTML_TEMPLATE, page='register', cart_count=get_cart_count(), categories_list=get_categories(), settings=get_settings())

@app.route("/profile", methods=["GET", "POST"])
@login_required
def profile():
    if request.method == "POST":
        current_user.first_name, current_user.last_name = request.form.get("first_name"), request.form.get("last_name")
        current_user.phone, current_user.address, current_user.birth_date = request.form.get("phone"), request.form.get("address"), request.form.get("birth_date")
        db.session.commit()
        flash("تم تحديث بيانات البروفايل بنجاح!")
        return redirect(url_for('profile'))
    return render_template_string(HTML_TEMPLATE, page='profile', cart_count=get_cart_count(), categories_list=get_categories(), settings=get_settings())

@app.route("/add-to-cart", methods=["POST"])
def add_to_cart():
    p_id = str(request.form.get("product_id"))
    cart = session.get('cart', {})
    cart[p_id] = cart.get(p_id, 0) + 1
    session['cart'] = cart
    flash("تمت إضافة المنتج للسلة بنجاح!")
    return redirect(request.referrer or url_for('home'))

@app.route("/apply-coupon", methods=["POST"])
def apply_coupon():
    code = request.form.get("coupon_code", "").strip()
    if code == "Anything Shop 10":
        session['applied_coupon'] = code
        flash("تم تفعيل كود الخصم (10%) بنجاح!")
    else:
        flash("كود الخصم غير صحيح أو منتهي الصلاحية.")
    return redirect(url_for('view_cart'))

@app.route("/remove-coupon")
def remove_coupon():
    session.pop('applied_coupon', None)
    flash("تم إلغاء كود الخصم.")
    return redirect(url_for('view_cart'))

@app.route("/cart")
def view_cart():
    cart = session.get('cart', {})
    cart_items, total_price = [], 0.0
    for p_id_str, qty in cart.items():
        product = Product.query.get(int(p_id_str))
        if product:
            total_price += product.price * qty
            cart_items.append({"name": product.name, "price": product.price, "qty": qty})
    
    is_first_order = False
    if current_user.is_authenticated and Order.query.filter_by(user_id=current_user.id).count() == 0:
        is_first_order = True

    discount_amount = 0.0
    if session.get('applied_coupon') == "Anything Shop 10":
        discount_amount = total_price * 0.10

    settings = get_settings()
    final_total = (total_price - discount_amount) + settings.shipping_fee

    return render_template_string(
        HTML_TEMPLATE, page='cart', cart_items=cart_items, total_price=total_price, 
        discount_amount=discount_amount, final_total=final_total, is_first_order=is_first_order,
        cart_count=get_cart_count(), categories_list=get_categories(), current_cat="Cart", settings=settings
    )

@app.route("/checkout", methods=["POST"])
@login_required
def checkout():
    phone, address, payment_method = request.form.get("phone"), request.form.get("address"), request.form.get("payment_method")
    cart = session.get('cart', {})
    if not cart: return redirect(url_for('home'))

    order_items, items_price = [], 0.0
    for p_id_str, qty in cart.items():
        product = Product.query.get(int(p_id_str))
        if product:
            items_price += product.price * qty
            order_items.append({"name": product.name, "price": product.price, "qty": qty})

    discount_amount = 0.0
    if session.get('applied_coupon') == "Anything Shop 10":
        discount_amount = items_price * 0.10

    settings = get_settings()
    total_price = (items_price - discount_amount) + settings.shipping_fee

    new_order = Order(
        user_id=current_user.id, phone=phone, address=address, payment_method=payment_method,
        payment_status='Pending' if payment_method == 'Paymob' else 'Cash on Delivery',
        items_price=items_price, discount_amount=discount_amount, shipping_fee=settings.shipping_fee, 
        total_price=total_price, items_json=json.dumps(order_items), is_read=False
    )
    db.session.add(new_order)
    db.session.commit()
    
    session['cart'] = {}
    session.pop('applied_coupon', None)

    flash("تم تسجيل طلبك بنجاح!")
    return redirect(url_for('my_orders'))

@app.route("/login/google")
def login_google():
    return google.authorize_redirect(url_for('google_callback', _external=True))

@app.route("/login/google/callback")
def google_callback():
    token = google.authorize_access_token()
    user_info = token.get('userinfo')
    if user_info:
        email = user_info['email']
        name_parts = user_info.get('name', 'مستخدم جوجل').split(' ', 1)
        first_name, last_name = name_parts[0], name_parts[1] if len(name_parts) > 1 else 'جوجل'
        picture = user_info.get('picture', '')

        user = User.query.filter_by(email=email).first()
        if not user:
            user = User(
                first_name=first_name, last_name=last_name, email=email,
                auth_provider='google', avatar_url=picture,
                is_admin=(email == "admin@shop.com"),
                phone="01000000000", address="يرجى تحديث العنوان", birth_date="2000-01-01"
            )
            db.session.add(user)
            db.session.commit()

        login_user(user)
        flash("تم تسجيل الدخول بواسطة Google بنجاح!")
    return redirect(url_for('home'))

@app.route("/orders")
@login_required
def my_orders():
    return render_template_string(HTML_TEMPLATE, page='orders', orders=Order.query.filter_by(user_id=current_user.id).order_by(Order.created_at.desc()).all(), cart_count=get_cart_count(), categories_list=get_categories(), current_cat="Orders", settings=get_settings())

@app.route("/admin")
@login_required
def admin_panel():
    if not current_user.is_admin: 
        flash("عذراً، هذه الصفحة مخصصة للأدمن فقط.")
        return redirect(url_for('home'))
    
    subquery = db.session.query(
        SupportMessage.session_id, 
        db.func.max(SupportMessage.created_at).label('max_time')
    ).group_by(SupportMessage.session_id).subquery()
    
    raw_sessions = db.session.query(subquery.c.session_id, subquery.c.max_time.label('last_time'))\
                      .order_by(subquery.c.max_time.desc()).all()
    
    chat_sessions = []
    for s in raw_sessions:
        unread_cnt = SupportMessage.query.filter_by(session_id=s.session_id, sender_type='client', is_read=False).count()
        chat_sessions.append({
            "session_id": s.session_id,
            "last_time": s.last_time,
            "unread_count": unread_cnt
        })
    
    active_session = request.args.get("session")
    if not active_session and chat_sessions:
        active_session = chat_sessions[0]["session_id"]

    return render_template_string(
        HTML_TEMPLATE, page='admin', 
        all_orders=Order.query.order_by(Order.created_at.desc()).all(), 
        all_products=Product.query.order_by(Product.id.desc()).all(), 
        chat_sessions=chat_sessions, active_session=active_session,
        cart_count=get_cart_count(), categories_list=get_categories(), current_cat="Admin", settings=get_settings()
    )

@app.route("/admin/mark-order-read/<int:order_id>")
@login_required
def mark_order_read(order_id):
    if not current_user.is_admin: return redirect(url_for('home'))
    ord = Order.query.get_or_404(order_id)
    ord.is_read = True
    db.session.commit()
    return redirect(url_for('admin_panel'))

@app.route("/admin/add-product", methods=["POST"])
@login_required
def admin_add_product():
    if not current_user.is_admin: return redirect(url_for('home'))
    
    name, price, category = request.form.get("name"), float(request.form.get("price")), request.form.get("category")
    image_url = request.form.get("image")
    
    image_file = request.files.get('image_file')
    if image_file and image_file.filename != '':
        filename = datetime.now().strftime("%Y%m%d%H%M%S_") + image_file.filename
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        image_file.save(filepath)
        image_url = f"/{filepath}"

    db.session.add(Product(name=name, price=price, category=category, image=image_url))
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
        
        image_url = request.form.get("image")
        image_file = request.files.get('image_file')
        if image_file and image_file.filename != '':
            filename = datetime.now().strftime("%Y%m%d%H%M%S_") + image_file.filename
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            image_file.save(filepath)
            image_url = f"/{filepath}"
            
        prod.image = image_url
        db.session.commit()
        flash("تم تعديل المنتج بنجاح!")
        return redirect(url_for('admin_panel'))
    return render_template_string(HTML_TEMPLATE, page='edit_product', edit_prod=prod, cart_count=get_cart_count(), categories_list=get_categories(), settings=get_settings())

@app.route("/admin/delete-product/<int:prod_id>")
@login_required
def admin_delete_product(prod_id):
    if not current_user.is_admin: return redirect(url_for('home'))
    db.session.delete(Product.query.get_or_404(prod_id))
    db.session.commit()
    flash("تم حذف المنتج بنجاح.")
    return redirect(url_for('admin_panel'))

@app.route("/admin/update-settings", methods=["POST"])
@login_required
def admin_update_settings():
    if not current_user.is_admin: return redirect(url_for('home'))
    settings = get_settings()
    settings.header_color, settings.primary_color, settings.price_color = request.form.get("header_color"), request.form.get("primary_color"), request.form.get("price_color")
    settings.bg_color, settings.font_size, settings.shipping_fee = request.form.get("bg_color"), int(request.form.get("font_size")), float(request.form.get("shipping_fee"))
    db.session.commit()
    flash("تم تحديث إعدادات التصميم بنجاح!")
    return redirect(url_for('admin_panel'))

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        user = User.query.filter_by(email=request.form.get("email")).first()
        if user and check_password_hash(user.password_hash, request.form.get("password")):
            login_user(user)
            return redirect(url_for('admin_panel' if user.is_admin else 'home'))
        flash("بيانات الدخول غير صحيحة.")
    return render_template_string(HTML_TEMPLATE, page='login', cart_count=get_cart_count(), categories_list=get_categories(), settings=get_settings())

@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for('home'))

def seed_data():
    if Product.query.count() == 0:
        db.session.add_all([
            Product(name="لبانة نعناع نكهة ممتازة", price=0.50, category="مأكولات ومشروبات", image="https://images.unsplash.com/photo-1582058091505-f87a2e55a40f?w=400"),
            Product(name="حذاء رياضي Pro", price=450.0, category="أحذية", image="https://images.unsplash.com/photo-1542291026-7eec264c27ff?w=400"),
            Product(name="سماعة لاسلكية Bluetooth", price=650.0, category="إلكترونيات", image="https://images.unsplash.com/photo-1505740420928-5e560c06d30e?w=400")
        ])
        db.session.commit()
    if not User.query.filter_by(email="admin@shop.com").first():
        db.session.add(User(first_name="أحمد", last_name="الأدمن", email="admin@shop.com", password_hash=generate_password_hash("admin123", method='scrypt'), is_admin=True, phone="01000000000", address="القاهرة", birth_date="2000-01-01"))
        db.session.commit()

with app.app_context():
    db.create_all()
    seed_data()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
