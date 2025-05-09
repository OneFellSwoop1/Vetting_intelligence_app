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
import logging.handlers

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
    data_source = request.args.get('data_source', 'senate').strip().lower()
    page = int(request.args.get('page', 1))
    page_size = int(request.args.get('items_per_page', 25))
    
    # Additional filters
    filters = {
        'search_type': search_type,
        'filing_type': filing_type,
        'filing_year': filing_year
    }
    
    # Add optional filters if present
    for filter_name in ['year_from', 'year_to', 'issue_area', 'government_entity', 'amount_min']:
        if filter_name in request.args and request.args[filter_name]:
            filters[filter_name] = request.args[filter_name]
    
    # Validate search parameters
    valid, error_msg = validate_search_params({
        'query': query,
        'page': page,
        'page_size': page_size
    })
    
    if not valid:
        flash(error_msg, 'error')
        return redirect(url_for('index'))
    
    # Log search query
    logger.info(f"Search request - Query: '{query}', Type: {search_type}, Source: {data_source}, Filters: {filters}")
    
    # Initialize variables for holding results
    results = []
    count = 0
    pagination = {'total_pages': 0}
    error = None
    start_time = time.time()
    
    # Execute search using the appropriate data source
    if data_source == 'senate' and data_sources.get('senate'):
        # Senate LDA source
        results, count, pagination, error = data_sources['senate'].search_filings(
            query=query,
            filters=filters,
            page=page,
            page_size=page_size
        )
    elif data_source == 'nyc' and data_sources.get('nyc'):
        # NYC Lobbying source
        results, count, pagination, error = data_sources['nyc'].search_filings(
            query=query,
            filters=filters,
            page=page,
            page_size=page_size
        )
    elif data_source == 'nyc_checkbook' and data_sources.get('nyc_checkbook'):
        # NYC Checkbook source
        results, count, pagination, error = data_sources['nyc_checkbook'].search_filings(
            query=query,
            filters=filters,
            page=page,
            page_size=page_size
        )
    else:
        error = f"Invalid data source: {data_source}"
    
    # Calculate search time
    search_time = time.time() - start_time
    logger.info(f"Search completed in {search_time:.2f} seconds. Found {count} results.")
    
    # If there's an error, display it and redirect
    if error:
        flash(f"Search error: {error}", 'error')
        return redirect(url_for('index'))
    
    # If no results were found, display a message
    if count == 0:
        flash(f"No results found for '{query}' in {data_source} data source.", 'info')
    
    # Render the results page
    return render_template(
        'results.html',
        query=query,
        search_type=search_type,
        filing_type=filing_type,
        filing_year=filing_year,
        data_source=data_source,
        results=results,
        count=count,
        pagination=pagination,
        page=page,
        search_time=search_time,
        filters=filters
    )

@app.route('/filing/<filing_id>')
@api_error_handler
def filing_detail(filing_id):
    """Display detailed information about a specific filing."""
    # Get data source from query parameters or default to 'senate'
    data_source = request.args.get('data_source', 'senate').strip().lower()
    
    # Log request
    logger.info(f"Filing detail request - ID: '{filing_id}', Source: {data_source}")
    
    # Initialize variables
    filing = None
    error = None
    
    # Retrieve filing detail using the appropriate data source
    if data_source == 'senate' and data_sources.get('senate'):
        filing, error = data_sources['senate'].get_filing_detail(filing_id)
    elif data_source == 'nyc' and data_sources.get('nyc'):
        filing, error = data_sources['nyc'].get_filing_detail(filing_id)
    elif data_source == 'nyc_checkbook' and data_sources.get('nyc_checkbook'):
        filing, error = data_sources['nyc_checkbook'].get_filing_detail(filing_id)
    else:
        error = f"Invalid data source: {data_source}"
    
    # If there's an error, display it and redirect
    if error:
        flash(f"Error retrieving filing details: {error}", 'error')
        return redirect(url_for('index'))
    
    # If filing not found, display a message
    if not filing:
        flash(f"Filing with ID '{filing_id}' not found in {data_source} data source.", 'error')
        return redirect(url_for('index'))
    
    # Render the filing detail page
    return render_template(
        'filing_detail.html',
        filing=filing,
        data_source=data_source,
        source_name=data_sources[data_source].source_name if data_sources.get(data_source) else data_source
    )

