from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.orm.session import Session
from typing import Optional, List, Dict, Any, Union
import os
import datetime

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
    def create_message(db: Session, user_id: int, content: str, wati_message_id: str = None) -> UserMessage:
        """Save a message from a user"""
        message = UserMessage(user_id=user_id, content=content, wati_message_id=wati_message_id)
        db.add(message)
        db.commit()
        db.refresh(message)
        return message
    
    @staticmethod
    def check_message_already_processed(db: Session, wati_message_id: str) -> bool:
        """Check if a message with this Wati message ID has already been processed"""
        if not wati_message_id:
            return False
        existing_message = db.query(UserMessage).filter(
            UserMessage.wati_message_id == wati_message_id
        ).first()
        return existing_message is not None
    
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
        """Get user conversation history formatted for LLM understanding"""
        # Get the last 'limit' messages from the user
        messages = db.query(UserMessage).filter(
            UserMessage.user_id == user_id
        ).order_by(
            UserMessage.timestamp.desc()
        ).limit(limit).all()
        
        history = []
        # Process messages in chronological order (oldest first)
        for msg in reversed(messages):
            # Add user message
            user_entry = {
                "role": "user",
                "content": f"user: {msg.content}",
                "timestamp": msg.timestamp.strftime("%Y-%m-%d %H:%M:%S") if msg.timestamp else None,
                "language": msg.language or 'ar',
                "raw_content": msg.content  # Keep original for reference
            }
            history.append(user_entry)
            
            # Add bot replies for this message (there should normally be only one reply per message)
            if msg.replies:
                # Sort replies by timestamp to ensure correct order
                sorted_replies = sorted(msg.replies, key=lambda x: x.timestamp or datetime.datetime.min)
                for reply in sorted_replies:
                    bot_entry = {
                        "role": "assistant", 
                        "content": f"bot: {reply.content}",
                        "timestamp": reply.timestamp.strftime("%Y-%m-%d %H:%M:%S") if reply.timestamp else None,
                        "language": reply.language or 'ar',
                        "raw_content": reply.content  # Keep original for reference
                    }
                    history.append(bot_entry)
        
        return history
    
    @staticmethod
    def get_formatted_conversation_for_llm(db: Session, user_id: int, limit: int = 5) -> str:
        """Get conversation history formatted as a single string for LLM context"""
        history = DatabaseManager.get_user_message_history(db, user_id, limit)
        
        if not history:
            return "No previous conversation history."
        
        # Format as a clean conversation string
        conversation_lines = []
        for entry in history:
            conversation_lines.append(entry["content"])
        
        return "\n".join(conversation_lines)
    
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
    
    @staticmethod
    def check_duplicate_bot_message(db: Session, user_id: int, proposed_message: str, limit: int = 3) -> bool:
        """Check if the bot is about to send a message similar to recent ones"""
        try:
            # Get recent bot replies
            recent_bot_replies = db.query(BotReply)\
                .join(UserMessage)\
                .filter(UserMessage.user_id == user_id)\
                .order_by(BotReply.timestamp.desc())\
                .limit(limit)\
                .all()
            
            if not recent_bot_replies:
                return False
            
            # Clean the proposed message for comparison
            proposed_clean = proposed_message.strip().lower()
            
            # Check if any recent bot reply is very similar
            for reply in recent_bot_replies:
                if reply.content:
                    reply_clean = reply.content.strip().lower()
                    
                    # Check for exact match
                    if proposed_clean == reply_clean:
                        print(f"🔄 Duplicate message detected: '{proposed_message[:50]}...'")
                        return True
                    
                    # Check for very similar messages (>80% similarity)
                    if len(proposed_clean) > 10 and len(reply_clean) > 10:
                        # Simple similarity check - if messages share >80% of words
                        proposed_words = set(proposed_clean.split())
                        reply_words = set(reply_clean.split())
                        
                        if len(proposed_words) > 0 and len(reply_words) > 0:
                            common_words = proposed_words.intersection(reply_words)
                            similarity = len(common_words) / max(len(proposed_words), len(reply_words))
                            
                            if similarity > 0.8:
                                print(f"🔄 Similar message detected (similarity: {similarity:.2f}): '{proposed_message[:50]}...'")
                                return True
            
            return False
            
        except Exception as e:
            print(f"Error checking duplicate bot message: {str(e)}")
            return False 