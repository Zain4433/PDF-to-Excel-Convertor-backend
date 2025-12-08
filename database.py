from pymongo import MongoClient
from pymongo.errors import ConnectionFailure
from config import Config

class Database:
    _instance = None
    _client = None
    _db = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(Database, cls).__new__(cls)
        return cls._instance
    
    def connect(self):
        """Connect to MongoDB"""
        try:
            self._client = MongoClient(Config.MONGODB_URI)
            # Test connection
            self._client.admin.command('ping')
            self._db = self._client[Config.DATABASE_NAME]
            print(f"✅ Connected to MongoDB: {Config.DATABASE_NAME}")
            return self._db
        except ConnectionFailure as e:
            print(f"❌ Failed to connect to MongoDB: {e}")
            raise
    
    def get_db(self):
        """Get database instance"""
        if self._db is None:
            self.connect()
        return self._db
    
    def close(self):
        """Close MongoDB connection"""
        if self._client:
            self._client.close()
            print("MongoDB connection closed")

# Create a singleton instance
db = Database()

