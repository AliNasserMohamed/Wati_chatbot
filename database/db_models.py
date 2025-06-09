from sqlalchemy import Column, Integer, String, Text, ForeignKey, DateTime, create_engine, Enum, Float, Table
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship, sessionmaker
import datetime
import enum

Base = declarative_base()

# Many-to-many association table between cities and brands
city_brand_association = Table(
    'city_brands',
    Base.metadata,
    Column('city_id', Integer, ForeignKey('cities.id'), primary_key=True),
    Column('brand_id', Integer, ForeignKey('brands.id'), primary_key=True),
    Column('created_at', DateTime, default=datetime.datetime.utcnow)
)

class MessageType(enum.Enum):
    SERVICE_REQUEST = "Service Request"
    INQUIRY = "Inquiry"
    COMPLAINT = "Complaint"
    SUGGESTION = "Suggestion or Note"
    GREETING = "Greeting or Random Messages"
    TEMPLATE_REPLY = "Template Reply"
    OTHERS = "Others"

class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    phone_number = Column(String(20), unique=True, index=True, nullable=False)
    name = Column(String(100), nullable=True)
    conclusion = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)
    
    # Relationship with messages
    messages = relationship("UserMessage", back_populates="user")

class UserMessage(Base):
    __tablename__ = "user_messages"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    content = Column(Text, nullable=False)
    timestamp = Column(DateTime, default=datetime.datetime.utcnow)
    message_type = Column(Enum(MessageType), nullable=True)
    language = Column(String(2), default='ar')  # 'ar' for Arabic, 'en' for English
    wati_message_id = Column(String(255), nullable=True)  # Track Wati message ID to prevent duplicates
    
    # Relationships
    user = relationship("User", back_populates="messages")
    replies = relationship("BotReply", back_populates="user_message")

class BotReply(Base):
    __tablename__ = "bot_replies"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    message_id = Column(Integer, ForeignKey("user_messages.id"), nullable=False)
    content = Column(Text, nullable=False)
    timestamp = Column(DateTime, default=datetime.datetime.utcnow)
    language = Column(String(2), default='ar')  # Add language field to track response language
    
    # Relationship
    user_message = relationship("UserMessage", back_populates="replies")

class Complaint(Base):
    __tablename__ = "complaints"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    message_id = Column(Integer, ForeignKey("user_messages.id"), nullable=False)
    content = Column(Text, nullable=False)
    status = Column(String(50), default="pending")
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)
    
    user = relationship("User")
    message = relationship("UserMessage")

class Suggestion(Base):
    __tablename__ = "suggestions"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    message_id = Column(Integer, ForeignKey("user_messages.id"), nullable=False)
    content = Column(Text, nullable=False)
    status = Column(String(50), default="pending")
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)
    
    user = relationship("User")
    message = relationship("UserMessage")

class UserSession(Base):
    __tablename__ = "user_sessions"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    session_id = Column(String(100), unique=True, nullable=False)
    started_at = Column(DateTime, default=datetime.datetime.utcnow)
    last_activity = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)
    context = Column(Text, nullable=True)  # Store session context as JSON
    
    user = relationship("User")

# New models for Cities, Brands, and Products
class City(Base):
    __tablename__ = "cities"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    external_id = Column(Integer, unique=True, nullable=False)  # ID from external API
    name = Column(String(200), nullable=False)  # Arabic name
    name_en = Column(String(200), nullable=True)  # English name
    title = Column(String(200), nullable=True)  # Alternative name field from API
    lat = Column(Float, nullable=True)  # Latitude
    lng = Column(Float, nullable=True)  # Longitude
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)
    
    # Many-to-many relationship with brands
    brands = relationship("Brand", secondary=city_brand_association, back_populates="cities")

class Brand(Base):
    __tablename__ = "brands"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    external_id = Column(Integer, unique=True, nullable=False)  # contract_id from external API
    title = Column(String(200), nullable=False)  # Arabic title
    title_en = Column(String(200), nullable=True)  # English title
    image_url = Column(Text, nullable=True)
    mounting_rate_image = Column(Text, nullable=True)
    meta_keywords = Column(Text, nullable=True)
    meta_description = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)
    
    # Many-to-many relationship with cities
    cities = relationship("City", secondary=city_brand_association, back_populates="brands")
    products = relationship("Product", back_populates="brand")

class Product(Base):
    __tablename__ = "products"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    external_id = Column(Integer, unique=True, nullable=False)  # product_id from external API
    brand_id = Column(Integer, ForeignKey("brands.id"), nullable=False)
    title = Column(String(200), nullable=False)
    title_en = Column(String(200), nullable=True)
    packing = Column(String(200), nullable=True)
    market_price = Column(Float, nullable=True)
    contract_price = Column(Float, nullable=True)  # Added contract_price field
    barcode = Column(String(50), nullable=True)
    image_url = Column(Text, nullable=True)
    meta_keywords_ar = Column(Text, nullable=True)
    meta_keywords_en = Column(Text, nullable=True)
    meta_description_ar = Column(Text, nullable=True)
    meta_description_en = Column(Text, nullable=True)
    description_rich_text_ar = Column(Text, nullable=True)
    description_rich_text_en = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)
    
    # Relationship
    brand = relationship("Brand", back_populates="products")

# Sync log to track data updates
class DataSyncLog(Base):
    __tablename__ = "data_sync_logs"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    sync_type = Column(String(50), nullable=False)  # 'cities', 'brands', 'products', 'brand_details'
    status = Column(String(20), nullable=False)  # 'success', 'failed', 'partial'
    records_processed = Column(Integer, default=0)
    error_message = Column(Text, nullable=True)
    started_at = Column(DateTime, default=datetime.datetime.utcnow)
    completed_at = Column(DateTime, nullable=True) 