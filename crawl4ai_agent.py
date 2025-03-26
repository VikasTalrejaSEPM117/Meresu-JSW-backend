#!/usr/bin/env python3
"""
Steel Contract News Agent - An AI agent that uses Crawl4AI to find news about 
companies winning contracts in India that would require steel.
"""
import os
import asyncio
import json
import re
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any
from dotenv import load_dotenv
from pydantic import BaseModel, Field
import csv
import importlib
import sys

# Import Crawl4AI components
from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig, CacheMode, LLMConfig
from crawl4ai.extraction_strategy import LLMExtractionStrategy, JsonCssExtractionStrategy
from playwright.async_api import Page, BrowserContext

# Load environment variables
load_dotenv()

# Validate required environment variables
required_env_vars = ["GEMINI_API_KEY"]
for var in required_env_vars:
    if not os.getenv(var):
        raise ValueError(f"{var} is not set. Please add it to your .env file.")

# Data models
class ContractNews(BaseModel):
    """Model for contract news data."""
    title: str = Field(..., description="Title of the news article")
    company: str = Field(..., description="Company that won the contract")
    project_type: str = Field(..., description="Type of project (infrastructure, railway, etc.)")
    location: str = Field(..., description="Location in India where the project will be executed")
    contract_value: Optional[str] = Field(None, description="Value of the contract if available")
    date_published: str = Field(..., description="Date when the news was published")
    source_url: str = Field(..., description="URL of the news source")
    description: str = Field(..., description="Brief description of the project and contract")

class SearchResult(BaseModel):
    """Model for search results."""
    keyword: str
    results: List[ContractNews]

