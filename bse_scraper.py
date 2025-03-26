"""BSE announcement scraper module focusing on steel and infrastructure announcements."""

from typing import List, Dict, Any
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
import logging
from pydantic import BaseModel, Field
import time
import json
import os
import re
import io
import PyPDF2

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),  # Log to console
        logging.FileHandler('bse_scraping.log')  # Log to file
    ]
)

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Target companies with their BSE URLs and scrip codes
TARGET_COMPANIES = [
    {
        'name': 'Larsen & Toubro Ltd',
        'symbol': 'LT',
        'scrip_code': '500510',
    },
    {
        'name': 'Rail Vikas Nigam Ltd',
        'symbol': 'RVNL',
        'scrip_code': '542649',
    },
    {
        'name': 'IRB Infrastructure Developers Ltd',
        'symbol': 'IRB',
        'scrip_code': '532947',
    },
    {
        'name': 'KEC International Ltd',
        'symbol': 'KEC',
        'scrip_code': '532714',
    },
    {
        'name': 'Kalpataru Projects International Ltd',
        'symbol': 'KPIL',
        'scrip_code': '522287',
    },
    {
        'name': 'NBCC (India) Ltd',
        'symbol': 'NBCC',
        'scrip_code': '534309',
    },
    {
        'name': 'Afcons Infrastructure Ltd',
        'symbol': 'AFCONS',
        'scrip_code': '544280',
    },
    {
        'name': 'IRCON International Ltd',
        'symbol': 'IRCON',
        'scrip_code': '541956',
    },
    {
        'name': 'NCC Limited',
        'symbol': 'NCC',
        'scrip_code': '500294',
    },
    {
        'name': 'Reliance Infrastructure Ltd',
        'symbol': 'RELINFRA',
        'scrip_code': '500390',
    },
    {
        'name': 'PNC Infratech Ltd',
        'symbol': 'PNCINFRA',
        'scrip_code': '539150',
    }
]

# Project type mapping
PROJECT_TYPE_MAPPING = {
    # Energy and Power
    'solar': 'Renewable Energy - Solar',
    'solar park': 'Renewable Energy - Solar',
    'solar power': 'Renewable Energy - Solar',
    'solar plant': 'Renewable Energy - Solar',
    'solar project': 'Renewable Energy - Solar',
    'solar energy': 'Renewable Energy - Solar',
    'wind': 'Renewable Energy - Wind',
    'wind farm': 'Renewable Energy - Wind',
    'wind power': 'Renewable Energy - Wind',
    'wind energy': 'Renewable Energy - Wind',
    'hydro': 'Renewable Energy - Hydro',
    'hydroelectric': 'Renewable Energy - Hydro',
    'hydropower': 'Renewable Energy - Hydro',
    'thermal': 'Power - Thermal',
    'coal': 'Power - Thermal',
    'gas': 'Power - Thermal/Gas',
    'power plant': 'Power Generation',
    'power generation': 'Power Generation',
    'electricity': 'Power Generation',
    'transmission': 'Power Transmission',
    'substation': 'Power Transmission',
    'grid': 'Power Transmission',
    
    # Transportation
    'highway': 'Transportation - Highway',
    'expressway': 'Transportation - Highway',
    'road': 'Transportation - Road',
    'roadway': 'Transportation - Road',
    'bridge': 'Transportation - Bridge',
    'flyover': 'Transportation - Bridge',
    'metro': 'Transportation - Metro',
    'railway': 'Transportation - Railway',
    'rail': 'Transportation - Railway',
    'airport': 'Transportation - Airport',
    'port': 'Transportation - Port',
    'terminal': 'Transportation - Port/Terminal',
    'logistics': 'Transportation - Logistics',
    
    # Construction
    'construction': 'Construction',
    'building': 'Construction - Building',
    'residential': 'Construction - Residential',
    'commercial': 'Construction - Commercial',
    'housing': 'Construction - Residential',
    'real estate': 'Real Estate',
    'property': 'Real Estate',
    'township': 'Urban Development',
    'smart city': 'Urban Development',
    'mixed-use': 'Real Estate - Mixed Use',
    'sez': 'Special Economic Zone',
    'industrial park': 'Industrial Park',
    'tech park': 'IT/Tech Park',
    'it park': 'IT/Tech Park',
    'data center': 'Data Center',
    
    # Water
    'water supply': 'Water Infrastructure',
    'water treatment': 'Water Infrastructure',
    'sewage': 'Water Infrastructure',
    'irrigation': 'Water Infrastructure',
    'pipeline': 'Pipeline',
    'water project': 'Water Infrastructure',
    'desalination': 'Water Infrastructure',
    'drainage': 'Water Infrastructure',
    'reservoir': 'Water Infrastructure',
    
    # Manufacturing
    'steel': 'Manufacturing - Steel',
    'iron': 'Manufacturing - Steel',
    'metal': 'Manufacturing - Metal',
    'metallurgy': 'Manufacturing - Metal',
    'cement': 'Manufacturing - Cement',
    'chemical': 'Manufacturing - Chemical',
    'petrochemical': 'Manufacturing - Petrochemical',
    'refinery': 'Manufacturing - Refinery',
    'textile': 'Manufacturing - Textile',
    'pharma': 'Manufacturing - Pharmaceutical',
    'food processing': 'Manufacturing - Food Processing',
    'factory': 'Manufacturing',
    'plant': 'Manufacturing',
    'manufacturing': 'Manufacturing',
    'production': 'Manufacturing',
    
    # Default
    'infrastructure': 'Infrastructure',
    'project': 'General Project',
    'epc': 'EPC',
    'engineering': 'Engineering Services',
    'contract': 'Contract',
    'order': 'Order/Contract'
}

