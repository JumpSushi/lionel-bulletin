import requests
from bs4 import BeautifulSoup
import re
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
import time
import os
import json
import hashlib

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
        
        # Strong indicators of feedback requests (forms, surveys, feedback collection)
        strong_feedback_phrases = [
            "fill out this form", "fill in the form", "fill out the form", "fill in this form",
            "survey", "questionnaire", "we need your feedback", "complete this form",
            "we would appreciate if you could", "take a minute", 
            "fill this form", "please fill out", "fill out form",
            "giving us feedback", "feedback and info",
            "feedback via", "share your thoughts", "provide feedback",
            "your response", "let us know what you think",
            "evaluation", "rate your experience", "how satisfied",
            "help shape", "your input would help", "by doing this form"
        ]
        
        # Check for strong feedback language first
        has_feedback_language = any(phrase in text_content for phrase in strong_feedback_phrases)
        
        # Check for Google Forms or other form URLs
        has_form_link = False
        links = item_text.find_all("a")
        for link in links:
            href = link.get("href", "")
            if ("forms.gle" in href or 
                "docs.google.com/forms" in href):
                has_form_link = True
                break
        
        # Very specific exceptions for donations only (not general volunteering)
        donation_exceptions = [
            "donate books", "books you could donate", "donation drive", 
            "food drive", "donate food", "clothing donation",
            "non-perishable", "storable foods", "bring donations"
        ]
        
        # If it's clearly a donation request, not feedback
        is_donation = any(phrase in text_content for phrase in donation_exceptions)
        if is_donation:
            return False
        
        # If it has strong feedback language OR a form link, it's likely feedback
        if has_feedback_language or has_form_link:
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
            "food drive", "donate food", "clothing donation", "support our students",
            "non-perishable", "storable foods", "donations", "donate",
            "collection box", "drop off", "fundraising",
            "books for donation", "donate items", "collecting", "contribute",
            "charitable", "food bank", "please bring", "collection drive", "community", "community project"
        ]
        
        # Exceptions that indicate this is NOT a donation request even if it mentions charity/fundraising
        non_donation_exceptions = [
            "charity committee", "artists needed", "volunteer", "help with",
            "join us", "looking for", "event", "competition", "read-a-thon",
            "audition", "trial", "participate", "sign up", "registration"
        ]
        
        # If this contains volunteer/event language, it's likely not a donation request
        if any(phrase in text_content for phrase in non_donation_exceptions):
            # Only consider it a donation if there are very explicit donation terms
            explicit_donation_phrases = [
                "donate books", "books you could donate", "donation drive", 
                "food drive", "donate food", "clothing donation",
                "non-perishable", "storable foods", "donations", "donate",
                "collection box", "drop off", "books for donation", "donate items"
            ]
            return any(phrase in text_content for phrase in explicit_donation_phrases)
        
        # Otherwise check for general donation phrases
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
    
    def extract_date_from_content(self, content):
        """Extract date information from bulletin content"""
        import re
        from datetime import datetime
        
        # Common date patterns
        date_patterns = [
            r'\b(\d{1,2})\s*[-/]\s*(\d{1,2})\s*[-/]\s*(\d{4}|\d{2})\b',  # 9/6/2025 or 9-6-25
            r'\b(\d{1,2})\s+(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{4})\b',
            r'\b(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{1,2}),?\s+(\d{4})\b',
            r'\b(\d{1,2})\s*(?:st|nd|rd|th)?\s+(January|February|March|April|May|June|July|August|September|October|November|December)\b',
            r'\b(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)\s*,?\s*(\d{1,2})\s+(January|February|March|April|May|June|July|August|September|October|November|December)\b'
        ]
        
        for pattern in date_patterns:
            matches = re.findall(pattern, content, re.IGNORECASE)
            if matches:
                return matches[0]  # Return first match
        
        return None
    
    def categorize_bulletin_item(self, content, title=""):
        """Categorize bulletin item based on content and title"""
        text = (content + " " + title).lower()
        
        # Form/Survey categories (check first to avoid misclassification)
        form_keywords = ['fill out form', 'fill in form', 'complete this form', 'google form', 'forms.gle', 'survey', 'questionnaire']
        if any(keyword in text for keyword in form_keywords):
            # Check if it's a sports-related form
            if any(word in text for word in ['exercise', 'fitness', 'physical activity', 'sport', 'athletic', 'workout']):
                return 'sports'
            # Check if it's academic-related
            elif any(word in text for word in ['study', 'research', 'academic', 'learning', 'education']):
                return 'academic'
            # Otherwise it's likely feedback/general
            else:
                return 'general'
        
        # Sports categories (more specific matching)
        sports_keywords = ['sport', 'sports', 'team', 'match', 'tournament', 'competition', 'trial', 'basketball', 'volleyball', 'football', 'soccer', 'tennis', 'swimming', 'athletics', 'rugby', 'badminton', 'issfhk', 'exercise', 'fitness', 'physical activity', 'workout', 'gym']
        if any(word in text for word in sports_keywords):
            # Exclude generic game references that aren't sports
            if 'free game' in text or 'video game' in text or 'board game' in text:
                return 'general'
            return 'sports'
        
        # Academic categories
        if any(word in text for word in ['exam', 'test', 'assessment', 'grade', 'marks', 'oral', 'written', 'quiz', 'homework', 'assignment', 'study', 'revision', 'academic', 'learning', 'education', 'research']):
            return 'academic'
        
        # Events categories (expanded to include volunteer recruitment)
        if any(word in text for word in ['event', 'meeting', 'conference', 'workshop', 'seminar', 'presentation', 'assembly', 'ceremony', 'celebration', 'audition', 'performance', 'volunteer', 'volunteers needed', 'help with', 'join us', 'artists needed', 'looking for', 'read-a-thon', 'charity', 'fundraising', 'media project']):
            return 'events'
        
        # Club activities
        if any(word in text for word in ['club', 'society', 'committee', 'group', 'organization']):
            return 'clubs'
        
        # Food/Canteen
        if any(word in text for word in ['canteen', 'menu', 'food', 'lunch', 'breakfast', 'snack']):
            return 'food'
        
        # Administrative
        if any(word in text for word in ['notice', 'announcement', 'policy', 'rule', 'guideline', 'procedure', 'access', 'restriction', 'schedule', 'timetable']):
            return 'administrative'
        
        # Default category
        return 'general'
    
    def determine_specific_year_group_targeting(self, content, year_groups_str=""):
        """Determine if bulletin specifically targets certain year groups"""
        text = (content + " " + (year_groups_str or "")).lower()
        
        # Check for explicit year group mentions
        year_indicators = {
            '7': ['year 7', 'yr 7', 'y7', 'grade 7', 'seventh grade', 'year seven'],
            '8': ['year 8', 'yr 8', 'y8', 'grade 8', 'eighth grade', 'year eight'],
            '9': ['year 9', 'yr 9', 'y9', 'grade 9', 'ninth grade', 'year nine'],
            '10': ['year 10', 'yr 10', 'y10', 'grade 10', 'tenth grade', 'year ten'],
            '11': ['year 11', 'yr 11', 'y11', 'grade 11', 'eleventh grade', 'year eleven'],
            '12': ['year 12', 'yr 12', 'y12', 'grade 12', 'twelfth grade', 'year twelve'],
            '13': ['year 13', 'yr 13', 'y13', 'grade 13', 'thirteenth grade', 'year thirteen']
        }
        
        # Find which year groups are specifically mentioned
        mentioned_years = []
        for year, indicators in year_indicators.items():
            if any(indicator in text for indicator in indicators):
                mentioned_years.append(year)
        
        # Return True if specific year groups are mentioned, False if it's general
        return len(mentioned_years) > 0
    
    def scrape_bulletin(self, max_items=20, generate_headlines=True, save_all_items=True):
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
                
                # Classify the item (but save ALL items regardless of classification)
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
                
                # Generate title (use AI headline if available, otherwise create from content)
                title = ai_headline if ai_headline else self.create_fallback_headline(content)
                
                # Extract date and categorize
                extracted_date = self.extract_date_from_content(content)
                category = self.categorize_bulletin_item(content, title)
                has_specific_year_targeting = self.determine_specific_year_group_targeting(content, year_groups)
                
                item_data = {
                    'title': title,
                    'content': content,
                    'ai_headline': ai_headline,
                    'is_feedback': is_feedback,
                    'is_donation': is_donation,
                    'is_from_student': is_student,
                    'is_year9': has_specific_year_targeting,  # Keep field name for API compatibility
                    'has_specific_targeting': has_specific_year_targeting,  # New field name
                    'category': category,
                    'date': str(extracted_date) if extracted_date else None,
                    'year_groups': year_groups,
                    'attachments': attachments,
                    'metadata': metadata,
                    'scraped_at': datetime.utcnow().isoformat()
                }
                
                scraped_items.append(item_data)
            
            return scraped_items
            
        except Exception as e:
            raise Exception(f"Failed to scrape bulletin: {str(e)}")
    
    def normalize_content_for_comparison(self, content):
        """Normalize content for better deduplication comparison"""
        import re
        # Remove extra whitespace and normalize
        normalized = re.sub(r'\s+', ' ', content.strip().lower())
        # Remove common variations that shouldn't affect deduplication
        normalized = re.sub(r'[^\w\s]', '', normalized)  # Remove punctuation
        return normalized
    
    def content_similarity(self, content1, content2, threshold=0.95):
        """Check if two content strings are similar enough to be considered duplicates"""
        norm1 = self.normalize_content_for_comparison(content1)
        norm2 = self.normalize_content_for_comparison(content2)
        
        # If one is much shorter than the other, check if it's contained in the longer one
        if len(norm1) > 0 and len(norm2) > 0:
            shorter = norm1 if len(norm1) < len(norm2) else norm2
            longer = norm2 if len(norm1) < len(norm2) else norm1
            
            # If the shorter content is contained in the longer one with high similarity
            if len(shorter) / len(longer) > threshold:
                return norm1 == norm2
            
            # Check for substring containment (one content fully contained in another)
            if shorter in longer and len(shorter) / len(longer) > 0.8:
                return True
        
        return norm1 == norm2
    
    def scrape_and_save_bulletins(self, max_items=20, save_all_items=True):
        """Scrape bulletins and save new ones to the database"""
        try:
            from app import db
            from app.models import BulletinItem
            
            # Scrape bulletin items (save all items by default)
            scraped_items = self.scrape_bulletin(max_items=max_items, save_all_items=save_all_items)
            new_count = 0
            skipped_duplicates = 0
            
            for item_data in scraped_items:
                # Check if item already exists by comparing content similarity
                existing_item = None
                
                # First, try exact content match (fastest)
                existing_item = BulletinItem.query.filter_by(content=item_data['content']).first()
                
                # If no exact match, check for similar content
                if not existing_item:
                    # Get recent bulletins to check similarity against
                    recent_bulletins = BulletinItem.query.order_by(BulletinItem.created_at.desc()).limit(50).all()
                    
                    for recent_bulletin in recent_bulletins:
                        if self.content_similarity(item_data['content'], recent_bulletin.content):
                            existing_item = recent_bulletin
                            print(f"Found similar content: '{item_data.get('title', 'No title')[:50]}...' matches existing ID {recent_bulletin.id}")
                            break
                
                if not existing_item:
                    # Create new bulletin item
                    bulletin_item = BulletinItem(
                        title=item_data.get('title', 'Untitled'),
                        content=item_data['content'],
                        ai_headline=item_data['ai_headline'],
                        is_feedback=item_data['is_feedback'],
                        is_donation=item_data['is_donation'],
                        is_from_student=item_data['is_from_student'],
                        has_specific_targeting=item_data.get('has_specific_targeting', False),  # New field name
                        category=item_data.get('category', 'general'),
                        date=item_data.get('date'),
                        year_groups=item_data['year_groups'],
                        attachments=json.dumps(item_data['attachments']) if item_data['attachments'] else None,
                        item_metadata=json.dumps(item_data['metadata']) if item_data['metadata'] else None,
                        scraped_at=datetime.utcnow()
                    )
                    
                    db.session.add(bulletin_item)
                    new_count += 1
                    print(f"Added new bulletin: '{item_data.get('title', 'No title')[:50]}...'")
                else:
                    skipped_duplicates += 1
            
            db.session.commit()
            print(f"Scraping completed: {new_count} new bulletins added, {skipped_duplicates} duplicates skipped")
            return new_count
            
        except Exception as e:
            if 'db' in locals():
                db.session.rollback()
            raise Exception(f"Failed to scrape and save bulletins: {str(e)}")
    
    def find_and_remove_duplicates(self, dry_run=True):
        """Find and optionally remove duplicate bulletins from the database"""
        try:
            from app import db
            from app.models import BulletinItem
            
            all_bulletins = BulletinItem.query.order_by(BulletinItem.created_at.asc()).all()
            duplicates_found = []
            to_delete = []
            
            print(f"Checking {len(all_bulletins)} bulletins for duplicates...")
            
            for i, bulletin in enumerate(all_bulletins):
                if bulletin.id in [d['id'] for d in to_delete]:
                    continue  # Already marked for deletion
                
                # Check against all subsequent bulletins
                for j in range(i + 1, len(all_bulletins)):
                    other_bulletin = all_bulletins[j]
                    
                    if other_bulletin.id in [d['id'] for d in to_delete]:
                        continue  # Already marked for deletion
                    
                    # Check if contents are similar
                    if self.content_similarity(bulletin.content, other_bulletin.content):
                        # Keep the older one (lower ID), mark the newer one for deletion
                        duplicate_info = {
                            'kept_id': bulletin.id,
                            'kept_title': bulletin.title,
                            'deleted_id': other_bulletin.id,
                            'deleted_title': other_bulletin.title,
                            'reason': 'Similar content'
                        }
                        duplicates_found.append(duplicate_info)
                        to_delete.append({
                            'id': other_bulletin.id,
                            'bulletin': other_bulletin
                        })
                        
                        print(f"Duplicate found: Keeping ID {bulletin.id} '{bulletin.title[:50]}...', "
                              f"removing ID {other_bulletin.id} '{other_bulletin.title[:50]}...'")
            
            print(f"\nFound {len(duplicates_found)} duplicate pairs ({len(to_delete)} bulletins to remove)")
            
            if not dry_run and to_delete:
                print("Removing duplicates from database...")
                for item in to_delete:
                    db.session.delete(item['bulletin'])
                
                db.session.commit()
                print(f"Successfully removed {len(to_delete)} duplicate bulletins")
            elif dry_run and to_delete:
                print("DRY RUN: No bulletins were actually deleted. Set dry_run=False to remove duplicates.")
            
            return {
                'duplicates_found': len(duplicates_found),
                'bulletins_to_remove': len(to_delete),
                'duplicate_details': duplicates_found
            }
            
        except Exception as e:
            if 'db' in locals():
                db.session.rollback()
            raise Exception(f"Failed to find/remove duplicates: {str(e)}")
    
    def generate_content_hash(self, content):
        """Generate a hash for content to speed up duplicate detection"""
        normalized = self.normalize_content_for_comparison(content)
        return hashlib.md5(normalized.encode('utf-8')).hexdigest()
    
    def add_content_hashes_to_existing_bulletins(self):
        """Add content hashes to existing bulletins for faster deduplication"""
        try:
            from app import db
            from app.models import BulletinItem
            
            # Check if content_hash column exists
            bulletins_without_hash = BulletinItem.query.all()
            updated_count = 0
            
            print(f"Adding content hashes to {len(bulletins_without_hash)} bulletins...")
            
            for bulletin in bulletins_without_hash:
                content_hash = self.generate_content_hash(bulletin.content)
                # Store hash in metadata for now (since we don't have a content_hash column)
                metadata = bulletin.get_metadata()
                metadata['content_hash'] = content_hash
                bulletin.set_metadata(metadata)
                updated_count += 1
            
            db.session.commit()
            print(f"Successfully added content hashes to {updated_count} bulletins")
            return updated_count
            
        except Exception as e:
            if 'db' in locals():
                db.session.rollback()
            raise Exception(f"Failed to add content hashes: {str(e)}")
    
    def get_database_stats(self):
        """Get statistics about the bulletin database"""
        try:
            from app import db
            from app.models import BulletinItem
            from sqlalchemy import func
            
            total_bulletins = BulletinItem.query.count()
            
            # Category distribution
            categories = db.session.query(
                BulletinItem.category, 
                func.count(BulletinItem.id)
            ).group_by(BulletinItem.category).all()
            
            # Recent bulletins
            recent_bulletins = BulletinItem.query.order_by(
                BulletinItem.created_at.desc()
            ).limit(5).all()
            
            return {
                'total_bulletins': total_bulletins,
                'categories': dict(categories),
                'recent_bulletins': [
                    {
                        'id': b.id, 
                        'title': b.title, 
                        'category': b.category,
                        'created_at': b.created_at.isoformat() if b.created_at else None
                    } 
                    for b in recent_bulletins
                ]
            }
            
        except Exception as e:
            raise Exception(f"Failed to get database stats: {str(e)}")

