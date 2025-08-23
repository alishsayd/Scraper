#!/usr/bin/env python3
"""
Automated Job Scraper for Product Management Positions
Scrapes target company websites and stores in CSV/JSON files
100% Free - No paid services required
"""

import requests
from bs4 import BeautifulSoup
import json
import csv
import time
import hashlib
from datetime import datetime, timedelta
from typing import List, Dict, Optional
import os
import logging
import re
from pathlib import Path

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class JobScraper:
    def __init__(self, data_dir: str = "data"):
        """Initialize the job scraper with local file storage"""
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(exist_ok=True)
        
        # File paths
        self.jobs_csv = self.data_dir / "jobs.csv"
        self.jobs_json = self.data_dir / "jobs.json"
        self.stats_json = self.data_dir / "stats.json"
        
        self.product_mgmt_keywords = [
            'product manager', 'product management', 'senior product manager',
            'principal product manager', 'product lead', 'product owner',
            'director of product', 'head of product', 'vp product', 'vp of product',
            'group product manager', 'staff product manager'
        ]
        
        # Initialize files if they don't exist
        self.initialize_files()
        
    def initialize_files(self):
        """Create initial data files if they don't exist"""
        if not self.jobs_csv.exists():
            with open(self.jobs_csv, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow([
                    'company', 'title', 'location', 'url', 'date_posted', 
                    'date_found', 'hash', 'status'
                ])
                
        if not self.jobs_json.exists():
            with open(self.jobs_json, 'w') as f:
                json.dump([], f)
                
        if not self.stats_json.exists():
            with open(self.stats_json, 'w') as f:
                json.dump({
                    'total_jobs_found': 0,
                    'last_run': '',
                    'companies_scraped': {},
                    'run_history': []
                }, f)

    def create_job_hash(self, job: Dict) -> str:
        """Create unique hash for job to detect duplicates"""
        unique_string = f"{job['company']}{job['title']}{job['location']}"
        return hashlib.md5(unique_string.encode()).hexdigest()[:12]

    def is_product_management_job(self, title: str, url: str = "", description: str = "") -> bool:
        """Check if job title/description matches Product Management criteria"""
        # Filter out non-job URLs first
        excluded_url_patterns = [
            '/product-managers/',  # General info pages
            '/about-product',
            '/what-is-product',
            '/product-management-guide',
            '/blog/',
            '/resources/',
            '/tools/',
            '/templates/'
        ]
        
        for pattern in excluded_url_patterns:
            if pattern in url.lower():
                return False
        
        text = f"{title.lower()} {description.lower()}"
        
        # Must contain product management keywords
        has_pm_keyword = any(keyword in text for keyword in self.product_mgmt_keywords)
        
        # Exclude non-PM roles that might contain "product"
        exclude_keywords = [
            'software engineer', 'frontend', 'backend', 'developer', 'designer',
            'marketing', 'sales', 'customer success', 'support', 'analyst',
            'intern', 'qa', 'test', 'devops', 'data scientist', 'recruiter'
        ]
        
        has_exclude = any(keyword in text for keyword in exclude_keywords)
        
        return has_pm_keyword and not has_exclude

    def scrape_generic_jobs(self, company: str, url: str) -> List[Dict]:
        """Generic job scraper that works for many job sites"""
        jobs = []
        
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            }
            
            logger.info(f"Fetching {url}")
            response = requests.get(url, headers=headers, timeout=30)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Common selectors for job listings (try multiple patterns)
            job_selectors = [
                '.job-listing', '.job-item', '.position', '.job-card', '.job-post',
                '[data-job-id]', '.job', '.career-item', '.opening', '.vacancy',
                '.role', '.position-item', '.job-opportunity'
            ]
            
            job_elements = []
            for selector in job_selectors:
                elements = soup.select(selector)
                if elements:
                    job_elements = elements
                    logger.info(f"Found {len(elements)} job elements using selector: {selector}")
                    break
            
            # If no structured job elements found, look for links with job-related text
            if not job_elements:
                logger.info("No structured elements found, trying link-based approach")
                all_links = soup.find_all('a', href=True)
                job_elements = []
                
                for link in all_links:
                    text = link.get_text().lower()
                    if any(word in text for word in ['manager', 'product', 'director', 'lead', 'senior']):
                        job_elements.append(link)
                
                logger.info(f"Found {len(job_elements)} potential job links")
            
            # Parse job elements
            parsed_count = 0
            for element in job_elements[:50]:  # Limit to prevent overload
                try:
                    # Extract job title
                    title_elem = (
                        element.find(['h1', 'h2', 'h3', 'h4']) or 
                        element.find(class_=re.compile(r'title|job-title|position|role-title', re.I)) or
                        element.find('a') or
                        element
                    )
                    title = title_elem.get_text(strip=True) if title_elem else "Unknown"
                    
                    # Clean up title
                    title = re.sub(r'\s+', ' ', title)  # Remove extra whitespace
                    title = title.split('\n')[0].strip()  # Take first line only
                    
                    # Skip if title is too generic, empty, or not relevant
                    if (len(title) < 5 or 
                        title.lower() in ['jobs', 'careers', 'apply', 'view all', 'see all', 'more'] or
                        len(title) > 200):
                        continue
                    
                    # Extract location
                    location_patterns = [
                        r'([A-Za-z\s]+,\s*[A-Z]{2,})',  # City, State/Country
                        r'(Remote)',
                        r'([A-Za-z\s]+,\s*[A-Z]{2})',  # City, ST
                        r'(New York|San Francisco|London|Berlin|Toronto|Seattle|Boston|Austin)'
                    ]
                    
                    location = "Remote/Unknown"
                    location_elem = element.find(class_=re.compile(r'location|city|office|geo', re.I))
                    
                    if location_elem:
                        location_text = location_elem.get_text(strip=True)
                    else:
                        location_text = element.get_text()
                    
                    for pattern in location_patterns:
                        match = re.search(pattern, location_text, re.I)
                        if match:
                            location = match.group(1).strip()
                            break
                    
                    # Extract job URL
                    job_url = ""
                    if element.name == 'a' and element.get('href'):
                        job_url = element.get('href')
                    else:
                        link_elem = element.find('a', href=True)
                        if link_elem:
                            job_url = link_elem.get('href')
                    
                    if job_url and not job_url.startswith('http'):
                        from urllib.parse import urljoin
                        job_url = urljoin(url, job_url)
                    
                    # Extract description (if available)
                    desc_elem = element.find(class_=re.compile(r'description|summary|excerpt|snippet', re.I))
                    description = ""
                    if desc_elem:
                        description = desc_elem.get_text(strip=True)[:300]
                    else:
                        # Use element text as backup
                        full_text = element.get_text(strip=True)
                        if len(full_text) > len(title) + 20:
                            description = full_text[len(title):300].strip()
                    
    def extract_date_posted(self, element, soup) -> str:
        """Try to extract when the job was posted"""
        # Common date patterns and selectors
        date_selectors = [
            '.posted-date', '.job-date', '.date-posted', '.publish-date',
            '[data-date]', '.timestamp', '.job-meta-date', '.listing-date'
        ]
        
        # Try to find date in the job element first
        for selector in date_selectors:
            date_elem = element.find(class_=re.compile(selector.replace('.', ''), re.I))
            if date_elem:
                date_text = date_elem.get_text(strip=True)
                parsed_date = self.parse_date_text(date_text)
                if parsed_date:
                    return parsed_date
        
        # Look for date patterns in the text
        element_text = element.get_text()
        date_patterns = [
            r'(\d{1,2})\s+(days?|weeks?|months?)\s+ago',
            r'(yesterday|today)',
            r'(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})',
            r'(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{1,2},?\s+\d{2,4}'
        ]
        
        for pattern in date_patterns:
            match = re.search(pattern, element_text, re.I)
            if match:
                parsed_date = self.parse_date_text(match.group(0))
                if parsed_date:
                    return parsed_date
        
        return "Unknown"
    
    def parse_date_text(self, date_text: str) -> str:
        """Parse various date formats into standardized format"""
        date_text = date_text.lower().strip()
        today = datetime.now()
        
        # Handle relative dates
        if 'today' in date_text or '0 days ago' in date_text:
            return today.strftime('%Y-%m-%d')
        elif 'yesterday' in date_text or '1 day ago' in date_text:
            return (today - timedelta(days=1)).strftime('%Y-%m-%d')
        
        # Handle "X days/weeks/months ago"
        time_ago_match = re.search(r'(\d+)\s+(day|week|month)s?\s+ago', date_text)
        if time_ago_match:
            number = int(time_ago_match.group(1))
            unit = time_ago_match.group(2)
            
            if unit == 'day':
                date = today - timedelta(days=number)
            elif unit == 'week':
                date = today - timedelta(weeks=number)
            elif unit == 'month':
                date = today - timedelta(days=number * 30)  # Approximate
            
            return date.strftime('%Y-%m-%d')
        
        # Handle absolute dates (basic parsing)
        date_match = re.search(r'(\d{1,2})[/-](\d{1,2})[/-](\d{2,4})', date_text)
        if date_match:
            month, day, year = date_match.groups()
            if len(year) == 2:
                year = f"20{year}"
            try:
                date = datetime(int(year), int(month), int(day))
                return date.strftime('%Y-%m-%d')
            except ValueError:
                pass
        
        return None
                        job = {
                            'company': company,
                            'title': title,
                            'location': location,
                            'url': job_url or url,
                            'description': description,
                            'date_found': datetime.now().strftime('%Y-%m-%d %H:%M'),
                            'status': 'Found',
                            'date_applied': '',
                            'hash': ''
                        }
                        job['hash'] = self.create_job_hash(job)
                        jobs.append(job)
                        parsed_count += 1
                        logger.info(f"Found PM job: {title} at {location}")
                        
                except Exception as e:
                    logger.debug(f"Error parsing job element: {e}")
                    continue
            
            logger.info(f"Successfully parsed {parsed_count} PM jobs from {len(job_elements)} elements")
                    
        except Exception as e:
            logger.error(f"Error scraping {company} ({url}): {e}")
            
        return jobs

    def scrape_company_specific(self, company: str, url: str) -> List[Dict]:
        """Company-specific scrapers for better accuracy"""
        
        # Add company-specific logic here based on the URL patterns
        if 'stripe.com' in url:
            return self.scrape_stripe(company, url)
        elif 'greenhouse.io' in url:
            return self.scrape_greenhouse(company, url)
        elif 'lever.co' in url:
            return self.scrape_lever(company, url)
        elif 'workday' in url or 'myworkdayjobs' in url:
            return self.scrape_workday(company, url)
        elif 'jobs.ashbyhq.com' in url:
            return self.scrape_ashby(company, url)
        else:
            return self.scrape_generic_jobs(company, url)

    def scrape_stripe(self, company: str, url: str) -> List[Dict]:
        """Specific scraper for Stripe jobs"""
        jobs = []
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            }
            
            # Stripe has a search API we can try
            api_url = "https://stripe.com/api/jobs"
            
            # First try the API
            try:
                response = requests.get(api_url, headers=headers, timeout=30)
                if response.status_code == 200:
                    data = response.json()
                    job_list = data.get('jobs', [])
                    
                    for job_data in job_list:
                        title = job_data.get('title', '')
                        if self.is_product_management_job(title, job_data.get('absolute_url', '')):
                            # Extract location
                            location = "Remote/Unknown"
                            if job_data.get('location'):
                                location = job_data['location']
                            elif job_data.get('office_locations'):
                                locations = job_data['office_locations']
                                location = ', '.join(locations[:2])  # First two locations
                            
                            # Extract date posted
                            date_posted = "Unknown"
                            if job_data.get('posted_at'):
                                try:
                                    from datetime import datetime
                                    posted_date = datetime.fromisoformat(job_data['posted_at'].replace('Z', '+00:00'))
                                    date_posted = posted_date.strftime('%Y-%m-%d')
                                except:
                                    pass
                            
                            job = {
                                'company': company,
                                'title': title,
                                'location': location,
                                'url': job_data.get('absolute_url', f"https://stripe.com/jobs/listing/{job_data.get('id', '')}"),
                                'date_posted': date_posted,
                                'date_found': datetime.now().strftime('%Y-%m-%d'),
                                'status': 'Found',
                                'hash': ''
                            }
                            job['hash'] = self.create_job_hash(job)
                            jobs.append(job)
                    
                    logger.info(f"Stripe API returned {len(jobs)} PM jobs")
                    if jobs:
                        return jobs
            except Exception as e:
                logger.warning(f"Stripe API failed: {e}")
            
            # Fallback: scrape the main jobs page
            response = requests.get(url, headers=headers, timeout=30)
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Look for job listings on Stripe's page
            job_links = soup.find_all('a', href=True)
            
            for link in job_links:
                href = link.get('href')
                if '/jobs/listing/' in href:
                    title = link.get_text(strip=True)
                    
                    if self.is_product_management_job(title, href):
                        # Make absolute URL
                        if not href.startswith('http'):
                            href = f"https://stripe.com{href}"
                        
                        # Try to extract location and date from the page context
                        location = "Remote/Unknown"
                        date_posted = "Unknown"
                        
                        # Look for location in nearby elements
                        parent = link.parent
                        if parent:
                            location_text = parent.get_text()
                            location_patterns = [
                                r'([A-Za-z\s]+,\s*[A-Z]{2,})',
                                r'(Remote|San Francisco|New York|Dublin|Singapore)'
                            ]
                            for pattern in location_patterns:
                                match = re.search(pattern, location_text, re.I)
                                if match:
                                    location = match.group(1).strip()
                                    break
                        
                        job = {
                            'company': company,
                            'title': title,
                            'location': location,
                            'url': href,
                            'date_posted': date_posted,
                            'date_found': datetime.now().strftime('%Y-%m-%d'),
                            'status': 'Found',
                            'hash': ''
                        }
                        job['hash'] = self.create_job_hash(job)
                        jobs.append(job)
            
            logger.info(f"Stripe fallback scraping found {len(jobs)} PM jobs")
            
        except Exception as e:
            logger.error(f"Error scraping Stripe: {e}")
        
        return jobs

    def scrape_greenhouse(self, company: str, url: str) -> List[Dict]:
        """Scraper for Greenhouse-based job sites"""
        jobs = []
        try:
            # Try the API endpoint first
            if '/jobs' in url:
                api_url = url.replace('/jobs', '/api/jobs')
                headers = {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                    'Accept': 'application/json'
                }
                
                response = requests.get(api_url, headers=headers, timeout=30)
                if response.status_code == 200:
                    try:
                        data = response.json()
                        job_list = data.get('jobs', []) if isinstance(data, dict) else data
                        
                        for job_data in job_list:
                            title = job_data.get('title', '')
                            if self.is_product_management_job(title, job_data.get('absolute_url', '')):
                                location = "Unknown"
                                if job_data.get('location'):
                                    location = job_data['location'].get('name', 'Unknown')
                                elif job_data.get('offices'):
                                    offices = job_data['offices']
                                    if offices:
                                        location = offices[0].get('name', 'Unknown')
                                
                                # Try to extract date posted
                                date_posted = "Unknown"
                                if job_data.get('updated_at') or job_data.get('created_at'):
                                    date_str = job_data.get('updated_at') or job_data.get('created_at')
                                    try:
                                        posted_date = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
                                        date_posted = posted_date.strftime('%Y-%m-%d')
                                    except:
                                        pass
                                
                                job = {
                                    'company': company,
                                    'title': title,
                                    'location': location,
                                    'url': job_data.get('absolute_url', url),
                                    'date_posted': date_posted,
                                    'date_found': datetime.now().strftime('%Y-%m-%d'),
                                    'status': 'Found',
                                    'hash': ''
                                }
                                job['hash'] = self.create_job_hash(job)
                                jobs.append(job)
                        
                        logger.info(f"Greenhouse API returned {len(jobs)} PM jobs")
                        return jobs
                        
                    except json.JSONDecodeError:
                        logger.warning("Greenhouse API returned invalid JSON, falling back to generic scraping")
                
        except Exception as e:
            logger.warning(f"Greenhouse API failed: {e}, falling back to generic scraping")
        
        # Fallback to generic scraping
        return self.scrape_generic_jobs(company, url)

    def scrape_lever(self, company: str, url: str) -> List[Dict]:
        """Scraper for Lever-based job sites"""
        # Lever often has API endpoints too
        try:
            # Try API first
            if 'jobs.lever.co' in url:
                api_url = url.replace('jobs.lever.co', 'api.lever.co/v0/postings')
                response = requests.get(api_url, timeout=30)
                if response.status_code == 200:
                    data = response.json()
                    jobs = []
                    
                    for job_data in data:
                        title = job_data.get('text', '')
                        if self.is_product_management_job(title, job_data.get('hostedUrl', '')):
                            location = job_data.get('categories', {}).get('location', 'Unknown')
                            
                            # Try to extract date posted
                            date_posted = "Unknown"
                            if job_data.get('createdAt'):
                                try:
                                    posted_date = datetime.fromtimestamp(job_data['createdAt'] / 1000)
                                    date_posted = posted_date.strftime('%Y-%m-%d')
                                except:
                                    pass
                            
                            job = {
                                'company': company,
                                'title': title,
                                'location': location,
                                'url': job_data.get('hostedUrl', url),
                                'date_posted': date_posted,
                                'date_found': datetime.now().strftime('%Y-%m-%d'),
                                'status': 'Found',
                                'hash': ''
                            }
                            job['hash'] = self.create_job_hash(job)
                            jobs.append(job)
                    
                    if jobs:
                        logger.info(f"Lever API returned {len(jobs)} PM jobs")
                        return jobs
        except Exception as e:
            logger.warning(f"Lever API failed: {e}, falling back to generic scraping")
        
        return self.scrape_generic_jobs(company, url)

    def scrape_workday(self, company: str, url: str) -> List[Dict]:
        """Scraper for Workday-based job sites (these are tricky due to JavaScript)"""
        # Workday sites are heavily JavaScript-based, so generic scraping might not work well
        # But let's try anyway
        return self.scrape_generic_jobs(company, url)

    def scrape_ashby(self, company: str, url: str) -> List[Dict]:
        """Scraper for Ashby-based job sites"""
        return self.scrape_generic_jobs(company, url)

    def load_existing_jobs(self) -> Dict[str, Dict]:
        """Load existing jobs from JSON file"""
        try:
            with open(self.jobs_json, 'r') as f:
                jobs_list = json.load(f)
                return {job['hash']: job for job in jobs_list}
        except Exception as e:
            logger.error(f"Error loading existing jobs: {e}")
            return {}

    def save_jobs(self, all_jobs: List[Dict]):
        """Save jobs to both CSV and JSON files"""
        try:
            # Save to JSON (complete data)
            with open(self.jobs_json, 'w') as f:
                json.dump(all_jobs, f, indent=2)
            
            # Save to CSV (for easy viewing)
            with open(self.jobs_csv, 'w', newline='', encoding='utf-8') as f:
                if all_jobs:
                    writer = csv.DictWriter(f, fieldnames=all_jobs[0].keys())
                    writer.writeheader()
                    writer.writerows(all_jobs)
            
            logger.info(f"Saved {len(all_jobs)} jobs to files")
            
        except Exception as e:
            logger.error(f"Error saving jobs: {e}")

    def update_stats(self, companies: Dict[str, str], new_jobs_count: int):
        """Update statistics file"""
        try:
            with open(self.stats_json, 'r') as f:
                stats = json.load(f)
            
            # Update stats
            stats['total_jobs_found'] = len(self.load_existing_jobs())
            stats['last_run'] = datetime.now().strftime('%Y-%m-%d %H:%M')
            stats['companies_scraped'] = {company: url for company, url in companies.items()}
            
            # Add to run history
            run_info = {
                'date': datetime.now().strftime('%Y-%m-%d %H:%M'),
                'new_jobs': new_jobs_count,
                'companies_scraped': len(companies)
            }
            stats['run_history'].append(run_info)
            
            # Keep only last 30 runs
            stats['run_history'] = stats['run_history'][-30:]
            
            with open(self.stats_json, 'w') as f:
                json.dump(stats, f, indent=2)
                
        except Exception as e:
            logger.error(f"Error updating stats: {e}")

    def run_scraper(self, companies: Dict[str, str]):
        """Main scraper function"""
        logger.info("🚀 Starting job scraper...")
        
        # Load existing jobs
        existing_jobs = self.load_existing_jobs()
        logger.info(f"Loaded {len(existing_jobs)} existing jobs")
        
        new_jobs = []
        
        for company, url in companies.items():
            logger.info(f"🔍 Scraping {company}...")
            try:
                jobs = self.scrape_company_specific(company, url)
                
                # Filter out existing jobs
                truly_new = [job for job in jobs if job['hash'] not in existing_jobs]
                new_jobs.extend(truly_new)
                
                logger.info(f"✅ {company}: {len(jobs)} PM jobs found, {len(truly_new)} new")
                
            except Exception as e:
                logger.error(f"❌ Failed to scrape {company}: {e}")
            
            # Be respectful with delays
            time.sleep(3)
        
        # Combine existing and new jobs
        all_jobs_dict = existing_jobs.copy()
        for job in new_jobs:
            all_jobs_dict[job['hash']] = job
        
        all_jobs = list(all_jobs_dict.values())
        
        # Sort by date found (newest first)
        all_jobs.sort(key=lambda x: x['date_found'], reverse=True)
        
        # Save all jobs
        self.save_jobs(all_jobs)
        
        # Update statistics
        self.update_stats(companies, len(new_jobs))
        
        logger.info(f"🎉 Scraper completed! Found {len(new_jobs)} new jobs out of {len(all_jobs)} total")
        
        return len(new_jobs), len(all_jobs)