@app.route('/visualize')
@api_error_handler
def visualize():
    """Generate visualizations for search results."""
    # Extract parameters from query string
    query = request.args.get('query', '').strip()
    search_type = request.args.get('search_type', 'registrant').strip().lower()
    filing_type = request.args.get('filing_type', 'all').strip()
    filing_year = request.args.get('filing_year', 'all').strip()
    data_source = request.args.get('data_source', 'senate').strip().lower()
    
    # Additional filters
    filters = {
        'search_type': search_type,
        'filing_type': filing_type,
        'filing_year': filing_year
    }
    
    # Add optional filters if present
    for filter_name in ['year_from', 'year_to', 'issue_area', 'government_entity', 'amount_min']:
        if filter_name in request.args and request.args[filter_name]:
            filters[filter_name] = request.args[filter_name]
    
    # Log visualization request
    logger.info(f"Visualization request - Query: '{query}', Source: {data_source}, Filters: {filters}")
    
    # Initialize variables
    visualization_data = None
    error = None
    chart_images = {}
    insights = []
    
    # Check if query is provided
    if not query:
        flash("Query is required for visualization", 'error')
        return redirect(url_for('index'))
    
    # Get visualization data using the appropriate data source
    if data_source == 'senate' and data_sources.get('senate'):
        vis_data, error = data_sources['senate'].fetch_visualization_data(query, filters)
        if vis_data:
            # Generate visualizations
            viz_result = visualizer.generate_visualizations(query, [], vis_data)
            visualization_data = viz_result.get('charts', {})
            insights = viz_result.get('insights', [])
            # Generate chart images
            chart_images = visualizer.generate_charts_as_base64(visualization_data)
    elif data_source == 'nyc' and data_sources.get('nyc'):
        vis_data, error = data_sources['nyc'].fetch_visualization_data(query, filters)
        if vis_data:
            # Generate visualizations
            viz_result = visualizer.generate_visualizations(query, [], vis_data)
            visualization_data = viz_result.get('charts', {})
            insights = viz_result.get('insights', [])
            # Generate chart images
            chart_images = visualizer.generate_charts_as_base64(visualization_data)
    elif data_source == 'nyc_checkbook' and data_sources.get('nyc_checkbook'):
        vis_data, error = data_sources['nyc_checkbook'].fetch_visualization_data(query, filters)
        if vis_data:
            # Generate visualizations
            viz_result = visualizer.generate_visualizations(query, [], vis_data)
            visualization_data = viz_result.get('charts', {})
            insights = viz_result.get('insights', [])
            # Generate chart images
            chart_images = visualizer.generate_charts_as_base64(visualization_data)
    else:
        error = f"Invalid data source: {data_source}"
    
    # If there's an error, display it and redirect
    if error:
        flash(f"Error generating visualizations: {error}", 'error')
        return redirect(url_for('search', query=query, data_source=data_source, **filters))
    
    # If no visualization data, display a message
    if not visualization_data:
        flash(f"No data available for visualization for '{query}'", 'info')
        return redirect(url_for('search', query=query, data_source=data_source, **filters))
    
    # Render the visualization page
    return render_template(
        'visualize.html',
        query=query,
        data_source=data_source,
        source_name=data_sources[data_source].source_name if data_sources.get(data_source) else data_source,
        visualization_data=visualization_data,
        chart_images=chart_images,
        insights=insights,
        filters=filters
    )

