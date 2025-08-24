#!/usr/bin/env python3
"""
Automated Job Scraper for Product Management Positions
Modular parser system for different ATS platforms
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
from abc import ABC, abstractmethod

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class BaseParser(ABC):
    """Abstract base class for job parsers"""
    
    def __init__(self):
        self.product_mgmt_keywords = [
            'product manager', 'product management', 'senior product manager',
            'principal product manager', 'product lead', 'product owner',
            'director of product', 'head of product', 'vp product', 'vp of product',
            'group product manager', 'staff product manager', 'product',
            'pm ', ' pm', 'product strategist', 'product marketing manager'
        ]
    
    @abstractmethod
    def can_parse(self, url: str) -> bool:
        """Check if this parser can handle the given URL"""
        pass
    
    @abstractmethod
    def parse_jobs(self, company: str, url: str) -> List[Dict]:
        """Parse jobs from the given URL"""
        pass
    
    def is_product_management_job(self, title: str, url: str = "", description: str = "") -> bool:
        """Check if job title/description matches Product Management criteria"""
        # Filter out non-job URLs
        excluded_url_patterns = [
            '/product-managers/', '/about-product', '/what-is-product', '/product-management-guide',
            '/blog/', '/resources/', '/tools/', '/templates/', '/product-development/',
            '/product/', '/customers/', '/features/', '/stories/', '/case-studies/',
            '/solutions/', '/pricing/', 'forbes.com', 'techcrunch.com', 'medium.com',
            '/company/', '/about/', '/contact/', '/support/', '.pdf', '.jpg', '.png', '.gif'
        ]
        
        for pattern in excluded_url_patterns:
            if pattern in url.lower():
                return False
        
        # Only consider URLs that look like job listings
        job_url_patterns = [
            '/jobs/', '/careers/', '/job/', '/career/', '/positions/', '/listing/',
            '/opening/', '/vacancy/', '/role/', 'greenhouse.io', 'lever.co', 
            'workday', 'ashbyhq.com'
        ]
        
        if url and not any(pattern in url.lower() for pattern in job_url_patterns):
            return False
        
        title_lower = title.lower()
        
        # Must have Product Manager/PM in the title specifically
        # More flexible matching to catch variations
        pm_patterns = [
            'product manager', 'product management', 'pm,', '- pm', '(pm)', 
            'senior pm', 'principal pm', 'staff pm', 'group pm',
            'director of product', 'director, product', 'director product',
            'head of product', 'vp product', 'vp of product', 'product lead',
            'product owner', 'associate pm', 'junior pm', 'lead pm',
            'product management', 'pm -', 'pm lead', 'pm director'
        ]
        
        has_pm_in_title = any(pattern in title_lower for pattern in pm_patterns)
        
        # Also check for "PM" as a standalone word (not part of another word)
        import re
        if not has_pm_in_title:
            # Check for PM as a word boundary (e.g., "PM, ChatGPT" or "ChatGPT PM")
            pm_word_pattern = r'\bpm\b'
            if re.search(pm_word_pattern, title_lower):
                has_pm_in_title = True
        
        # If it doesn't have PM in title, skip it
        if not has_pm_in_title:
            return False
        
        # Exclude non-PM roles even if they have "product" in title
        # Be more specific with exclusions to avoid false negatives
        exclude_patterns = [
            'engineer', 'engineering manager', 'frontend', 'backend', 'developer',
            'designer', 'design', 'marketing manager', 'sales', 'customer success',
            'support', 'data analyst', 'intern', 'qa', 'test', 'devops', 
            'data scientist', 'recruiter', 'account executive', 'content writer',
            'researcher', 'research scientist', 'technical writer', 'program manager',
            'project manager', 'operations manager', 'business development', 
            'partnerships manager', 'growth marketing', 'strategist', 'evangelist'
        ]
        
        # Check if any exclude keywords are prominently in the title
        for pattern in exclude_patterns:
            if pattern in title_lower:
                # Make exception for "Product Marketing Manager" which is sometimes grouped with PM
                if pattern == 'marketing' and 'product marketing manager' in title_lower:
                    continue
                return False
        
        return True

    def create_job_hash(self, job: Dict) -> str:
        """Create unique hash for job to detect duplicates"""
        unique_string = f"{job['company']}{job['title']}{job['location']}"
        return hashlib.md5(unique_string.encode()).hexdigest()[:12]


class AshbyParser(BaseParser):
    """Parser for Ashby-powered job boards (OpenAI, etc.)"""
    
    def can_parse(self, url: str) -> bool:
        return 'ashbyhq.com' in url
    
    def parse_jobs(self, company: str, url: str) -> List[Dict]:
        """Parse jobs from Ashby GraphQL API"""
        jobs = []
        
        try:
            # Extract organization name from URL
            # https://jobs.ashbyhq.com/openai/?departmentId=... -> openai
            org_match = re.search(r'ashbyhq\.com/([^/?]+)', url)
            if not org_match:
                logger.error(f"Could not extract organization from URL: {url}")
                return jobs
            
            org_name = org_match.group(1)
            
            # Make GraphQL request to Ashby API
            api_url = "https://jobs.ashbyhq.com/api/non-user-graphql?op=ApiJobBoardWithTeams"
            
            query = """
            query ApiJobBoardWithTeams($organizationHostedJobsPageName: String!) {
              jobBoard: jobBoardWithTeams(
                organizationHostedJobsPageName: $organizationHostedJobsPageName
              ) {
                teams {
                  id
                  name
                  parentTeamId
                  __typename
                }
                jobPostings {
                  id
                  title
                  teamId
                  locationId
                  locationName
                  workplaceType
                  employmentType
                  secondaryLocations {
                    locationId
                    locationName
                    __typename
                  }
                  compensationTierSummary
                  __typename
                }
                __typename
              }
            }
            """
            
            payload = {
                "operationName": "ApiJobBoardWithTeams",
                "variables": {"organizationHostedJobsPageName": org_name},
                "query": query
            }
            
            headers = {
                'Content-Type': 'application/json',
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'apollographql-client-name': 'frontend_non_user',
                'apollographql-client-version': '0.1.0',
                'Accept': '*/*',
                'Origin': 'https://jobs.ashbyhq.com',
                'Referer': url
            }
            
            logger.info(f"Making GraphQL request to Ashby for {org_name}")
            response = requests.post(api_url, json=payload, headers=headers, timeout=30)
            response.raise_for_status()
            
            data = response.json()
            
            if 'data' not in data or not data['data'].get('jobBoard'):
                logger.error(f"No job board data found in response: {data}")
                return jobs
            
            job_board = data['data']['jobBoard']
            job_postings = job_board.get('jobPostings', [])
            teams = job_board.get('teams', [])
            
            # Create team lookup
            team_lookup = {team['id']: team['name'] for team in teams}
            
            logger.info(f"Found {len(job_postings)} total jobs, {len(teams)} teams")
            
            # Define Product Management team IDs for different companies
            pm_team_ids = {
                'openai': ['db3c67d7-3646-4555-925b-40f30ab09f28'],  # Product Management team
                # Add other companies' PM team IDs as needed
            }
            
            # Filter for Product Manager jobs
            for job in job_postings:
                title = job.get('title', '')
                team_id = job.get('teamId', '')
                team_name = team_lookup.get(team_id, '').lower()
                
                # Check if it's a Product Manager role - strict title matching only
                is_pm_by_title = self.is_product_management_job(title, "", "")
                
                # Skip jobs that don't have Product Manager in the title
                if is_pm_by_title:
                    
                    # Build location string
                    location = job.get('locationName', 'Unknown')
                    secondary_locations = job.get('secondaryLocations', [])
                    if secondary_locations:
                        additional_locs = [loc.get('locationName', '') for loc in secondary_locations 
                                         if loc.get('locationName')]
                        if additional_locs:
                            location += f" (+ {', '.join(additional_locs)})"
                    
                    # Add workplace type
                    workplace_type = job.get('workplaceType')
                    if workplace_type and workplace_type not in ['null', None, '']:
                        location += f" - {workplace_type}"
                    
                    # Construct job URL
                    job_url = f"https://jobs.ashbyhq.com/{org_name}/{job.get('id', '')}"
                    
                    job_data = {
                        'company': company,
                        'title': title,
                        'location': location,
                        'url': job_url,
                        'date_posted': 'Unknown',  # Ashby doesn't expose posting dates in this API
                        'date_found': datetime.now().strftime('%Y-%m-%d'),
                        'status': 'active'
                    }
                    job_data['hash'] = self.create_job_hash(job_data)
                    
                    jobs.append(job_data)
                    team_info = team_lookup.get(team_id, 'Unknown team')
                    logger.info(f"✅ Found PM job: {title} ({team_info})")
            
            logger.info(f"📊 Total PM jobs found at {company}: {len(jobs)}")
            
        except Exception as e:
            logger.error(f"❌ Error parsing Ashby jobs from {company}: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
        
        return jobs


class GreenhouseParser(BaseParser):
    """Parser for Greenhouse-powered job boards (Anthropic, etc.)"""
    
    def can_parse(self, url: str) -> bool:
        return 'greenhouse.io' in url
    
    def parse_jobs(self, company: str, url: str) -> List[Dict]:
        """Parse jobs from Greenhouse job boards"""
        jobs = []
        
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
            
            logger.info(f"Fetching Greenhouse board: {url}")
            response = requests.get(url, headers=headers, timeout=30)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Greenhouse-specific selectors
            job_selectors = [
                '.opening', '.job-post', '.position', '[data-job-id]',
                '.job-listing', '.career-listing', '.opening-item'
            ]
            
            job_elements = []
            for selector in job_selectors:
                elements = soup.select(selector)
                if elements:
                    job_elements = elements
                    logger.info(f"Found {len(elements)} jobs using selector: {selector}")
                    break
            
            # If no elements found, try link approach
            if not job_elements:
                all_links = soup.find_all('a', href=True)
                for link in all_links:
                    text = link.get_text().lower()
                    if any(word in text for word in ['manager', 'product', 'director']):
                        job_elements.append(link)
                logger.info(f"Found {len(job_elements)} potential job links")
            
            for element in job_elements:
                try:
                    # Extract title
                    title_elem = element.find(['h3', 'h4', 'a']) or element
                    title = title_elem.get_text(strip=True)
                    
                    if not self.is_product_management_job(title):
                        continue
                    
                    # Extract location
                    location_elem = element.find(class_=re.compile(r'location', re.I))
                    location = location_elem.get_text(strip=True) if location_elem else "Unknown"
                    
                    # Extract URL
                    link_elem = element.find('a', href=True) if element.name != 'a' else element
                    job_url = ""
                    if link_elem and link_elem.get('href'):
                        job_url = link_elem.get('href')
                        if not job_url.startswith('http'):
                            from urllib.parse import urljoin
                            job_url = urljoin(url, job_url)
                    
                    job_data = {
                        'company': company,
                        'title': title,
                        'location': location,
                        'url': job_url or url,
                        'date_posted': 'Unknown',
                        'date_found': datetime.now().strftime('%Y-%m-%d'),
                        'status': 'active'
                    }
                    job_data['hash'] = self.create_job_hash(job_data)
                    
                    jobs.append(job_data)
                    logger.info(f"✅ Found Greenhouse PM job: {title}")
                    
                except Exception as e:
                    logger.debug(f"Error parsing Greenhouse job element: {e}")
                    continue
            
        except Exception as e:
            logger.error(f"❌ Error parsing Greenhouse jobs from {company}: {e}")
        
        return jobs


class GenericParser(BaseParser):
    """Generic parser for standard websites"""
    
    def can_parse(self, url: str) -> bool:
        # Default parser - can handle any URL
        return True
    
    def parse_date_text(self, date_text: str) -> str:
        """Parse various date formats into standardized format"""
        if not date_text:
            return None
            
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

    def extract_date_posted(self, element) -> str:
        """Try to extract when the job was posted"""
        element_text = element.get_text()
        
        # Common date patterns
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
    
    def parse_jobs(self, company: str, url: str) -> List[Dict]:
        """Parse jobs using BeautifulSoup (original logic)"""
        jobs = []
        
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
            
            logger.info(f"Fetching {url}")
            response = requests.get(url, headers=headers, timeout=30)
            response.raise_for_status()
            logger.info(f"Got response: {response.status_code}, Content length: {len(response.text)} chars")
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Common selectors for job listings
            job_selectors = [
                '.JobsListings__link',  # Stripe specific
                'a[href*="/jobs/listing/"]',  # Stripe URL pattern
                '.job-listing', '.job-item', '.position', '.job-card', '.job-post',
                '[data-job-id]', '.job', '.career-item', '.opening', '.vacancy',
                '.role', '.position-item', '.job-opportunity',
                '.OpenRoles_role-heading__sBi1o',  # Anthropic
                '.JobCard', '.JobListing',  # Generic
                '.VfPpkd-rymPhb',  # Google
                '[data-testid*="job"]',  # Various modern sites
                '.career-position', '.posting', '.role-card',
                'a[data-js-target-list*="JobsListings"]',  # Stripe data attribute
                'a[data-analytics-category="Links"]'  # Stripe analytics
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
                logger.info(f"Found {len(all_links)} total links on page")
                job_elements = []
                
                for link in all_links:
                    href = link.get('href', '')
                    text = link.get_text().lower()
                    
                    # Check if it's a job listing URL or has job-related text
                    is_job_url = any(pattern in href for pattern in ['/jobs/listing/', '/careers/', '/job/', '/opening/'])
                    has_job_text = any(word in text for word in ['manager', 'product', 'director', 'lead', 'senior', 'principal', 'staff'])
                    
                    if is_job_url or has_job_text:
                        job_elements.append(link)
                
                logger.info(f"Found {len(job_elements)} potential job links")
            
            # Parse job elements
            parsed_count = 0
            for element in job_elements[:50]:  # Limit to prevent overload
                try:
                    # Extract job title
                    title = ""
                    
                    # For Stripe and similar sites, the link text itself is often the title
                    if element.name == 'a':
                        title = element.get_text(strip=True)
                    
                    # If not found, try other methods
                    if not title or len(title) < 5:
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
                        logger.debug(f"Skipping generic title: '{title}'")
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
                    
                    # Extract description (for filtering only)
                    desc_elem = element.find(class_=re.compile(r'description|summary|excerpt|snippet', re.I))
                    description = ""
                    if desc_elem:
                        description = desc_elem.get_text(strip=True)[:300]
                    
                    # Extract date posted
                    date_posted = self.extract_date_posted(element)
                    
                    # Check if it's a Product Management role
                    if self.is_product_management_job(title, job_url, description):
                        job_data = {
                            'company': company,
                            'title': title,
                            'location': location,
                            'url': job_url or url,
                            'date_posted': date_posted,
                            'date_found': datetime.now().strftime('%Y-%m-%d'),
                            'status': 'active'
                        }
                        job_data['hash'] = self.create_job_hash(job_data)
                        
                        jobs.append(job_data)
                        parsed_count += 1
                        logger.info(f"✅ Found PM job: {title} at {location}")
                        
                except Exception as e:
                    logger.debug(f"Error parsing job element: {e}")
                    continue
            
            logger.info(f"Successfully parsed {parsed_count} PM jobs from {len(job_elements)} elements")
                    
        except Exception as e:
            logger.error(f"❌ Error parsing generic jobs from {company}: {e}")
            
        return jobs


class JobScraper:
    def __init__(self, data_dir: str = "data"):
        """Initialize the job scraper with local file storage"""
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(exist_ok=True)
        
        # File paths
        self.jobs_csv = self.data_dir / "jobs.csv"
        self.jobs_json = self.data_dir / "jobs.json"
        self.stats_json = self.data_dir / "stats.json"
        
        # Initialize parsers (order matters - most specific first)
        self.parsers = [
            AshbyParser(),
            GreenhouseParser(),
            GenericParser()  # Always last as fallback
        ]
        
        self.initialize_files()
    
    def get_parser_for_url(self, url: str) -> BaseParser:
        """Get the appropriate parser for a given URL"""
        for parser in self.parsers:
            if parser.can_parse(url):
                logger.info(f"Using {parser.__class__.__name__} for {url}")
                return parser
        
        # Should never reach here due to GenericParser fallback
        return self.parsers[-1]
    
    def scrape_company_jobs(self, company: str, url: str) -> List[Dict]:
        """Scrape jobs from a specific company using appropriate parser"""
        parser = self.get_parser_for_url(url)
        return parser.parse_jobs(company, url)
    
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
            logger.info(f"✅ Saved {len(all_jobs)} jobs to JSON")
            
            # Save to CSV (for easy viewing)
            with open(self.jobs_csv, 'w', newline='', encoding='utf-8') as f:
                if all_jobs:
                    writer = csv.DictWriter(f, fieldnames=all_jobs[0].keys())
                    writer.writeheader()
                    writer.writerows(all_jobs)
                    logger.info(f"✅ Saved {len(all_jobs)} jobs to CSV")
            
        except Exception as e:
            logger.error(f"❌ Error saving jobs: {e}")
    
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
        logger.info("🚀 Starting modular job scraper...")
        
        # Load existing jobs
        existing_jobs = self.load_existing_jobs()
        logger.info(f"Loaded {len(existing_jobs)} existing jobs")
        
        new_jobs = []
        
        for company, url in companies.items():
            logger.info(f"🔍 Scraping {company}...")
            try:
                jobs = self.scrape_company_jobs(company, url)
                
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
        
        # Create HTML report
        create_html_report(self.data_dir)
        
        logger.info(f"🎉 Scraper completed! Found {len(new_jobs)} new jobs out of {len(all_jobs)} total")
        
        return len(new_jobs), len(all_jobs)


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
        .filters {{ background: #f9f9f9; padding: 15px; border-radius: 8px; margin-bottom: 20px; }}
        .filter-group {{ display: flex; align-items: center; gap: 10px; margin-bottom: 10px; }}
        select {{ padding: 8px 12px; border: 1px solid #ddd; border-radius: 4px; font-size: 14px; }}
        .job-card {{ border: 1px solid #ddd; padding: 15px; margin-bottom: 15px; border-radius: 8px; transition: opacity 0.3s; }}
        .job-card.hidden {{ display: none; }}
        .job-title {{ font-weight: bold; color: #333; margin-bottom: 5px; }}
        .job-meta {{ color: #666; font-size: 0.9em; }}
        .fresh-job {{ border-left: 4px solid #4CAF50; }}
        .recent-job {{ border-left: 4px solid #FF9800; }}
        .old-job {{ border-left: 4px solid #999; }}
        a {{ color: #0066cc; text-decoration: none; }}
        a:hover {{ text-decoration: underline; }}
        .results-info {{ color: #666; font-style: italic; margin-bottom: 15px; }}
    </style>
</head>
<body>
    <div class="header">
        <h1>🔎 Product Management Job Dashboard</h1>
        <p>Last updated: {stats.get('last_run', 'Never')}</p>
    </div>
    
    <div class="stats">
        <div class="stat-box">
            <h3>📊 Total Jobs</h3>
            <h2 id="total-jobs">{len(jobs)}</h2>
        </div>
        <div class="stat-box">
            <h3>🏢 Companies</h3>
            <h2>{len(stats.get('companies_scraped', {}))}</h2>
        </div>
        <div class="stat-box">
            <h3>🆕 Today's New Jobs</h3>
            <h2>{len([j for j in jobs if j['date_found'] == datetime.now().strftime('%Y-%m-%d')])}</h2>
        </div>
    </div>
    
    <div class="filters">
        <div class="filter-group">
            <label for="company-filter"><strong>🏢 Filter by Company:</strong></label>
            <select id="company-filter" onchange="filterJobs()">
                <option value="all">All Companies</option>"""

        # Add company options
        companies = sorted(set([job['company'] for job in jobs]))
        for company in companies:
            company_count = len([job for job in jobs if job['company'] == company])
            html_content += f'<option value="{company}">{company} ({company_count})</option>'

        html_content += f"""
            </select>
        </div>
        <div class="results-info" id="results-info">Showing all {len(jobs)} jobs</div>
    </div>
    
    <h2>📋 Latest Jobs</h2>
    <div id="jobs-container">
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
    <div class="{job_class}" data-company="{job['company']}">
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
    </div>

    <script>
        function filterJobs() {
            const selectedCompany = document.getElementById('company-filter').value;
            const jobCards = document.querySelectorAll('.job-card');
            const resultsInfo = document.getElementById('results-info');
            const totalJobsCounter = document.getElementById('total-jobs');
            
            let visibleCount = 0;
            
            jobCards.forEach(card => {
                const cardCompany = card.getAttribute('data-company');
                
                if (selectedCompany === 'all' || cardCompany === selectedCompany) {
                    card.classList.remove('hidden');
                    visibleCount++;
                } else {
                    card.classList.add('hidden');
                }
            });
            
            // Update results info
            if (selectedCompany === 'all') {
                resultsInfo.textContent = `Showing all ${visibleCount} jobs`;
            } else {
                resultsInfo.textContent = `Showing ${visibleCount} jobs from ${selectedCompany}`;
            }
            
            // Update total counter in stats
            totalJobsCounter.textContent = visibleCount;
        }
        
        // Initialize filter on page load
        document.addEventListener('DOMContentLoaded', function() {
            filterJobs();
        });
    </script>
</body>
</html>
"""
        
        with open(data_dir / "dashboard.html", 'w', encoding='utf-8') as f:
            f.write(html_content)
        
        logger.info("📊 HTML dashboard created: data/dashboard.html")
        
    except Exception as e:
        logger.error(f"Error creating HTML report: {e}")


