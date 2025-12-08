# PDF to Excel Converter - Backend API

Python Flask backend with MongoDB for the PDF to Excel Converter application.

## Features

- User authentication (Signup/Login)
- JWT token-based authentication
- MongoDB database integration
- Password hashing with bcrypt
- CORS enabled for frontend integration

## Setup Instructions

### 1. Install Dependencies

```bash
# Create virtual environment (recommended)
python -m venv venv

# Activate virtual environment
# On Windows:
venv\Scripts\activate
# On macOS/Linux:
source venv/bin/activate

# Install packages
pip install -r requirements.txt
```

### 2. MongoDB Setup

Make sure MongoDB is installed and running on your system.

**Option 1: Local MongoDB**
- Install MongoDB from https://www.mongodb.com/try/download/community
- Start MongoDB service
- Default connection: `mongodb://localhost:27017/`

**Option 2: MongoDB Atlas (Cloud)**
- Create a free account at https://www.mongodb.com/cloud/atlas
- Get your connection string
- Update `MONGODB_URI` in `.env` file

### 3. Environment Configuration

```bash
# Copy example environment file
cp .env.example .env

# Edit .env file with your configuration
# Important: Change JWT_SECRET_KEY to a secure random string
```

### 4. Run the Server

```bash
python app.py
```

The server will start on `http://localhost:4000`

## API Endpoints

### Authentication

- `POST /api/auth/user/signup` - Register a new user
  ```json
  {
    "email": "user@example.com",
    "password": "password123",
    "name": "John Doe" // optional
  }
  ```

- `POST /api/auth/user/login` - Login user
  ```json
  {
    "email": "user@example.com",
    "password": "password123"
  }
  ```

- `GET /api/auth/user` - Get current user (requires Bearer token)
  ```
  Headers: Authorization: Bearer <token>
  ```

- `POST /api/auth/user/logout` - Logout user

### Health Check

- `GET /` - Basic health check
- `GET /api/health` - Detailed health check with database status

## Project Structure

```
backend/
├── app.py                 # Main Flask application
├── config.py              # Configuration settings
├── database.py            # MongoDB connection
├── requirements.txt       # Python dependencies
├── .env.example          # Environment variables template
├── models/
│   └── user.py           # User model
├── routes/
│   └── auth.py           # Authentication routes
└── utils/
    └── auth_utils.py     # Authentication utilities
```

## Environment Variables

- `MONGODB_URI` - MongoDB connection string
- `DATABASE_NAME` - Database name (default: pdf_converter)
- `JWT_SECRET_KEY` - Secret key for JWT tokens (CHANGE THIS!)
- `JWT_ALGORITHM` - JWT algorithm (default: HS256)
- `JWT_EXPIRATION_HOURS` - Token expiration time (default: 24)
- `PORT` - Server port (default: 4000)
- `FLASK_DEBUG` - Debug mode (default: True)

## Security Notes

- Always change `JWT_SECRET_KEY` in production
- Use strong passwords
- Enable HTTPS in production
- Keep dependencies updated

