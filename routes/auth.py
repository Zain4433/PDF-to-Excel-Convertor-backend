from flask import Blueprint, request, jsonify
from database import db
from models.user import User
from utils.auth_utils import hash_password, verify_password, generate_token, verify_token
from bson import ObjectId
import re

auth_bp = Blueprint('auth', __name__, url_prefix='/api/auth')

def validate_email(email):
    """Validate email format"""
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email) is not None

@auth_bp.route('/user/signup', methods=['POST'])
def signup():
    """User registration endpoint"""
    try:
        data = request.get_json()
        
        # Validation
        if not data:
            return jsonify({'error': 'No data provided'}), 400
        
        email = data.get('email', '').strip().lower()
        password = data.get('password', '')
        
        if not email:
            return jsonify({'error': 'Email is required'}), 400
        
        if not validate_email(email):
            return jsonify({'error': 'Invalid email format'}), 400
        
        if not password:
            return jsonify({'error': 'Password is required'}), 400
        
        if len(password) < 6:
            return jsonify({'error': 'Password must be at least 6 characters'}), 400
        
        # Check if user already exists
        users_collection = db.get_db().users
        existing_user = users_collection.find_one({'email': email})
        
        if existing_user:
            return jsonify({'error': 'User with this email already exists'}), 409
        
        # Create new user
        password_hash = hash_password(password)
        user = User(
            email=email,
            password_hash=password_hash
        )
        
        # Insert user into database
        user_dict = {
            'email': user.email,
            'password_hash': user.password_hash,
            'created_at': user.created_at
        }
        result = users_collection.insert_one(user_dict)
        user._id = result.inserted_id
        
        # Generate token
        token = generate_token(user._id, user.email)
        
        return jsonify({
            'message': 'User registered successfully',
            'token': token,
            'user': user.to_dict()
        }), 201
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@auth_bp.route('/user/login', methods=['POST'])
def login():
    """User login endpoint"""
    try:
        data = request.get_json()
        
        # Validation
        if not data:
            return jsonify({'error': 'No data provided'}), 400
        
        email = data.get('email', '').strip().lower()
        password = data.get('password', '')
        
        if not email:
            return jsonify({'error': 'Email is required'}), 400
        
        if not password:
            return jsonify({'error': 'Password is required'}), 400
        
        # Find user
        users_collection = db.get_db().users
        user_data = users_collection.find_one({'email': email})
        
        if not user_data:
            return jsonify({'error': 'Invalid email or password'}), 401
        
        # Verify password
        if not verify_password(password, user_data['password_hash']):
            return jsonify({'error': 'Invalid email or password'}), 401
        
        # Create user object
        user = User.from_dict(user_data)
        
        # Generate token
        token = generate_token(user._id, user.email)
        
        return jsonify({
            'message': 'Login successful',
            'token': token,
            'user': user.to_dict()
        }), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@auth_bp.route('/user', methods=['GET'])
def get_user():
    """Get current user endpoint"""
    try:
        # Get token from Authorization header
        auth_header = request.headers.get('Authorization')
        
        if not auth_header:
            return jsonify({'error': 'No authorization token provided'}), 401
        
        # Extract token
        try:
            token = auth_header.split(' ')[1]  # Bearer <token>
        except IndexError:
            return jsonify({'error': 'Invalid authorization header format'}), 401
        
        # Verify token
        payload = verify_token(token)
        if not payload:
            return jsonify({'error': 'Invalid or expired token'}), 401
        
        # Get user from database
        users_collection = db.get_db().users
        user_data = users_collection.find_one({'_id': ObjectId(payload['user_id'])})
        
        if not user_data:
            return jsonify({'error': 'User not found'}), 404
        
        user = User.from_dict(user_data)
        
        return jsonify({
            'user': user.to_dict()
        }), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@auth_bp.route('/user/logout', methods=['POST'])
def logout():
    """User logout endpoint (client-side token removal)"""
    return jsonify({'message': 'Logout successful'}), 200

