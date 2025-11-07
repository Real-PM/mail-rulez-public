"""
Mail-Rulez - Intelligent Email Management System
Copyright (c) 2024 Real Project Management Solutions

This software is dual-licensed:
1. AGPL v3 for open source/self-hosted use
2. Commercial license for hosted services and enterprise use

For commercial licensing, contact: license@mail-rulez.com
See LICENSE-DUAL for complete licensing information.
"""


"""
Mail-Rulez Web Interface

Flask application for managing email processing rules, accounts, and monitoring.
Integrates with the existing Mail-Rulez security and configuration systems.
"""

import os
import sys
from pathlib import Path
from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
from flask_wtf.csrf import CSRFProtect

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from config import get_config
from security import get_security_manager
import logging

# Get version from git tags
def get_version():
    """Get version from git tags, fallback to dev version"""
    try:
        import subprocess
        version = subprocess.check_output(
            ['git', 'describe', '--tags', '--always'],
            stderr=subprocess.DEVNULL,
            cwd=Path(__file__).parent.parent
        ).decode('utf-8').strip()
        # Remove 'v' prefix if present
        return version.lstrip('v')
    except Exception:
        return "dev"

__version__ = get_version()


def create_app(config_dir=None, testing=False):
    """Create and configure Flask application"""
    app = Flask(__name__)
    
    # Setup logging first
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Configure Flask
    app.config['SECRET_KEY'] = os.getenv('FLASK_SECRET_KEY') or 'dev-key-change-in-production'
    app.config['WTF_CSRF_TIME_LIMIT'] = 3600  # 1 hour
    app.config['PERMANENT_SESSION_LIFETIME'] = 24 * 3600  # 24 hour session timeout to match SecurityManager
    app.config['TESTING'] = testing
    
    # Initialize CSRF protection
    csrf = CSRFProtect(app)
    
    # Logging
    logger = logging.getLogger(__name__)
    logger.info(f"Flask app initializing - Version {__version__}")
    
    # Initialize Mail-Rulez components
    mail_config = get_config(base_dir=config_dir)
    security_manager = get_security_manager()
    
    # Store managers in app context for access in routes
    app.mail_config = mail_config
    app.security_manager = security_manager
    
    # Register error handlers
    @app.errorhandler(404)
    def not_found(error):
        return render_template('errors/404.html'), 404
    
    @app.errorhandler(500)
    def internal_error(error):
        return render_template('errors/500.html'), 500
    
    @app.errorhandler(403)
    def forbidden(error):
        return render_template('errors/403.html'), 403
    
    # Context processor to make common data available to all templates
    @app.context_processor
    def inject_globals():
        return {
            'app_name': 'Mail-Rulez',
            'version': __version__,
            'current_user': get_current_user(),
            'account_count': len(app.mail_config.accounts),
            'lists_dir': str(app.mail_config.lists_dir)
        }
    
    # Helper function to get current user from session
    def get_current_user():
        # Use Flask's built-in session directly - works across multiple worker processes
        return session.get('username')
    
    # Make get_current_user available to routes
    app.get_current_user = get_current_user
    
    # Register blueprints
    from web.routes.auth import auth_bp
    from web.routes.dashboard import dashboard_bp
    from web.routes.accounts import accounts_bp
    from web.routes.lists import lists_bp
    from web.routes.rules import rules_bp
    from web.routes.services import services_bp
    from web.routes.logs import logs_bp

    app.register_blueprint(auth_bp, url_prefix='/auth')
    app.register_blueprint(dashboard_bp, url_prefix='/')
    app.register_blueprint(accounts_bp, url_prefix='/accounts')
    app.register_blueprint(lists_bp, url_prefix='/lists')
    app.register_blueprint(rules_bp, url_prefix='/rules')
    app.register_blueprint(services_bp)
    app.register_blueprint(logs_bp)
    
    
    # Exempt API services from CSRF protection
    csrf.exempt(services_bp)
    
    # Root route
    @app.route('/')
    def index():
        if get_current_user():
            return redirect(url_for('dashboard.overview'))
        return redirect(url_for('auth.login'))
    
    return app


def run_app():
    """Run the Flask application in development mode"""
    import os
    app = create_app()
    port = int(os.environ.get('FLASK_PORT', 5001))
    app.run(debug=True, host='0.0.0.0', port=port)


# Create application instance for WSGI servers like Gunicorn
application = create_app()

if __name__ == '__main__':
    run_app()