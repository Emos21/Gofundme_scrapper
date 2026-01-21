"""
Playwright-based scraper for JavaScript-rendered GoFundMe pages.
Provides more reliable scraping than basic requests/BeautifulSoup.
"""

import asyncio
import re
from datetime import date
from typing import Optional, Dict, Any

try:
    from playwright.async_api import async_playwright
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False


def remove_duplicate_words(text: str) -> str:
    """Remove duplicate words from text while preserving order."""
    words = text.split()
    seen = set()
    result = []
    for word in words:
        if word.lower() not in seen:
            seen.add(word.lower())
            result.append(word)
    return ' '.join(result)


def parse_amount(amount_str: str) -> Optional[float]:
    """Parse amount string to float."""
    if not amount_str or amount_str == 'N/A':
        return None
    cleaned = re.sub(r'[^\d.]', '', amount_str)
    try:
        return float(cleaned)
    except ValueError:
        return None


async def scrape_campaign_playwright(url: str) -> Dict[str, Any]:
    """
    Scrape a GoFundMe campaign using Playwright.
    This handles JavaScript-rendered content better than requests.
    """
    if not PLAYWRIGHT_AVAILABLE:
        return {"error": "Playwright not installed. Run: pip install playwright && playwright install chromium", "url": url}
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        )
        page = await context.new_page()
        
        try:
            # Navigate to the page
            await page.goto(url, wait_until='networkidle', timeout=30000)
            
            # Wait for key elements to load
            await page.wait_for_selector('h1', timeout=10000)
            
            # Extract title
            title_elem = await page.query_selector('h1.p-campaign-title, h1[class*="campaign-title"]')
            title = await title_elem.inner_text() if title_elem else 'Title not found'
            title = remove_duplicate_words(title.strip())
            
            # Extract description
            desc_elems = await page.query_selector_all('div[class*="campaign-description"]')
            description = ''
            for elem in desc_elems:
                text = await elem.inner_text()
                description += text.strip() + '\n'
            description = remove_duplicate_words(description.strip()) or 'Description not found'
            
            # Extract amount raised
            amount_elem = await page.query_selector('div[class*="progress-meter"] div[class*="largeType"], .hrt-disp-inline')
            amount_raised = await amount_elem.inner_text() if amount_elem else 'N/A'
            
            # Extract goal
            goal_elem = await page.query_selector('span[class*="hrt-text-gray"]')
            goal_text = await goal_elem.inner_text() if goal_elem else ''
            goal_match = re.search(r'($?[\d,]+)', goal_text)
            goal_amount = goal_match.group() if goal_match else 'N/A'
            
            # Extract organizer
            organizer_elem = await page.query_selector('a[class*="campaign-byline"], .campaign-organizer')
            organizer = await organizer_elem.inner_text() if organizer_elem else None
            
            # Extract location
            location_elem = await page.query_selector('span[class*="location"], div[class*="location"]')
            location = await location_elem.inner_text() if location_elem else None
            
            # Extract donor count
            donor_count_elem = await page.query_selector('span[class*="donor-count"], div[class*="donations-count"]')
            donor_count_text = await donor_count_elem.inner_text() if donor_count_elem else '0'
            donor_count_match = re.search(r'(\d+)', donor_count_text.replace(',', ''))
            donor_count = int(donor_count_match.group()) if donor_count_match else 0
            
            # Extract recent donations
            donations = []
            donation_elems = await page.query_selector_all('div[class*="avatar-lockup-content"]')
            for elem in donation_elems[:10]:
                name_elem = await elem.query_selector('div')
                name = await name_elem.inner_text() if name_elem else 'Anonymous'
                amount_elem = await elem.query_selector('span[class*="font-bold"]')
                amount = await amount_elem.inner_text() if amount_elem else 'N/A'
                donations.append({'name': name.strip(), 'amount': amount.strip()})
            
            # Extract share count if available
            share_elem = await page.query_selector('span[class*="share-count"]')
            share_count_text = await share_elem.inner_text() if share_elem else '0'
            share_count_match = re.search(r'(\d+)', share_count_text.replace(',', ''))
            share_count = int(share_count_match.group()) if share_count_match else 0
            
            await browser.close()
            
            return {
                'title': title,
                'statement': description[:500] + '...' if len(description) > 500 else description,
                'full_statement': description,
                'amount_raised': amount_raised.strip(),
                'goal_amount': goal_amount,
                'organizer': organizer,
                'location': location,
                'donor_count': donor_count,
                'share_count': share_count,
                'donations': donations,
                'url': url,
                'date_scraped': str(date.today()),
                'scraper': 'playwright'
            }
            
        except Exception as e:
            await browser.close()
            return {"error": f"Playwright error: {str(e)}", "url": url}


def scrape_campaign_sync(url: str) -> Dict[str, Any]:
    """Synchronous wrapper for the async Playwright scraper."""
    return asyncio.run(scrape_campaign_playwright(url))


async def scrape_multiple_campaigns(urls: list) -> list:
    """Scrape multiple campaigns concurrently."""
    tasks = [scrape_campaign_playwright(url) for url in urls]
    return await asyncio.gather(*tasks)


def check_playwright_installed() -> bool:
    """Check if Playwright is installed and ready."""
    return PLAYWRIGHT_AVAILABLE