# List of Indian states and major cities for location detection
INDIAN_LOCATIONS = [
    'andhra pradesh', 'arunachal pradesh', 'assam', 'bihar', 'chhattisgarh', 'goa', 'gujarat', 
    'haryana', 'himachal pradesh', 'jharkhand', 'karnataka', 'kerala', 'madhya pradesh', 
    'maharashtra', 'manipur', 'meghalaya', 'mizoram', 'nagaland', 'odisha', 'punjab', 'rajasthan', 
    'sikkim', 'tamil nadu', 'telangana', 'tripura', 'uttar pradesh', 'uttarakhand', 'west bengal',
    'delhi', 'chandigarh', 'puducherry', 'ladakh', 'jammu and kashmir', 'lakshadweep', 
    'andaman and nicobar',
    # Major cities
    'mumbai', 'delhi', 'bangalore', 'bengaluru', 'hyderabad', 'chennai', 'kolkata', 'ahmedabad', 
    'pune', 'jaipur', 'lucknow', 'kanpur', 'nagpur', 'indore', 'thane', 'bhopal', 'visakhapatnam', 
    'surat', 'coimbatore', 'kochi', 'vadodara', 'agra', 'nashik', 'patna', 'faridabad', 'meerut',
    'rajkot', 'kalyan', 'vasai', 'varanasi', 'srinagar', 'ghaziabad', 'amritsar', 'raipur'
]

class BSEAnnouncement(BaseModel):
    """Model for BSE announcements"""
    title: str
    date: datetime
    company: str
    symbol: str
    scrip_code: str
    category: str = Field(default="")
    attachment_url: str = Field(default="")
    xbrl_url: str = Field(default="")
    pdf_content: str = Field(default="")
    project_type: str = Field(default="")
    location: str = Field(default="")
    contract_value: str = Field(default="")
    description: str = Field(default="")

def extract_project_type(text: str) -> str:
    """Extract project type from text."""
    text_lower = text.lower()
    
    # Find all matching keywords
    matches = []
    for keyword, project_type in PROJECT_TYPE_MAPPING.items():
        if keyword.lower() in text_lower:
            matches.append((keyword, project_type))
    
    # Sort by keyword length (longer matches are more specific)
    matches.sort(key=lambda x: len(x[0]), reverse=True)
    
    # Return the most specific match, or a default
    if matches:
        return matches[0][1]
    return "Infrastructure Project"

def extract_location(text: str) -> str:
    """Extract location information from text."""
    text_lower = text.lower()
    
    # Check for Indian locations
    for location in INDIAN_LOCATIONS:
        if location in text_lower:
            # Capitalize properly
            return location.title()
    
    # Look for "in [location]" pattern
    location_pattern = r'in\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)'
    matches = re.findall(location_pattern, text)
    if matches:
        return matches[0]
    
    return ""

