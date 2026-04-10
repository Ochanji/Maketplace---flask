from flask import Flask, render_template, redirect, url_for, request, flash, abort
from flask_sqlalchemy import SQLAlchemy
from flask_login import (LoginManager, UserMixin, login_user,
                         logout_user, login_required, current_user)
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
from functools import wraps
import os

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'mk-super-secret-2026')

# Database: defaults to SQLite for local dev.
# To switch to MySQL, set DATABASE_URL env var:
#   DATABASE_URL=mysql+pymysql://user:pass@host:3306/marketplace
# Install PyMySQL: pip install PyMySQL
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get(
    'DATABASE_URL', 'sqlite:///marketplace.db'
)
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    'pool_pre_ping': True,      # auto-reconnect on stale connections (important for MySQL)
    'pool_recycle': 300,        # recycle connections every 5 min (MySQL drops idle ones)
}

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'
login_manager.login_message = 'Please log in to access this page.'
login_manager.login_message_category = 'info'

# ─── Models ───────────────────────────────────────────────────────────────────

class User(UserMixin, db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    is_admin = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


class Category(db.Model):
    __tablename__ = 'categories'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), unique=True, nullable=False)
    slug = db.Column(db.String(80), unique=True, nullable=False)
    icon = db.Column(db.String(50), default='📦')
    products = db.relationship('Product', backref='category', lazy=True)


class Product(db.Model):
    __tablename__ = 'products'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=False)
    price = db.Column(db.Float, nullable=False)
    original_price = db.Column(db.Float, nullable=True)
    image_url = db.Column(db.String(500), default='')
    category_id = db.Column(db.Integer, db.ForeignKey('categories.id'), nullable=True)
    stock = db.Column(db.Integer, default=0)
    featured = db.Column(db.Boolean, default=False)
    badge = db.Column(db.String(50), default='')   # e.g. "New", "Sale", "Hot"
    rating = db.Column(db.Float, default=4.5)
    reviews = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    @property
    def discount_pct(self):
        if self.original_price and self.original_price > self.price:
            return int((1 - self.price / self.original_price) * 100)
        return 0

    @property
    def in_stock(self):
        return self.stock > 0


class SiteSettings(db.Model):
    __tablename__ = 'site_settings'
    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(100), unique=True, nullable=False)
    value = db.Column(db.Text, default='')


# ─── Helpers ──────────────────────────────────────────────────────────────────

@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))


def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin:
            abort(403)
        return f(*args, **kwargs)
    return decorated


def get_setting(key, default=''):
    s = SiteSettings.query.filter_by(key=key).first()
    return s.value if s else default


def set_setting(key, value):
    s = SiteSettings.query.filter_by(key=key).first()
    if s:
        s.value = value
    else:
        db.session.add(SiteSettings(key=key, value=value))
    db.session.commit()


@app.context_processor
def inject_globals():
    settings = {s.key: s.value for s in SiteSettings.query.all()}
    categories = Category.query.all()
    return dict(settings=settings, all_categories=categories)


# ─── Public Routes ────────────────────────────────────────────────────────────

@app.route('/')
def index():
    featured = Product.query.filter_by(featured=True).limit(8).all()
    all_products = Product.query.order_by(Product.created_at.desc()).limit(12).all()
    categories = Category.query.all()
    return render_template('index.html', featured=featured,
                           all_products=all_products, categories=categories)


@app.route('/shop')
def shop():
    q = request.args.get('q', '')
    cat_slug = request.args.get('category', '')
    sort = request.args.get('sort', 'newest')

    query = Product.query
    if q:
        query = query.filter(Product.name.ilike(f'%{q}%'))
    if cat_slug:
        cat = Category.query.filter_by(slug=cat_slug).first()
        if cat:
            query = query.filter_by(category_id=cat.id)

    if sort == 'price_asc':
        query = query.order_by(Product.price.asc())
    elif sort == 'price_desc':
        query = query.order_by(Product.price.desc())
    elif sort == 'rating':
        query = query.order_by(Product.rating.desc())
    else:
        query = query.order_by(Product.created_at.desc())

    products = query.all()
    active_cat = cat_slug
    return render_template('shop/shop.html', products=products, q=q,
                           active_cat=active_cat, sort=sort)


@app.route('/product/<int:pid>')
def product_detail(pid):
    product = Product.query.get_or_404(pid)
    related = Product.query.filter(
        Product.category_id == product.category_id,
        Product.id != product.id
    ).limit(4).all()
    return render_template('shop/product_detail.html', product=product, related=related)


