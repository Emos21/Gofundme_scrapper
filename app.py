from flask import Flask, render_template, request, jsonify, send_file
from flask_sqlalchemy import SQLAlchemy
from bs4 import BeautifulSoup
import requests
import pandas as pd
import re
from datetime import datetime, date
import os
import io
import json

# Initialize Flask app
app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///gofundme.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Initialize database
from models import db, Campaign, CampaignSnapshot, Donation, ScheduledTask, User
db.init_app(app)

# Create tables
with app.app_context():
    db.create_all()


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


def parse_amount(amount_str):
    """Parse amount string to float."""
    if not amount_str or amount_str == 'N/A':
        return None
    # Remove currency symbols and commas
    cleaned = re.sub(r'[^\d.]', '', amount_str)
    try:
        return float(cleaned)
    except ValueError:
        return None


def scrape_campaign(url, save_to_db=True):
    """Scrape a single GoFundMe campaign page."""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }
        response = requests.get(url, headers=headers, timeout=15)
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
    amount_raised = "N/A"
    goal_amount = "N/A"
    
    if progress_meter:
        amount_elem = progress_meter.find("div", class_="hrt-disp-inline progress-meter_largeType__L_4O8")
        goal_elem = progress_meter.find("span", class_="hrt-text-body-sm hrt-text-gray")
        
        amount_raised = amount_elem.text.strip() if amount_elem else "N/A"
        goal_match = re.search(r'($?[\d,]+)', goal_elem.text.strip()) if goal_elem else None
        goal_amount = goal_match.group() if goal_match else "N/A"

    # Get donations
    donors = soup.find_all("div", class_="hrt-avatar-lockup-content")
    donations = []
    for donor in donors[:10]:
        donor_name_elem = donor.find("div")
        donor_name = donor_name_elem.text.strip() if donor_name_elem else "Anonymous"
        amount_elem = donor.find("span", class_="hrt-font-bold")
        donation_amount = amount_elem.text.strip() if amount_elem else "N/A"
        donations.append({"name": donor_name, "amount": donation_amount})

    result = {
        "title": title,
        "statement": statement[:500] + "..." if len(statement) > 500 else statement,
        "full_statement": statement,
        "amount_raised": amount_raised,
        "goal_amount": goal_amount,
        "donations": donations,
        "url": url,
        "date_scraped": str(date.today())
    }

    # Save to database if enabled
    if save_to_db:
        try:
            campaign = Campaign.query.filter_by(url=url).first()
            if not campaign:
                campaign = Campaign(
                    url=url,
                    title=title,
                    description=statement,
                    goal_amount=parse_amount(goal_amount)
                )
                db.session.add(campaign)
                db.session.flush()
            else:
                campaign.title = title
                campaign.description = statement
                campaign.goal_amount = parse_amount(goal_amount)
                campaign.updated_at = datetime.utcnow()
            
            # Create snapshot
            snapshot = CampaignSnapshot(
                campaign_id=campaign.id,
                amount_raised=parse_amount(amount_raised),
                donor_count=len(donations)
            )
            db.session.add(snapshot)
            
            # Save donations
            for d in donations:
                donation = Donation(
                    campaign_id=campaign.id,
                    donor_name=d['name'],
                    amount=parse_amount(d['amount'])
                )
                db.session.add(donation)
            
            db.session.commit()
            result['campaign_id'] = campaign.id
            result['snapshot_id'] = snapshot.id
        except Exception as e:
            db.session.rollback()
            print(f"Database error: {e}")

    return result


def discover_campaigns(max_urls=20):
    """Discover GoFundMe campaign URLs from the discover page."""
    discovered_urls = set()

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
                urls_found = re.findall(r'https://www\.gofundme\.com/f/[a-zA-Z0-9\-_]+', response.text)

                for url in urls_found:
                    url = url.rstrip('\\').rstrip('"').rstrip("'")
                    if url not in discovered_urls:
                        discovered_urls.add(url)
                        if len(discovered_urls) >= max_urls:
                            break

    except Exception as e:
        return {"error": str(e), "urls": list(discovered_urls)}

    return {"urls": list(discovered_urls), "count": len(discovered_urls)}


# ============== ROUTES ==============

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

    output = io.StringIO()
    df.to_csv(output, index=False)
    output.seek(0)

    bytes_output = io.BytesIO()
    bytes_output.write(output.getvalue().encode('utf-8'))
    bytes_output.seek(0)

    return send_file(
        bytes_output,
        mimetype='text/csv',
        as_attachment=True,
        download_name=f'gofundme_data_{date.today()}.csv'
    )


# ============== DATABASE API ROUTES ==============

@app.route('/api/campaigns', methods=['GET'])
def get_campaigns():
    """Get all campaigns from database."""
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    
    campaigns = Campaign.query.order_by(Campaign.updated_at.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )
    
    return jsonify({
        'campaigns': [c.to_dict() for c in campaigns.items],
        'total': campaigns.total,
        'pages': campaigns.pages,
        'current_page': page
    })


@app.route('/api/campaigns/<int:campaign_id>', methods=['GET'])
def get_campaign(campaign_id):
    """Get a specific campaign with all snapshots."""
    campaign = Campaign.query.get_or_404(campaign_id)
    snapshots = campaign.snapshots.order_by(CampaignSnapshot.scraped_at.asc()).all()
    
    return jsonify({
        'campaign': campaign.to_dict(),
        'snapshots': [s.to_dict() for s in snapshots],
        'donations': [d.to_dict() for d in campaign.donations.limit(50).all()]
    })


@app.route('/api/campaigns/<int:campaign_id>/track', methods=['POST'])
def track_campaign(campaign_id):
    """Create a new snapshot for tracking."""
    campaign = Campaign.query.get_or_404(campaign_id)
    
    # Re-scrape the campaign
    result = scrape_campaign(campaign.url, save_to_db=True)
    
    if 'error' in result:
        return jsonify(result), 400
    
    return jsonify({
        'message': 'Campaign tracked successfully',
        'result': result
    })


@app.route('/api/stats', methods=['GET'])
def get_stats():
    """Get overall statistics."""
    total_campaigns = Campaign.query.count()
    total_snapshots = CampaignSnapshot.query.count()
    total_donations = Donation.query.count()
    
    # Get total amount raised across all campaigns
    from sqlalchemy import func
    latest_snapshots = db.session.query(
        CampaignSnapshot.campaign_id,
        func.max(CampaignSnapshot.scraped_at).label('latest')
    ).group_by(CampaignSnapshot.campaign_id).subquery()
    
    total_raised = db.session.query(func.sum(CampaignSnapshot.amount_raised)).join(
        latest_snapshots,
        (CampaignSnapshot.campaign_id == latest_snapshots.c.campaign_id) &
        (CampaignSnapshot.scraped_at == latest_snapshots.c.latest)
    ).scalar() or 0
    
    return jsonify({
        'total_campaigns': total_campaigns,
        'total_snapshots': total_snapshots,
        'total_donations': total_donations,
        'total_raised': total_raised
    })


@app.route('/dashboard')
def dashboard():
    """Analytics dashboard page."""
    return render_template('dashboard.html')


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
