"""BSE announcement scraper module focusing on infrastructure and project-related announcements."""

from typing import List, Optional, Dict, Any
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
import logging
from pydantic import BaseModel, Field
import time
import json
import os
import io
import PyPDF2  # Add PyPDF2 import for PDF parsing
import re

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

# Set fixed date for consistent results
SCRAPER_DATE = datetime(2025, 3, 25)

# Infrastructure and project-related keywords (single words or short phrases for better matching)
INFRA_KEYWORDS = [
    # Steel and Metal
    'steel', 'stainless steel', 'metal', 'metallurgy', 'iron', 'ore',
    'pig iron', 'sponge iron', 'steel plant', 'rolling mill', 'furnace',
    'steel capacity', 'steel production', 'steel manufacturing',
    
    # Manufacturing and Production
    'factory', 'plant', 'production', 'manufacturing', 'assembly line',
    'capacity expansion', 'new facility', 'greenfield', 'brownfield',
    'production capacity', 'manufacturing unit', 'industrial unit',
    'commissioning', 'commercial production', 'trial production',
    
    # Automotive and Vehicles
    'automotive', 'vehicle', 'car', 'truck', 'bus', 'two-wheeler',
    'electric vehicle', 'ev', 'automobile', 'auto component',
    'vehicle production', 'car manufacturing', 'assembly plant',
    
    # Construction and Infrastructure
    'infrastructure', 'construction', 'project', 'civil works',
    'building', 'development', 'infrastructure work', 'construction work',
    'infra project', 'infrastructure development', 'civil construction',
    
    # Transportation Infrastructure
    'highway', 'road', 'bridge', 'metro', 'railway', 'airport',
    'port', 'terminal', 'transport', 'flyover', 'tunnel', 'station',
    'rail corridor', 'expressway', 'roadway', 'freight corridor',
    
    # Energy and Power
    'power plant', 'energy', 'solar', 'wind', 'transmission',
    'substation', 'renewable', 'hydro', 'thermal', 'electricity',
    'power generation', 'power project', 'solar park', 'wind farm',
    'power transmission', 'power distribution', 'grid', 'megawatt',
    
    # Urban Development and Real Estate
    'smart city', 'urban', 'township', 'municipal', 'city development',
    'real estate', 'residential', 'commercial', 'industrial', 
    'housing', 'property development', 'mixed-use', 'tech park',
    'it park', 'sez', 'special economic zone',
    
    # Water and Environment
    'water supply', 'water treatment', 'sewage', 'irrigation',
    'pipeline', 'water project', 'desalination', 'effluent',
    'water infrastructure', 'drainage', 'reservoir',
    
    # Project Awards and Contracts
    'order', 'contract', 'awarded', 'secured', 'bagged', 
    'tender', 'bid', 'LOA', 'letter of award', 'work order',
    'order win', 'new order', 'contract win', 'project win',
    'order book', 'order inflow', 'order received',
    
    # Engineering and Technical
    'EPC', 'engineering', 'procurement', 'technical', 'design build',
    'turnkey', 'design and build', 'engineering works',
    
    # Industrial and Process
    'cement', 'chemical', 'refinery', 'petrochemical', 'textile',
    'pharma', 'food processing', 'industrial park', 'logistics park',
    'warehouse', 'storage terminal', 'data center', 'industrial corridor',
    
    # Value and Size Indicators
    'crore', 'million', 'billion', 'value', 'worth', 'capacity',
    'tonnes', 'tons', 'tpa', 'mtpa', 'mw', 'gw', 'sqft', 'acres'
]