@app.route('/export')
@api_error_handler
def export_results():
    """Export search results as CSV."""
    # Extract parameters from query string
    query = request.args.get('query', '').strip()
    search_type = request.args.get('search_type', 'registrant').strip().lower()
    filing_type = request.args.get('filing_type', 'all').strip()
    filing_year = request.args.get('filing_year', 'all').strip()
    data_source = request.args.get('data_source', 'senate').strip().lower()
    
    # Additional filters
    filters = {
        'search_type': search_type,
        'filing_type': filing_type,
        'filing_year': filing_year
    }
    
    # Add optional filters if present
    for filter_name in ['year_from', 'year_to', 'issue_area', 'government_entity', 'amount_min']:
        if filter_name in request.args and request.args[filter_name]:
            filters[filter_name] = request.args[filter_name]
    
    # Log export request
    logger.info(f"Export request - Query: '{query}', Source: {data_source}, Filters: {filters}")
    
    # Check if query is provided
    if not query:
        flash("Query is required for export", 'error')
        return redirect(url_for('index'))
    
    # Initialize variables
    results = []
    error = None
    
    # Get search results using the appropriate data source (with increased page size)
    if data_source == 'senate' and data_sources.get('senate'):
        results, _, _, error = data_sources['senate'].search_filings(
            query=query,
            filters=filters,
            page=1,
            page_size=1000  # Get a larger set of results for export
        )
    elif data_source == 'nyc' and data_sources.get('nyc'):
        results, _, _, error = data_sources['nyc'].search_filings(
            query=query,
            filters=filters,
            page=1,
            page_size=1000
        )
    elif data_source == 'nyc_checkbook' and data_sources.get('nyc_checkbook'):
        results, _, _, error = data_sources['nyc_checkbook'].search_filings(
            query=query,
            filters=filters,
            page=1,
            page_size=1000
        )
    else:
        error = f"Invalid data source: {data_source}"
    
    # If there's an error, display it and redirect
    if error:
        flash(f"Error exporting results: {error}", 'error')
        return redirect(url_for('search', query=query, data_source=data_source, **filters))
    
    # If no results, display a message
    if not results:
        flash(f"No results to export for '{query}'", 'info')
        return redirect(url_for('search', query=query, data_source=data_source, **filters))
    
    # Generate CSV data
    import csv
    from io import StringIO
    
    # Determine fields based on data source
    if data_source == 'senate':
        fields = ['filing_uuid', 'filing_type', 'filing_year', 'registrant.name', 'client.name', 'income', 'expenses', 'filing_date']
        headers = ['Filing ID', 'Type', 'Year', 'Registrant', 'Client', 'Income', 'Expenses', 'Date']
    elif data_source == 'nyc':
        fields = ['filing_uuid', 'filing_type', 'filing_year', 'registrant.name', 'client.name', 'income', 'expenses', 'filing_date']
        headers = ['Filing ID', 'Type', 'Year', 'Registrant', 'Client', 'Income', 'Expenses', 'Date']
    elif data_source == 'nyc_checkbook':
        fields = ['contract_id', 'contract_type', 'fiscal_year', 'payee_name', 'agency_name', 'maximum_contract_amount', 'start_date', 'end_date']
        headers = ['Contract ID', 'Type', 'Year', 'Payee', 'Agency', 'Amount', 'Start Date', 'End Date']
    else:
        fields = []
        headers = []
    
    # Create CSV file in memory
    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(headers)
    
    # Write data rows
    for result in results:
        row = []
        for field in fields:
            if '.' in field:
                # Handle nested fields
                parent, child = field.split('.')
                value = result.get(parent, {}).get(child, '') if result.get(parent) else ''
            else:
                # Handle regular fields
                value = result.get(field, '')
            row.append(value)
        writer.writerow(row)
    
    # Create response with CSV file
    response = make_response(output.getvalue())
    response.headers["Content-Disposition"] = f"attachment; filename=search_results_{data_source}_{query}.csv"
    response.headers["Content-type"] = "text/csv"
    
    return response

