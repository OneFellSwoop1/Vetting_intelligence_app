"""
Vetting Intelligence Hub - Main Application

A comprehensive web application for searching and analyzing lobbying disclosure data 
and government contracts from multiple sources at the federal, state, and local levels.
"""

from flask import Flask, render_template, request, jsonify, url_for, redirect, flash, session, make_response
import os
import logging
import time
import traceback
import json
import urllib.parse
from datetime import datetime
from collections import defaultdict
from pathlib import Path

from dotenv import load_dotenv
from flask_wtf.csrf import CSRFProtect

# Import data sources
from data_sources.improved_senate_lda import ImprovedSenateLDADataSource
from data_sources.nyc import NYCLobbyingDataSource
from data_sources.nyc_checkbook import NYCCheckbookDataSource

# Import utilities
from utils.error_handling import api_error_handler, validate_search_params, handle_api_response
from utils.caching import app_cache, cached
from utils.visualization import LobbyingVisualizer

# Load environment variables
load_dotenv()

# Setup logging
log_dir = Path(__file__).parent / 'logs'
log_dir.mkdir(exist_ok=True)

# Configure logger
logger = logging.getLogger('vetting_hub')
logger.setLevel(logging.INFO)

# Create handlers
file_handler = logging.handlers.RotatingFileHandler(
    log_dir / 'app.log',
    maxBytes=10485760,  # 10MB
    backupCount=10
)
console_handler = logging.StreamHandler()

# Create formatters
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
file_handler.setFormatter(formatter)
console_handler.setFormatter(formatter)

# Add handlers
logger.addHandler(file_handler)
logger.addHandler(console_handler)

# Initialize Flask app
app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "vetting_intelligence_hub_secret_key")

# Add CSRF protection
csrf = CSRFProtect(app)

# Configure app
app.config['PERMANENT_SESSION_LIFETIME'] = 1800  # 30 minutes
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max upload size
app.config['WTF_CSRF_ENABLED'] = True  # Enable CSRF protection
app.config['TEMPLATES_AUTO_RELOAD'] = True  # Auto reload templates

# Get API keys from environment
LDA_API_KEY = os.getenv("LDA_API_KEY")
NYC_API_APP_TOKEN = os.getenv("NYC_API_APP_TOKEN")
NYC_API_SECRET = os.getenv("NYC_API_SECRET")

# Log API keys status (without revealing the actual keys)
if LDA_API_KEY:
    logger.info(f"LDA_API_KEY found: {LDA_API_KEY[:5]}...")
else:
    logger.warning("LDA_API_KEY not found in environment variables. Senate LDA functionality may be limited.")

if NYC_API_APP_TOKEN:
    logger.info(f"NYC_API_APP_TOKEN found: {NYC_API_APP_TOKEN[:5]}...")
    if NYC_API_SECRET:
        logger.info("NYC_API_SECRET found (not logged for security)")
    else:
        logger.warning("NYC_API_SECRET not found. Using app token without authentication.")
else:
    logger.warning("NYC_API_APP_TOKEN not found. NYC data sources will use anonymous access with lower rate limits.")

# Initialize visualization tools
visualizer = LobbyingVisualizer()

# Initialize data sources
data_sources = {}

# Initialize Senate LDA data source
try:
    # Always try real API data first
    senate_lda = ImprovedSenateLDADataSource(LDA_API_KEY, use_mock_data=False)
    logger.info("Successfully initialized Senate LDA data source with real API data")
    
    # Verify API key is working by making a simple API request
    test_result = senate_lda.session.get(f"{senate_lda.api_base_url}/filings/?limit=1", timeout=5)
    if test_result.status_code == 200:
        logger.info("Senate LDA API connection verified successful")
    else:
        logger.warning(f"Senate LDA API connection test returned status code: {test_result.status_code}")
        logger.warning("Senate LDA API key may not be valid, falling back to mock data")
        senate_lda = ImprovedSenateLDADataSource(LDA_API_KEY, use_mock_data=True)
        logger.info("Using mock data for Senate LDA as fallback")
    
    # Add to data sources dictionary
    data_sources['senate'] = senate_lda
