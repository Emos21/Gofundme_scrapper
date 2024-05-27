import requests
from bs4 import BeautifulSoup
import re

def get_gofundme_urls(seed_url, max_pages=10):
    visited_urls = set()
    urls_to_visit = [seed_url]
    gofundme_urls = set()

    urls_scraped = 0  # Counter to keep track of scraped URLs

    while urls_to_visit and urls_scraped < max_pages:
        current_url = urls_to_visit.pop(0)

        if current_url in visited_urls:
            continue

        try:
            print(f"Scraping: {current_url}")
            response = requests.get(current_url)
            visited_urls.add(current_url)

            if response.status_code == 200:
                soup = BeautifulSoup(response.text, 'html.parser')
                links = soup.find_all('a', href=True)
                
                for link in links:
                    url = link['href']
                    if re.match(r'^https://www.gofundme.com/f/.*$', url):
                        gofundme_urls.add(url)
                        urls_scraped += 1  # Increment the counter
                        print(f"Found GoFundMe URL: {url} ({urls_scraped}/{max_pages})")  # Print the count
                    elif url.startswith('/') and not url.startswith('//'):
                        url = f"https://www.gofundme.com{url}"
                        urls_to_visit.append(url)
        
        except Exception as e:
            print(f"Error accessing {current_url}: {e}")
    
    if not urls_to_visit:
        print("No more pages to scrape.")

    # Write URLs to a text file
    with open('newurls.txt', 'w') as f:
        for url in gofundme_urls:
            f.write("%s\n" % url)

    return list(gofundme_urls)

# Example usage:
seed_url = 'https://www.gofundme.com/discover'
gofundme_urls = get_gofundme_urls(seed_url, max_pages=100)  # Increase max_pages to scrape more URLs
print("URLs saved to newurls.txt")