def main():
    """Main function"""
    
    # Company URLs with parser auto-detection
    companies = {
        "Stripe": "https://stripe.com/jobs/search?query=product+manager",
        "Notion": "https://www.notion.com/careers?department=product-management#open-positions",
        "Figma": "https://www.figma.com/careers/#job-openings",
        "Linear": "https://linear.app/careers#join-us",
        "Vercel": "https://vercel.com/careers?function=Product",
        "OpenAI": "https://jobs.ashbyhq.com/openai/?departmentId=db3c67d7-3646-4555-925b-40f30ab09f28",
        "Anthropic": "https://job-boards.greenhouse.io/anthropic/?departments%5B%5D=4002057008",
        "Discord": "https://discord.com/careers#all-jobs",
        "Google": "https://www.google.com/about/careers/applications/jobs/results?target_level=DIRECTOR_PLUS&target_level=ADVANCED&q=product%20manager",
    }
    
    try:
        scraper = JobScraper(data_dir="data")
        new_jobs, total_jobs = scraper.run_scraper(companies)
        
        print(f"✅ Scraper completed successfully!")
        print(f"📊 New PM jobs found: {new_jobs}")
        print(f"🔍 Total jobs tracked: {total_jobs}")
        print(f"🏢 Companies scraped: {len(companies)}")
        
        return 0
        
    except Exception as e:
        print(f"❌ Scraper failed: {e}")
        logger.exception("Full error details:")
        return 1


if __name__ == "__main__":
    exit(main())