except Exception as e:
    logger.error(f"Failed to initialize Senate LDA data source: {str(e)}")
    logger.error(traceback.format_exc())
    # Fall back to mock data if API initialization fails
    try:
        senate_lda = ImprovedSenateLDADataSource(LDA_API_KEY, use_mock_data=True)
        logger.info("Falling back to mock data for Senate LDA due to API initialization failure")
        data_sources['senate'] = senate_lda
    except Exception as e2:
        logger.critical(f"Failed to initialize Senate LDA mock data source: {str(e2)}")
        data_sources['senate'] = None

# Initialize NYC Lobbying data source
try:
    # Initialize with real API data
    nyc_lobbying = NYCLobbyingDataSource(use_mock_data=False)
    logger.info("Successfully initialized NYC Lobbying data source")
    
    # Test connection (optional)
    test_results, _, _, test_error = nyc_lobbying.search_filings("test", page=1, page_size=1)
    if test_error:
        logger.warning(f"NYC Lobbying API test returned an error: {test_error}")
        logger.warning("Falling back to mock data for NYC Lobbying")
        nyc_lobbying = NYCLobbyingDataSource(use_mock_data=True)
    
    # Add to data sources dictionary
    data_sources['nyc'] = nyc_lobbying
except Exception as e:
    logger.error(f"Failed to initialize NYC Lobbying data source: {str(e)}")
    logger.error(traceback.format_exc())
    # Fall back to mock data
    nyc_lobbying = NYCLobbyingDataSource(use_mock_data=True)
    logger.info("Falling back to mock data for NYC Lobbying")
    data_sources['nyc'] = nyc_lobbying

# Initialize NYC Checkbook data source
try:
    # Initialize with real API data and credentials
    nyc_checkbook = NYCCheckbookDataSource(
        api_app_token=NYC_API_APP_TOKEN,
        api_secret=NYC_API_SECRET,
        use_mock_data=False
    )
    logger.info("Successfully initialized NYC Checkbook data source with API credentials")
    
    # Test connection
    test_results, _, _, test_error = nyc_checkbook.search_filings("test", page=1, page_size=1)
    if test_error:
        logger.warning(f"NYC Checkbook API test returned an error: {test_error}")
        logger.warning("Falling back to mock data for NYC Checkbook")
        nyc_checkbook = NYCCheckbookDataSource(
            api_app_token=NYC_API_APP_TOKEN,
            api_secret=NYC_API_SECRET,
            use_mock_data=True
        )
    
    # Add to data sources dictionary
    data_sources['nyc_checkbook'] = nyc_checkbook
except Exception as e:
    logger.error(f"Failed to initialize NYC Checkbook data source: {str(e)}")
    logger.error(traceback.format_exc())
    # Fall back to mock data
    nyc_checkbook = NYCCheckbookDataSource(
        api_app_token=NYC_API_APP_TOKEN,
        api_secret=NYC_API_SECRET,
        use_mock_data=True
    )
    logger.info("Falling back to mock data for NYC Checkbook")
    data_sources['nyc_checkbook'] = nyc_checkbook

# Set response headers to prevent caching
@app.after_request
def add_header(response):
    """Add headers to prevent caching."""
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response

@app.route('/')
def index():
    """Render the search form homepage."""
    return render_template('index.html')

@app.route('/search', methods=['GET'])
@api_error_handler
def search():
    """Process search query from get parameters."""
    # Extract search parameters from query string
    query = request.args.get('query', '').strip()
    search_type = request.args.get('search_type', 'registrant').strip().lower()
    filing_type = request.args.get('filing_type', 'all').strip()
    filing_year = request.args.get('filing_year', 'all').strip()
    data_source = request.