import requests
from bs4 import BeautifulSoup
import re
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
import time
import os
import json

class BulletinScraperService:
    def __init__(self):
        self.bulletin_url = os.getenv('BULLETIN_URL', 'https://lionel2.kgv.edu.hk/local/mis/bulletin/bulletin.php')
        self.ai_api_url = os.getenv('AI_API_URL', 'https://ai.hackclub.com/chat/completions')
    
    def is_feedback_request(self, item):
        """Check if an item is primarily asking for feedback or form filling"""
        item_text = item.find("div", class_="itemtext")
        if not item_text:
            return False
        
        text_content = item_text.get_text().lower()
        
        # Strong indicators of feedback requests
        strong_feedback_phrases = [
            "fill out this form", "fill in the form", "fill out the form",
            "survey", "questionnaire", "we need your feedback",
            "we would appreciate if you could", "take a minute", 
            "fill this form", "please fill out", "forms.gle", 
            "google form", "giving us feedback", "feedback and info",
            "feedback via", "share your thoughts", "provide feedback",
            "your response", "let us know what you think"
        ]
        
        # If any strong indicator is found, it's definitely a feedback request
        if any(phrase in text_content for phrase in strong_feedback_phrases):
            return True
        
        # Items explicitly about donations are not feedback requests
        donation_exceptions = [
            "donate books", "books you could donate", "donation drive", 
            "food drive", "donate food", "clothing donation", "support our year 9",
            "non-perishable", "storable foods"
        ]
        
        if any(phrase in text_content for phrase in donation_exceptions):
            return False
        
        # Check for form URLs in links
        links = item_text.find_all("a")
        for link in links:
            href = link.get("href", "")
            if ("forms.gle" in href or 
                "docs.google.com/forms" in href or 
                "sites.google.com" in href and "form" in text_content.lower()):
                if any(phrase in text_content for phrase in donation_exceptions):
                    return False
                return True
        
        return False
    
    def is_donation_request(self, item):
        """Check if an item is primarily about donations"""
        item_text = item.find("div", class_="itemtext")
        if not item_text:
            return False
        
        text_content = item_text.get_text().lower()
        
        # Strong indicators of donation requests
        donation_phrases = [
            "donate books", "books you could donate", "donation drive", 
            "food drive", "donate food", "clothing donation", "support our year 9",
            "non-perishable", "storable foods", "donations", "donate",
            "collection box", "drop off", "fundraising", "charity", 
            "books for donation", "donate items", "collecting", "contribute",
            "charitable", "food bank", "please bring", "collection drive", "community", "community project"
        ]
        
        for phrase in donation_phrases:
            if phrase in text_content:
                return True
        
        # Check for links that might be about donations
        links = item_text.find_all("a")
        for link in links:
            link_text = link.get_text().lower()
            href = link.get("href", "").lower()
            if any(phrase in link_text for phrase in donation_phrases):
                return True
            if "donate" in href or "donation" in href:
                return True
                
        return False
    
    def is_from_student(self, item):
        """Check if an item is posted by a student"""
        meta = item.find("div", class_="itemmeta")
        if not meta:
            return False
        
        meta_text = meta.get_text()
        
        # Check for student ID pattern [XXYXX]
        if re.search(r'\[\d+[A-Z]\d+\]', meta_text):
            return True
        
        # Check for Teacher Supervisor text
        if 'Teacher Supervisor' in meta_text:
            return True
        
        return False
    
    def generate_headline(self, text, max_retries=2):
        """Generate a concise headline using Hack Club AI API"""
        for attempt in range(max_retries + 1):
            try:
                prompt = (
                    f"You are a talented headline writer for a school newspaper, creating single-line headlines. Create a single-line headline that is under 10 words "
                    f"for this school bulletin announcement. Make it catchy, clear, and informative, and make sure it conveys the most important aspects of the announcement. If the body content simply contains a date, it is probably a Canteen Menu, not Exams. PLease give it a sutible name.\n\n"
                    f"Return ONLY the headline without quotes, explanation, or additional text:\n\n"
                    f"{text[:500]}..."
                )
                
                headers = {"Content-Type": "application/json"}
                data = {
                    "messages": [{"role": "user", "content": prompt}]
                }
                
                response = requests.post(self.ai_api_url, headers=headers, json=data, timeout=15)
                
                if response.status_code == 200:
                    result = response.json()
                    
                    headline = None
                    if 'choices' in result and len(result['choices']) > 0:
                        choice = result['choices'][0]
                        if 'message' in choice and 'content' in choice['message']:
                            headline = choice['message']['content'].strip()
                        elif 'text' in choice:
                            headline = choice['text'].strip()
                    
                    if headline:
                        headline = headline.strip('"\'').strip()
                        
                        if '\n' in headline:
                            headline = headline.split('\n')[0].strip()
                        
                        if len(headline.split()) > 10:
                            headline = ' '.join(headline.split()[:10]) + "..."
                        
                        if len(headline) > 5:
                            return headline
                
                if attempt == max_retries:
                    return self.create_fallback_headline(text)
                    
                time.sleep(0.5)
                    
            except Exception as e:
                if attempt == max_retries:
                    return self.create_fallback_headline(text)
                
        return self.create_fallback_headline(text)
    
    def create_fallback_headline(self, text):
        """Create a fallback headline from the original text"""
        first_sentence = text.split('.')[0]
        
        if len(first_sentence.split()) > 10:
            return ' '.join(first_sentence.split()[:10]) + "..."
        return first_sentence + "..."
    
    def extract_year_groups(self, item):
        """Extract year groups that this item targets"""
        year_groups = []
        
        # Check metadata
        meta = item.find("div", class_="itemmeta")
        if meta:
            meta_text = meta.get_text()
            
            # Look for targeting information
            if "Targeting" in meta_text:
                # Extract year group patterns
                year_patterns = re.findall(r'Yr\s*(\d+)', meta_text)
                year_groups.extend(year_patterns)
                
                year_patterns = re.findall(r'Year\s*(\d+)', meta_text)
                year_groups.extend(year_patterns)
        
        # Check content for year group mentions
        item_text = item.find("div", class_="itemtext")
        if item_text:
            text_content = item_text.get_text()
            
            year_patterns = re.findall(r'\bYear\s*(\d+)\b', text_content)
            year_groups.extend(year_patterns)
            
            year_patterns = re.findall(r'\bYr\s*(\d+)\b', text_content)
            year_groups.extend(year_patterns)
            
            year_patterns = re.findall(r'\bY(\d+)\b', text_content)
            year_groups.extend(year_patterns)
        
        # Remove duplicates and return as comma-separated string
        unique_years = list(set(year_groups))
        return ','.join(unique_years) if unique_years else None
    
    def extract_attachments(self, item):
        """Extract attachments from bulletin item"""
        attachments = []
        attachments_div = item.find("div", class_="itemattachments")
        
        if attachments_div:
            for link in attachments_div.find_all("a"):
                attachment = {
                    'name': link.get_text(strip=True),
                    'url': link.get('href')
                }
                attachments.append(attachment)
        
        return attachments
    
    def extract_metadata(self, item):
        """Extract metadata from bulletin item"""
        metadata = {}
        
        meta = item.find("div", class_="itemmeta")
        if meta:
            metadata['posted_info'] = meta.get_text(strip=True)
        
        return metadata
    
    def scrape_bulletin(self, max_items=20, generate_headlines=True):
        """Scrape bulletin items from KGV website"""
        try:
            response = requests.get(self.bulletin_url, timeout=10)
            response.raise_for_status()
            soup = BeautifulSoup(response.content, "html.parser")
            
            # Find the main bulletin content area
            main_content = soup.find("div", class_="studentbuletin")
            
            if not main_content:
                raise Exception("Could not find bulletin content on page")
            
            # Extract bulletin items
            all_bulletin_items = main_content.find_all("div", class_="row-fluid")
            
            scraped_items = []
            
            for item in all_bulletin_items[:max_items]:
                # Extract text content
                item_text = item.find("div", class_="itemtext")
                if not item_text:
                    continue
                
                content = item_text.get_text()
                content = re.sub(r'\n\s*\n', '\n\n', content).strip()
                
                if not content:
                    continue
                
                # Classify the item
                is_feedback = self.is_feedback_request(item)
                is_donation = self.is_donation_request(item)
                is_student = self.is_from_student(item)
                
                # Extract additional information
                year_groups = self.extract_year_groups(item)
                attachments = self.extract_attachments(item)
                metadata = self.extract_metadata(item)
                
                # Generate AI headline if requested
                ai_headline = None
                if generate_headlines:
                    try:
                        ai_headline = self.generate_headline(content)
                    except Exception as e:
                        print(f"Failed to generate headline: {e}")
                        ai_headline = self.create_fallback_headline(content)
                
                item_data = {
                    'content': content,
                    'ai_headline': ai_headline,
                    'is_feedback': is_feedback,
                    'is_donation': is_donation,
                    'is_from_student': is_student,
                    'year_groups': year_groups,
                    'attachments': attachments,
                    'metadata': metadata,
                    'scraped_at': datetime.utcnow().isoformat()
                }
                
                scraped_items.append(item_data)
            
            return scraped_items
            
        except Exception as e:
            raise Exception(f"Failed to scrape bulletin: {str(e)}")
    
    def scrape_and_save_bulletins(self, max_items=20):
        """Scrape bulletins and save new ones to the database"""
        try:
            from app import db
            from app.models import BulletinItem
            
            # Scrape bulletin items
            scraped_items = self.scrape_bulletin(max_items=max_items)
            new_count = 0
            
            for item_data in scraped_items:
                # Check if item already exists (basic deduplication by content hash)
                content_hash = hash(item_data['content'])
                existing_item = BulletinItem.query.filter_by(
                    title=item_data.get('title', ''),
                    content=item_data['content']
                ).first()
                
                if not existing_item:
                    # Create new bulletin item
                    bulletin_item = BulletinItem(
                        title=item_data.get('title', 'Untitled'),
                        content=item_data['content'],
                        ai_headline=item_data['ai_headline'],
                        is_feedback=item_data['is_feedback'],
                        is_donation=item_data['is_donation'],
                        is_from_student=item_data['is_from_student'],
                        year_groups=item_data['year_groups'],
                        attachments=json.dumps(item_data['attachments']) if item_data['attachments'] else None,
                        item_metadata=json.dumps(item_data['metadata']) if item_data['metadata'] else None,
                        scraped_at=datetime.utcnow()
                    )
                    
                    db.session.add(bulletin_item)
                    new_count += 1
            
            db.session.commit()
            return new_count
            
        except Exception as e:
            if 'db' in locals():
                db.session.rollback()
            raise Exception(f"Failed to scrape and save bulletins: {str(e)}")

    # ...existing code...