def extract_contract_value(text: str) -> str:
    """Extract contract value from text."""
    text_lower = text.lower()
    
    # Look for currency patterns
    # INR/Rs patterns
    inr_pattern = r'(?:rs\.?|inr|₹)\s*(\d+(?:,\d+)*(?:\.\d+)?)\s*(?:crore|cr\.?|lakh|lac|million|mn|billion|bn)'
    inr_matches = re.findall(inr_pattern, text_lower)
    
    # USD patterns
    usd_pattern = r'(?:usd|\$)\s*(\d+(?:,\d+)*(?:\.\d+)?)\s*(?:million|mn|billion|bn)'
    usd_matches = re.findall(usd_pattern, text_lower)
    
    # Value with units
    value_pattern = r'(\d+(?:,\d+)*(?:\.\d+)?)\s*(?:crore|cr\.?|lakh|lac|million|mn|billion|bn|mw|gw|mwp)'
    value_matches = re.findall(value_pattern, text_lower)
    
    # Combined pattern for "value of" expressions
    value_of_pattern = r'(?:value|worth|amount|order value|contract value|size) of (?:rs\.?|inr|₹|usd|\$)?\s*(\d+(?:,\d+)*(?:\.\d+)?)\s*(?:crore|cr\.?|lakh|lac|million|mn|billion|bn)'
    value_of_matches = re.findall(value_of_pattern, text_lower)
    
    # Combine all matches
    all_matches = []
    
    if inr_matches:
        all_matches.append(f"Rs. {inr_matches[0]} crore")
    
    if usd_matches:
        all_matches.append(f"USD {usd_matches[0]} million")
    
    if value_of_matches:
        if "rs" in text_lower or "inr" in text_lower or "₹" in text_lower:
            all_matches.append(f"Rs. {value_of_matches[0]} crore")
        elif "usd" in text_lower or "$" in text_lower:
            all_matches.append(f"USD {value_of_matches[0]} million")
        else:
            all_matches.append(f"{value_of_matches[0]} crore")
    
    # If no specific pattern found, but there are value matches
    if not all_matches and value_matches:
        all_matches.append(f"{value_matches[0]} crore")
    
    return all_matches[0] if all_matches else ""

