# Data Service for Abar Chatbot

This document describes the comprehensive data service implementation that scrapes data from external APIs and provides internal APIs for the chatbot system.

## Overview

The data service consists of three main components:

1. **Data Scraper** - Fetches data from external APIs
2. **Data API Service** - Provides internal APIs to access scraped data
3. **Scheduler** - Automates daily data synchronization

## Features

### Data Scraping
- Fetches cities, brands, and products from external APIs
- Handles data relationships (cities → brands → products)
- Upserts data (create or update existing records)
- Comprehensive error handling and logging
- Sync tracking with status logs

### Internal APIs
- RESTful endpoints for all data entities
- Search functionality across all entities
- Hierarchical data retrieval (city with brands and products)
- Structured JSON responses

### Automated Scheduling
- Daily data synchronization at configurable times
- Manual sync triggers
- Scheduler status monitoring
- Background thread execution

## Database Models

### City
```python
- id: Primary key
- external_id: ID from external API
- name: City name (Arabic)
- name_en: City name (English)
- created_at, updated_at: Timestamps
```

### Brand
```python
- id: Primary key
- external_id: contract_id from external API
- city_id: Foreign key to City
- title: Brand title (Arabic)
- title_en: Brand title (English)
- image_url: Brand image URL
- mounting_rate_image: Additional image
- meta_keywords, meta_description: SEO fields
- created_at, updated_at: Timestamps
```

### Product
```python
- id: Primary key
- external_id: product_id from external API
- brand_id: Foreign key to Brand
- title: Product title (Arabic)
- title_en: Product title (English)
- packing: Package information
- market_price: Product price
- barcode: Product barcode
- image_url: Product image
- meta_keywords_ar/en: SEO keywords
- meta_description_ar/en: SEO descriptions
- description_rich_text_ar/en: Rich text descriptions
- created_at, updated_at: Timestamps
```

### DataSyncLog
```python
- id: Primary key
- sync_type: Type of sync (cities, brands, products, brand_details)
- status: Sync status (success, failed, partial)
- records_processed: Number of records processed
- error_message: Error details if failed
- started_at, completed_at: Timestamps
```

## API Endpoints

### Data Sync Management

#### Manual Data Sync
```http
POST /data/sync
```
Triggers a full manual data synchronization.

**Response:**
```json
{
  "status": "success",
  "results": {
    "cities": 15,
    "brands": 120,
    "brand_details_and_products": 500
  }
}
```

#### Get Sync Status
```http
GET /data/sync/status
```
Returns the current status of the data sync scheduler.

**Response:**
```json
{
  "is_running": true,
  "scheduled_jobs": 1,
  "next_sync": "2024-01-02 02:00:00"
}
```

#### Start Scheduler
```http
POST /data/sync/start?daily_time=02:00
```
Starts the automated data sync scheduler.

#### Stop Scheduler
```http
POST /data/sync/stop
```
Stops the automated data sync scheduler.

### Cities API

#### Get All Cities
```http
GET /api/cities
GET /api/cities?search=الرياض
```

**Response:**
```json
{
  "status": "success",
  "data": [
    {
      "id": 1,
      "external_id": 1,
      "name": "الرياض",
      "name_en": "Riyadh",
      "created_at": "2024-01-01T00:00:00",
      "updated_at": "2024-01-01T00:00:00"
    }
  ]
}
```

#### Get City by ID
```http
GET /api/cities/{city_id}
```

#### Get City Brands
```http
GET /api/cities/{city_id}/brands
```

#### Get City with Full Data
```http
GET /api/cities/{city_id}/full
```
Returns city with all brands and their products.

### Brands API

#### Get All Brands
```http
GET /api/brands
GET /api/brands?search=مياه
```

#### Get Brand by ID
```http
GET /api/brands/{brand_id}
```

#### Get Brand Products
```http
GET /api/brands/{brand_id}/products
```

#### Get Brand with Products
```http
GET /api/brands/{brand_id}/full
```

### Products API

#### Get All Products
```http
GET /api/products
GET /api/products?search=تانيا
```

#### Get Product by ID
```http
GET /api/products/{product_id}
```

## Usage Examples

### Running Manual Sync
```python
from services.data_scraper import data_scraper
from database.db_utils import SessionLocal

db = SessionLocal()
try:
    results = data_scraper.full_sync(db)
    print(f"Sync completed: {results}")
finally:
    db.close()
```

### Using Internal APIs
```python
from services.data_api import data_api
from database.db_utils import SessionLocal

db = SessionLocal()
try:
    # Get all cities
    cities = data_api.get_all_cities(db)
    
    # Search brands
    brands = data_api.search_brands(db, "مياه")
    
    # Get brand with products
    brand_data = data_api.get_brand_with_products(db, 1)
finally:
    db.close()
```

### Starting Scheduler
```python
from services.scheduler import scheduler

# Start daily sync at 2 AM
scheduler.start_scheduler("02:00")

# Check status
status = scheduler.get_scheduler_status()
print(status)

# Manual sync
result = scheduler.run_manual_sync()
print(result)
```

## External API Configuration

The service connects to these external endpoints:

1. **Cities:** `GET /api/admin/ai/get-cities`
2. **Brands by City:** `GET /api/admin/ai/get-location-brands/{city_id}`
3. **Products by Brand:** `GET /api/admin/ai/get-brand-products/{brand_id}`
4. **Brand Details:** `GET /api/admin/ai/get-all-brand-details`

### Required Headers
```python
headers = {
    'ApiToken': '4e7f1b2c-3d5a-4b6c-9f7d-8e0f1b2c3d5a',
    'AccessKey': '1234',
    'Lang': 'ar'
}

# For brand details endpoint (no ApiToken required)
headers_no_token = {
    'AccessKey': '1234'
}
```

## Installation and Setup

1. **Install Dependencies:**
```bash
pip install -r requirements.txt
```

2. **Run Database Migrations:**
The database tables will be created automatically when the app starts.

3. **Test the Service:**
```bash
python test_data_service.py
```

4. **Start the Application:**
```bash
python app.py
```

The scheduler will automatically start and sync data daily at 2 AM.

## Error Handling

- All sync operations are logged with detailed error messages
- Failed syncs are tracked in the `DataSyncLog` table
- API endpoints return proper HTTP status codes
- Database transactions ensure data consistency

## Integration with Query Agent

The data APIs can be integrated with your query agent to provide real-time information about cities, brands, and products:

```python
from services.data_api import data_api

def get_brand_info(db, brand_name):
    """Get brand information for the query agent"""
    brands = data_api.search_brands(db, brand_name)
    if brands:
        brand_id = brands[0]['id']
        return data_api.get_brand_with_products(db, brand_id)
    return None
```

## Monitoring and Maintenance

- Monitor sync logs in the database
- Check scheduler status via `/data/sync/status` endpoint
- Manual sync can be triggered via `/data/sync` endpoint
- Review error logs for troubleshooting

## Performance Considerations

- Database uses indexes on external_id fields for fast lookups
- Upsert operations prevent duplicate data
- Batch processing for large datasets
- Background scheduling doesn't block main application

This data service provides a robust foundation for maintaining up-to-date product information in your chatbot system. 