async def search_news_with_crawl4ai(keyword: str = None, days_back: int = 30, source_type: str = "all") -> List[ContractNews]:
    """
    Search for contract news using Crawl4AI.
    
    Args:
        keyword: Search keyword (optional, only used for search engines)
        days_back: Number of days back to search
        source_type: Type of source to search ("all", "news_site", or "search_engine")
    
    Returns:
        List of contract news items
    """
    print(f"Searching for news about: {keyword}")
    
    # Calculate date range for search
    end_date = datetime.now()
    start_date = end_date - timedelta(days=days_back)
    date_range = f"{start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}"
    
    # List of news sources to search
    news_sources = []
    
    # Add sources based on type
    if source_type == "all" or source_type == "news_site":
        # Static news sites that don't require keywords
        news_sources.extend([
            {
                "name": "Economic Times Infrastructure",
                "url": "https://economictimes.indiatimes.com/industry/indl-goods/svs/construction/articlelist/13358759.cms",
                "type": "news_site"
            },
            {
                "name": "Construction World",
                "url": "https://www.constructionworld.in/latest-infrastructure-news",
                "type": "news_site"
            },
            {
                "name": "Business Standard Infrastructure",
                "url": "https://www.business-standard.com/industry/infrastructure",
                "type": "news_site"
            },
            {
                "name": "BidDetail EPC",
                "url": "https://www.biddetail.com/procurement-news/epc-contract",
                "type": "news_site"
            },
            {
                "name": "News on Projects",
                "url": "https://newsonprojects.com",
                "type": "news_site"
            },
            {
                "name": "Construction Opportunities",
                "url": "https://constructionopportunities.in/",
                "type": "news_site"
            },
            {
                "name": "Project X India",
                "url": "https://projectxindia.com",
                "type": "news_site"
            },
            {
                "name": "Metro Rail Today",
                "url": "https://metrorailtoday.com",
                "type": "news_site"
            },
            {
                "name": "The Metro Rail Guy",
                "url": "https://themetrorailguy.com",
                "type": "news_site"
            },
            {
                "name": "Projects Today",
                "url": "https://www.projectstoday.com",
                "type": "news_site"
            },
            {
                "name": "Biltrax",
                "url": "https://www.biltrax.com",
                "type": "news_site"
            }
        ])
    
    # Add search engine if keyword is provided and source type is appropriate
    if keyword and (source_type == "all" or source_type == "search_engine"):
        # Add "latest" to the keyword for better results
        search_term = f"latest {keyword}"
        
        news_sources.append({
            "name": f"Google News Search - {keyword}",
            "url": f"https://www.google.com/search?q={search_term}+contract+win+india&tbm=nws&tbs=qdr:m",
            "type": "search_engine"
        })
    
    if not news_sources:
        return []
        
    # Configure browser
    browser_config = BrowserConfig(
        headless=True,
        verbose=True,
    )
    
    # Create crawler run config without extraction strategy initially
    crawler_config = CrawlerRunConfig(
        cache_mode=CacheMode.BYPASS,  # Always get fresh content
        wait_for='body',  # Wait for body to load
        js_code="""
        // Wait for the page to load and scroll down to make sure all content is loaded
        function waitForElement(selector, timeout = 30000) {
            return new Promise((resolve, reject) => {
                const startTime = Date.now();
                const checkElement = () => {
                    const element = document.querySelector(selector);
                    if (element) {
                        resolve(element);
                    } else if (Date.now() - startTime > timeout) {
                        reject(new Error(`Timeout waiting for ${selector}`));
                    } else {
                        setTimeout(checkElement, 500);
                    }
                };
                checkElement();
            });
        }
        
        // Wait for page content to load
        await waitForElement('body');
        
        // Scroll down to load all content
        for (let i = 0; i < 5; i++) {
            window.scrollBy(0, window.innerHeight);
            await new Promise(r => setTimeout(r, 1000));
        }
        
        // Wait a bit for any lazy-loaded content
        await new Promise(r => setTimeout(r, 2000));
        """
    )
    
    # Create and run the crawler with hooks for better page loading
    async with AsyncWebCrawler(config=browser_config) as crawler:
        # Define hook functions for better page interaction
        async def on_page_context_created(page: Page, context: BrowserContext, **kwargs):
            print("[HOOK] Setting up page & context")
            # Set a larger viewport for better rendering
            await page.set_viewport_size({"width": 1920, "height": 1080})
            return page
        
        async def after_goto(page: Page, context: BrowserContext, url: str, response, **kwargs):
            print(f"[HOOK] Successfully loaded: {url}")
            
            # Handle Google News search specifically
            if "google.com/search" in url:
                try:
                    print("[HOOK] Handling Google News search...")
                    
                    # Wait for search results to load
                    await page.wait_for_selector('div[role="main"]', timeout=30000)
                    
                    # If there's a Tools button, click it to access date filters
                    tools_button = await page.query_selector('div[aria-label="Search tools"]')
                    if tools_button:
                        await tools_button.click()
                        await page.wait_for_timeout(1000)
                        
                        # Look for time filter dropdown
                        time_filter = await page.query_selector('div[aria-label="Recent"]')
                        if time_filter:
                            await time_filter.click()
                            await page.wait_for_timeout(1000)
                            
                            # Select "Past month" or similar option
                            past_month = await page.query_selector('div[aria-label="Past month"]')
                            if past_month:
                                await past_month.click()
                                await page.wait_for_timeout(2000)
                except Exception as e:
                    print(f"[HOOK] Error handling Google News: {str(e)}")
            
            return page
        
        async def before_retrieve_html(page: Page, context: BrowserContext, **kwargs):
            print("[HOOK] Performing final actions before retrieving HTML")
            
            # Scroll to make sure all content is loaded
            for i in range(5):
                await page.evaluate(f"window.scrollBy(0, {i * 500});")
                await page.wait_for_timeout(500)
            
            # Wait for a moment to let any lazy-loaded content appear
            await page.wait_for_timeout(2000)
            
            # Try to expand any collapsed sections if they exist
            try:
                # Look for "View More" or "Load More" buttons
                more_buttons = await page.query_selector_all('button:text-matches("View More|Load More|Show More")')
                for button in more_buttons:
                    await button.click()
                    await page.wait_for_timeout(1000)  # Wait a bit after clicking
            except Exception as e:
                print(f"[HOOK] Error expanding content: {str(e)}")
            
            # Scroll again after expanding
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight);")
            await page.wait_for_timeout(1000)
            
            return page
        
        # Attach hooks to the crawler
        crawler.crawler_strategy.set_hook("on_page_context_created", on_page_context_created)
        crawler.crawler_strategy.set_hook("after_goto", after_goto)
        crawler.crawler_strategy.set_hook("before_retrieve_html", before_retrieve_html)
        
        all_results = []
        
        # Crawl each news source
        for source in news_sources:
            print(f"Crawling {source['name']} at {source['url']}")
            try:
                # Run the crawler on the current source
                result = await crawler.arun(url=source['url'], config=crawler_config)
                
                # Get the markdown content
                if result.markdown:
                    print(f"Successfully retrieved content from {source['name']}")
                    
                    # Use Gemini to extract structured data from the markdown
                    extracted_items = await extract_with_gemini(
                        result.markdown, 
                        keyword, 
                        source['url'], 
                        date_range
                    )
                    
                    if extracted_items:
                        print(f"Found {len(extracted_items)} news items from {source['name']}")
                        all_results.extend(extracted_items)
                    else:
                        print(f"No relevant news items found in {source['name']}")
                else:
                    print(f"No content retrieved from {source['name']}")
                    
            except Exception as e:
                print(f"Error crawling {source['name']}: {str(e)}")
            
            # Add delay between crawling different sources
            if source != news_sources[-1]:
                print("Waiting 5 seconds before crawling next source...")
                await asyncio.sleep(5)
    
    print(f"Total news items found: {len(all_results)}")
    return all_results