@app.route('/api/search', methods=['GET'])
@api_error_handler
def api_search():
    """API endpoint for search."""
    # Extract parameters from query string
    query = request.args.get('query', '').strip()
    search_type = request.args.get('search_type', 'registrant').strip().lower()
    filing_type = request.args.get('filing_type', 'all').strip()
    filing_year = request.args.get('filing_year', 'all').strip()
    data_source = request.args.get('data_source', 'senate').strip().lower()
    page = int(request.args.get('page', 1))
    page_size = int(request.args.get('items_per_page', 25))
    
    # Additional filters
    filters = {
        'search_type': search_type,
        'filing_type': filing_type,
        'filing_year': filing_year
    }
    
    # Add optional filters if present
    for filter_name in ['year_from', 'year_to', 'issue_area', 'government_entity', 'amount_min']:
        if filter_name in request.args and request.args[filter_name]:
            filters[filter_name] = request.args[filter_name]
    
    # Validate search parameters
    valid, error_msg = validate_search_params({
        'query': query,
        'page': page,
        'page_size': page_size
    })
    
    if not valid:
        return jsonify({
            'error': error_msg,
            'success': False
        }), 400
    
    # Execute search using the appropriate data source
    if data_source == 'senate' and data_sources.get('senate'):
        results, count, pagination, error = data_sources['senate'].search_filings(
            query=query,
            filters=filters,
            page=page,
            page_size=page_size
        )
    elif data_source == 'nyc' and data_sources.get('nyc'):
        results, count, pagination, error = data_sources['nyc'].search_filings(
            query=query,
            filters=filters,
            page=page,
            page_size=page_size
        )
    elif data_source == 'nyc_checkbook' and data_sources.get('nyc_checkbook'):
        results, count, pagination, error = data_sources['nyc_checkbook'].search_filings(
            query=query,
            filters=filters,
            page=page,
            page_size=page_size
        )
    else:
        return jsonify({
            'error': f"Invalid data source: {data_source}",
            'success': False
        }), 400
    
    # If there's an error, return it
    if error:
        return jsonify({
            'error': error,
            'success': False
        }), 400
    
    # Return search results as JSON
    return jsonify({
        'success': True,
        'query': query,
        'data_source': data_source,
        'filters': filters,
        'results': results,
        'count': count,
        'pagination': pagination
    })

@app.route('/api/filing/<filing_id>', methods=['GET'])
@api_error_handler
def api_filing_detail(filing_id):
    """API endpoint for filing detail."""
    # Get data source from query parameters or default to 'senate'
    data_source = request.args.get('data_source', 'senate').strip().lower()
    
    # Retrieve filing detail using the appropriate data source
    if data_source == 'senate' and data_sources.get('senate'):
        filing, error = data_sources['senate'].get_filing_detail(filing_id)
    elif data_source == 'nyc' and data_sources.get('nyc'):
        filing, error = data_sources['nyc'].get_filing_detail(filing_id)
    elif data_source == 'nyc_checkbook' and data_sources.get('nyc_checkbook'):
        filing, error = data_sources['nyc_checkbook'].get_filing_detail(filing_id)
    else:
        return jsonify({
            'error': f"Invalid data source: {data_source}",
            'success': False
        }), 400
    
    # If there's an error, return it
    if error:
        return jsonify({
            'error': error,
            'success': False
        }), 400
    
    # If filing not found, return 404
    if not filing:
        return jsonify({
            'error': f"Filing with ID '{filing_id}' not found",
            'success': False
        }), 404
    
    # Return filing details as JSON
    return jsonify({
        'success': True,
        'data_source': data_source,
        'filing': filing
    })

@app.route('/api/visualize', methods=['GET'])
@api_error_handler
def api_visualize():
    """API endpoint for visualization data."""
    # Extract parameters from query string
    query = request.args.get('query', '').strip()
    search_type = request.args.get('search_type', 'registrant').strip().lower()
    filing_type = request.args.get('filing_type', 'all').strip()
    filing_year = request.args.get('filing_year', 'all').strip()
    data_source = request.args.get('data_source', 'senate').strip().lower()
    
    # Additional filters
    filters = {
        'search_type': search_type,
        'filing_type': filing_type,
        'filing_year': filing_year
    }
    
    # Add optional filters if present
    for filter_name in ['year_from', 'year_to', 'issue_area', 'government_entity', 'amount_min']:
        if filter_name in request.args and request.args[filter_name]:
            filters[filter_name] = request.args[filter_name]
    
    # Check if query is provided
    if not query:
        return jsonify({
            'error': "Query is required for visualization",
            'success': False
        }), 400
    
    # Get visualization data using the appropriate data source
    if data_source == 'senate' and data_sources.get('senate'):
        vis_data, error = data_sources['senate'].fetch_visualization_data(query, filters)
    elif data_source == 'nyc' and data_sources.get('nyc'):
        vis_data, error = data_sources['nyc'].fetch_visualization_data(query, filters)
    elif data_source == 'nyc_checkbook' and data_sources.get('nyc_checkbook'):
        vis_data, error = data_sources['nyc_checkbook'].fetch_visualization_data(query, filters)
    else:
        return jsonify({
            'error': f"Invalid data source: {data_source}",
            'success': False
        }), 400
    
    # If there's an error, return it
    if error:
        return jsonify({
            'error': error,
            'success': False
        }), 400
    
    # Return visualization data as JSON
    return jsonify({
        'success': True,
        'query': query,
        'data_source': data_source,
        'filters': filters,
        'visualization_data': vis_data
    })

