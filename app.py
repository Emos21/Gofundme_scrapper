from flask import Flask, render_template, request, jsonify, send_file
from bs4 import BeautifulSoup
import requests
import pandas as pd
import re
from datetime import date
import os
import io

app = Flask(__name__)

def remove_duplicate_words(text):
    """Remove duplicate words from text while preserving order."""
    words = text.split()
    seen = set()
    result = []
    for word in words:
        if word.lower() not in seen:
            seen.add(word.lower())
            result.append(word)
    return ' '.join(result)

def scrape_campaign(url):
    """Scrape a single GoFundMe campaign page."""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        return {"error": f"Error fetching URL: {str(e)}", "url": url}

    soup = BeautifulSoup(response.text, "html.parser")

    # Get title
    title_elem = soup.find("h1", class_="hrt-mb-0 p-campaign-title")
    title = title_elem.text.strip() if title_elem else "Title not found"
    title = remove_duplicate_words(title)

    # Get description/statement
    statement_divs = soup.find_all("div", class_="campaign-description_content__C1C_5")
    statement = "\n".join([div.text.strip() for div in statement_divs])
    statement = remove_duplicate_words(statement) if statement else "Description not found"

    # Get amount raised and goal
    progress_meter = soup.find("div", class_="progress-meter_progressMeterHeading__A6Slt")
    if progress_meter:
        amount_elem = progress_meter.find("div", class_="hrt-disp-inline progress-meter_largeType__L_4O8")
        goal_elem = progress_meter.find("span", class_="hrt-text-body-sm hrt-text-gray")

        amount_raised = amount_elem.text.strip() if amount_elem else "N/A"
        goal_match = re.search(r'(\$?[\d,]+)', goal_elem.text.strip()) if goal_elem else None
        goal_amount = goal_match.group() if goal_match else "N/A"
    else:
        amount_raised = "N/A"
        goal_amount = "N/A"

    # Get donations
    donors = soup.find_all("div", class_="hrt-avatar-lockup-content")
    donations = []
    for donor in donors[:10]:  # Limit to first 10 donations
        donor_name_elem = donor.find("div")
        donor_name = donor_name_elem.text.strip() if donor_name_elem else "Anonymous"
        amount_elem = donor.find("span", class_="hrt-font-bold")
        donation_amount = amount_elem.text.strip() if amount_elem else "N/A"
        donations.append({"name": donor_name, "amount": donation_amount})

    return {
        "title": title,
        "statement": statement[:500] + "..." if len(statement) > 500 else statement,
        "full_statement": statement,
        "amount_raised": amount_raised,
        "goal_amount": goal_amount,
        "donations": donations,
        "url": url,
        "date_scraped": str(date.today())
    }

def discover_campaigns(max_urls=20):
    """Discover GoFundMe campaign URLs from the discover page."""
    discovered_urls = set()

    # Try multiple discovery sources
    discovery_urls = [
        'https://www.gofundme.com/discover',
        'https://www.gofundme.com/discover/trending',
        'https://www.gofundme.com/c/crisis-relief',
        'https://www.gofundme.com/c/medical'
    ]

    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5'
        }

        for seed_url in discovery_urls:
            if len(discovered_urls) >= max_urls:
                break

            response = requests.get(seed_url, headers=headers, timeout=15)

            if response.status_code == 200:
                # Use regex to find all GoFundMe campaign URLs
                urls_found = re.findall(r'https://www\.gofundme\.com/f/[a-zA-Z0-9\-_]+', response.text)

                for url in urls_found:
                    # Clean URL (remove trailing backslashes or quotes)
                    url = url.rstrip('\\').rstrip('"').rstrip("'")
                    if url not in discovered_urls:
                        discovered_urls.add(url)
                        if len(discovered_urls) >= max_urls:
                            break

    except Exception as e:
        return {"error": str(e), "urls": list(discovered_urls)}

    return {"urls": list(discovered_urls), "count": len(discovered_urls)}

@app.route('/')
def index():
    """Main page."""
    return render_template('index.html')

@app.route('/scrape', methods=['POST'])
def scrape():
    """Scrape campaigns from provided URLs."""
    data = request.json
    urls = data.get('urls', [])

    if not urls:
        return jsonify({"error": "No URLs provided"}), 400

    results = []
    for url in urls:
        url = url.strip()
        if url and 'gofundme.com' in url:
            result = scrape_campaign(url)
            results.append(result)

    return jsonify({"results": results, "count": len(results)})

@app.route('/discover', methods=['POST'])
def discover():
    """Discover campaign URLs from GoFundMe."""
    data = request.json
    max_urls = data.get('max_urls', 20)

    result = discover_campaigns(max_urls)
    return jsonify(result)

@app.route('/export', methods=['POST'])
def export_csv():
    """Export scraped data to CSV."""
    data = request.json
    results = data.get('results', [])

    if not results:
        return jsonify({"error": "No data to export"}), 400

    # Create DataFrame
    df_data = []
    for r in results:
        if 'error' not in r:
            df_data.append({
                'Title': r.get('title', ''),
                'Amount Raised': r.get('amount_raised', ''),
                'Goal Amount': r.get('goal_amount', ''),
                'Description': r.get('full_statement', r.get('statement', '')),
                'URL': r.get('url', ''),
                'Date Scraped': r.get('date_scraped', '')
            })

    df = pd.DataFrame(df_data)

    # Create CSV in memory
    output = io.StringIO()
    df.to_csv(output, index=False)
    output.seek(0)

    # Convert to bytes for download
    bytes_output = io.BytesIO()
    bytes_output.write(output.getvalue().encode('utf-8'))
    bytes_output.seek(0)

    return send_file(
        bytes_output,
        mimetype='text/csv',
        as_attachment=True,
        download_name=f'gofundme_data_{date.today()}.csv'
    )

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