async def extract_with_gemini(markdown_content: str, keyword: str, source_url: str, date_range: str) -> List[ContractNews]:
    """
    Extract contract news from markdown content using Gemini.
    
    Args:
        markdown_content: Markdown content from the crawler
        keyword: Original search keyword
        source_url: URL of the source
        date_range: Date range for filtering
    
    Returns:
        List of contract news items
    """
    from langchain_google_genai import ChatGoogleGenerativeAI
    from langchain.schema import HumanMessage
    
    # Create Gemini model
    model = ChatGoogleGenerativeAI(
        model="gemini-2.0-flash-exp",
        api_key=os.environ.get("GEMINI_API_KEY"),
        temperature=0.2,
    )
    
    # Create extraction prompt
    prompt = f"""
    Extract information about companies winning contracts in India that would require steel.
    Focus on contracts related to infrastructure, construction, railways, highways, metros, buildings, etc.
    
    The contract news must be from within this date range: {date_range}
    
    For each relevant contract news article, extract the following in JSON format:
    {{
        "title": "The title of the news article",
        "company": "The name of the company that won the contract",
        "project_type": "The type of project (infrastructure, railway, highway, etc.)",
        "location": "The location in India where the project will be executed",
        "contract_value": "The value of the contract if available",
        "date_published": "The date when the news was published (YYYY-MM-DD format)",
        "source_url": "{source_url}",
        "description": "A brief description of the project and contract"
    }}
    
    IMPORTANT:
    - Only extract news about contract wins, not general industry news
    - Focus on projects that would require steel in their execution
    - Consider ALL types of construction, infrastructure, and manufacturing projects as potential steel consumers
    - Include projects involving buildings, transportation, energy, water, manufacturing facilities, oil & gas, etc.
    - When in doubt about steel requirements, include the contract rather than exclude it
    - If you can't find all the information, provide as much as you can
    - Format dates as YYYY-MM-DD
    - Return the data as a JSON array of objects, even if there's only one item
    - If no relevant news is found, return an empty array []
    
    Here's the content to extract from:
    
    {markdown_content[:50000]}  # Limit content length to avoid token limits
    """
    
    try:
        # Call Gemini to extract structured data
        response = await model.ainvoke([HumanMessage(content=prompt)])
        
        # Parse the response
        response_text = response.content
        
        # Extract JSON from the response
        import re
        import json
        
        # Look for JSON array in the response
        json_match = re.search(r'\[\s*\{.*?\}\s*\]', response_text, re.DOTALL)
        if json_match:
            json_str = json_match.group(0)
            try:
                extracted_data = json.loads(json_str)
                
                # Convert to ContractNews objects
                result = []
                for item in extracted_data:
                    try:
                        # Ensure required fields are present
                        if not all(k in item for k in ["title", "company", "project_type", "location", "date_published", "description"]):
                            print(f"Skipping incomplete item: {item}")
                            continue
                        
                        # Create ContractNews object
                        news_item = ContractNews(
                            title=item["title"],
                            company=item["company"],
                            project_type=item["project_type"],
                            location=item["location"],
                            contract_value=item.get("contract_value", "N/A"),
                            date_published=item["date_published"],
                            source_url=item.get("source_url", source_url),
                            description=item["description"]
                        )
                        
                        result.append(news_item)
                    except Exception as e:
                        print(f"Error processing news item: {str(e)}")
                
                return result
            except json.JSONDecodeError:
                print("Failed to parse JSON from response")
                return []
        else:
            print("No JSON array found in response")
            return []
    except Exception as e:
        print(f"Error extracting with Gemini: {str(e)}")
        return []