@app.route('/about')
def about():
    """About page with information about the application."""
    return render_template('about.html')

@app.route('/sources')
def sources():
    """Page with information about the data sources."""
    return render_template('sources.html')

@app.route('/diagnostics', methods=['GET'])
def diagnostics():
    """API diagnostics endpoint for all data sources."""
    results = {}

    # Senate LDA diagnostics
    try:
        senate_status = {'status': 'unavailable', 'error': None}
        if data_sources.get('senate'):
            ds = data_sources['senate']
            if hasattr(ds, 'session') and hasattr(ds, 'api_base_url'):
                resp = ds.session.get(f"{ds.api_base_url}/filings/?limit=1", timeout=10)
                if resp.status_code == 200:
                    senate_status['status'] = 'ok'
                else:
                    senate_status['error'] = f"Status code: {resp.status_code}, Body: {resp.text[:200]}"
            else:
                senate_status['error'] = 'Senate data source not properly initialized.'
        else:
            senate_status['error'] = 'Senate data source not available.'
        results['senate_lda'] = senate_status
    except Exception as e:
        results['senate_lda'] = {'status': 'error', 'error': str(e)}

    # NYC Lobbying diagnostics
    try:
        nyc_status = {'status': 'unavailable', 'error': None}
        if data_sources.get('nyc'):
            ds = data_sources['nyc']
            if hasattr(ds, 'session') and hasattr(ds, 'api_base_url'):
                resp = ds.session.get(f"{ds.api_base_url}/lobbyists", params={'limit': 1}, timeout=10)
                if resp.status_code == 200:
                    nyc_status['status'] = 'ok'
                else:
                    nyc_status['error'] = f"Status code: {resp.status_code}, Body: {resp.text[:200]}"
            else:
                nyc_status['error'] = 'NYC data source not properly initialized.'
        else:
            nyc_status['error'] = 'NYC data source not available.'
        results['nyc_lobbying'] = nyc_status
    except Exception as e:
        results['nyc_lobbying'] = {'status': 'error', 'error': str(e)}

    # NYC Checkbook diagnostics
    try:
        checkbook_status = {'status': 'unavailable', 'error': None}
        if data_sources.get('nyc_checkbook'):
            ds = data_sources['nyc_checkbook']
            if hasattr(ds, 'session') and hasattr(ds, 'api_base_url') and hasattr(ds, 'datasets'):
                url = f"{ds.api_base_url}/{ds.datasets['contracts']}.json"
                resp = ds.session.get(url, params={'$limit': 1}, timeout=10)
                if resp.status_code == 200:
                    checkbook_status['status'] = 'ok'
                else:
                    checkbook_status['error'] = f"Status code: {resp.status_code}, Body: {resp.text[:200]}"
            else:
                checkbook_status['error'] = 'NYC Checkbook data source not properly initialized.'
        else:
            checkbook_status['error'] = 'NYC Checkbook data source not available.'
        results['nyc_checkbook'] = checkbook_status
    except Exception as e:
        results['nyc_checkbook'] = {'status': 'error', 'error': str(e)}

    return jsonify(results)

@app.errorhandler(404)
def page_not_found(e):
    """Custom 404 page."""
    return render_template('404.html'), 404

@app.errorhandler(500)
def server_error(e):
    """Custom 500 page."""
    logger.error(f"Server error: {str(e)}")
    return render_template('500.html'), 500

if __name__ == '__main__':
    # Run the application
    port = int(os.environ.get('PORT', 5001))
    debug = os.environ.get('DEBUG', 'False').lower() == 'true'
    
    logger.info(f"Starting Vetting Intelligence Hub on port {port} (debug: {debug})")
    app.run(host='0.0.0.0', port=port, debug=debug)