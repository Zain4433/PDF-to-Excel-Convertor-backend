from flask import Flask
from flask_cors import CORS
from config import Config
from database import db
from routes.auth import auth_bp
from routes.pdf import pdf_bp

def create_app():
    """Create and configure Flask app"""
    app = Flask(__name__)
    
    # Enable CORS
    CORS(app, origins=['http://localhost:3000'], supports_credentials=True)
    
    # Register blueprints
    app.register_blueprint(auth_bp)
    app.register_blueprint(pdf_bp)
    
    # Connect to database
    try:
        db.connect()
    except Exception as e:
        print(f"Warning: Could not connect to MongoDB: {e}")
    
    @app.route('/')
    def health_check():
        """Health check endpoint"""
        return {
            'status': 'ok',
            'message': 'PDF to Excel Converter API is running',
            'version': '1.0.0'
        }
    
    @app.route('/api/health', methods=['GET'])
    def health():
        """Detailed health check"""
        try:
            # Test database connection
            db.get_db().command('ping')
            db_status = 'connected'
        except:
            db_status = 'disconnected'
        
        return {
            'status': 'ok',
            'database': db_status,
            'version': '1.0.0'
        }
    
    return app

if __name__ == '__main__':
    app = create_app()
    app.run(
        host='0.0.0.0',
        port=Config.PORT,
        debug=Config.DEBUG
    )

