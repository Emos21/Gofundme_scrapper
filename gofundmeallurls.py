import requests
from bs4 import BeautifulSoup

def extract_gofundme_urls(url):
    response = requests.get(url)
    if response.status_code == 200:
        soup = BeautifulSoup(response.content, 'html.parser')
        links = soup.find_all('a', href=True)
        gofundme_urls = [link['href'] for link in links if 'gofundme.com' in link['href']]
        return gofundme_urls
    else:
        print("Failed to fetch the page:", response.status_code)
        return []

def save_urls_to_file(urls, filename):
    with open(filename, 'w') as file:
        for url in urls:
            file.write(url + '\n')

if __name__ == "__main__":
    url = "https://www.gofundme.com/"
    
    gofundme_urls = extract_gofundme_urls(url)

    save_urls_to_file(gofundme_urls, 'gofundme_all_urls.txt')
