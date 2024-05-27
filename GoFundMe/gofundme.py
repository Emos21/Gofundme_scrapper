from bs4 import BeautifulSoup
import requests
import pandas as pd
import re
from datetime import date


def remove_duplicate_words(text):
    words = text.split()
    seen = set()
    result = []
    for word in words:
        if word.lower() not in seen:
            seen.add(word.lower())
            result.append(word)
    return ' '.join(result)

def scrape_data(url):
    try:
        page_to_scrape = requests.get(url)
        page_to_scrape.raise_for_status()
    except requests.exceptions.RequestException as e:
        print(f"Error fetching URL '{url}': {e}")
        return None
    
    soup = BeautifulSoup(page_to_scrape.text, "html.parser")
    
    title = soup.find("h1", class_="hrt-mb-0 p-campaign-title")
    if title:
        title = title.text.strip()
        print(f"Original Title: {title}")
        title = remove_duplicate_words(title)
        print(f"Processed Title: {title}")
    else:
        title = "Title not found"
    
   
    statement_divs = soup.find_all("div", class_="campaign-description_content__C1C_5")
    statement = "\n".join([div.text.strip() for div in statement_divs])
    print(f"Original Statement: {statement}")
    statement = remove_duplicate_words(statement)  
    print(f"Processed Statement: {statement}")

    progress_meter = soup.find("div", class_="progress-meter_progressMeterHeading__A6Slt")
    if progress_meter:
        amount_raised_element = progress_meter.find("div", class_="hrt-disp-inline progress-meter_largeType__L_4O8")
        goal_amount_element = progress_meter.find("span", class_="hrt-text-body-sm hrt-text-gray")
        
        amount_raised = amount_raised_element.text.strip() if amount_raised_element else "Amount not found"
        goal_amount = re.search(r'(\d[\d.,]*)', goal_amount_element.text.strip()).group() if goal_amount_element else "Goal amount not found"
    else:
        amount_raised = "Amount not found"
        goal_amount = "Goal amount not found"

    donors = soup.find_all("div", class_="hrt-avatar-lockup-content")
    donations = []
    for donor in donors:
        donor_name = donor.find("div").text.strip()
        donation_amount_element = donor.find("span", class_="hrt-font-bold")
        donation_amount = donation_amount_element.text.strip() if donation_amount_element else "Donation amount not found"
        donations.append({"Donor Name": donor_name, "Donation Amount": donation_amount})

    return {"Title": title, "Statement": statement, "Amount Raised": amount_raised, "Goal Amount": goal_amount, "Donations": donations, "Source URL": url, "Date Scraped": date.today()}

def read_urls_from_file(filename):
    try:
        with open(filename, "r") as file:
            urls = [line.strip() for line in file.readlines()]
        return urls
    except FileNotFoundError:
        print(f"Error: File '{filename}' not found.")
        return []

url_pairs = read_urls_from_file("urls.txt")

csv_filename = 'gofundme.csv'
data_list = []
for full_url in url_pairs:
    scraped_data = scrape_data(full_url)
    if scraped_data:
        data_list.append(scraped_data)

df = pd.DataFrame(data_list, columns=["Title", "Statement", "Amount Raised", "Goal Amount", "Donations", "Source URL", "Date Scraped"])

df_filtered = df[df['Source URL'].str.endswith('tab=all')]

df_filtered.to_csv(csv_filename, index=False)
print(f"Data scraped and saved successfully in CSV file '{csv_filename}'!")
