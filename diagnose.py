#!/usr/bin/env python3
"""
Diagnostic tool for Anthropic and Stripe specifically
"""
import requests
from bs4 import BeautifulSoup
import re

def diagnose_anthropic():
    """Diagnose Anthropic job page structure"""
    url = "https://www.anthropic.com/jobs"
    
    print(f"🔍 ANTHROPIC DIAGNOSIS")
    print(f"URL: {url}")
    print(f"="*50)
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=30)
        print(f"📡 Status: {response.status_code}")
        print(f"📄 Content length: {len(response.text):,} chars")
        
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Look for the specific class you mentioned
        print(f"\n🎯 Looking for OpenRoles_role-heading__sBi1o:")
        role_headings = soup.find_all('h2', class_=re.compile(r'OpenRoles_role-heading', re.I))
        print(f"Found {len(role_headings)} role headings")
        
        for i, heading in enumerate(role_headings):
            title = heading.get_text(strip=True)
            print(f"   {i+1}: '{title}'")
            
            # Look for the apply link
            parent = heading.find_parent()
            if parent:
                apply_link = parent.find('a', href=re.compile(r'greenhouse\.io'))
                if apply_link:
                    href = apply_link.get('href')
                    print(f"      Apply URL: {href}")
        
        # Also check for any h2 elements
        print(f"\n📋 All h2 elements:")
        all_h2 = soup.find_all('h2')
        print(f"Found {len(all_h2)} h2 elements")
        
        for i, h2 in enumerate(all_h2[:10]):
            title = h2.get_text(strip=True)
            classes = h2.get('class', [])
            print(f"   {i+1}: '{title}' (classes: {classes})")
        
        # Check for greenhouse links
        print(f"\n🌿 Greenhouse links:")
        greenhouse_links = soup.find_all('a', href=re.compile(r'greenhouse\.io'))
        print(f"Found {len(greenhouse_links)} greenhouse links")
        
        for i, link in enumerate(greenhouse_links[:5]):
            text = link.get_text(strip=True)
            href = link.get('href')
            print(f"   {i+1}: '{text}' -> {href}")
        
        # Check if page uses JavaScript heavily
        script_tags = soup.find_all('script')
        print(f"\n⚡ JavaScript info:")
        print(f"Script tags: {len(script_tags)}")
        
        js_indicators = ['react', 'vue', 'angular', '__NEXT_DATA__', 'window.__']
        page_text = response.text.lower()
        js_found = [indicator for indicator in js_indicators if indicator in page_text]
        if js_found:
            print(f"JS frameworks detected: {js_found}")
        
    except Exception as e:
        print(f"❌ Error: {e}")

def diagnose_stripe():
    """Diagnose Stripe job page structure"""
    url = "https://stripe.com/jobs/search"
    
    print(f"\n🔍 STRIPE DIAGNOSIS")
    print(f"URL: {url}")
    print(f"="*50)
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=30)
        print(f"📡 Status: {response.status_code}")
        print(f"📄 Content length: {len(response.text):,} chars")
        
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Check for job-related elements
        print(f"\n🎯 Testing Stripe-specific selectors:")
        stripe_selectors = [
            '.JobCard', '.job-card', '.JobListing', '.job-listing',
            '.JobSearchResult', '.search-result', '.position',
            '[data-testid*="job"]', '[class*="Job"]'
        ]
        
        for selector in stripe_selectors:
            elements = soup.select(selector)
            if elements:
                print(f"✅ {selector}: {len(elements)} elements")
                for i, elem in enumerate(elements[:2]):
                    text = elem.get_text(strip=True)[:100]
                    print(f"   Sample {i+1}: {text}...")
            else:
                print(f"❌ {selector}: 0 elements")
        
        # Look for any links containing "product"
        print(f"\n🔗 Links containing 'product':")
        all_links = soup.find_all('a', href=True)
        product_links = []
        
        for link in all_links:
            text = link.get_text().lower()
            href = link.get('href', '')
            if 'product' in text or 'product' in href:
                product_links.append((text.strip()[:80], href))
        
        print(f"Found {len(product_links)} product-related links")
        for i, (text, href) in enumerate(product_links[:5]):
            print(f"   {i+1}: '{text}' -> {href}")
        
        # Check if it's a search results page that needs form submission
        forms = soup.find_all('form')
        print(f"\n📝 Forms found: {len(forms)}")
        if forms:
            print("This might be a search page that requires form submission")
        
        # Check for any obvious job titles in the text
        page_text = response.text
        if 'product manager' in page_text.lower():
            print(f"\n✅ 'Product Manager' text found in page content")
            # Find context around it
            import re
            matches = re.finditer(r'.{0,50}product manager.{0,50}', page_text, re.I)
            for i, match in enumerate(list(matches)[:3]):
                print(f"   Context {i+1}: ...{match.group()}...")
        else:
            print(f"\n❌ 'Product Manager' text NOT found in page")
            
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    diagnose_anthropic()
    print("\n" + "="*80 + "\n")
    diagnose_stripe()
