#!/usr/bin/env python3
"""
District Lookup Test Script
Tests district lookup functionality with comprehensive logging and statistics
"""

import sys
import os
from typing import List, Dict, Any
from database.db_utils import SessionLocal, DATABASE_URL
from database.db_models import District
from database.district_utils import district_lookup

def print_header(title: str):
    """Print a formatted header"""
    print(f"\n{'='*60}")
    print(f"🔍 {title}")
    print(f"{'='*60}")

def print_section(title: str):
    """Print a formatted section header"""
    print(f"\n{'─'*40}")
    print(f"📋 {title}")
    print(f"{'─'*40}")

def get_district_statistics(session) -> Dict[str, Any]:
    """Get comprehensive district statistics"""
    try:
        # Total districts
        total_districts = session.query(District).count()
        
        # Total cities
        total_cities = session.query(District.city_name).distinct().count()
        
        # Cities with most districts
        from sqlalchemy import func
        city_district_counts = session.query(
            District.city_name,
            func.count(District.id).label('district_count')
        ).group_by(District.city_name).order_by(
            func.count(District.id).desc()
        ).limit(10).all()
        
        # Districts by name frequency
        district_name_counts = session.query(
            District.name,
            func.count(District.id).label('name_count')
        ).group_by(District.name).having(
            func.count(District.id) > 1
        ).order_by(
            func.count(District.id).desc()
        ).limit(15).all()
        
        return {
            'total_districts': total_districts,
            'total_cities': total_cities,
            'top_cities': city_district_counts,
            'common_district_names': district_name_counts
        }
        
    except Exception as e:
        print(f"❌ Error getting statistics: {str(e)}")
        return {}

def test_specific_districts(session, district_names: List[str]):
    """Test specific district names"""
    print_section("Testing Specific Districts")
    
    for district_name in district_names:
        print(f"\n🔍 Testing district: '{district_name}'")
        
        # Check if district exists in database
        matching_districts = session.query(District).filter(
            District.name.contains(district_name)
        ).all()
        
        if matching_districts:
            print(f"   ✅ Found {len(matching_districts)} district(s) with name containing '{district_name}':")
            for d in matching_districts:
                print(f"      🏘️ '{d.name}' -> 🏙️ '{d.city_name}'")
        else:
            print(f"   ❌ No districts found containing '{district_name}'")
        
        # Test district lookup function
        test_messages = [
            f"فيه توصيل لحي {district_name}",
            f"حي {district_name}",
            f"في {district_name}",
            f"منطقة {district_name}",
            district_name
        ]
        
        print(f"   🧪 Testing district lookup function:")
        for msg in test_messages:
            try:
                result = district_lookup.find_district_in_message(msg, session)
                if result:
                    print(f"      ✅ '{msg}' -> {result}")
                else:
                    print(f"      ❌ '{msg}' -> None")
            except Exception as e:
                print(f"      ❌ '{msg}' -> Error: {str(e)}")

def test_message_patterns(session):
    """Test various message patterns"""
    print_section("Testing Message Patterns")
    
    test_patterns = [
        # Arabic patterns
        "فيه توصيل لحي النخيل",
        "فيه توصيل لحي الكوثر", 
        "حي الحمراء الأول",
        "في حي المعلمين",
        "منطقة النزهة",
        "الحي الشمالي",
        "حي البحيرة",
        "في اليرموك",
        "حينا الروضة",
        
        # Edge cases
        "النخيل",
        "الكوثر بالرياض",
        "حي   النخيل   ",  # Extra spaces
        "حي‌النخيل",      # With invisible characters
    ]
    
    for pattern in test_patterns:
        print(f"\n🔍 Testing: '{pattern}'")
        try:
            result = district_lookup.find_district_in_message(pattern, session)
            if result:
                print(f"   ✅ Found: {result}")
            else:
                print(f"   ❌ Not found")
        except Exception as e:
            print(f"   ❌ Error: {str(e)}")

def show_database_info():
    """Show database connection information"""
    print_section("Database Information")
    print(f"📁 Database URL: {DATABASE_URL}")
    print(f"🐍 Python Version: {sys.version}")
    print(f"📂 Current Directory: {os.getcwd()}")
    
def show_district_samples(session, limit: int = 20):
    """Show sample districts from each city"""
    print_section(f"District Samples (First {limit})")
    
    try:
        # Get sample districts grouped by city
        cities_with_districts = session.query(District.city_name).distinct().all()
        
        for (city_name,) in cities_with_districts[:10]:  # Show first 10 cities
            print(f"\n🏙️ {city_name}:")
            city_districts = session.query(District).filter_by(
                city_name=city_name
            ).limit(5).all()  # Show first 5 districts per city
            
            for district in city_districts:
                print(f"   🏘️ {district.name}")
                
    except Exception as e:
        print(f"❌ Error showing samples: {str(e)}")

def main():
    """Main test function"""
    print_header("District Lookup Test Suite")
    
    # Show database info
    show_database_info()
    
    # Create database session
    session = SessionLocal()
    try:
        # Get and show statistics
        print_section("Database Statistics")
        stats = get_district_statistics(session)
        
        if stats:
            print(f"📊 Total Districts: {stats['total_districts']}")
            print(f"🏙️ Total Cities: {stats['total_cities']}")
            
            print(f"\n📈 Top Cities by District Count:")
            for city, count in stats['top_cities']:
                print(f"   🏙️ {city}: {count} districts")
                
            print(f"\n📝 Most Common District Names:")
            for name, count in stats['common_district_names']:
                print(f"   🏘️ '{name}': appears in {count} cities")
        
        # Show district samples
        show_district_samples(session)
        
        # Test specific districts mentioned in the conversation
        specific_districts = [
            "النخيل",
            "الكوثر", 
            "البحيرة",
            "الحمراء الأول",
            "المعلمين",
            "النزهة",
            "اليرموك"
        ]
        
        test_specific_districts(session, specific_districts)
        
        # Test various message patterns
        test_message_patterns(session)
        
        print_header("Test Complete")
        print("🎉 All tests completed successfully!")
        
    except Exception as e:
        print(f"\n❌ Error during testing: {str(e)}")
        import traceback
        print(f"📋 Traceback:")
        traceback.print_exc()
        
    finally:
        session.close()

if __name__ == "__main__":
    main() 