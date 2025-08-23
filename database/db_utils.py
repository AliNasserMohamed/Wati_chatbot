from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.orm.session import Session
from typing import Optional, List, Dict, Any, Union
import os
import datetime

from database.db_models import Base, User, UserMessage, BotReply, City, Brand, Product, DataSyncLog, Complaint, Suggestion

# Create database directory if it doesn't exist
os.makedirs("database/data", exist_ok=True)

# Database connection
DATABASE_URL = "sqlite:///database/data/chatbot.sqlite?charset=utf8"

# Configure SQLite for better concurrency
engine = create_engine(
    DATABASE_URL, 
    pool_pre_ping=True,
    pool_recycle=300,
    connect_args={
        "check_same_thread": False,
        "isolation_level": None  # Enable autocommit mode for better concurrency
    },
    echo=False  # Set to True for SQL debugging
)

# Enable WAL mode for better concurrent access
from sqlalchemy import event
@event.listens_for(engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    """Configure SQLite for better concurrency and UTF-8 support"""
    cursor = dbapi_connection.cursor()
    # Enable WAL mode for better concurrent reads/writes
    cursor.execute("PRAGMA journal_mode=WAL")
    # Reduce lock timeout
    cursor.execute("PRAGMA busy_timeout=30000")  # 30 seconds
    # Optimize for concurrency
    cursor.execute("PRAGMA synchronous=NORMAL")
    # Ensure UTF-8 encoding
    cursor.execute("PRAGMA encoding='UTF-8'")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()

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
    def get_most_recent_user_message(db: Session, user_id: int) -> Optional[UserMessage]:
        """Get the most recent message from a user"""
        return db.query(UserMessage).filter(
            UserMessage.user_id == user_id
        ).order_by(
            UserMessage.timestamp.desc()
        ).first()
    
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
    
    @staticmethod
    def clear_user_messages_by_phone(db: Session, phone_number: str, delete_user_record: bool = False) -> Dict[str, Union[str, int, bool]]:
        """
        Clear all messages for a specific phone number
        
        Args:
            db: Database session
            phone_number: The phone number to clear messages for
            delete_user_record: Whether to also delete the user record (default: False)
        
        Returns:
            Dictionary with operation results
        """
        results = {
            "phone_number": phone_number,
            "user_found": False,
            "bot_replies_deleted": 0,
            "complaints_deleted": 0,
            "suggestions_deleted": 0,
            "user_messages_deleted": 0,
            "user_deleted": False,
            "success": False,
            "error": None
        }
        
        try:
            # Find user by phone number
            user = db.query(User).filter(User.phone_number == phone_number).first()
            
            if not user:
                results["error"] = "User not found"
                return results
                
            results["user_found"] = True
            user_id = user.id
            
            # Get all user messages
            user_messages = db.query(UserMessage).filter(UserMessage.user_id == user_id).all()
            
            # Delete dependent records first (to maintain referential integrity)
            total_bot_replies = 0
            total_complaints = 0
            total_suggestions = 0
            
            for message in user_messages:
                # Delete bot replies
                bot_replies_count = db.query(BotReply).filter(BotReply.message_id == message.id).delete()
                total_bot_replies += bot_replies_count
                
                # Delete complaints  
                complaints_count = db.query(Complaint).filter(Complaint.message_id == message.id).delete()
                total_complaints += complaints_count
                
                # Delete suggestions
                suggestions_count = db.query(Suggestion).filter(Suggestion.message_id == message.id).delete()
                total_suggestions += suggestions_count
            
            results["bot_replies_deleted"] = total_bot_replies
            results["complaints_deleted"] = total_complaints
            results["suggestions_deleted"] = total_suggestions
            
            # Delete user messages
            messages_deleted = db.query(UserMessage).filter(UserMessage.user_id == user_id).delete()
            results["user_messages_deleted"] = messages_deleted
            
            # Optionally delete user record
            if delete_user_record:
                db.delete(user)
                results["user_deleted"] = True
                
            db.commit()
            results["success"] = True
            
        except Exception as e:
            results["error"] = str(e)
            db.rollback()
            
        return results
    
    @staticmethod
    def get_user_message_count(db: Session, phone_number: str) -> Dict[str, Union[str, int, bool]]:
        """
        Get message count for a specific phone number
        
        Args:
            db: Database session
            phone_number: The phone number to check
        
        Returns:
            Dictionary with message counts
        """
        result = {
            "phone_number": phone_number,
            "user_found": False,
            "user_messages_count": 0,
            "bot_replies_count": 0,
            "total_messages": 0,
            "user_created": None,
            "last_activity": None
        }
        
        try:
            # Find user by phone number
            user = db.query(User).filter(User.phone_number == phone_number).first()
            
            if not user:
                return result
                
            result["user_found"] = True
            result["user_created"] = user.created_at.strftime("%Y-%m-%d %H:%M:%S") if user.created_at else None
            result["last_activity"] = user.updated_at.strftime("%Y-%m-%d %H:%M:%S") if user.updated_at else None
            
            # Count user messages
            user_messages_count = db.query(UserMessage).filter(UserMessage.user_id == user.id).count()
            result["user_messages_count"] = user_messages_count
            
            # Count bot replies
            bot_replies_count = db.query(BotReply).join(UserMessage).filter(
                UserMessage.user_id == user.id
            ).count()
            result["bot_replies_count"] = bot_replies_count
            
            result["total_messages"] = user_messages_count + bot_replies_count
            
        except Exception as e:
            result["error"] = str(e)
            
        return result
    
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
    def check_duplicate_bot_message(db: Session, user_id: int, proposed_message: str, limit: int = 5) -> Dict[str, Any]:
        """
        Check if the proposed bot message is a duplicate of recent messages
        Returns dict with 'is_duplicate' and 'recent_messages'
        """
        # Get recent bot replies for this user
        recent_replies = db.query(BotReply).join(UserMessage).filter(
            UserMessage.user_id == user_id
        ).order_by(BotReply.timestamp.desc()).limit(limit).all()
        
        recent_messages = [reply.content for reply in recent_replies]
        
        # Simple duplicate check - could be enhanced with fuzzy matching
        is_duplicate = proposed_message in recent_messages
        
        return {
            'is_duplicate': is_duplicate,
            'recent_messages': recent_messages
        }
    
    
        """Get statistics about embedding Q&A performance"""
        query = db.query(EmbeddingQA)
        if user_id:
            query = query.filter(EmbeddingQA.user_id == user_id)
        
        qa_records = query.all()
        
        if not qa_records:
            return {
                'total_records': 0,
                'avg_similarity': 0,
                'llm_evaluations': {}
            }
        
        similarities = [record.cosine_similarity for record in qa_records]
        evaluations = [record.llm_evaluation for record in qa_records if record.llm_evaluation]
        
        evaluation_counts = {}
        for eval_type in evaluations:
            evaluation_counts[eval_type] = evaluation_counts.get(eval_type, 0) + 1
        
        return {
            'total_records': len(qa_records),
            'avg_similarity': sum(similarities) / len(similarities),
            'min_similarity': min(similarities),
            'max_similarity': max(similarities),
            'llm_evaluations': evaluation_counts
        } 