# ─── Auth Routes ──────────────────────────────────────────────────────────────

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        remember = bool(request.form.get('remember'))
        user = User.query.filter_by(username=username).first()
        if user and user.check_password(password):
            login_user(user, remember=remember)
            next_page = request.args.get('next')
            flash(f'Welcome back, {user.username}!', 'success')
            return redirect(next_page or url_for('index'))
        flash('Invalid username or password.', 'danger')
    return render_template('auth/login.html')


@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '')
        confirm = request.form.get('confirm', '')

        if not username or not email or not password:
            flash('All fields are required.', 'danger')
        elif password != confirm:
            flash('Passwords do not match.', 'danger')
        elif User.query.filter_by(username=username).first():
            flash('Username already taken.', 'danger')
        elif User.query.filter_by(email=email).first():
            flash('Email already registered.', 'danger')
        else:
            user = User(username=username, email=email)
            user.set_password(password)
            db.session.add(user)
            db.session.commit()
            login_user(user)
            flash('Account created! Welcome to the marketplace.', 'success')
            return redirect(url_for('index'))
    return render_template('auth/register.html')


@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('You have been logged out.', 'info')
    return redirect(url_for('index'))


# ─── Admin Routes ─────────────────────────────────────────────────────────────

@app.route('/admin')
@login_required
@admin_required
def admin_dashboard():
    stats = {
        'products': Product.query.count(),
        'users': User.query.count(),
        'categories': Category.query.count(),
        'featured': Product.query.filter_by(featured=True).count(),
    }
    recent_products = Product.query.order_by(Product.created_at.desc()).limit(5).all()
    return render_template('admin/dashboard.html', stats=stats,
                           recent_products=recent_products)


@app.route('/admin/products')
@login_required
@admin_required
def admin_products():
    products = Product.query.order_by(Product.created_at.desc()).all()
    return render_template('admin/products.html', products=products)


@app.route('/admin/products/new', methods=['GET', 'POST'])
@login_required
@admin_required
def admin_product_new():
    categories = Category.query.all()
    if request.method == 'POST':
        p = Product(
            name=request.form['name'],
            description=request.form['description'],
            price=float(request.form['price']),
            original_price=float(request.form['original_price']) if request.form.get('original_price') else None,
            image_url=request.form.get('image_url', ''),
            category_id=int(request.form['category_id']) if request.form.get('category_id') else None,
            stock=int(request.form.get('stock', 0)),
            featured=bool(request.form.get('featured')),
            badge=request.form.get('badge', ''),
            rating=float(request.form.get('rating', 4.5)),
            reviews=int(request.form.get('reviews', 0)),
        )
        db.session.add(p)
        db.session.commit()
        flash('Product created successfully!', 'success')
        return redirect(url_for('admin_products'))
    return render_template('admin/product_form.html', product=None, categories=categories)


@app.route('/admin/products/<int:pid>/edit', methods=['GET', 'POST'])
@login_required
@admin_required
def admin_product_edit(pid):
    product = Product.query.get_or_404(pid)
    categories = Category.query.all()
    if request.method == 'POST':
        product.name = request.form['name']
        product.description = request.form['description']
        product.price = float(request.form['price'])
        product.original_price = float(request.form['original_price']) if request.form.get('original_price') else None
        product.image_url = request.form.get('image_url', '')
        product.category_id = int(request.form['category_id']) if request.form.get('category_id') else None
        product.stock = int(request.form.get('stock', 0))
        product.featured = bool(request.form.get('featured'))
        product.badge = request.form.get('badge', '')
        product.rating = float(request.form.get('rating', 4.5))
        product.reviews = int(request.form.get('reviews', 0))
        db.session.commit()
        flash('Product updated!', 'success')
        return redirect(url_for('admin_products'))
    return render_template('admin/product_form.html', product=product, categories=categories)


@app.route('/admin/products/<int:pid>/delete', methods=['POST'])
@login_required
@admin_required
def admin_product_delete(pid):
    product = Product.query.get_or_404(pid)
    db.session.delete(product)
    db.session.commit()
    flash('Product deleted.', 'warning')
    return redirect(url_for('admin_products'))


@app.route('/admin/categories')
@login_required
@admin_required
def admin_categories():
    categories = Category.query.all()
    return render_template('admin/categories.html', categories=categories)


@app.route('/admin/categories/new', methods=['POST'])
@login_required
@admin_required
def admin_category_new():
    name = request.form.get('name', '').strip()
    icon = request.form.get('icon', '📦').strip()
    if name:
        slug = name.lower().replace(' ', '-')
        if not Category.query.filter_by(slug=slug).first():
            db.session.add(Category(name=name, slug=slug, icon=icon))
            db.session.commit()
            flash('Category added!', 'success')
        else:
            flash('Category already exists.', 'danger')
    return redirect(url_for('admin_categories'))


