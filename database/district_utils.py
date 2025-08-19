from typing import Optional, List, Dict, Any
from sqlalchemy.orm import Session
from database.db_models import District
from database.db_utils import SessionLocal
import re

class DistrictLookup:
    """Utility class for looking up cities by district names"""
    
    @staticmethod
    def normalize_city_name(city_name: str) -> str:
        """
        Comprehensive Arabic text normalization for better city extraction
        Removes hamza and normalizes common Arabic character variations
        """
        if not city_name:
            return city_name
            
        normalized = city_name.strip().lower()
        
        # Comprehensive Arabic character normalization
        normalizations = {
            # Remove standalone hamza
            'ء': '',
            # Alif variations
            'أ': 'ا',  # alif with hamza above -> alif
            'إ': 'ا',  # alif with hamza below -> alif
            'آ': 'ا',  # alif with madda -> alif
            # Yeh variations  
            'ى': 'ي',  # alif maksura -> yeh
            'ئ': 'ي',  # yeh with hamza -> yeh
            # Waw variations
            'ؤ': 'و',  # waw with hamza -> waw
            # Teh marbuta
            'ة': 'ه',  # teh marbuta -> heh
        }
        
        # Apply all normalizations
        for original, replacement in normalizations.items():
            normalized = normalized.replace(original, replacement)
        
        # Remove extra whitespace
        normalized = ' '.join(normalized.split())
                
        return normalized
    
    @staticmethod
    def get_city_by_district(district_name: str, session: Optional[Session] = None) -> Optional[str]:
        """
        Get the city name for a given district name
        
        Args:
            district_name: The district name to search for
            session: Optional database session, if not provided a new one will be created
            
        Returns:
            The city name if found, None otherwise
        """
        should_close_session = False
        if session is None:
            session = SessionLocal()
            should_close_session = True
        
        try:
            # Clean the district name
            clean_district = district_name.strip()
            
            # Direct match first
            district = session.query(District).filter_by(name=clean_district).first()
            
            if district:
                # Normalize the city name to handle spelling variations
                return DistrictLookup.normalize_city_name(district.city_name)
            
            # If no direct match, try partial matching (case-insensitive)
            district = session.query(District).filter(
                District.name.like(f'%{clean_district}%')
            ).first()
            
            if district:
                return DistrictLookup.normalize_city_name(district.city_name)
                
            return None
            
        except Exception as e:
            print(f"❌ Error looking up district '{district_name}': {str(e)}")
            return None
        finally:
            if should_close_session:
                session.close()
    
    @staticmethod
    def get_all_districts_for_city(city_name: str, session: Optional[Session] = None) -> List[str]:
        """
        Get all districts for a given city name
        
        Args:
            city_name: The city name to search for
            session: Optional database session, if not provided a new one will be created
            
        Returns:
            List of district names for the city
        """
        should_close_session = False
        if session is None:
            session = SessionLocal()
            should_close_session = True
        
        try:
            districts = session.query(District).filter_by(city_name=city_name.strip()).all()
            return [district.name for district in districts]
            
        except Exception as e:
            print(f"❌ Error getting districts for city '{city_name}': {str(e)}")
            return []
        finally:
            if should_close_session:
                session.close()
    
    @staticmethod
    def find_district_in_message(message: str, session: Optional[Session] = None) -> Optional[Dict[str, str]]:
        """
        Find district mentions in a message and return the corresponding city
        Supports both exact and partial matching (e.g., "حي الحمراء" matches "الحمراء الأول")
        
        Args:
            message: The user message to search
            session: Optional database session
            
        Returns:
            Dict with 'district' and 'city' keys if found, None otherwise
        """
        should_close_session = False
        if session is None:
            session = SessionLocal()
            should_close_session = True
        
        try:
            # Get all districts from database
            all_districts = session.query(District).all()
            
            # Sort by length (longest first) for better exact matching
            districts_sorted = sorted(all_districts, key=lambda d: len(d.name), reverse=True)
            
            message_lower = message.lower()
            
            # Apply normalization to user message for better matching
            normalized_message = DistrictLookup.normalize_city_name(message)
            
            # PHASE 1: Look for exact district name matches first
            for district in districts_sorted:
                district_name = district.name.strip()
                # Normalize district name for comparison
                normalized_district_name = DistrictLookup.normalize_city_name(district_name)
                
                if normalized_district_name.lower() in normalized_message.lower():
                    print(f"🎯 District match found:")
                    print(f"   Original district: '{district_name}'")
                    print(f"   Normalized district: '{normalized_district_name}'")
                    print(f"   User message normalized: '{normalized_message}'")
                    return {
                        'district': district_name,
                        'city': DistrictLookup.normalize_city_name(district.city_name)
                    }
            
            # PHASE 2: Look for partial district name matches
            # Extract potential district names after keywords
            district_keywords = ['حي', 'منطقة', 'الحي', 'في حي', 'حيكم', 'حينا']
            
            for keyword in district_keywords:
                if keyword in message_lower:
                    # Find the position after the keyword
                    keyword_pos = message_lower.find(keyword)
                    after_keyword = message[keyword_pos + len(keyword):].strip()
                    
                    # Extract the next few words as potential district name
                    words = after_keyword.split()[:3]  # Take up to 3 words
                    if words:
                        potential_district = ' '.join(words)
                        potential_district_clean = potential_district.lower().strip('،؟!.')
                        
                        # Normalize potential district for better matching
                        normalized_potential_district = DistrictLookup.normalize_city_name(potential_district_clean)
                        
                        # Look for partial matches with normalization
                        for district in all_districts:
                            district_name = district.name.strip()
                            normalized_district_name = DistrictLookup.normalize_city_name(district_name).lower()
                            
                            # Check if the potential district is a substring of the actual district
                            # or vice versa (handles "الحمراء" matching "الحمراء الأول")
                            if (normalized_potential_district in normalized_district_name or 
                                normalized_district_name in normalized_potential_district or
                                any(word in normalized_district_name for word in normalized_potential_district.split() if len(word) > 2)):
                                
                                print(f"🔍 Partial match with normalization:")
                                print(f"   Original potential: '{potential_district_clean}' -> Normalized: '{normalized_potential_district}'")
                                print(f"   Original district: '{district_name}' -> Normalized: '{normalized_district_name}'")
                                return {
                                    'district': district.name.strip(),
                                    'city': DistrictLookup.normalize_city_name(district.city_name)
                                }
            
            return None
            
        except Exception as e:
            print(f"❌ Error finding district in message: {str(e)}")
            return None
        finally:
            if should_close_session:
                session.close()
    
    @staticmethod
    def is_city_serviced(city_name: str, session: Optional[Session] = None) -> Dict[str, Any]:
        """
        Check if a city is serviced by Abar delivery
        
        Args:
            city_name: The city name to check
            session: Optional database session
            
        Returns:
            Dict with 'is_serviced', 'city_info', and 'message' keys
        """
        should_close_session = False
        if session is None:
            session = SessionLocal()
            should_close_session = True
        
        try:
            # Import here to avoid circular imports
            from services.data_api import data_api
            
            # Normalize city name
            normalized_city = DistrictLookup.normalize_city_name(city_name)
            
            # Get all serviced cities
            system_cities = data_api.get_all_cities(session)
            
            # Check if city is serviced (normalize both for comparison)
            for city in system_cities:
                system_city_name = city.get('name', '').strip()
                normalized_system_city = DistrictLookup.normalize_city_name(system_city_name)
                
                if normalized_system_city == normalized_city:
                    return {
                        'is_serviced': True,
                        'city_info': city,
                        'message': f"نعم، نوصل إلى {system_city_name}"  # Use original system city name in message
                    }
            
            # City not serviced
            return {
                'is_serviced': False,
                'city_info': None,
                'message': "بتحصل الاصناف والاسعار في التطبيق وهذا هو الرابط https://onelink.to/abar_app https://abar.app/en/store/ وايضا عن طريق الموقع الالكتروني"
            }
            
        except Exception as e:
            print(f"❌ Error checking if city is serviced: {str(e)}")
            return {
                'is_serviced': False,
                'city_info': None,
                'message': "عذراً، حدث خطأ في التحقق من التوصيل"
            }
        finally:
            if should_close_session:
                session.close()
    
    @staticmethod
    def handle_district_query(message: str, session: Optional[Session] = None) -> Dict[str, Any]:
        """
        Complete handler for district queries - finds district, maps to city, checks service availability
        
        Args:
            message: The user message
            session: Optional database session
            
        Returns:
            Dict with query processing results
        """
        should_close_session = False
        if session is None:
            session = SessionLocal()
            should_close_session = True
        
        try:
            # Step 1: Find district in message
            district_match = DistrictLookup.find_district_in_message(message, session)
            
            if not district_match:
                return {
                    'found_district': False,
                    'message': None
                }
            
            district_name = district_match['district']
            city_name = district_match['city']
            
            print(f"🏘️ DistrictLookup: Found district '{district_name}' -> city '{city_name}'")
            
            # Step 2: Check if city is serviced
            service_info = DistrictLookup.is_city_serviced(city_name, session)
            
            return {
                'found_district': True,
                'district_name': district_name,
                'city_name': city_name,
                'is_serviced': service_info['is_serviced'],
                'city_info': service_info['city_info'],
                'message': service_info['message']
            }
            
        except Exception as e:
            print(f"❌ Error handling district query: {str(e)}")
            return {
                'found_district': False,
                'message': "عذراً، حدث خطأ في معالجة الاستفسار"
            }
        finally:
            if should_close_session:
                session.close()
    
    @staticmethod
    def is_district_query(message: str) -> bool:
        """
        Check if a message is asking about a district (rather than a city)
        
        Args:
            message: The user message to analyze
            
        Returns:
            True if the message seems to be asking about a district
        """
        # Common Arabic words that indicate district queries
        district_indicators = [
            'حي',     # district/neighborhood
            'منطقة',  # area/zone
            'حيكم',   # your district 
            'حينا',   # our district
            'الحي',   # the district
            'في حي', # in district
            'حي ',    # district (with space)
        ]
        
        message_lower = message.lower()
        
        return any(indicator in message_lower for indicator in district_indicators)
    
    @staticmethod
    def get_district_statistics(session: Optional[Session] = None) -> Dict[str, Any]:
        """
        Get statistics about districts in the database
        
        Returns:
            Dictionary with district statistics
        """
        should_close_session = False
        if session is None:
            session = SessionLocal()
            should_close_session = True
        
        try:
            total_districts = session.query(District).count()
            total_cities = session.query(District.city_name).distinct().count()
            
            # Get cities with most districts
            from sqlalchemy import func
            city_district_counts = session.query(
                District.city_name,
                func.count(District.id).label('district_count')
            ).group_by(District.city_name).order_by(
                func.count(District.id).desc()
            ).limit(10).all()
            
            return {
                'total_districts': total_districts,
                'total_cities': total_cities,
                'top_cities_by_district_count': [
                    {'city': city, 'district_count': count} 
                    for city, count in city_district_counts
                ]
            }
            
        except Exception as e:
            print(f"❌ Error getting district statistics: {str(e)}")
            return {}
        finally:
            if should_close_session:
                session.close()

# Create a global instance for easy access
district_lookup = DistrictLookup() 