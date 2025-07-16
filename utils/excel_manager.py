import json
import os
from typing import List, Dict, Any, Optional
from datetime import datetime
import pandas as pd

class ExcelManager:
    """
    Manager class for handling Q&A pairs in Excel format
    """
    
    def __init__(self, excel_path: str = "knowledge_base/chatbot_qa_pairs.xlsx"):
        self.excel_path = excel_path
        self.columns = [
            'question', 'answer', 'category', 'language', 
            'source', 'priority', 'metadata'
        ]
        self._ensure_excel_exists()
    
    def _ensure_excel_exists(self):
        """Ensure the Excel file exists with proper headers"""
        if not os.path.exists(self.excel_path):
            os.makedirs(os.path.dirname(self.excel_path), exist_ok=True)
            # Create empty DataFrame with headers
            df = pd.DataFrame(columns=self.columns)
            df.to_excel(self.excel_path, index=False, engine='openpyxl')
    
    def read_qa_pairs(self) -> List[Dict[str, Any]]:
        """
        Read all Q&A pairs from the Excel file
        Returns a list of dictionaries with Q&A data
        """
        qa_pairs = []
        try:
            # Read Excel file
            df = pd.read_excel(self.excel_path, engine='openpyxl')
            
            # Replace NaN values with empty strings
            df = df.fillna('')
            
            for _, row in df.iterrows():
                # Parse metadata JSON if it exists
                metadata = {}
                if row.get('metadata') and str(row['metadata']).strip():
                    try:
                        metadata = json.loads(str(row['metadata']))
                    except (json.JSONDecodeError, ValueError):
                        metadata = {}
                
                qa_pair = {
                    'question': str(row['question']).strip() if row['question'] else '',
                    'answer': str(row['answer']).strip() if row['answer'] else '',
                    'category': str(row.get('category', 'general')).strip() if row.get('category') else 'general',
                    'language': str(row.get('language', 'ar')).strip() if row.get('language') else 'ar',
                    'source': str(row.get('source', 'excel')).strip() if row.get('source') else 'excel',
                    'priority': str(row.get('priority', 'normal')).strip() if row.get('priority') else 'normal',
                    'metadata': metadata
                }
                
                # Only add if question is not empty
                if qa_pair['question']:
                    qa_pairs.append(qa_pair)
            
            print(f"✅ Successfully read {len(qa_pairs)} Q&A pairs from Excel")
            return qa_pairs
            
        except FileNotFoundError:
            print(f"❌ Excel file not found: {self.excel_path}")
            return []
        except Exception as e:
            print(f"❌ Error reading Excel file: {str(e)}")
            return []
    
    def write_qa_pairs(self, qa_pairs: List[Dict[str, Any]], mode: str = 'w') -> bool:
        """
        Write Q&A pairs to the Excel file
        
        Args:
            qa_pairs: List of Q&A pair dictionaries
            mode: 'w' for overwrite, 'a' for append (default: 'w')
        
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            # Ensure directory exists
            os.makedirs(os.path.dirname(self.excel_path), exist_ok=True)
            
            # Prepare data for DataFrame
            data = []
            for qa_pair in qa_pairs:
                # Convert metadata to JSON string if it's a dict
                metadata_str = ""
                if qa_pair.get('metadata'):
                    if isinstance(qa_pair['metadata'], dict):
                        metadata_str = json.dumps(qa_pair['metadata'], ensure_ascii=False)
                    else:
                        metadata_str = str(qa_pair['metadata'])
                
                row = {
                    'question': qa_pair.get('question', ''),
                    'answer': qa_pair.get('answer', ''),
                    'category': qa_pair.get('category', 'general'),
                    'language': qa_pair.get('language', 'ar'),
                    'source': qa_pair.get('source', 'excel'),
                    'priority': qa_pair.get('priority', 'normal'),
                    'metadata': metadata_str
                }
                data.append(row)
            
            if mode == 'a' and os.path.exists(self.excel_path):
                # Read existing data and append
                existing_df = pd.read_excel(self.excel_path, engine='openpyxl')
                new_df = pd.DataFrame(data)
                combined_df = pd.concat([existing_df, new_df], ignore_index=True)
                combined_df.to_excel(self.excel_path, index=False, engine='openpyxl')
            else:
                # Create new DataFrame and write
                df = pd.DataFrame(data)
                df.to_excel(self.excel_path, index=False, engine='openpyxl')
            
            print(f"✅ Successfully wrote {len(qa_pairs)} Q&A pairs to Excel")
            return True
            
        except Exception as e:
            print(f"❌ Error writing to Excel file: {str(e)}")
            return False
    
    def add_qa_pair(self, question: str, answer: str, category: str = 'general', 
                    language: str = 'ar', source: str = 'admin', 
                    priority: str = 'normal', metadata: Dict[str, Any] = None) -> bool:
        """
        Add a single Q&A pair to the Excel file
        
        Args:
            question: The question text
            answer: The answer text
            category: Category of the Q&A pair
            language: Language code ('ar' or 'en')
            source: Source of the Q&A pair
            priority: Priority level
            metadata: Additional metadata
        
        Returns:
            bool: True if successful, False otherwise
        """
        if not question or not question.strip():
            print("❌ Question cannot be empty")
            return False
        
        # Default metadata
        if metadata is None:
            metadata = {
                'created_at': datetime.now().isoformat(),
                'type': category
            }
        
        qa_pair = {
            'question': question.strip(),
            'answer': answer.strip() if answer else '',
            'category': category,
            'language': language,
            'source': source,
            'priority': priority,
            'metadata': metadata
        }
        
        try:
            # Add single Q&A pair using append mode
            return self.write_qa_pairs([qa_pair], mode='a')
            
        except Exception as e:
            print(f"❌ Error adding Q&A pair: {str(e)}")
            return False
    
    def search_qa_pairs(self, query: str, category: str = None, 
                        language: str = None) -> List[Dict[str, Any]]:
        """
        Search for Q&A pairs by query text
        
        Args:
            query: Search query
            category: Filter by category (optional)
            language: Filter by language (optional)
        
        Returns:
            List of matching Q&A pairs
        """
        all_pairs = self.read_qa_pairs()
        results = []
        
        query_lower = query.lower()
        
        for pair in all_pairs:
            # Check if query matches question or answer
            matches_text = (query_lower in pair['question'].lower() or 
                          query_lower in pair['answer'].lower())
            
            # Check category filter
            matches_category = category is None or pair['category'] == category
            
            # Check language filter
            matches_language = language is None or pair['language'] == language
            
            if matches_text and matches_category and matches_language:
                results.append(pair)
        
        return results
    
    def get_stats(self) -> Dict[str, Any]:
        """
        Get statistics about the Q&A pairs in the Excel file
        
        Returns:
            Dictionary with statistics
        """
        qa_pairs = self.read_qa_pairs()
        
        if not qa_pairs:
            return {'total': 0, 'categories': {}, 'languages': {}}
        
        stats = {
            'total': len(qa_pairs),
            'categories': {},
            'languages': {},
            'sources': {}
        }
        
        for pair in qa_pairs:
            # Count by category
            category = pair.get('category', 'general')
            stats['categories'][category] = stats['categories'].get(category, 0) + 1
            
            # Count by language
            language = pair.get('language', 'ar')
            stats['languages'][language] = stats['languages'].get(language, 0) + 1
            
            # Count by source
            source = pair.get('source', 'excel')
            stats['sources'][source] = stats['sources'].get(source, 0) + 1
        
        return stats
    
    def backup_excel(self, backup_suffix: str = None) -> str:
        """
        Create a backup of the current Excel file
        
        Args:
            backup_suffix: Optional suffix for backup filename
        
        Returns:
            Path to the backup file
        """
        if backup_suffix is None:
            backup_suffix = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        backup_path = f"{self.excel_path}.backup_{backup_suffix}"
        
        try:
            import shutil
            shutil.copy2(self.excel_path, backup_path)
            print(f"✅ Created backup: {backup_path}")
            return backup_path
        except Exception as e:
            print(f"❌ Error creating backup: {str(e)}")
            return ""

# Create a global instance
excel_manager = ExcelManager()

# For backward compatibility, create csv_manager alias
csv_manager = excel_manager 