@app.route('/admin/categories/<int:cid>/delete', methods=['POST'])
@login_required
@admin_required
def admin_category_delete(cid):
    cat = Category.query.get_or_404(cid)
    db.session.delete(cat)
    db.session.commit()
    flash('Category deleted.', 'warning')
    return redirect(url_for('admin_categories'))


@app.route('/admin/settings', methods=['GET', 'POST'])
@login_required
@admin_required
def admin_settings():
    setting_keys = [
        'site_name', 'site_tagline', 'site_description',
        'hero_title', 'hero_subtitle', 'hero_cta',
        'contact_email', 'footer_text',
        'primary_color', 'accent_color',
        'logo_url', 'hero_image_url',
    ]
    if request.method == 'POST':
        for key in setting_keys:
            set_setting(key, request.form.get(key, ''))
        flash('Site settings saved!', 'success')
        return redirect(url_for('admin_settings'))
    current = {k: get_setting(k) for k in setting_keys}
    return render_template('admin/settings.html', current=current, setting_keys=setting_keys)


# ─── Error Handlers ───────────────────────────────────────────────────────────

@app.errorhandler(403)
def forbidden(e):
    return render_template('errors/403.html'), 403


@app.errorhandler(404)
def not_found(e):
    return render_template('errors/404.html'), 404


# ─── DB Init & Seed ───────────────────────────────────────────────────────────