def save_contract_news_to_csv(news_items: List[ContractNews], filename: str = "contract_news.csv"):
    """Save contract news to a CSV file."""
    import csv
    
    # Debug: Print URLs before saving
    print(f"\nVerifying source URLs before saving to {filename}:")
    for i, item in enumerate(news_items[:5]):  # Just show first 5 for brevity
        print(f"  Item {i+1}: {item.title[:30]}... -> URL: {item.source_url}")
    if len(news_items) > 5:
        print(f"  ... and {len(news_items)-5} more items")
    
    # Write to CSV file
    with open(filename, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        
        # Write header
        writer.writerow([
            "Title", 
            "Company", 
            "Project Type", 
            "Location", 
            "Contract Value", 
            "Date Published", 
            "Source URL", 
            "Description"
        ])
        
        # Write data
        for item in news_items:
            writer.writerow([
                item.title,
                item.company,
                item.project_type,
                item.location,
                item.contract_value,
                item.date_published,
                item.source_url,
                item.description
            ])
    
    print(f"Saved {len(news_items)} news items to {filename}")

def read_csv_to_contract_news(filename: str) -> List[ContractNews]:
    """Read a CSV file and convert to ContractNews objects."""
    news_items = []
    
    try:
        with open(filename, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                try:
                    news_item = ContractNews(
                        title=row["Title"],
                        company=row["Company"],
                        project_type=row["Project Type"],
                        location=row["Location"],
                        contract_value=row["Contract Value"],
                        date_published=row["Date Published"],
                        source_url=row["Source URL"],
                        description=row["Description"]
                    )
                    news_items.append(news_item)
                except Exception as e:
                    print(f"Error converting row to ContractNews: {str(e)}")
    except Exception as e:
        print(f"Error reading CSV file {filename}: {str(e)}")
        
    return news_items

def merge_contract_news_files(output_file: str, input_files: List[str]) -> List[ContractNews]:
    """Merge multiple CSV files of contract news into one, removing duplicates."""
    all_news = []
    seen_titles = set()
    
    # Read each input file
    for filename in input_files:
        if os.path.exists(filename):
            news_items = read_csv_to_contract_news(filename)
            print(f"Read {len(news_items)} items from {filename}")
            
            # Add unique items
            for item in news_items:
                if item.title not in seen_titles:
                    seen_titles.add(item.title)
                    all_news.append(item)
    
    # Save merged results
    if all_news:
        save_contract_news_to_csv(all_news, output_file)
        print(f"Merged {len(all_news)} unique items to {output_file}")
    
    return all_news

def run_bse_scrapers():
    """Run both BSE scrapers and save results to separate CSV files."""
    results = []
    
    # Check if BSE scraper modules exist
    if os.path.exists("bse_scraper.py"):
        print("\nRunning BSE Scraper 1...")
        try:
            # Import the module
            sys.path.append(os.getcwd())
            bse_scraper = importlib.import_module("bse_scraper")
            
            # Run the scraper
            announcements = bse_scraper.scrape_bse_announcements()
            
            # Debug: Print first few announcements to see their structure
            if announcements:
                print(f"\nReceived {len(announcements)} announcements from BSE Scraper 1")
                print("Sample announcement structure:")
                sample = announcements[0] if announcements else {}
                
                # Print the raw announcement
                print(f"Raw announcement: {type(sample)}")
                if hasattr(sample, '__dict__'):
                    print(json.dumps(sample.__dict__, indent=2, default=str))
                else:
                    print(json.dumps(sample, indent=2, default=str))
            
            # Convert to ContractNews and save
            if announcements:
                news_items = []
                for ann in announcements:
                    try:
                        # Handle both dictionary and object responses
                        if hasattr(ann, '__dict__'):
                            # It's an object, convert to dict
                            ann_dict = ann.__dict__
                            # Check if we need to convert from BSEAnnouncement model
                            title = getattr(ann, 'title', None)
                            company = getattr(ann, 'company', None)
                            project_type = getattr(ann, 'project_type', None)
                            location = getattr(ann, 'location', None)
                            contract_value = getattr(ann, 'contract_value', None)
                            date_obj = getattr(ann, 'date', None)
                            description = getattr(ann, 'pdf_content', getattr(ann, 'description', None))
                            attachment_url = getattr(ann, 'attachment_url', None)
                        else:
                            # It's already a dictionary - handle the exact JSON structure 
                            # from the example
                            title = ann.get("Title", ann.get("title", ""))
                            company = ann.get("Company", ann.get("company", ""))
                            project_type = ann.get("Project Type", ann.get("project_type", "Infrastructure"))
                            location = ann.get("Location", ann.get("location", "India"))
                            contract_value = ann.get("Contract Value", ann.get("contract_value", "Not specified"))
                            date_obj = ann.get("Date", ann.get("date", None))
                            description = ann.get("Description", ann.get("description", ""))
                            # Get attachment URL directly from the key used in the example
                            attachment_url = ann.get("attachment_url", None)
                        
                        # Handle date formatting
                        if isinstance(date_obj, datetime):
                            date_str = date_obj.strftime("%Y-%m-%d")
                        elif isinstance(date_obj, str):
                            date_str = date_obj
                        else:
                            date_str = datetime.now().strftime("%Y-%m-%d")
                        
                        # Debug: Print attachment URL if found
                        if attachment_url:
                            print(f"Found attachment URL for {title[:50]}...: {attachment_url}")
                            print(f"Description: {description[:100]}...")
                        
                        # Use attachment_url if available, otherwise fall back to default BSE URL
                        source_url = attachment_url if attachment_url else "https://www.bseindia.com/corporates/ann.html"
                        
                        news_item = ContractNews(
                            title=title or "",
                            company=company or "",
                            project_type=project_type or "Infrastructure",
                            location=location or "India",
                            contract_value=contract_value or "Not specified",
                            date_published=date_str,
                            source_url=source_url,
                            description=description or ""
                        )
                        news_items.append(news_item)
                    except Exception as e:
                        print(f"Error converting BSE announcement to ContractNews: {str(e)}")
                        print(f"Problematic announcement: {ann}")
                
                # Save to CSV
                save_contract_news_to_csv(news_items, "bse_scraper1_results.csv")
                print(f"Saved {len(news_items)} items from BSE Scraper 1")
                results.append("bse_scraper1_results.csv")
        except Exception as e:
            print(f"Error running BSE Scraper 1: {str(e)}")
    
    # Run BSE Scraper 2
    if os.path.exists("bse_scraper2.py"):
        print("\nRunning BSE Scraper 2...")
        try:
            # Import the module
            sys.path.append(os.getcwd())
            bse_scraper2 = importlib.import_module("bse_scraper2")
            
            # Run the scraper
            announcements = bse_scraper2.scrape_bse_announcements()
            
            # Debug: Print first few announcements to see their structure
            if announcements:
                print(f"\nReceived {len(announcements)} announcements from BSE Scraper 2")
                print("Sample announcement structure:")
                sample = announcements[0] if announcements else {}
                
                # Print the raw announcement
                print(f"Raw announcement: {type(sample)}")
                if hasattr(sample, '__dict__'):
                    print(json.dumps(sample.__dict__, indent=2, default=str))
                else:
                    print(json.dumps(sample, indent=2, default=str))
            
            # Convert to ContractNews and save
            if announcements:
                news_items = []
                for ann in announcements:
                    try:
                        # Handle both dictionary and object responses
                        if hasattr(ann, '__dict__'):
                            # It's an object, convert to dict
                            ann_dict = ann.__dict__
                            # Check if we need to convert from BSEAnnouncement model
                            title = getattr(ann, 'title', None)
                            company = getattr(ann, 'company', None)
                            project_type = getattr(ann, 'project_type', None)
                            location = getattr(ann, 'location', None)
                            contract_value = getattr(ann, 'contract_value', None)
                            date_obj = getattr(ann, 'date', None)
                            description = getattr(ann, 'pdf_content', getattr(ann, 'description', None))
                            attachment_url = getattr(ann, 'attachment_url', None)
                        else:
                            # It's already a dictionary - handle the exact JSON structure 
                            # from the example
                            title = ann.get("Title", ann.get("title", ""))
                            company = ann.get("Company", ann.get("company", ""))
                            project_type = ann.get("Project Type", ann.get("project_type", "Infrastructure"))
                            location = ann.get("Location", ann.get("location", "India"))
                            contract_value = ann.get("Contract Value", ann.get("contract_value", "Not specified"))
                            date_obj = ann.get("Date", ann.get("date", None))
                            description = ann.get("Description", ann.get("description", ""))
                            # Get attachment URL directly from the key used in the example
                            attachment_url = ann.get("attachment_url", None)
                        
                        # Handle date formatting
                        if isinstance(date_obj, datetime):
                            date_str = date_obj.strftime("%Y-%m-%d")
                        elif isinstance(date_obj, str):
                            date_str = date_obj
                        else:
                            date_str = datetime.now().strftime("%Y-%m-%d")
                        
                        # Debug: Print attachment URL if found
                        if attachment_url:
                            print(f"Found attachment URL for {title[:50]}...: {attachment_url}")
                            print(f"Description: {description[:100]}...")
                        
                        # Use attachment_url if available, otherwise fall back to default BSE URL
                        source_url = attachment_url if attachment_url else "https://www.bseindia.com/corporates/ann.html"
                        
                        news_item = ContractNews(
                            title=title or "",
                            company=company or "",
                            project_type=project_type or "Infrastructure",
                            location=location or "India",
                            contract_value=contract_value or "Not specified",
                            date_published=date_str,
                            source_url=source_url,
                            description=description or ""
                        )
                        news_items.append(news_item)
                    except Exception as e:
                        print(f"Error converting BSE announcement to ContractNews: {str(e)}")
                        print(f"Problematic announcement: {ann}")
                
                # Save to CSV
                save_contract_news_to_csv(news_items, "bse_scraper2_results.csv")
                print(f"Saved {len(news_items)} items from BSE Scraper 2")
                results.append("bse_scraper2_results.csv")
        except Exception as e:
            print(f"Error running BSE Scraper 2: {str(e)}")
    
    return results

def display_contract_news(news_items: List[ContractNews]):
    """Display contract news in a readable format."""
    if not news_items:
        print("No news items found.")
        return
    
    print("\n===== STEEL CONTRACT NEWS RESULTS =====\n")
    
    for i, item in enumerate(news_items, 1):
        print(f"[{i}] {item.title}")
        print(f"    Company: {item.company}")
        print(f"    Project: {item.project_type} in {item.location}")
        print(f"    Value: {item.contract_value}")
        print(f"    Date: {item.date_published}")
        print(f"    Source: {item.source_url}")
        print(f"    Description: {item.description[:150]}..." if len(item.description) > 150 else f"    Description: {item.description}")
        print()
    
    print(f"Total: {len(news_items)} news items found")

async def main():
    """Main function."""
    try:
        # Print welcome message
        print("Steel Contract News Agent (Combined Pipeline)")
        print("This agent will search for news about companies winning contracts in India")
        print("that would require steel in their execution.")
        print("-------------------------------------------------------------------")
        
        # Step 1: Run both BSE scrapers first
        print("\nStep 1: Running BSE Scrapers...")
        bse_result_files = run_bse_scrapers()
        
        # Step 2: Run Crawl4AI
        print("\nStep 2: Running Crawl4AI search...")
        
        # Define the search keywords
        keywords = [
            "Infrastructure contract wins",
            "Railway Contract wins",
            "Port development contract wins",
            "Highway contract wins",
            "EPC contract wins",
            "Data center contract wins",
            "Metro contract wins",
            "Bridge construction contract win",
            "Tunnel project contract win",
            "Airport expansion contract win",
            "Smart City development contract win",
            "Freight corridor contract win",
            "Transmission tower contract win",
            "Logistics park contract win",
            "Industrial corridor contract win",
            "Multimodal logistics contract win",
            "metro rail phase contract win",
            "oil and gas pipeline project",
            "wind energy contract wins"
        ]
        
        # Print the keywords
        print("Search keywords:")
        for i, keyword in enumerate(keywords, 1):
            print(f"{i}) {keyword}")
        print()
        
        # First, search static news sites once
        print("Searching static news sites...")
        all_news_items = await search_news_with_crawl4ai(source_type="news_site")
        
        # Then search Google News for each keyword
        for keyword in keywords:
            # Search for contract news using only search engines
            news_items = await search_news_with_crawl4ai(keyword, source_type="search_engine")
            
            # Add to overall results
            if news_items:
                all_news_items.extend(news_items)
        
        # Deduplicate news items by title
        unique_news_items = []
        seen_titles = set()
        for item in all_news_items:
            if item.title not in seen_titles:
                seen_titles.add(item.title)
                unique_news_items.append(item)
        
        # Save Crawl4AI results to its own CSV
        save_contract_news_to_csv(unique_news_items, "crawl4ai_results.csv")
        
        # Step 3: Merge all results
        print("\nStep 3: Merging all results...")
        all_files = bse_result_files + ["crawl4ai_results.csv"]
        merged_news = merge_contract_news_files("contract_news.csv", all_files)
        
        # Display the combined results
        display_contract_news(merged_news)
        
        print(f"\nSearch completed. Combined {len(merged_news)} unique news items from all sources.")
        print(f"Results saved to contract_news.csv")
        
    except Exception as e:
        print(f"Error: {str(e)}")

if __name__ == "__main__":
    asyncio.run(main())
