from datetime import datetime
from bson import ObjectId

class User:
    def __init__(self, email, password_hash, _id=None, created_at=None):
        self._id = _id or ObjectId()
        self.email = email
        self.password_hash = password_hash
        self.created_at = created_at or datetime.utcnow()
    
    def to_dict(self):
        """Convert user to dictionary"""
        return {
            '_id': str(self._id),
            'email': self.email,
            'created_at': self.created_at.isoformat()
        }
    
    @staticmethod
    def from_dict(data):
        """Create user from dictionary"""
        return User(
            email=data.get('email'),
            password_hash=data.get('password_hash'),
            _id=data.get('_id'),
            created_at=data.get('created_at')
        )