def seed_db():
    # Admin user
    if not User.query.filter_by(username='admin').first():
        admin = User(username='admin', email='admin@marketplace.com', is_admin=True)
        admin.set_password('admin')
        db.session.add(admin)

    # Default settings
    defaults = {
        'site_name': 'Nexus Market',
        'site_tagline': 'Discover · Buy · Enjoy',
        'site_description': 'The premium marketplace for exclusive products.',
        'hero_title': 'Shop the Future',
        'hero_subtitle': 'Curated products. Unbeatable prices. Delivered fast.',
        'hero_cta': 'Explore Now',
        'contact_email': 'hello@nexusmarket.com',
        'footer_text': '© 2026 Nexus Market. All rights reserved.',
        'primary_color': '#6366f1',
        'accent_color': '#ec4899',
        'logo_url': '',
        'hero_image_url': '',
    }
    for k, v in defaults.items():
        if not SiteSettings.query.filter_by(key=k).first():
            db.session.add(SiteSettings(key=k, value=v))

    # Categories
    cats_data = [
        ('Electronics', 'electronics', '⚡'),
        ('Fashion', 'fashion', '👗'),
        ('Home & Living', 'home-living', '🏠'),
        ('Sports', 'sports', '🏆'),
        ('Books', 'books', '📚'),
        ('Beauty', 'beauty', '✨'),
    ]
    cats = {}
    for name, slug, icon in cats_data:
        c = Category.query.filter_by(slug=slug).first()
        if not c:
            c = Category(name=name, slug=slug, icon=icon)
            db.session.add(c)
        cats[slug] = c
    db.session.flush()

    # Products
    products_data = [
        {
            'name': 'Pro Wireless Headphones',
            'description': 'Immersive 3D audio with 40-hour battery life, active noise cancellation, and plush ear cushions. Perfect for work or travel.',
            'price': 149.99, 'original_price': 249.99,
            'image_url': 'https://images.unsplash.com/photo-1505740420928-5e560c06d30e?w=600&q=80',
            'category': 'electronics', 'stock': 25, 'featured': True,
            'badge': 'Sale', 'rating': 4.8, 'reviews': 2847,
        },
        {
            'name': 'Smart Fitness Watch',
            'description': 'Track your health 24/7 with heart rate, SpO2, sleep analysis, and GPS. Waterproof up to 50m. 7-day battery.',
            'price': 199.00, 'original_price': None,
            'image_url': 'https://images.unsplash.com/photo-1523275335684-37898b6baf30?w=600&q=80',
            'category': 'electronics', 'stock': 40, 'featured': True,
            'badge': 'New', 'rating': 4.9, 'reviews': 1523,
        },
        {
            'name': 'Leather Minimalist Wallet',
            'description': 'Slim genuine leather wallet with RFID blocking. Holds up to 8 cards and cash. Available in 5 colors.',
            'price': 39.99, 'original_price': None,
            'image_url': 'https://images.unsplash.com/photo-1627123424574-724758594e93?w=600&q=80',
            'category': 'fashion', 'stock': 100, 'featured': True,
            'badge': '', 'rating': 4.7, 'reviews': 984,
        },
        {
            'name': 'Portable Bluetooth Speaker',
            'description': '360° surround sound with deep bass, IPX7 waterproof rating and 20-hour playtime. Pair two for stereo mode.',
            'price': 79.99, 'original_price': 119.99,
            'image_url': 'https://images.unsplash.com/photo-1608043152269-423dbba4e7e1?w=600&q=80',
            'category': 'electronics', 'stock': 60, 'featured': True,
            'badge': 'Sale', 'rating': 4.6, 'reviews': 3201,
        },
        {
            'name': 'Ceramic Coffee Mug Set',
            'description': 'Set of 4 hand-crafted ceramic mugs. Microwave & dishwasher safe. Each mug holds 350ml. Minimalist matte finish.',
            'price': 34.99, 'original_price': None,
            'image_url': 'https://images.unsplash.com/photo-1514228742587-6b1558fcca3d?w=600&q=80',
            'category': 'home-living', 'stock': 80, 'featured': False,
            'badge': '', 'rating': 4.5, 'reviews': 456,
        },
        {
            'name': 'Yoga Mat Premium',
            'description': 'Non-slip, eco-friendly TPE yoga mat. 6mm thick for joint support. Includes carrying strap. 183×61cm.',
            'price': 49.99, 'original_price': None,
            'image_url': 'https://images.unsplash.com/photo-1601925228037-c1ea2bced7a8?w=600&q=80',
            'category': 'sports', 'stock': 55, 'featured': False,
            'badge': 'Hot', 'rating': 4.8, 'reviews': 1102,
        },
        {
            'name': 'Skincare Glow Kit',
            'description': 'Complete 5-step skincare routine. Vitamin C serum, hyaluronic acid moisturizer, gentle cleanser, toner, and SPF 50 sunscreen.',
            'price': 89.99, 'original_price': 129.99,
            'image_url': 'https://images.unsplash.com/photo-1570194065650-d99fb4bedf0a?w=600&q=80',
            'category': 'beauty', 'stock': 30, 'featured': True,
            'badge': 'Sale', 'rating': 4.9, 'reviews': 2109,
        },
        {
            'name': 'Mechanical Keyboard TKL',
            'description': 'Tenkeyless mechanical keyboard with tactile blue switches. RGB per-key backlight, aluminum frame, PBT keycaps.',
            'price': 119.00, 'original_price': None,
            'image_url': 'https://images.unsplash.com/photo-1618384887929-16ec33fab9ef?w=600&q=80',
            'category': 'electronics', 'stock': 20, 'featured': True,
            'badge': 'New', 'rating': 4.7, 'reviews': 872,
        },
        {
            'name': 'Running Sneakers Pro',
            'description': 'Lightweight mesh upper with responsive foam midsole. Breathable, cushioned, and built for long-distance runs.',
            'price': 109.00, 'original_price': 150.00,
            'image_url': 'https://images.unsplash.com/photo-1542291026-7eec264c27ff?w=600&q=80',
            'category': 'sports', 'stock': 45, 'featured': False,
            'badge': 'Sale', 'rating': 4.6, 'reviews': 3567,
        },
        {
            'name': 'Linen Throw Blanket',
            'description': 'Soft woven linen throw blanket, 130×160cm. Machine washable. Perfect for sofa or bed layering.',
            'price': 44.99, 'original_price': None,
            'image_url': 'https://images.unsplash.com/photo-1555041469-a586c61ea9bc?w=600&q=80',
            'category': 'home-living', 'stock': 70, 'featured': False,
            'badge': '', 'rating': 4.4, 'reviews': 234,
        },
        {
            'name': 'Atomic Habits — James Clear',
            'description': 'The #1 New York Times bestseller. Practical strategies that will teach you exactly how to form good habits and break bad ones.',
            'price': 14.99, 'original_price': None,
            'image_url': 'https://images.unsplash.com/photo-1544947950-fa07a98d237f?w=600&q=80',
            'category': 'books', 'stock': 200, 'featured': False,
            'badge': 'Bestseller', 'rating': 4.9, 'reviews': 12488,
        },
        {
            'name': 'Perfume — Midnight Rose',
            'description': 'Luxurious Eau de Parfum with notes of rose, jasmine, and warm sandalwood. 100ml. Long lasting 12+ hours.',
            'price': 69.99, 'original_price': 99.99,
            'image_url': 'https://images.unsplash.com/photo-1541643600914-78b084683702?w=600&q=80',
            'category': 'beauty', 'stock': 25, 'featured': False,
            'badge': 'Sale', 'rating': 4.7, 'reviews': 789,
        },
    ]

    for pd in products_data:
        if not Product.query.filter_by(name=pd['name']).first():
            cat_slug = pd.pop('category')
            cat = Category.query.filter_by(slug=cat_slug).first()
            p = Product(**pd, category_id=cat.id if cat else None)
            db.session.add(p)

    db.session.commit()
    print('Database seeded successfully.')


with app.app_context():
    db.create_all()
    seed_db()

if __name__ == '__main__':
    app.run(debug=True)
