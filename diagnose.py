#!/usr/bin/env python3
"""
Analyze what's actually in the OpenAI Ashby page
"""
import requests
from bs4 import BeautifulSoup
import re

def analyze_ashby_page():
    """Analyze the OpenAI Ashby page content"""
    url = "https://jobs.ashbyhq.com/openai/?departmentId=db3c67d7-3646-4555-925b-40f30ab09f28"
    
    print(f"🔍 ASHBY PAGE ANALYSIS")
    print(f"URL: {url}")
    print(f"="*60)
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=30)
        print(f"📡 Status: {response.status_code}")
        print(f"📄 Content length: {len(response.text):,} chars")
        
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Check what's actually in the page
        print(f"\n📝 Page structure analysis:")
        
        # Count different element types
        elements_count = {
            'div': len(soup.find_all('div')),
            'a': len(soup.find_all('a')),
            'script': len(soup.find_all('script')),
            'h1': len(soup.find_all('h1')),
            'h2': len(soup.find_all('h2')),
            'h3': len(soup.find_all('h3')),
            'span': len(soup.find_all('span')),
            'p': len(soup.find_all('p'))
        }
        
        for element, count in elements_count.items():
            print(f"   {element}: {count}")
        
        # Check if it's a single-page app
        print(f"\n⚡ JavaScript analysis:")
        scripts = soup.find_all('script')
        
        # Look for Next.js or React indicators
        js_frameworks = []
        for script in scripts:
            script_content = script.get_text() if script.string else ""
            if '__NEXT_DATA__' in script_content:
                js_frameworks.append('Next.js')
            if 'react' in script_content.lower():
                js_frameworks.append('React')
            if '_app' in script_content or 'chunks' in script_content:
                js_frameworks.append('SPA')
        
        print(f"Detected frameworks: {list(set(js_frameworks))}")
        
        # Check for job data in script tags (Next.js often embeds data)
        print(f"\n🔍 Looking for job data in scripts:")
        job_data_found = False
        
        for script in scripts:
            script_text = script.get_text() if script.string else ""
            if 'product' in script_text.lower() and ('manager' in script_text.lower() or 'job' in script_text.lower()):
                job_data_found = True
                print(f"✅ Found job-related data in script tag")
                # Extract a sample
                lines = script_text.split('\n')
                for line in lines:
                    if 'product' in line.lower() and 'manager' in line.lower():
                        print(f"   Sample: {line.strip()[:100]}...")
                        break
                break
        
        if not job_data_found:
            print(f"❌ No job data found in script tags")
        
        # Check the raw HTML for any obvious job titles
        print(f"\n🎯 Raw HTML text search:")
        raw_text = response.text
        
        # Look for job titles that might be embedded
        job_title_patterns = [
            r'product\s+manager[^"]*',
            r'senior\s+product[^"]*',
            r'principal\s+product[^"]*',
            r'director[^"]*product[^"]*'
        ]
        
        for pattern in job_title_patterns:
            matches = re.findall(pattern, raw_text, re.I)
            if matches:
                print(f"✅ Pattern '{pattern}' found {len(matches)} times:")
                for match in matches[:3]:
                    print(f"   • {match}")
            else:
                print(f"❌ Pattern '{pattern}': no matches")
        
        # Check if there's an API endpoint we can try
        print(f"\n🔌 Looking for API patterns:")
        api_indicators = ['/api/jobs', '/api/postings', 'ashby.com/api', 'fetch(']
        
        for indicator in api_indicators:
            if indicator in raw_text:
                print(f"✅ Found API indicator: {indicator}")
            else:
                print(f"❌ No {indicator}")
        
        # Save a sample of the HTML for manual inspection
        with open('ashby_sample.html', 'w', encoding='utf-8') as f:
            f.write(raw_text[:50000])  # First 50k chars
        print(f"\n💾 Saved first 50k chars to ashby_sample.html")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        print(traceback.format_exc())

if __name__ == "__main__":
    analyze_ashby_page()
