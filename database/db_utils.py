from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.orm.session import Session
from typing import Optional, List, Dict, Any, Union
import os

from database.db_models import Base, User, UserMessage, BotReply, City, Brand, Product, DataSyncLog

# Create database directory if it doesn't exist
os.makedirs("database/data", exist_ok=True)

# Database connection
DATABASE_URL = "sqlite:///database/data/chatbot.sqlite"
engine = create_engine(DATABASE_URL)

# Create all tables
Base.metadata.create_all(engine)

# Session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_db():
    """Get database session"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

class DatabaseManager:
    @staticmethod
    def create_user(db: Session, phone_number: str, name: Optional[str] = None) -> User:
        """Create a new user or get existing one"""
        user = db.query(User).filter(User.phone_number == phone_number).first()
        if user:
            return user
            
        user = User(phone_number=phone_number, name=name)
        db.add(user)
        db.commit()
        db.refresh(user)
        return user
    
    @staticmethod
    def get_user_by_phone(db: Session, phone_number: str) -> Optional[User]:
        """Get a user by phone number"""
        return db.query(User).filter(User.phone_number == phone_number).first()
    
    @staticmethod
    def update_user_conclusion(db: Session, user_id: int, conclusion: str) -> User:
        """Update user conclusion"""
        user = db.query(User).filter(User.id == user_id).first()
        if user:
            user.conclusion = conclusion
            db.commit()
            db.refresh(user)
        return user
    
    @staticmethod
    def create_message(db: Session, user_id: int, content: str) -> UserMessage:
        """Save a message from a user"""
        message = UserMessage(user_id=user_id, content=content)
        db.add(message)
        db.commit()
        db.refresh(message)
        return message
    
    @staticmethod
    def create_bot_reply(db: Session, message_id: int, content: str, language: str = 'ar') -> BotReply:
        """Save a reply from the bot"""
        reply = BotReply(message_id=message_id, content=content, language=language)
        db.add(reply)
        db.commit()
        db.refresh(reply)
        return reply
    
    @staticmethod
    def get_user_message_history(db: Session, user_id: int, limit: int = 10) -> List[Dict[str, Any]]:
        """Get user conversation history"""
        messages = db.query(UserMessage).filter(
            UserMessage.user_id == user_id
        ).order_by(
            UserMessage.timestamp.desc()
        ).limit(limit).all()
        
        history = []
        for msg in reversed(messages):  # Oldest first
            history.append({
                "role": "user",
                "content": msg.content,
                "timestamp": msg.timestamp
            })
            
            # Add bot replies for this message
            for reply in msg.replies:
                history.append({
                    "role": "assistant",
                    "content": reply.content,
                    "timestamp": reply.timestamp
                })
        
        return history
    
    # New methods for managing Cities, Brands, and Products
    @staticmethod
    def upsert_city(db: Session, external_id: int, name: str, name_en: str = None, 
                   title: str = None, lat: float = None, lng: float = None) -> City:
        """Create or update a city"""
        city = db.query(City).filter(City.external_id == external_id).first()
        if city:
            city.name = name
            city.name_en = name_en
            city.title = title
            city.lat = lat
            city.lng = lng
        else:
            city = City(
                external_id=external_id, 
                name=name, 
                name_en=name_en, 
                title=title,
                lat=lat,
                lng=lng
            )
            db.add(city)
        
        db.commit()
        db.refresh(city)
        return city
    
    @staticmethod
    def upsert_brand(db: Session, external_id: int, title: str, image_url: str = None,
                     title_en: str = None, **kwargs) -> Brand:
        """Create or update a brand"""
        brand = db.query(Brand).filter(Brand.external_id == external_id).first()
        if brand:
            brand.title = title
            brand.title_en = title_en
            brand.image_url = image_url
            for key, value in kwargs.items():
                if hasattr(brand, key):
                    setattr(brand, key, value)
        else:
            brand = Brand(
                external_id=external_id,
                title=title,
                title_en=title_en,
                image_url=image_url,
                **kwargs
            )
            db.add(brand)
        
        db.commit()
        db.refresh(brand)
        return brand
    
    @staticmethod
    def link_brand_to_city(db: Session, brand_external_id: int, city_external_id: int) -> bool:
        """Link a brand to a city (many-to-many relationship)"""
        try:
            brand = db.query(Brand).filter(Brand.external_id == brand_external_id).first()
            city = db.query(City).filter(City.external_id == city_external_id).first()
            
            if brand and city:
                # Check if relationship already exists
                if city not in brand.cities:
                    brand.cities.append(city)
                    db.commit()
                return True
            return False
        except Exception as e:
            print(f"Error linking brand {brand_external_id} to city {city_external_id}: {str(e)}")
            return False
    
    @staticmethod
    def upsert_product(db: Session, external_id: int, brand_id: int, title: str, **kwargs) -> Product:
        """Create or update a product"""
        product = db.query(Product).filter(Product.external_id == external_id).first()
        if product:
            product.title = title
            product.brand_id = brand_id
            for key, value in kwargs.items():
                if hasattr(product, key):
                    setattr(product, key, value)
        else:
            product = Product(
                external_id=external_id,
                brand_id=brand_id,
                title=title,
                **kwargs
            )
            db.add(product)
        
        db.commit()
        db.refresh(product)
        return product
    
    @staticmethod
    def create_sync_log(db: Session, sync_type: str, status: str, records_processed: int = 0, 
                       error_message: str = None) -> DataSyncLog:
        """Create a sync log entry"""
        sync_log = DataSyncLog(
            sync_type=sync_type,
            status=status,
            records_processed=records_processed,
            error_message=error_message
        )
        db.add(sync_log)
        db.commit()
        db.refresh(sync_log)
        return sync_log
    
    @staticmethod
    def get_all_cities(db: Session) -> List[City]:
        """Get all cities from database"""
        return db.query(City).all()
    
    @staticmethod
    def get_brands_by_city(db: Session, city_external_id: int) -> List[Brand]:
        """Get all brands for a specific city using external ID"""
        city = db.query(City).filter(City.external_id == city_external_id).first()
        if city:
            return city.brands
        return []
    
    @staticmethod
    def get_brands_by_city_id(db: Session, city_id: int) -> List[Brand]:
        """Get all brands for a specific city using internal ID"""
        city = db.query(City).filter(City.id == city_id).first()
        if city:
            return city.brands
        return []
    
    @staticmethod
    def get_products_by_brand(db: Session, brand_id: int) -> List[Product]:
        """Get all products for a specific brand"""
        return db.query(Product).filter(Product.brand_id == brand_id).all()
    
    @staticmethod
    def get_brand_by_external_id(db: Session, external_id: int) -> Optional[Brand]:
        """Get brand by external ID"""
        return db.query(Brand).filter(Brand.external_id == external_id).first() 