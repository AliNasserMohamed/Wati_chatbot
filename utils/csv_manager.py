import csv
import json
import os
from typing import List, Dict, Any, Optional
from datetime import datetime
import pandas as pd

class CSVManager:
    """
    Manager class for handling Q&A pairs in CSV format
    """
    
    def __init__(self, csv_path: str = "knowledge_base/chatbot_qa_pairs.csv"):
        self.csv_path = csv_path
        self.columns = [
            'question', 'answer', 'category', 'language', 
            'source', 'priority', 'metadata'
        ]
        self._ensure_csv_exists()
    
    def _ensure_csv_exists(self):
        """Ensure the CSV file exists with proper headers"""
        if not os.path.exists(self.csv_path):
            os.makedirs(os.path.dirname(self.csv_path), exist_ok=True)
            with open(self.csv_path, 'w', newline='', encoding='utf-8') as file:
                writer = csv.DictWriter(file, fieldnames=self.columns)
                writer.writeheader()
    
    def read_qa_pairs(self) -> List[Dict[str, Any]]:
        """
        Read all Q&A pairs from the CSV file
        Returns a list of dictionaries with Q&A data
        """
        qa_pairs = []
        try:
            with open(self.csv_path, 'r', encoding='utf-8') as file:
                reader = csv.DictReader(file)
                for row in reader:
                    # Parse metadata JSON if it exists
                    metadata = {}
                    if row.get('metadata'):
                        try:
                            metadata = json.loads(row['metadata'])
                        except json.JSONDecodeError:
                            metadata = {}
                    
                    qa_pair = {
                        'question': row['question'],
                        'answer': row['answer'],
                        'category': row.get('category', 'general'),
                        'language': row.get('language', 'ar'),
                        'source': row.get('source', 'csv'),
                        'priority': row.get('priority', 'normal'),
                        'metadata': metadata
                    }
                    qa_pairs.append(qa_pair)
            
            print(f"✅ Successfully read {len(qa_pairs)} Q&A pairs from CSV")
            return qa_pairs
            
        except FileNotFoundError:
            print(f"❌ CSV file not found: {self.csv_path}")
            return []
        except Exception as e:
            print(f"❌ Error reading CSV file: {str(e)}")
            return []
    
    def write_qa_pairs(self, qa_pairs: List[Dict[str, Any]], mode: str = 'w') -> bool:
        """
        Write Q&A pairs to the CSV file
        
        Args:
            qa_pairs: List of Q&A pair dictionaries
            mode: 'w' for overwrite, 'a' for append (default: 'w')
        
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            # Ensure directory exists
            os.makedirs(os.path.dirname(self.csv_path), exist_ok=True)
            
            with open(self.csv_path, mode, newline='', encoding='utf-8') as file:
                writer = csv.DictWriter(file, fieldnames=self.columns)
                
                # Write header only if we're overwriting or file is empty
                if mode == 'w' or (mode == 'a' and os.path.getsize(self.csv_path) == 0):
                    writer.writeheader()
                
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
                        'source': qa_pair.get('source', 'csv'),
                        'priority': qa_pair.get('priority', 'normal'),
                        'metadata': metadata_str
                    }
                    writer.writerow(row)
            
            print(f"✅ Successfully wrote {len(qa_pairs)} Q&A pairs to CSV")
            return True
            
        except Exception as e:
            print(f"❌ Error writing to CSV file: {str(e)}")
            return False
    
    def add_qa_pair(self, question: str, answer: str, category: str = 'general', 
                    language: str = 'ar', source: str = 'admin', 
                    priority: str = 'normal', metadata: Dict[str, Any] = None) -> bool:
        """
        Add a single Q&A pair to the CSV file
        
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
            # Check if file exists and has content
            file_exists = os.path.exists(self.csv_path)
            has_content = file_exists and os.path.getsize(self.csv_path) > 0
            
            with open(self.csv_path, 'a', newline='', encoding='utf-8') as file:
                writer = csv.DictWriter(file, fieldnames=self.columns)
                
                # Write header if file is empty or doesn't exist
                if not has_content:
                    writer.writeheader()
                
                # Convert metadata to JSON string
                metadata_str = json.dumps(metadata, ensure_ascii=False) if metadata else ""
                
                row = {
                    'question': qa_pair['question'],
                    'answer': qa_pair['answer'],
                    'category': qa_pair['category'],
                    'language': qa_pair['language'],
                    'source': qa_pair['source'],
                    'priority': qa_pair['priority'],
                    'metadata': metadata_str
                }
                writer.writerow(row)
            
            print(f"✅ Successfully added Q&A pair: {question[:50]}...")
            return True
            
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
        Get statistics about the Q&A pairs in the CSV
        
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
            source = pair.get('source', 'csv')
            stats['sources'][source] = stats['sources'].get(source, 0) + 1
        
        return stats
    
    def backup_csv(self, backup_suffix: str = None) -> str:
        """
        Create a backup of the current CSV file
        
        Args:
            backup_suffix: Optional suffix for backup filename
        
        Returns:
            Path to the backup file
        """
        if backup_suffix is None:
            backup_suffix = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        backup_path = f"{self.csv_path}.backup_{backup_suffix}"
        
        try:
            import shutil
            shutil.copy2(self.csv_path, backup_path)
            print(f"✅ Created backup: {backup_path}")
            return backup_path
        except Exception as e:
            print(f"❌ Error creating backup: {str(e)}")
            return ""

# Create a global instance
csv_manager = CSVManager() 