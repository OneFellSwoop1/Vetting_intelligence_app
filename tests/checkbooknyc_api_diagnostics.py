#!/usr/bin/env python3
"""
CheckbookNYC API Diagnostic Tool

This script helps diagnose and explore the NYC Checkbook OpenData API.
It tests multiple search methods and logs detailed information about each request and response.

How to use:
1. Make sure your .env file has the NYC_API_APP_TOKEN set
2. Run this script from the command line: python checkbooknyc_api_diagnostics.py
3. Enter a payee or agency name when prompted
4. Review the detailed results
"""

import os
import sys
import json
import requests
import logging
import time
from dotenv import load_dotenv

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("checkbooknyc_api_diagnostic.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger('checkbooknyc_api_diagnostic')

# Load environment variables
load_dotenv()
API_TOKEN = os.getenv("NYC_API_APP_TOKEN")
BASE_URL = "https://data.cityofnewyork.us/resource/mxwn-eh3b.json"  # Correct CheckbookNYC dataset

if not API_TOKEN:
    logger.error("NYC_API_APP_TOKEN not found in environment variables")
    print("\n❌ NYC_API_APP_TOKEN not found in environment variables. Check your .env file.")
    sys.exit(1)

headers = {
    'X-App-Token': API_TOKEN,
    'Accept': 'application/json',
    'User-Agent': 'CheckbookNYCDiagnostic/1.0'
}

def print_separator(title=""):
    width = 80
    if title:
        print(f"\n{'=' * 5} {title} {'=' * (width - 7 - len(title))}")
    else:
        print(f"\n{'=' * width}")

def test_api_connection():
    url = f"{BASE_URL}?$limit=1"
    print(f"\n⏳ Testing API connection to: {url}")
    try:
        response = requests.get(url, headers=headers, timeout=30)
        print(f"Response status code: {response.status_code}")
        if response.status_code == 200:
            print("✅ Connection successful!")
            return True
        else:
            print(f"❌ API request failed with status code: {response.status_code}")
            print(f"Error response: {response.text[:200]}")
            return False
    except Exception as e:
        print(f"❌ Connection error: {str(e)}")
        return False

def test_search_patterns(query, fiscal_year=None, page_size=10):
    print_separator(f"Testing Search Patterns for '{query}'")
    patterns = [
        {"name": "Payee Name", "params": {"payee_name": query}},
        {"name": "Agency Name", "params": {"agency_name": query}},
        {"name": "Payee Name (2023)", "params": {"payee_name": query, "fiscal_year": "2023"}},
        {"name": "Payee Name (2022)", "params": {"payee_name": query, "fiscal_year": "2022"}},
        {"name": "Contract Amount > $1M", "params": {"payee_name": query, "contract_amount": ">1000000"}},
    ]
    for pattern in patterns:
        params = pattern["params"].copy()
        params["$limit"] = page_size
        url = BASE_URL
        print(f"\n⏳ Trying {pattern['name']}...")
        logger.info(f"Testing pattern: {pattern['name']} - Params: {params}")
        try:
            start_time = time.time()
            response = requests.get(url, headers=headers, params=params, timeout=30)
            elapsed_time = time.time() - start_time
            print(f"Response status code: {response.status_code} (in {elapsed_time:.2f}s)")
            if response.status_code == 200:
                data = response.json()
                count = len(data)
                print(f"✅ Success! Found {count} results.")
                logger.info(f"Found {count} results for pattern: {pattern['name']}")
                if count > 0:
                    print("Preview:")
                    print(json.dumps(data[:2], indent=2) if count > 1 else json.dumps(data, indent=2))
            else:
                print(f"❌ Request failed: {response.text[:200]}")
                logger.warning(f"Request failed: {response.status_code} - {response.text[:200]}")
        except Exception as e:
            print(f"❌ Exception: {str(e)}")
            logger.error(f"Exception for pattern {pattern['name']}: {str(e)}")

def main():
    print("\nCheckbookNYC API Diagnostic Tool\n")
    if not test_api_connection():
        print("\n❌ API connection failed. Exiting.")
        return
    query = input("\nEnter a payee or agency name to search: ").strip()
    if not query:
        print("No query entered. Exiting.")
        return
    test_search_patterns(query)

if __name__ == "__main__":
    main() 