def main():
    """Main function for GitHub Actions"""
    
    # Company URLs - ADD YOUR COMPANIES HERE
    companies = {
        "Stripe": "https://stripe.com/jobs/search",
        "Notion": "https://www.notion.com/careers?department=product-management#open-positions",
        "Figma": "https://www.figma.com/careers/#job-openings",
        "Linear": "https://linear.app/careers#join-us",
        "Vercel": "https://vercel.com/careers?function=Product",
        "OpenAI": "https://openai.com/careers/search/?c=db3c67d7-3646-4555-925b-40f30ab09f28",
        "Anthropic": "https://www.anthropic.com/jobs?team=4002057008",
        "Discord": "https://discord.com/careers#all-jobs",
        # Add more companies here...
    }
    
    try:
        # Initialize and run scraper
        scraper = JobScraper(data_dir="data")
        new_jobs, total_jobs = scraper.run_scraper(companies)
        
        # Print summary for GitHub Actions
        print(f"✅ Scraper completed successfully!")
        print(f"📊 New PM jobs found: {new_jobs}")
        print(f"📝 Total jobs tracked: {total_jobs}")
        print(f"🏢 Companies scraped: {len(companies)}")
        
        # Create a simple HTML report
        create_html_report(scraper.data_dir)
        
        return 0
        
    except Exception as e:
        print(f"❌ Scraper failed: {e}")
        logger.exception("Full error details:")
        return 1


