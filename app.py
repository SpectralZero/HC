"""
CareBox Flask Application

Main application entry point with:
- Application factory pattern
- Security headers middleware
- Route definitions
- Structured logging
- Error handlers
"""

import os
import sys
import logging
import json

from datetime import datetime
from functools import wraps

from flask import (
    Flask, 
    render_template, 
    request, 
    redirect, 
    session, 
    abort, 
    url_for,
    g,
    Response,
    jsonify
)
from werkzeug.exceptions import HTTPException

# Add project root to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import get_config, DevelopmentConfig
from services.security import (
    add_security_headers,
    generate_csrf_token,
    get_client_ip,
    get_truncated_user_agent,
    hash_ip,
    sanitize_text,
    validate_csrf_token,
    check_honeypot,
)
from services.bags import get_bags_service
from services.events import get_events_service
from services.orders import get_orders_service


# =============================================================================
# STRUCTURED LOGGING
# =============================================================================

class JSONFormatter(logging.Formatter):
    """JSON log formatter for structured logging."""
    
    def format(self, record: logging.LogRecord) -> str:
        log_data = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        
        # Add extra fields if present
        if hasattr(record, "extra"):
            log_data.update(record.extra)
        
        # Add exception info if present
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)
        
        return json.dumps(log_data)


def setup_logging(app: Flask) -> None:
    """Configure structured logging for the application."""
    handler = logging.StreamHandler()
    
    if app.config.get("ENV") == "production":
        handler.setFormatter(JSONFormatter())
        handler.setLevel(logging.INFO)
    else:
        handler.setFormatter(logging.Formatter(
            "[%(asctime)s] %(levelname)s in %(module)s: %(message)s"
        ))
        handler.setLevel(logging.DEBUG)
    
    app.logger.handlers.clear()
    app.logger.addHandler(handler)
    app.logger.setLevel(logging.DEBUG if app.debug else logging.INFO)


# =============================================================================
# APPLICATION FACTORY
# =============================================================================

def create_app(config_class=None) -> Flask:
    """
    Application factory for CareBox.
    
    Args:
        config_class: Configuration class to use (optional)
        
    Returns:
        Configured Flask application
    """
    app = Flask(__name__)
    
    # Load configuration
    if config_class is None:
        config_class = get_config()
    
    # Handle both class and instance configs
    if isinstance(config_class, type):
        app.config.from_object(config_class)
        # Also set custom attributes
        for attr in dir(config_class):
            if attr.isupper():
                app.config[attr] = getattr(config_class, attr)
    else:
        app.config.from_object(config_class)
    
    # Setup logging
    setup_logging(app)
    
    # Register middleware
    register_middleware(app)
    
    # Register error handlers
    register_error_handlers(app)
    
    # Register routes
    register_routes(app)
    
    app.logger.info(f"CareBox application initialized in {app.config.get('ENV', 'unknown')} mode")
    
    return app


# =============================================================================
# MIDDLEWARE
# =============================================================================

def register_middleware(app: Flask) -> None:
    """Register application middleware."""
    
    @app.before_request
    def before_request():
        """Pre-request processing."""
        # Store request start time for timing
        g.request_start = datetime.utcnow()
        
        # Store client IP (hashed for privacy)
        g.client_ip = get_client_ip()
        g.client_ip_hash = hash_ip(g.client_ip, app.config.get("IP_HASH_SALT", ""))
        
        # Detect language preference (session first, then Accept-Language header)
        if "lang" in session:
            g.lang = session["lang"]
        else:
            accept_lang = request.headers.get("Accept-Language", "en")
            g.lang = "ar" if "ar" in accept_lang.lower() else "en"
        g.dir = "rtl" if g.lang == "ar" else "ltr"
    
    @app.after_request
    def after_request(response: Response) -> Response:
        """Post-request processing."""
        # Add security headers
        is_https = request.is_secure or request.headers.get("X-Forwarded-Proto") == "https"
        response = add_security_headers(response, is_https)
        
        # Log request
        duration = (datetime.utcnow() - g.request_start).total_seconds() * 1000
        app.logger.debug(
            f"{request.method} {request.path} - {response.status_code} - {duration:.2f}ms"
        )
        
        return response
    
    @app.context_processor
    def inject_globals():
        """Inject global variables into templates."""
        return {
            "csrf_token": generate_csrf_token,
            "lang": getattr(g, "lang", "en"),
            "dir": getattr(g, "dir", "ltr"),
            "business_name": app.config.get("BUSINESS_NAME", "CareBox"),
            "business_whatsapp": app.config.get("BUSINESS_WHATSAPP", ""),
            "current_year": datetime.utcnow().year,
        }


