"""
Steel Contract News Qualification Pipeline

This module implements a pipeline with two AI model tasks:
1. Headline deduplication - Check if the news has been previously sent to the sales team
2. Content qualification - Determine if the news is worth sending based on steel requirements 
   and potential for selling steel to the company in the news

Supports both DeepSeek R1 and Google Gemini models, with fallback logic.
"""

import os
import json
import asyncio
import csv
from datetime import datetime
from typing import List, Dict, Any, Optional
from pydantic import BaseModel

# Try to use langchain's model integrations
try:
    from langchain_deepseek import ChatDeepSeek
    DEEPSEEK_AVAILABLE = True
except ImportError:
    DEEPSEEK_AVAILABLE = False

try:
    from langchain_google_genai import ChatGoogleGenerativeAI
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False

# Import ContractNews model from the crawl4ai_agent module
from crawl4ai_agent import ContractNews

# Configuration
HEADLINES_FILE = "sent_headlines.json"
QUALIFIED_NEWS_FILE = "qualified_news.csv"

class NewsQualificationPipeline:
    """Pipeline for processing contract news with AI models."""
    
    def __init__(self, deepseek_api_key: Optional[str] = None, gemini_api_key: Optional[str] = None):
        """
        Initialize the news qualification pipeline.
        
        Args:
            deepseek_api_key: DeepSeek API key. If None, tries to use the DEEPSEEK_API_KEY environment variable.
            gemini_api_key: Gemini API key. If None, tries to use the GEMINI_API_KEY environment variable.
        """
        self.deepseek_api_key = deepseek_api_key or os.environ.get("DEEPSEEK_API_KEY")
        self.gemini_api_key = gemini_api_key or os.environ.get("GEMINI_API_KEY")
        
        if not self.deepseek_api_key and not self.gemini_api_key:
            raise ValueError("Neither DeepSeek nor Gemini API keys are available")
        
        # Log the API keys
        print(f"DeepSeek API Key: {self.deepseek_api_key}")
        print(f"Gemini API Key: {self.gemini_api_key}")

        self.headlines_file = HEADLINES_FILE
        self.qualified_news_file = QUALIFIED_NEWS_FILE
        
        # Load previously sent headlines
        self.sent_headlines = self._load_sent_headlines()
        
        # Initialize API clients
        self.deepseek = None
        self.gemini = None
        
        # Try to initialize DeepSeek
        if self.deepseek_api_key and DEEPSEEK_AVAILABLE:
            try:
                self.deepseek = ChatDeepSeek(
                    model="deepseek-reasoner",
                    api_key=self.deepseek_api_key
                )
                print("DeepSeek model initialized successfully")
            except Exception as e:
                print(f"Failed to initialize DeepSeek model: {e}")
        
        # Try to initialize Gemini
        if self.gemini_api_key and GEMINI_AVAILABLE:
            try:
                self.gemini = ChatGoogleGenerativeAI(
                    model="gemini-2.0-flash",
                    api_key=self.gemini_api_key,
                    temperature=0.2,
                )
                print("Gemini model initialized successfully")
            except Exception as e:
                print(f"Failed to initialize Gemini model: {e}")
                
        if not self.deepseek and not self.gemini:
            print("WARNING: No AI models available. Will use direct API calls.")
    
    def _load_sent_headlines(self) -> List[str]:
        """Load previously sent headlines from file."""
        if not os.path.exists(self.headlines_file):
            return []
        
        try:
            with open(self.headlines_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, FileNotFoundError):
            print(f"Error loading headlines from {self.headlines_file}, starting with empty list")
            return []
    
    def _save_sent_headlines(self):
        """Save sent headlines to file."""
        with open(self.headlines_file, 'w', encoding='utf-8') as f:
            json.dump(self.sent_headlines, f, ensure_ascii=False, indent=2)
    
    async def _check_headline_duplicate(self, headline: str) -> bool:
        """
        Check if headline is a duplicate using AI.
        
        Args:
            headline: The headline to check
            
        Returns:
            True if duplicate, False otherwise
        """
        prompt = f"""
        You are a news deduplication system. Your task is to check if a news headline is semantically similar 
        to any headlines in our database of previously sent news.

        Here are the previously sent headlines:
        {json.dumps(self.sent_headlines, indent=2)}

        New headline to check:
        "{headline}"

        Answer with EXACTLY ONE WORD: either "DUPLICATE" if this headline is semantically equivalent 
        to any in the list (meaning it refers to the same news event, even if worded differently) 
        or "UNIQUE" if it represents news we haven't seen before.
        """
        
        result = await self._call_ai_model(prompt)
        is_duplicate = "DUPLICATE" in result.upper()
        return is_duplicate
    
    async def _qualify_news_content(self, news: ContractNews) -> Dict[str, Any]:
        """
        Qualify news content using AI.
        
        Args:
            news: The news item to qualify
            
        Returns:
            Dictionary with qualification results
        """
        prompt = f"""
You are a Steel Sales Lead Qualification System for a steel manufacturing company. Your task is to:
1. Identify the industry and sub-category of the project
2. Determine if the news article about a contract award or project is worth sending to our sales team for potential steel sales

You need to evaluate this news to determine:
1. Whether the project would require significant steel materials
2. Whether we could potentially sell steel to the company mentioned in the news (not to the government)
3. The specific potential steel requirements (types, quantities if mentioned)
4. The urgency/timeline of the opportunity


### ALLOWED TAGS:
- `Automotive-Confirmed`  
- `Automotive-Predictive_Alert`  
- `Infrastructure-Contract_Won`  
- `Infrastructure-Ongoing_Tender`  
- `Realty-Announced`  
- `Realty-Predictive_Alert`  
- `Renewable_Energy-Contract_Won`  
- `Renewable_Energy-Ongoing_Tender`  
- `Renewable_Energy-Predictive_Alert` 


News article details:
Title: {news.title}
Company: {news.company}
Project Type: {news.project_type}
Location: {news.location}
Contract Value: {news.contract_value}
Date: {news.date_published}
Description: {news.description}

Here are important criteria:
- First identify the industry and sub-category from the options above
- Government entities are **not** direct targets for steel sales
- Small-scale IT or service contracts typically don't require significant steel
- Construction, infrastructure, manufacturing, energy projects often need substantial steel
- The contract value should be significant enough to indicate large material requirements
- We want to focus on opportunities where the company (not the government) would be purchasing steel

Provide your analysis in the following JSON format only:
{{
    "qualified": true/false,
    "tag": "Industry-SubCategory",  # MUST MATCH ALLOWED TAGS ABOVE
    "sub_category": "Specific sub-category from the provided options",
    "steel_requirements": "Detailed description of likely steel requirements",
    "potential_value": "Estimated percentage of the contract value that might be spent on steel",
    "target_company": "The specific company that would potentially purchase the steel",
    "urgency": "high/medium/low",
    "reasoning": "Your detailed reasoning including industry classification justification"
}}

Response MUST be valid JSON.
"""
        result = await self._call_ai_model(prompt)
        
        # Extract JSON from the response
        try:
            # Find JSON in the response using simple heuristic
            start_idx = result.find('{')
            end_idx = result.rfind('}') + 1
            if start_idx >= 0 and end_idx > start_idx:
                json_str = result[start_idx:end_idx]
                return json.loads(json_str)
            else:
                return {"qualified": False, "reasoning": "Failed to parse AI model response"}
        except (json.JSONDecodeError, ValueError) as e:
            print(f"Error parsing qualification result: {e}")
            return {"qualified": False, "reasoning": f"Failed to parse AI model response: {str(e)}"}
    
    async def _call_ai_model(self, prompt: str) -> str:
        """Call AI models with fallback logic."""
        # Try DeepSeek first if available
        if self.deepseek:
            try:
                print("Trying DeepSeek model...")
                response = await self.deepseek.ainvoke(prompt)
                return response.content
            except Exception as e:
                print(f"Error calling DeepSeek API: {e}")
                # Fall through to next model
        
        # Try Gemini if available
        if self.gemini:
            try:
                print("Trying Gemini model...")
                from langchain.schema import HumanMessage
                response = await self.gemini.ainvoke([HumanMessage(content=prompt)])
                return response.content
            except Exception as e:
                print(f"Error calling Gemini API: {e}")
                # Fall through to direct API calls
        
        # Direct API calls as last resort
        # Try DeepSeek direct API
        if self.deepseek_api_key:
            try:
                import requests
                print("Trying DeepSeek direct API call...")
                headers = {
                    "Authorization": f"Bearer {self.deepseek_api_key}",
                    "Content-Type": "application/json"
                }
                payload = {
                    "model": "deepseek-reasoner",
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.1
                }
                response = requests.post(
                    "https://api.deepseek.com/v1/chat/completions", 
                    headers=headers, 
                    json=payload
                )
                response.raise_for_status()
                return response.json()["choices"][0]["message"]["content"]
            except Exception as e:
                print(f"Error calling DeepSeek API directly: {e}")
        
        # Try Gemini direct API
        if self.gemini_api_key:
            try:
                import google.generativeai as genai
                print("Trying Gemini direct API call...")
                genai.configure(api_key=self.gemini_api_key)
                model = genai.GenerativeModel('gemini-pro')
                response = model.generate_content(prompt)
                return response.text
            except Exception as e:
                print(f"Error calling Gemini API directly: {e}")
        
        # If all else fails
        raise Exception("All AI model calls failed")
    
    async def process_news(self, news_items: List[ContractNews]) -> List[Dict[str, Any]]:
        """
        Process a list of news items through the AI pipeline.
        
        Args:
            news_items: List of news items to process
            
        Returns:
            List of dictionaries containing both news items and their qualifications
        """
        qualified_news = []
        newly_sent_headlines = []
        
        print(f"\nProcessing {len(news_items)} news items through the AI pipeline...\n")
        
        for i, news in enumerate(news_items, 1):
            print(f"[{i}/{len(news_items)}] Processing: {news.title}")
            
            try:
                # Task 1: Check for headline duplication
                is_duplicate = await self._check_headline_duplicate(news.title)
                if is_duplicate:
                    print(f"  ❌ Headline is a duplicate, skipping")
                    continue
                
                # Task 2: Qualify news content
                qualification = await self._qualify_news_content(news)
                is_qualified = qualification.get("qualified", False)
                
                if is_qualified:
                    print(f"  ✓ News qualified: {qualification.get('reasoning', '')[:100]}...")
                    # Create a dictionary with both news and qualification data
                    qualified_item = {
                        "news": news,
                        "qualification": qualification
                    }
                    qualified_news.append(qualified_item)
                    newly_sent_headlines.append(news.title)
                else:
                    print(f"  ❌ News not qualified: {qualification.get('reasoning', '')[:100]}...")
            except Exception as e:
                print(f"  ❌ Error processing news: {str(e)}")
        
        # Update sent headlines list
        if newly_sent_headlines:
            self.sent_headlines.extend(newly_sent_headlines)
            self._save_sent_headlines()
            
            # Save qualified news to CSV
            self._save_qualified_news(qualified_news)
        
        print(f"\nAI pipeline completed: {len(qualified_news)}/{len(news_items)} news qualified\n")
        return qualified_news
    
    def _save_qualified_news(self, news_items: List[Dict[str, Any]]):
        """Save qualified news to a CSV file."""
        if not news_items:
            return
        
        with open(self.qualified_news_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            
            # Write header
            writer.writerow([
                "Title", 
                "Company", 
                "Project Type", 
                "Location", 
                "Contract Value", 
                "Date Published", 
                 "Tag",  # Combined Industry-SubCategory
                "Steel Requirements",
                "Potential Value",
                "Target Company",
                "Urgency",
                "Reasoning"
            ])
            
            # Write data
            for item in news_items:
                news = item["news"]
                qualification = item["qualification"]
                writer.writerow([
                    news.title,
                    news.company,
                    news.project_type,
                    news.location,
                    news.contract_value,
                    news.date_published,
                    qualification.get("tag", ""),  # e.g., "Automotive-Confirmed"
                    qualification.get("steel_requirements", ""),
                    qualification.get("potential_value", ""),
                    qualification.get("target_company", ""),
                    qualification.get("urgency", ""),
                    qualification.get("reasoning", "")
                ])
        
        print(f"Saved {len(news_items)} qualified news items to {self.qualified_news_file}")

async def main():
    """Main function to run the AI pipeline."""
    try:
        from crawl4ai_agent import main as crawl_main
        # Step 1: Run the crawler to get news
        await crawl_main()
        
        # Step 2: Load the scraped news
        from crawl4ai_agent import ContractNews
        news_items = []
        
        try:
            with open("contract_news.csv", 'r', newline='', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    news_items.append(ContractNews(
                        title=row["Title"],
                        company=row["Company"],
                        project_type=row["Project Type"],
                        location=row["Location"],
                        contract_value=row["Contract Value"],
                        date_published=row["Date Published"],
                        source_url=row["Source URL"],
                        description=row["Description"]
                    ))
        except Exception as e:
            print(f"Error loading news from CSV: {e}")
            return
        
        if not news_items:
            print("No news items found")
            return
        
        # Step 3: Process through AI pipeline
        pipeline = NewsQualificationPipeline()
        qualified_news = await pipeline.process_news(news_items)
        
        # Step 4: Display results
        print("\n===== QUALIFIED STEEL CONTRACT NEWS =====\n")
        for i, item in enumerate(qualified_news, 1):
            news = item["news"]
            qualification = item["qualification"]
            print(f"[{i}] {news.title}")
            print(f"    Company: {news.company}")
            print(f"    Project: {news.project_type} in {news.location}")
            print(f"    Value: {news.contract_value}")
            print(f"    Steel Requirements: {qualification.get('steel_requirements', '')}")
            print(f"    Potential Value: {qualification.get('potential_value', '')}")
            print(f"    Target Company: {qualification.get('target_company', '')}")
            print(f"    Urgency: {qualification.get('urgency', '')}")
            print(f"    Reasoning: {qualification.get('reasoning', '')[:150]}..." if len(qualification.get('reasoning', '')) > 150 else f"    Reasoning: {qualification.get('reasoning', '')}")
            print()
    
    except Exception as e:
        print(f"Error running AI pipeline: {e}")

if __name__ == "__main__":
    asyncio.run(main())