def scrape_bse_announcements() -> List[Dict[str, Any]]:
    """Scrape steel and infrastructure related announcements from BSE company pages."""
    try:
        announcements = []
        
        # Project-related keywords to filter announcements
        project_keywords = [
            'project', 'contract', 'order', 'steel', 'infrastructure',
            'awarded', 'wins', 'secured', 'bags', 'development', 'execution',
            'tender', 'bid', 'loa', 'letter of award', 'work order',
            'construction', 'metro', 'railway', 'road', 'highway', 'bridge'
        ]

        # BSE API headers
        headers = {
            'authority': 'api.bseindia.com',
            'accept': 'application/json, text/plain, */*',
            'accept-language': 'en-US,en;q=0.9',
            'origin': 'https://www.bseindia.com',
            'referer': 'https://www.bseindia.com/',
            'sec-ch-ua': '"Not A(Brand";v="99", "Google Chrome";v="121", "Chromium";v="121"',
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': '"Windows"',
            'sec-fetch-dest': 'empty',
            'sec-fetch-mode': 'cors',
            'sec-fetch-site': 'same-site',
            'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36'
        }

        # Get today's date and 30 days ago for the date range
        today = datetime.now()
        prev_date = today - timedelta(days=30)

        for company in TARGET_COMPANIES:
            try:
                logger.info(f"Scraping BSE announcements for {company['name']} ({company['symbol']})")
                
                # BSE API endpoint
                url = "https://api.bseindia.com/BseIndiaAPI/api/AnnGetData/w"
                
                # Query parameters
                params = {
                    'strCat': '-1',
                    'strPrevDate': prev_date.strftime('%Y%m%d'),
                    'strScrip': company['scrip_code'],
                    'strSearch': 'P',
                    'strToDate': today.strftime('%Y%m%d'),
                    'strType': 'C'
                }
                
                response = requests.get(url, headers=headers, params=params, timeout=30)
                
                if response.status_code == 200:
                    try:
                        result = response.json()
                        if isinstance(result.get('Table'), list):
                            for item in result['Table']:
                                try:
                                    title = item.get('NEWSSUB', '').strip()
                                    
                                    # Check if announcement is project-related
                                    if any(keyword in title.lower() for keyword in project_keywords):
                                        date_str = item.get('NEWS_DT', '').strip()
                                        try:
                                            date = datetime.strptime(date_str.split('.')[0], '%Y-%m-%dT%H:%M:%S')
                                        except ValueError:
                                            try:
                                                date = datetime.strptime(date_str, '%d %b %Y')
                                            except ValueError:
                                                date = datetime.now()
                                        
                                        # Create attachment URLs
                                        attachment_url = f"http://www.bseindia.com/stockinfo/AnnPdfOpen.aspx?Pname={item.get('ATTACHMENTNAME', '')}"
                                        xbrl_url = f"https://www.bseindia.com/Msource/90D/CorpXbrlGen.aspx?Bsenewid={item.get('NEWSID', '')}&Scripcode={company['scrip_code']}"
                                        
                                        # Extract project type from title
                                        project_type = extract_project_type(title)
                                        
                                        # Create announcement object
                                        announcement = BSEAnnouncement(
                                            title=title,
                                            date=date,
                                            company=company['name'],
                                            symbol=company['symbol'],
                                            scrip_code=company['scrip_code'],
                                            category=item.get('CATEGORYNAME', ''),
                                            attachment_url=attachment_url,
                                            xbrl_url=xbrl_url,
                                            project_type=project_type
                                        )
                                        announcements.append(announcement)
                                        logger.debug(f"Added announcement: {title}")
                                except Exception as e:
                                    logger.error(f"Error processing announcement for {company['symbol']}: {str(e)}")
                                    continue
                    except json.JSONDecodeError:
                        logger.error(f"Failed to parse JSON response for {company['symbol']}")
                else:
                    logger.error(f"Failed to fetch announcements for {company['symbol']}: HTTP {response.status_code}")
                
                # Add delay between requests to avoid rate limiting
                time.sleep(2)
                
            except Exception as e:
                logger.error(f"Error scraping {company['symbol']}: {str(e)}")
                continue
        
        # Sort announcements by date (newest first)
        announcements.sort(key=lambda x: x.date, reverse=True)
        
        # Extract PDF content and additional details
        for announcement in announcements:
            if announcement.attachment_url:
                try:
                    logger.info(f"Extracting PDF content from {announcement.attachment_url}")
                    # Use a 30-second timeout for PDF downloads
                    pdf_response = requests.get(announcement.attachment_url, headers=headers, timeout=30)
                    
                    if pdf_response.status_code == 200:
                        try:
                            # Parse PDF content
                            with io.BytesIO(pdf_response.content) as pdf_file:
                                try:
                                    pdf_reader = PyPDF2.PdfReader(pdf_file)
                                    text = ""
                                    for page in pdf_reader.pages:
                                        page_text = page.extract_text()
                                        if page_text:
                                            text += page_text + "\n"
                                    
                                    # Store the PDF content
                                    full_text = text[:1000] if text else ""
                                    announcement.pdf_content = full_text
                                    
                                    # Set description from PDF content
                                    announcement.description = full_text
                                    
                                    # Extract more details from full text content
                                    combined_text = announcement.title + " " + announcement.company + " " + full_text
                                    
                                    # Try to extract location
                                    if not announcement.location:
                                        location = extract_location(combined_text)
                                        announcement.location = location
                                    
                                    # Try to extract contract value
                                    if not announcement.contract_value:
                                        contract_value = extract_contract_value(combined_text)
                                        announcement.contract_value = contract_value
                                    
                                    # Refine project type if needed
                                    if announcement.project_type == "Infrastructure Project" or not announcement.project_type:
                                        refined_type = extract_project_type(combined_text)
                                        if refined_type != "Infrastructure Project":
                                            announcement.project_type = refined_type
                                except Exception as e:
                                    logger.error(f"Error parsing PDF: {str(e)}")
                        except Exception as e:
                            logger.error(f"Error reading PDF content: {str(e)}")
                    else:
                        logger.error(f"Failed to download PDF: HTTP {pdf_response.status_code}")
                except Exception as e:
                    logger.error(f"Error downloading PDF: {str(e)}")
        
        # Convert to the new requested format
        formatted_announcements = []
        for announcement in announcements:
            formatted_announcement = {
                "Title": announcement.title,
                "Company": announcement.company,
                "Project Type": announcement.project_type,
                "Location": announcement.location,
                "Contract Value": announcement.contract_value,
                "Date": announcement.date.strftime('%Y-%m-%d'),
                "Description": announcement.pdf_content,
                "attachment_url":announcement.attachment_url
            }
            formatted_announcements.append(formatted_announcement)
        
        # Save announcements to JSON file
        try:
            output_path = os.path.join(os.path.dirname(__file__), 'bse_announcements.json')
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(
                    formatted_announcements,
                    f,
                    indent=2,
                    default=str
                )
            logger.info(f"Total project-related announcements found: {len(formatted_announcements)}")
            logger.info(f"Saved announcements to {output_path}")
        except Exception as e:
            logger.error(f"Error saving announcements to JSON: {str(e)}")
        
        return formatted_announcements
        
    except Exception as e:
        logger.error(f"Error in scrape_bse_announcements: {str(e)}")
        return []

if __name__ == "__main__":
    scrape_bse_announcements() 