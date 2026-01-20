# GoFundMe Scraper

A web-based tool to scrape GoFundMe campaign data with an easy-to-use interface.

## Features

- **Manual URL Entry**: Enter GoFundMe campaign URLs to scrape
- **Auto-Discover**: Automatically discover trending campaigns from GoFundMe
- **Data Extraction**: Extracts title, description, amount raised, goal, and recent donations
- **CSV Export**: Export scraped data to CSV file
- **Modern UI**: Clean, responsive interface

## Installation

1. Clone the repository:
```bash
git clone https://github.com/Emos21/Gofundme_scrapper.git
cd Gofundme_scrapper
```

2. Create virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Run the application:
```bash
python app.py
```

5. Open your browser and go to `http://localhost:5000`

## Usage

### Manual Scraping
1. Go to the "Enter URLs" tab
2. Paste GoFundMe campaign URLs (one per line)
3. Click "Scrape Campaigns"

### Auto-Discover
1. Go to the "Discover" tab
2. Select how many campaigns to discover
3. Click "Discover Campaigns"
4. Review discovered URLs and click "Scrape All Discovered"

### Export Data
- After scraping, click "Export CSV" to download the data

## Tech Stack

- **Backend**: Flask (Python)
- **Frontend**: HTML, CSS, JavaScript, Bootstrap 5
- **Scraping**: BeautifulSoup4, Requests
- **Data**: Pandas

## License

MIT License