# Exclude these terms to avoid false positives
EXCLUDE_KEYWORDS = [
    # Corporate Events
    'trading window', 'board meeting', 'agm', 'egm', 'postal ballot',
    'investor meet', 'investor presentation', 'annual report',
    'quarterly results', 'financial results', 'dividend',
    
    # Regulatory
    'compliance', 'regulation 30', 'sebi', 'disclosure requirements',
    'listing obligations', 'corporate governance',
    
    # Administrative
    'appointment', 'resignation', 'key managerial', 'director',
    'company secretary', 'auditor', 'closure of register',
    
    # Others
    'credit rating', 'share transfer', 'shareholding pattern',
    'certificate', 'intimation', 'clarification',
    
    # Exclude specific updates
    'trading update', 'business update', 'covid update',
    'operational update', 'status update', 'progress update'
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
    title: str = Field(default="")
    date: datetime
    company: str = Field(default="")
    security_code: str = Field(default="")
    category: str = Field(default="")
    sub_category: str = Field(default="")
    attachment_url: str = Field(default="")
    pdf_content: str = Field(default="")
    is_infra_related: bool = Field(default=False)
    project_type: str = Field(default="")
    location: str = Field(default="")
    contract_value: str = Field(default="")
    description: str = Field(default="")

    class Config:
        json_encoders = {
            datetime: lambda v: v.strftime('%Y-%m-%d %H:%M:%S')
        }

def safe_get(data: dict, key: str, default: str = "") -> str:
    """Safely get a string value from a dictionary."""
    value = data.get(key)
    return str(value).strip() if value is not None else default

def is_infrastructure_related(title: str, company: str, security_code: str) -> bool:
    """Check if the announcement is infrastructure-related."""
    title_lower = title.lower()
    company_lower = company.lower()
    
    # First check exclusions
    if any(keyword.lower() in title_lower for keyword in EXCLUDE_KEYWORDS):
        return False
    
    # Look for value indicators (e.g., "Rs. 100 crore", "USD 50 million")
    value_indicators = ['rs.', 'rs', 'inr', 'usd', '₹', '$', 'crore', 'million', 'billion',
                       'tonnes', 'tons', 'tpa', 'mtpa', 'mw', 'gw', 'sqft', 'acres']
    has_value = any(indicator in title_lower for indicator in value_indicators)
    
    # Strong keywords that indicate relevant announcements
    strong_keywords = [
        'project', 'infrastructure', 'construction', 'awarded', 'contract', 'order',
        'steel', 'factory', 'plant', 'production', 'manufacturing', 'capacity',
        'facility', 'commissioning', 'commercial production'
    ]
    
    # Check for infrastructure keywords
    has_infra_keyword = any(keyword.lower() in title_lower or keyword.lower() in company_lower 
                          for keyword in INFRA_KEYWORDS)
    
    # Return True if we have both a value and an infrastructure keyword,
    # or if we have a strong infrastructure keyword
    return has_infra_keyword and (has_value or 
                                 any(keyword in title_lower for keyword in strong_keywords))

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
    """Scrape infrastructure and project-related announcements from BSE."""
    try:
        announcements = []
        infra_announcements = []
        
        # BSE API endpoint for announcements
        api_url = "https://api.bseindia.com/BseIndiaAPI/api/AnnGetData/w"
        
        # Headers to mimic browser request
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
        
        # Get today's date and 1 year ago for the date range
        today = SCRAPER_DATE
        one_year_ago = today - timedelta(days=60)
            
        # Since BSE API might limit results per request, we'll fetch data month by month
        current_date = one_year_ago
        while current_date <= today:
            try:
                # Calculate end date for this iteration (1 month from current_date or today)
                end_date = min(current_date + timedelta(days=30), today)
                
                # Query parameters for the API
                params = {
                    'strCat': '-1',  # All categories
                    'strPrevDate': current_date.strftime('%Y%m%d'),
                    'strScrip': '',  # All companies
                    'strSearch': 'P',
                    'strToDate': end_date.strftime('%Y%m%d'),
                    'strType': 'C'
                }

                logger.info(f"Fetching announcements from {current_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}")

                # Make the API request
                response = requests.get(api_url, headers=headers, params=params, timeout=30)
                
                if response.status_code == 200:
                    try:
                        data = response.json()
                        if isinstance(data.get('Table'), list):
                            for item in data['Table']:
                                try:
                                    # Get announcement details with safe defaults
                                    title = safe_get(item, 'NEWSSUB')
                                    date_str = safe_get(item, 'NEWS_DT')
                                    company = safe_get(item, 'SLONGNAME')
                                    security_code = safe_get(item, 'SCRIP_CD')
                                    category = safe_get(item, 'CATEGORYNAME')
                                    attachment_name = safe_get(item, 'ATTACHMENTNAME')
                                    
                                    # Skip if no title
                                    if not title:
                                        continue
                                    
                                    # Check if announcement is infrastructure-related
                                    is_infra = is_infrastructure_related(title, company, security_code)
                                    if not is_infra:
                                        continue
                                    
                                    # Parse date with better error handling
                                    try:
                                        # First try the ISO format that BSE actually uses
                                        date = datetime.strptime(date_str.split('.')[0], '%Y-%m-%dT%H:%M:%S')
                                    except ValueError:
                                        try:
                                            # Try the standard BSE format as fallback
                                            date = datetime.strptime(date_str, '%d %b %Y')
                                        except ValueError:
                                            try:
                                                # Try simple date format as last resort
                                                date = datetime.strptime(date_str, '%Y-%m-%d')
                                            except ValueError:
                                                logger.warning(f"Could not parse date '{date_str}' for announcement: {title}")
                                                # Use the date from the current batch as fallback
                                                date = current_date
                                    
                                    # Create attachment URLs exactly as in the original
                                    attachment_url = f"http://www.bseindia.com/stockinfo/AnnPdfOpen.aspx?Pname={item.get('ATTACHMENTNAME', '')}"
                                    # Ensure there's no whitespace in the attachment URL
                                    attachment_url = attachment_url.strip()
                                    xbrl_url = f"https://www.bseindia.com/Msource/90D/CorpXbrlGen.aspx?Bsenewid={item.get('NEWSID', '')}&Scripcode={security_code}"
                                    
                                    # Extract project type from title and company
                                    project_type = extract_project_type(title + " " + company)
                                    
                                    # Create announcement object with the parsed date
                                    announcement = BSEAnnouncement(
                                        title=title,
                                        date=date.replace(microsecond=0),  # Remove microseconds for cleaner output
                                        company=company,
                                        security_code=security_code,
                                        category=category,
                                        attachment_url=attachment_url,
                                        xbrl_url=xbrl_url,
                                        is_infra_related=is_infra,
                                        project_type=project_type
                                    )
                                    announcements.append(announcement)
                                    if is_infra:
                                        infra_announcements.append(announcement)
                                    logger.debug(f"Added announcement: {title}")
                                    
                                except Exception as e:
                                    logger.error(f"Error processing announcement: {str(e)}")
                                    continue
                                    
                            logger.info(f"Found {len(infra_announcements)} infrastructure-related announcements in this batch")
                        else:
                            logger.error("Invalid response format: 'Table' not found or not a list")
                    except json.JSONDecodeError:
                        logger.error("Failed to parse JSON response")
                else:
                    logger.error(f"Failed to fetch announcements: HTTP {response.status_code}")
                
                # Move to next month
                current_date = end_date + timedelta(days=1)
                
                # Add delay between requests to avoid rate limiting
                time.sleep(1)
                
            except Exception as e:
                logger.error(f"Error during API request: {str(e)}")
                # Move to next month even if there's an error
                current_date = current_date + timedelta(days=30)
        
        # Sort announcements by date (newest first)
        infra_announcements.sort(key=lambda x: x.date, reverse=True)
        
        # Extract PDF content from announcements and further details
        for announcement in infra_announcements:
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
                                    combined_text = title + " " + company + " " + full_text
                                    
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
        for announcement in infra_announcements:
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
            # Save to the same location as the original
            output_path = os.path.join(os.path.dirname(__file__), 'bse_announcements2.json')
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(
                    formatted_announcements,
                    f,
                    indent=2,
                    default=str
                )
            logger.info(f"Total infrastructure announcements found: {len(formatted_announcements)}")
            logger.info(f"Saved infrastructure announcements to {output_path}")
        except Exception as e:
            logger.error(f"Error saving announcements to JSON: {str(e)}")
        
        return formatted_announcements
        
    except Exception as e:
        logger.error(f"Error in scrape_bse_announcements: {str(e)}")
        return []

if __name__ == "__main__":
    scrape_bse_announcements()