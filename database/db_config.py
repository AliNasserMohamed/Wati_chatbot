"""
Database configuration optimized for concurrency
"""
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.pool import StaticPool
from sqlalchemy import event
import os

def create_optimized_engine(database_url: str) -> Engine:
    """Create an optimized database engine for better concurrency"""
    
    # Create database directory if it doesn't exist
    os.makedirs("database/data", exist_ok=True)
    
    # Configure SQLite for maximum concurrency
    engine = create_engine(
        database_url,
        # Connection pooling for better concurrency
        poolclass=StaticPool,
        pool_size=20,  # Increased from default
        max_overflow=30,  # Allow more overflow connections
        pool_pre_ping=True,
        pool_recycle=3600,  # Recycle connections every hour
        
        # SQLite-specific optimizations
        connect_args={
            "check_same_thread": False,
            "timeout": 60,  # Increased timeout for busy database
            "isolation_level": None,  # Enable autocommit for better concurrency
        },
        
        # Disable echo in production for performance
        echo=False,
        
        # Connection execution options
        execution_options={
            "isolation_level": "AUTOCOMMIT"
        }
    )
    
    # Configure SQLite pragmas for optimal concurrency
    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        """Configure SQLite for better concurrency and performance"""
        cursor = dbapi_connection.cursor()
        
        # WAL mode for better concurrent reads/writes
        cursor.execute("PRAGMA journal_mode=WAL")
        
        # Optimize for concurrent access
        cursor.execute("PRAGMA synchronous=NORMAL")  # Balance between safety and performance
        cursor.execute("PRAGMA cache_size=10000")    # Increase cache size
        cursor.execute("PRAGMA temp_store=MEMORY")   # Use memory for temp tables
        cursor.execute("PRAGMA mmap_size=268435456") # 256MB memory-mapped I/O
        
        # Reduce lock contention
        cursor.execute("PRAGMA busy_timeout=60000")  # 60 second timeout
        cursor.execute("PRAGMA wal_autocheckpoint=100")  # Checkpoint every 100 pages
        
        # Optimize queries
        cursor.execute("PRAGMA optimize")
        
        cursor.close()
    
    return engine

# Connection pool monitoring
@event.listens_for(Engine, "connect")
def receive_connect(dbapi_connection, connection_record):
    """Monitor connection events"""
    print(f"🔗 Database connection established: {id(dbapi_connection)}")

@event.listens_for(Engine, "close")
def receive_close(dbapi_connection, connection_record):
    """Monitor connection close events"""
    print(f"❌ Database connection closed: {id(dbapi_connection)}") 