# =============================================================================
# ERROR HANDLERS
# =============================================================================

def register_error_handlers(app: Flask) -> None:
    """Register error handlers."""
    
    @app.errorhandler(404)
    def not_found_error(error):
        """Handle 404 errors."""
        app.logger.warning(f"404 Not Found: {request.path}")
        return render_template("errors/404.html"), 404
    
    @app.errorhandler(403)
    def forbidden_error(error):
        """Handle 403 errors."""
        app.logger.warning(f"403 Forbidden: {request.path} from {g.client_ip_hash}")
        return render_template("errors/403.html"), 403
    
    @app.errorhandler(500)
    def internal_error(error):
        """Handle 500 errors."""
        app.logger.error(f"500 Internal Error: {error}")
        return render_template("errors/500.html"), 500
    
    @app.errorhandler(HTTPException)
    def handle_http_exception(error):
        """Handle all HTTP exceptions."""
        app.logger.error(f"HTTP {error.code}: {error.description}")
        return render_template("errors/generic.html", error=error), error.code


# =============================================================================
# ADMIN AUTH DECORATOR
# =============================================================================

def admin_required(f):
    """Decorator to require admin authentication."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get("admin_authenticated"):
            return redirect(url_for("admin_login"))
        return f(*args, **kwargs)
    return decorated_function


# =============================================================================
# ROUTES
# =============================================================================

def register_routes(app: Flask) -> None:
    """Register application routes."""
    
    def _youtube_to_embed(url: str) -> str:
        """Convert YouTube watch/share URLs to embed format."""
        if not url:
            return url
        import re
        # youtu.be/VIDEO_ID
        m = re.match(r'https?://youtu\.be/([A-Za-z0-9_-]+)', url)
        if m:
            return f'https://www.youtube.com/embed/{m.group(1)}'
        # youtube.com/watch?v=VIDEO_ID
        m = re.match(r'https?://(?:www\.)?youtube\.com/watch\?v=([A-Za-z0-9_-]+)', url)
        if m:
            return f'https://www.youtube.com/embed/{m.group(1)}'
        # Already embed format or other URL
        return url

    def _enrich_product(p: dict) -> dict:
        """Parse contents, options, and convert video URLs for a product dict."""
        # Parse contents
        if isinstance(p.get("contents"), str) and p["contents"]:
            try:
                p["contents_parsed"] = json.loads(p["contents"])
            except (json.JSONDecodeError, TypeError):
                p["contents_parsed"] = []
        else:
            p["contents_parsed"] = p.get("contents", []) if isinstance(p.get("contents"), list) else []
        # Parse options
        if isinstance(p.get("options"), str) and p["options"]:
            try:
                p["options_parsed"] = json.loads(p["options"])
            except (json.JSONDecodeError, TypeError):
                p["options_parsed"] = []
        else:
            p["options_parsed"] = p.get("options", []) if isinstance(p.get("options"), list) else []
        # Convert video URL to embed format
        p["video_embed_url"] = _youtube_to_embed(p.get("video_url", ""))
        return p

    @app.route("/")
    def index():
        """Landing page with products."""
        bags_service = get_bags_service()
        products = bags_service.get_all_bags_raw()
        for p in products:
            _enrich_product(p)
        return render_template("index.html", products=products)
    
    @app.route("/g/<bag_id>", methods=["GET", "POST"])
    def guide_by_id(bag_id: str):
        """
        Digital Twin guide page for a specific bag.
        
        Route: /g/CBX-0001
        
        If ENABLE_SERIAL_CHECK is true, prompts for serial verification first.
        """
        # Sanitize bag_id
        bag_id = sanitize_text(bag_id, 10).upper()
        
        # Fetch bag from sheets
        bags_service = get_bags_service()
        events_service = get_events_service()
        bag = bags_service.get_bag_by_id(bag_id)
        
        # Check if serial verification is enabled
        enable_serial = app.config.get("ENABLE_SERIAL_CHECK", True)
        
        # Check if already verified in session
        verified_bags = session.get("verified_bags", [])
        already_verified = bag_id in verified_bags
        
        if enable_serial and not already_verified and bag:
            # Check for lockout
            if events_service.is_locked_out(g.client_ip_hash):
                lockout_remaining = events_service.get_lockout_remaining(g.client_ip_hash)
                return render_template("serial_check.html",
                    bag_id=bag_id,
                    locked_out=True,
                    lockout_remaining=lockout_remaining
                )
            
            if request.method == "POST":
                # Validate CSRF
                csrf_token = request.form.get("csrf_token", "")
                if not validate_csrf_token(csrf_token):
                    return render_template("serial_check.html",
                        bag_id=bag_id,
                        error="Invalid request. Please try again." if g.lang == "en" else "طلب غير صالح. حاول مرة أخرى.",
                        attempts_remaining=events_service.get_remaining_attempts(g.client_ip_hash)
                    )
                
                # Get submitted serial
                serial = request.form.get("serial", "").strip()
                serial = sanitize_text(serial, 4)
                
                # Verify serial
                if bags_service.verify_serial(bag_id, serial):
                    # Success - log and mark as verified
                    events_service.log_serial_attempt(
                        bag_id=bag_id,
                        ip_hash=g.client_ip_hash,
                        success=True,
                        user_agent=get_truncated_user_agent()
                    )
                    
                    # Store in session
                    verified_bags.append(bag_id)
                    session["verified_bags"] = verified_bags
                    
                    # Redirect to guide (PRG pattern)
                    return redirect(url_for("guide_by_id", bag_id=bag_id))
                else:
                    # Failed - log and show error
                    events_service.log_serial_attempt(
                        bag_id=bag_id,
                        ip_hash=g.client_ip_hash,
                        success=False,
                        user_agent=get_truncated_user_agent()
                    )
                    
                    # Check if now locked out
                    if events_service.is_locked_out(g.client_ip_hash):
                        lockout_remaining = events_service.get_lockout_remaining(g.client_ip_hash)
                        return render_template("serial_check.html",
                            bag_id=bag_id,
                            locked_out=True,
                            lockout_remaining=lockout_remaining
                        )
                    
                    error_msg = "Incorrect serial number. Please try again." if g.lang == "en" else "الرقم التسلسلي غير صحيح. حاول مرة أخرى."
                    return render_template("serial_check.html",
                        bag_id=bag_id,
                        error=error_msg,
                        attempts_remaining=events_service.get_remaining_attempts(g.client_ip_hash)
                    )
            
            # GET - show serial check form
            return render_template("serial_check.html",
                bag_id=bag_id,
                attempts_remaining=events_service.get_remaining_attempts(g.client_ip_hash)
            )
        
        # Log scan event
        if bag:
            events_service.log_scan(
                bag_id=bag_id,
                box_type=bag.box_type,
                ip_hash=g.client_ip_hash,
                user_agent=get_truncated_user_agent()
            )
            return render_template("guide.html", bag=bag.to_dict(g.lang))
        
        # Fallback placeholder if bag not found
        return render_template("guide.html", bag={
            "bag_id": bag_id,
            "box_type": "travel",
            "title": f"CareBox {bag_id}",
            "video_url": "https://www.youtube.com/embed/dQw4w9WgXcQ",
            "tips": ["Stay hydrated", "Take medications on time", "Contact pharmacist if needed"] if g.lang == "en" else ["حافظ على الترطيب", "تناول الأدوية في الوقت المحدد", "تواصل مع الصيدلي عند الحاجة"],
            "contents": [],
            "options": [],
        })
    
    @app.route("/guide/<box_type>")
    def guide_by_type(box_type: str):
        """
        Digital Twin guide page by box type (fallback route).
        
        Route: /guide/travel
        """
        box_type = sanitize_text(box_type, 20).lower()
        
        # Fetch bag by type from sheets
        bags_service = get_bags_service()
        bag = bags_service.get_bag_by_type(box_type)
        
        if bag:
            return render_template("guide.html", bag=bag.to_dict(g.lang))
        
        # Fallback placeholder if bag not found
        return render_template("guide.html", bag={
            "bag_id": None,
            "box_type": box_type,
            "title": f"CareBox {box_type.title()} Guide",
            "video_url": "https://www.youtube.com/embed/dQw4w9WgXcQ",
            "tips": ["Stay hydrated", "Take medications on time", "Contact pharmacist if needed"] if g.lang == "en" else ["حافظ على الترطيب", "تناول الأدوية في الوقت المحدد", "تواصل مع الصيدلي عند الحاجة"],
            "contents": [],
            "options": [],
        })
    
    @app.route("/order", methods=["GET", "POST"])
    def order():
        """
        Order form page.
        
        GET: Display order form with products
        POST: Process order and redirect to WhatsApp
        """
        bags_service = get_bags_service()
        
        if request.method == "GET":
            products = bags_service.get_all_bags_raw()
            for p in products:
                _enrich_product(p)
            
            preselect = request.args.get("bag_id", "")
            return render_template("order.html", products=products, preselect=preselect)
        
        # POST processing
        orders_service = get_orders_service()
        events_service = get_events_service()
        
        # Check honeypot (bot detection)
        if not check_honeypot(request.form):
            app.logger.warning(f"Bot detected on order form from {g.client_ip_hash}")
            return redirect(url_for("index"))
        
        # Validate CSRF token
        csrf_token = request.form.get("_csrf_token", "")
        if not validate_csrf_token(csrf_token):
            error = "Invalid request. Please try again." if g.lang == "en" else "طلب غير صالح. حاول مرة أخرى."
            products = bags_service.get_all_bags_raw()
            return render_template("order.html", error=error, products=products)
        
        # Get form data
        name = request.form.get("name", "").strip()
        phone = request.form.get("phone", "").strip()
        box_type = request.form.get("box_type", "").strip().lower()
        notes = request.form.get("notes", "").strip()
        bag_id = request.form.get("bag_id", "").strip().upper()
        
        # Parse selected add-ons and bag contents from hidden fields
        selected_addons_json = request.form.get("selected_addons", "[]")
        bag_contents_json = request.form.get("bag_contents", "[]")
        
        try:
            selected_addons = json.loads(selected_addons_json) if selected_addons_json else []
        except (json.JSONDecodeError, TypeError):
            selected_addons = []
        
        try:
            bag_contents = json.loads(bag_contents_json) if bag_contents_json else []
        except (json.JSONDecodeError, TypeError):
            bag_contents = []
        
        # Validate order
        is_valid, error = orders_service.validate_order(
            name=name,
            phone=phone,
            box_type=box_type,
            notes=notes,
            lang=g.lang
        )
        
        if not is_valid:
            products = bags_service.get_all_bags_raw()
            return render_template("order.html", error=error, products=products)
        
        # Sanitize inputs
        name = sanitize_text(name, 60)
        phone = sanitize_text(phone, 20)
        notes = sanitize_text(notes, 200)
        
        # Get product details
        product_name = ""
        price = 0.0
        
        if bag_id:
            product = bags_service.get_bag_raw(bag_id)
            if product:
                product_name = product.get("title_en", "") if g.lang == "en" else product.get("title_ar", product.get("title_en", ""))
                price = product.get("price", 0)
        else:
            # Try to find a product by box_type
            all_products = bags_service.get_all_bags_raw()
            for product in all_products:
                if product.get("box_type") == box_type and product.get("is_active"):
                    bag_id = product.get("bag_id", "")
                    product_name = product.get("title_en", "") if g.lang == "en" else product.get("title_ar", product.get("title_en", ""))
                    price = product.get("price", 0)
                    break
        
        # Save order to Google Sheets
        orders_service.save_order(
            name=name,
            phone=phone,
            box_type=box_type,
            notes=notes,
            bag_id=bag_id,
            ip_hash=g.client_ip_hash
        )
        
        # Log order event
        events_service.log_order(
            box_type=box_type,
            bag_id=bag_id or None,
            ip_hash=g.client_ip_hash,
            user_agent=get_truncated_user_agent()
        )
        
        # Generate WhatsApp URL and redirect
        whatsapp_url = orders_service.generate_whatsapp_url(
            business_whatsapp=app.config.get("BUSINESS_WHATSAPP", ""),
            name=name,
            phone=phone,
            box_type=box_type,
            notes=notes,
            lang=g.lang,
            product_name=product_name,
            bag_id=bag_id,
            price=price,
            bag_contents=bag_contents,
            selected_addons=selected_addons
        )
        
        return redirect(whatsapp_url)
    
    # =========================================================================
    # API ENDPOINTS
    # =========================================================================
    
    @app.route("/api/product/<bag_id>")
    def api_product(bag_id: str):
        """API endpoint to get product details for JS dynamic loading."""
        bags_service = get_bags_service()
        bag_id = sanitize_text(bag_id, 10).upper()
        product = bags_service.get_bag_raw(bag_id)
        
        if not product:
            return jsonify({"error": "Product not found"}), 404
        
        # Parse JSON fields
        contents = []
        options = []
        if isinstance(product.get("contents"), str) and product["contents"]:
            try:
                contents = json.loads(product["contents"])
            except (json.JSONDecodeError, TypeError):
                contents = []
        
        if isinstance(product.get("options"), str) and product["options"]:
            try:
                options = json.loads(product["options"])
            except (json.JSONDecodeError, TypeError):
                options = []
        
        return jsonify({
            "bag_id": product["bag_id"],
            "box_type": product["box_type"],
            "title_en": product["title_en"],
            "title_ar": product.get("title_ar", ""),
            "image_url": product.get("image_url", ""),
            "video_url": product.get("video_url", ""),
            "price": product.get("price", 0),
            "contents": contents,
            "options": options,
        })
    
    @app.route("/health")
    def health():
        """Health check endpoint for deployment monitoring."""
        return {"status": "healthy", "timestamp": datetime.utcnow().isoformat()}
    
    # =========================================================================
    # ADMIN ROUTES
    # =========================================================================
    
    @app.route("/admin/login", methods=["GET", "POST"])
    def admin_login():
        """Admin login page."""
        if session.get("admin_authenticated"):
            return redirect(url_for("admin_dashboard"))
        
        if request.method == "GET":
            return render_template("admin/login.html")
        
        # Validate CSRF
        csrf_token = request.form.get("csrf_token", "")
        if not validate_csrf_token(csrf_token):
            return render_template("admin/login.html", error="Invalid request.")
        
        password = request.form.get("password", "")
        admin_password = app.config.get("ADMIN_PASSWORD", "")
        
        if admin_password and password == admin_password:
            session["admin_authenticated"] = True
            return redirect(url_for("admin_dashboard"))
        
        return render_template("admin/login.html", error="Incorrect password.")
    
    @app.route("/admin")
    @app.route("/admin/dashboard")
    @admin_required
    def admin_dashboard():
        """Admin dashboard with stats."""
        # Get basic stats from events service
        events_service = get_events_service()
        bags_service = get_bags_service()
        orders_service = get_orders_service()
        
        # Aggregate stats
        stats = {
            "total_scans": 0,
            "total_orders": 0,
            "serial_verifications": 0,
            "serial_failures": 0,
            "total_products": 0,
        }
        
        events = []
        
        try:
            # Get product count
            products = bags_service.get_all_bags_raw()
            stats["total_products"] = len(products)
            active_products = sum(1 for p in products if p.get("is_active"))
            stats["active_products"] = active_products
        except Exception:
            pass
        
        try:
            # Try to get events from sheets
            from config import get_config
            from services.sheets_client import SheetsClient
            config = get_config()
            client = SheetsClient(config.get_google_credentials_path())
            worksheet = client.get_worksheet(config.SHEETS_DOC_NAME, config.SHEET_TAB_EVENTS)
            rows = worksheet.get_all_values()
            
            # Skip header, process rows
            for row in rows[1:]:
                if len(row) >= 2:
                    event_type = row[1]
                    if event_type == "SCAN":
                        stats["total_scans"] += 1
                    elif event_type == "ORDER":
                        stats["total_orders"] += 1
                    elif event_type == "SERIAL_OK":
                        stats["serial_verifications"] += 1
                    elif event_type == "SERIAL_FAIL":
                        stats["serial_failures"] += 1
            
            # Get last 20 events
            recent_rows = rows[-21:-1] if len(rows) > 21 else rows[1:]
            for row in reversed(recent_rows):
                if len(row) >= 4:
                    events.append({
                        "timestamp": row[0][:16] if row[0] else "",
                        "type": row[1],
                        "bag_id": row[2],
                        "box_type": row[3],
                    })
        except Exception as e:
            app.logger.warning(f"Could not load events: {e}")
        
        return render_template("admin/dashboard.html", stats=stats, events=events[:20])
    
    # =========================================================================
    # ADMIN PRODUCT MANAGEMENT
    # =========================================================================
    
    @app.route("/admin/products")
    @admin_required
    def admin_products():
        """List all products."""
        bags_service = get_bags_service()
        products = bags_service.get_all_bags_raw()
        # Parse contents count for display
        for p in products:
            if isinstance(p.get("contents"), str) and p["contents"]:
                try:
                    p["contents_count"] = len(json.loads(p["contents"]))
                except (json.JSONDecodeError, TypeError):
                    p["contents_count"] = 0
            else:
                p["contents_count"] = 0
        message = request.args.get("message")
        return render_template("admin/products.html", products=products, message=message)
    
    @app.route("/admin/products/add", methods=["GET", "POST"])
    @admin_required
    def admin_product_add():
        """Add new product."""
        if request.method == "GET":
            return render_template("admin/product_form.html", product=None)
        
        # Validate CSRF
        if not validate_csrf_token(request.form.get("csrf_token", "")):
            return render_template("admin/product_form.html", product=None, error="Invalid request.")
        
        bags_service = get_bags_service()
        
        data = {
            "bag_id": sanitize_text(request.form.get("bag_id", ""), 10).upper(),
            "box_type": sanitize_text(request.form.get("box_type", ""), 20).lower(),
            "title_en": sanitize_text(request.form.get("title_en", ""), 100),
            "title_ar": sanitize_text(request.form.get("title_ar", ""), 100),
            "image_url": request.form.get("image_url", "").strip()[:500],
            "video_url": request.form.get("video_url", "").strip()[:500],
            "tips_en": sanitize_text(request.form.get("tips_en", ""), 500),
            "tips_ar": sanitize_text(request.form.get("tips_ar", ""), 500),
            "price": request.form.get("price", "0"),
            "options": request.form.get("options_json", ""),
            "serial_last4": sanitize_text(request.form.get("serial_last4", ""), 4),
            "is_active": request.form.get("is_active") == "TRUE",
            "contents": request.form.get("contents_json", ""),
        }
        
        # Basic validation
        if not data["bag_id"] or not data["box_type"] or not data["title_en"]:
            return render_template("admin/product_form.html", product=data, error="Please fill required fields.")
        
        # Check if exists
        if bags_service.get_bag_raw(data["bag_id"]):
            return render_template("admin/product_form.html", product=data, error="Bag ID already exists.")
        
        if bags_service.add_bag(data):
            return redirect(url_for("admin_products", message=f"Added {data['bag_id']}"))
        return render_template("admin/product_form.html", product=data, error="Failed to add product.")
    
    @app.route("/admin/products/edit/<bag_id>", methods=["GET", "POST"])
    @admin_required
    def admin_product_edit(bag_id: str):
        """Edit existing product."""
        bags_service = get_bags_service()
        product = bags_service.get_bag_raw(bag_id)
        
        if not product:
            return redirect(url_for("admin_products"))
        
        if request.method == "GET":
            return render_template("admin/product_form.html", product=product)
        
        # Validate CSRF
        if not validate_csrf_token(request.form.get("csrf_token", "")):
            return render_template("admin/product_form.html", product=product, error="Invalid request.")
        
        data = {
            "box_type": sanitize_text(request.form.get("box_type", ""), 20).lower(),
            "title_en": sanitize_text(request.form.get("title_en", ""), 100),
            "title_ar": sanitize_text(request.form.get("title_ar", ""), 100),
            "image_url": request.form.get("image_url", "").strip()[:500],
            "video_url": request.form.get("video_url", "").strip()[:500],
            "tips_en": sanitize_text(request.form.get("tips_en", ""), 500),
            "tips_ar": sanitize_text(request.form.get("tips_ar", ""), 500),
            "price": request.form.get("price", "0"),
            "options": request.form.get("options_json", ""),
            "serial_last4": sanitize_text(request.form.get("serial_last4", ""), 4),
            "is_active": request.form.get("is_active") == "TRUE",
            "contents": request.form.get("contents_json", ""),
        }
        
        if bags_service.update_bag(bag_id, data):
            return redirect(url_for("admin_products", message=f"Updated {bag_id}"))
        return render_template("admin/product_form.html", product=product, error="Failed to update.")
    
    @app.route("/admin/products/delete/<bag_id>")
    @admin_required
    def admin_product_delete(bag_id: str):
        """Delete product."""
        bags_service = get_bags_service()
        bags_service.delete_bag(bag_id)
        return redirect(url_for("admin_products", message=f"Deleted {bag_id}"))
    
    @app.route("/admin/products/toggle/<bag_id>")
    @admin_required
    def admin_product_toggle(bag_id: str):
        """Toggle product active status."""
        bags_service = get_bags_service()
        bags_service.toggle_active(bag_id)
        return redirect(url_for("admin_products", message=f"Toggled {bag_id}"))
    
    # =========================================================================
    # ADMIN ORDERS
    # =========================================================================
    
    @app.route("/admin/orders")
    @admin_required
    def admin_orders():
        """View all orders."""
        orders_service = get_orders_service()
        orders = orders_service.get_all_orders()
        # Reverse for newest first
        orders.reverse()
        return render_template("admin/orders.html", orders=orders)
    
    @app.route("/admin/logout")
    def admin_logout():
        """Admin logout."""
        session.pop("admin_authenticated", None)
        return redirect(url_for("index"))
    
    @app.route("/lang/<lang_code>")
    def set_language(lang_code: str):
        """
        Set language preference.
        
        Route: /lang/ar or /lang/en
        """
        if lang_code in ("ar", "en"):
            session["lang"] = lang_code
        return redirect(request.referrer or url_for("index"))


# =============================================================================
# MAIN ENTRY POINT
# =============================================================================

# Create app instance
app = create_app()

if __name__ == "__main__":
    # Development server
    app.run(
        host="0.0.0.0",
        port=int(os.getenv("PORT", 5000)),
        debug=app.config.get("DEBUG", False)
    )
