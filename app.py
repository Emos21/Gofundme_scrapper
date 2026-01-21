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


# ============== MULTI-FORMAT EXPORT ==============

@app.route('/export/json', methods=['POST'])
def export_json():
    """Export scraped data to JSON."""
    data = request.json
    results = data.get('results', [])

    if not results:
        return jsonify({"error": "No data to export"}), 400

    export_data = []
    for r in results:
        if 'error' not in r:
            export_data.append({
                'title': r.get('title', ''),
                'amount_raised': r.get('amount_raised', ''),
                'goal_amount': r.get('goal_amount', ''),
                'description': r.get('full_statement', r.get('statement', '')),
                'donations': r.get('donations', []),
                'url': r.get('url', ''),
                'date_scraped': r.get('date_scraped', '')
            })

    output = io.BytesIO()
    output.write(json.dumps(export_data, indent=2).encode('utf-8'))
    output.seek(0)

    return send_file(
        output,
        mimetype='application/json',
        as_attachment=True,
        download_name=f'gofundme_data_{date.today()}.json'
    )


@app.route('/export/excel', methods=['POST'])
def export_excel():
    """Export scraped data to Excel."""
    data = request.json
    results = data.get('results', [])

    if not results:
        return jsonify({"error": "No data to export"}), 400

    df_data = []
    for r in results:
        if 'error' not in r:
            donations_str = '; '.join([f"{d['name']}: {d['amount']}" for d in r.get('donations', [])])
            df_data.append({
                'Title': r.get('title', ''),
                'Amount Raised': r.get('amount_raised', ''),
                'Goal Amount': r.get('goal_amount', ''),
                'Description': r.get('full_statement', r.get('statement', ''))[:500],
                'Recent Donations': donations_str,
                'URL': r.get('url', ''),
                'Date Scraped': r.get('date_scraped', '')
            })

    df = pd.DataFrame(df_data)

    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Campaigns')
        
        # Auto-adjust column widths
        worksheet = writer.sheets['Campaigns']
        for idx, col in enumerate(df.columns):
            max_length = max(df[col].astype(str).map(len).max(), len(col)) + 2
            worksheet.column_dimensions[chr(65 + idx)].width = min(max_length, 50)
    
    output.seek(0)

    return send_file(
        output,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        as_attachment=True,
        download_name=f'gofundme_data_{date.today()}.xlsx'
    )


@app.route('/export/pdf', methods=['POST'])
def export_pdf():
    """Export scraped data to PDF."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter, landscape
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import inch

    data = request.json
    results = data.get('results', [])

    if not results:
        return jsonify({"error": "No data to export"}), 400

    output = io.BytesIO()
    doc = SimpleDocTemplate(output, pagesize=landscape(letter), rightMargin=30, leftMargin=30, topMargin=30, bottomMargin=30)
    
    elements = []
    styles = getSampleStyleSheet()
    
    # Title
    title_style = ParagraphStyle('Title', parent=styles['Heading1'], fontSize=18, spaceAfter=20)
    elements.append(Paragraph(f"GoFundMe Scraper Report - {date.today()}", title_style))
    elements.append(Spacer(1, 20))

    # Table data
    table_data = [['Title', 'Amount Raised', 'Goal', 'URL']]
    
    for r in results:
        if 'error' not in r:
            title = r.get('title', '')[:40] + ('...' if len(r.get('title', '')) > 40 else '')
            table_data.append([
                title,
                r.get('amount_raised', 'N/A'),
                r.get('goal_amount', 'N/A'),
                r.get('url', '')[:50] + '...'
            ])

    # Create table
    table = Table(table_data, colWidths=[3*inch, 1.5*inch, 1.5*inch, 3.5*inch])
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#02a95c')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 11),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -1), colors.white),
        ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 1), (-1, -1), 9),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f8f9fa')]),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 1), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 1), (-1, -1), 8),
    ]))
    
    elements.append(table)
    
    # Summary
    elements.append(Spacer(1, 30))
    summary_style = ParagraphStyle('Summary', parent=styles['Normal'], fontSize=10, textColor=colors.grey)
    elements.append(Paragraph(f"Total campaigns: {len([r for r in results if 'error' not in r])}", summary_style))
    
    doc.build(elements)
    output.seek(0)

    return send_file(
        output,
        mimetype='application/pdf',
        as_attachment=True,
        download_name=f'gofundme_report_{date.today()}.pdf'
    )


@app.route('/export/database', methods=['GET'])
def export_database():
    """Export all database data to JSON."""
    campaigns = Campaign.query.all()
    
    export_data = {
        'exported_at': datetime.utcnow().isoformat(),
        'campaigns': []
    }
    
    for c in campaigns:
        campaign_data = c.to_dict()
        campaign_data['all_snapshots'] = [s.to_dict() for s in c.snapshots.all()]
        campaign_data['all_donations'] = [d.to_dict() for d in c.donations.all()]
        export_data['campaigns'].append(campaign_data)
    
    output = io.BytesIO()
    output.write(json.dumps(export_data, indent=2).encode('utf-8'))
    output.seek(0)

    return send_file(
        output,
        mimetype='application/json',
        as_attachment=True,
        download_name=f'gofundme_database_export_{date.today()}.json'
    )