def create_html_report(data_dir: Path):
    """Create a simple HTML report"""
    try:
        with open(data_dir / "jobs.json", 'r') as f:
            jobs = json.load(f)
        
        with open(data_dir / "stats.json", 'r') as f:
            stats = json.load(f)
        
        html_content = f"""
<!DOCTYPE html>
<html>
<head>
    <title>Job Search Dashboard</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 20px; }}
        .header {{ background: #f0f8ff; padding: 20px; border-radius: 8px; margin-bottom: 20px; }}
        .stats {{ display: flex; gap: 20px; margin-bottom: 20px; }}
        .stat-box {{ background: #fff; border: 1px solid #ddd; padding: 15px; border-radius: 8px; flex: 1; }}
        .job-card {{ border: 1px solid #ddd; padding: 15px; margin-bottom: 15px; border-radius: 8px; }}
        .job-title {{ font-weight: bold; color: #333; margin-bottom: 5px; }}
        .job-meta {{ color: #666; font-size: 0.9em; }}
        .fresh-job {{ border-left: 4px solid #4CAF50; }}
        .recent-job {{ border-left: 4px solid #FF9800; }}
        .old-job {{ border-left: 4px solid #999; }}
        a {{ color: #0066cc; text-decoration: none; }}
        a:hover {{ text-decoration: underline; }}
    </style>
</head>
<body>
    <div class="header">
        <h1>🔍 Product Management Job Dashboard</h1>
        <p>Last updated: {stats.get('last_run', 'Never')}</p>
    </div>
    
    <div class="stats">
        <div class="stat-box">
            <h3>📊 Total Jobs</h3>
            <h2>{len(jobs)}</h2>
        </div>
        <div class="stat-box">
            <h3>🏢 Companies</h3>
            <h2>{len(stats.get('companies_scraped', {}))}</h2>
        </div>
        <div class="stat-box">
            <h3>🆕 Today's New Jobs</h3>
            <h2>{len([j for j in jobs if j['date_found'].startswith(datetime.now().strftime('%Y-%m-%d'))])}</h2>
        </div>
    </div>
    
    <h2>📋 Latest Jobs</h2>
"""
        
        # Add job cards (latest 50)
        for job in jobs[:50]:
            is_today = job['date_found'] == datetime.now().strftime('%Y-%m-%d')
            
            # Determine job freshness based on date_posted
            job_class = "job-card"
            freshness_emoji = ""
            
            if job.get('date_posted') and job['date_posted'] != 'Unknown':
                try:
                    posted_date = datetime.strptime(job['date_posted'], '%Y-%m-%d')
                    days_ago = (datetime.now() - posted_date).days
                    
                    if days_ago <= 3:
                        job_class += " fresh-job"
                        freshness_emoji = "🆕"
                    elif days_ago <= 14:
                        job_class += " recent-job" 
                        freshness_emoji = "📅"
                    else:
                        job_class += " old-job"
                        freshness_emoji = "📰"
                except:
                    job_class += " job-card"
            
            elif is_today:  # Fallback to found date if posted date unavailable
                job_class += " fresh-job"
                freshness_emoji = "🆕"
            
            html_content += f"""
    <div class="{job_class}">
        <div class="job-title">
            <a href="{job['url']}" target="_blank">{job['title']}</a>
            {freshness_emoji}
        </div>
        <div class="job-meta">
            📍 {job['location']} | 🏢 {job['company']} | 
            {'📅 Posted: ' + job.get('date_posted', 'Unknown') + ' | ' if job.get('date_posted') != 'Unknown' else ''}
            🔍 Found: {job['date_found']} | Status: {job['status']}
        </div>
    </div>
"""
        
        html_content += """
</body>
</html>
"""
        
        with open(data_dir / "dashboard.html", 'w', encoding='utf-8') as f:
            f.write(html_content)
        
        print("📊 HTML dashboard created: data/dashboard.html")
        
    except Exception as e:
        logger.error(f"Error creating HTML report: {e}")


if __name__ == "__main__":
    exit(main())
