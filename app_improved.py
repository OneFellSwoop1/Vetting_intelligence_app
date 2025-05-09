"""
Vetting Intelligence Hub - Improved Application

A comprehensive web application for searching and analyzing lobbying disclosure data 
and government contracts from multiple sources at the federal, state, and local levels.

This improved version prioritizes real API data and has better error handling.
"""

from flask import Flask, render_template, request, jsonify, url_for, redirect, flash, session, make_response
import os
import logging
import time
import traceback
import json
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from flask_wtf.csrf import CSRFProtect

# Import our improved API connection manager
from api_connection import create_api_connection_manager

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

# Initialize API connection manager
api_manager = create_api_connection_manager()

# Test API connections and log status
api_status = api_manager.test_api_connections()
for api_name, status in api_status.items():
    if status['status'] == 'ok':
        logger.info(f"{api_name} connection successful: {status['message']}")
    else:
        logger.warning(f"{api_name} connection issue: {status['status']} - {status['message']}")
        if status.get('error'):
            logger.warning(f"Error details: {status['error']}")

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

@app.route('/api/status')
def api_status():
    """Return the status of API connections."""
    status = api_manager.test_api_connections()
    return jsonify(status)

@app.route('/search', methods=['GET'])
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
    if not query:
        flash("Search query is required", "error")
        return redirect(url_for('index'))
    
    # Log search query
    logger.info(f"Search request - Query: '{query}', Type: {search_type}, Source: {data_source}, Filters: {filters}")
    
    # Initialize variables for holding results
    results = []
    count = 0
    pagination = {'total_pages': 0}
    error = None
    start_time = time.time()
    
    # Execute search using the appropriate data source via our API manager
    try:
        if data_source == 'senate':
            results, count, pagination, error = api_manager.search_senate_lda(
                query=query,
                search_type=search_type,
                filters=filters,
                page=page,
                page_size=page_size
            )
        elif data_source == 'nyc':
            results, count, pagination, error = api_manager.search_nyc_lobbying(
                query=query,
                search_type=search_type,
                filters=filters,
                page=page,
                page_size=page_size
            )
        elif data_source == 'nyc_checkbook':
            results, count, pagination, error = api_manager.search_nyc_checkbook(
                query=query,
                search_type=search_type,
                filters=filters,
                page=page,
                page_size=page_size
            )
        else:
            error = f"Invalid data source: {data_source}"
    except Exception as e:
        logger.error(f"Search error: {str(e)}")
        logger.error(traceback.format_exc())
        error = f"Error processing search: {str(e)}"
    
    # Calculate search time
    search_time = time.time() - start_time
    logger.info(f"Search completed in {search_time:.2f} seconds. Found {count} results.")
    
    # If there's an error, display it and redirect
    if error:
        flash(f"Search error: {error}", "error")
        return redirect(url_for('index'))
    
    # If no results were found, display a message
    if count == 0:
        flash(f"No results found for '{query}' in {data_source} data source.", "info")
    
    # Determine the source name for display
    source_names = {
        'senate': 'Senate LDA (Federal)',
        'nyc': 'NYC Lobbying',
        'nyc_checkbook': 'NYC Checkbook (Contracts)'
    }
    source_name = source_names.get(data_source, data_source)
    
    # Render the results page
    return render_template(
        'results.html',
        query=query,
        search_type=search_type,
        filing_type=filing_type,
        filing_year=filing_year,
        data_source=data_source,
        source_name=source_name,
        results=results,
        count=count,
        pagination=pagination,
        page=page,
        search_time=search_time,
        filters=filters
    )

@app.route('/filing/<filing_id>')
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
    try:
        if data_source == 'senate':
            filing, error = api_manager.get_senate_filing_detail(filing_id)
        elif data_source == 'nyc':
            filing, error = api_manager.get_nyc_lobbying_detail(filing_id)
        elif data_source == 'nyc_checkbook':
            filing, error = api_manager.get_nyc_checkbook_detail(filing_id)
        else:
            error = f"Invalid data source: {data_source}"
    except Exception as e:
        logger.error(f"Filing detail error: {str(e)}")
        logger.error(traceback.format_exc())
        error = f"Error retrieving filing details: {str(e)}"
    
    # If there's an error, display it and redirect
    if error:
        flash(f"Error retrieving filing details: {error}", "error")
        return redirect(url_for('index'))
    
    # If filing not found, display a message
    if not filing:
        flash(f"Filing with ID '{filing_id}' not found in {data_source} data source.", "error")
        return redirect(url_for('index'))
    
    # Determine the source name for display
    source_names = {
        'senate': 'Senate LDA (Federal)',
        'nyc': 'NYC Lobbying',
        'nyc_checkbook': 'NYC Checkbook (Contracts)'
    }
    source_name = source_names.get(data_source, data_source)
    
    # Render the filing detail page
    return render_template(
        'filing_detail.html',
        filing=filing,
        data_source=data_source,
        source_name=source_name
    )

@app.route('/api/search', methods=['GET'])
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
    if not query:
        return jsonify({
            'error': "Search query is required",
            'success': False
        }), 400
    
    # Execute search using the appropriate data source
    try:
        if data_source == 'senate':
            results, count, pagination, error = api_manager.search_senate_lda(
                query=query,
                search_type=search_type,
                filters=filters,
                page=page,
                page_size=page_size
            )
        elif data_source == 'nyc':
            results, count, pagination, error = api_manager.search_nyc_lobbying(
                query=query,
                search_type=search_type,
                filters=filters,
                page=page,
                page_size=page_size
            )
        elif data_source == 'nyc_checkbook':
            results, count, pagination, error = api_manager.search_nyc_checkbook(
                query=query,
                search_type=search_type,
                filters=filters,
                page=page,
                page_size=page_size
            )
        else:
            return jsonify({
                'error': f"Invalid data source: {data_source}",
                'success': False
            }), 400
    except Exception as e:
        logger.error(f"API search error: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({
            'error': f"Error processing search: {str(e)}",
            'success': False
        }), 500
    
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
def api_filing_detail(filing_id):
    """API endpoint for filing detail."""
    # Get data source from query parameters or default to 'senate'
    data_source = request.args.get('data_source', 'senate').strip().lower()
    
    # Retrieve filing detail using the appropriate data source
    try:
        if data_source == 'senate':
            filing, error = api_manager.get_senate_filing_detail(filing_id)
        elif data_source == 'nyc':
            filing, error = api_manager.get_nyc_lobbying_detail(filing_id)
        elif data_source == 'nyc_checkbook':
            filing, error = api_manager.get_nyc_checkbook_detail(filing_id)
        else:
            return jsonify({
                'error': f"Invalid data source: {data_source}",
                'success': False
            }), 400
    except Exception as e:
        logger.error(f"API filing detail error: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({
            'error': f"Error retrieving filing details: {str(e)}",
            'success': False
        }), 500
    
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

@app.route('/export')
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
    try:
        if data_source == 'senate':
            results, _, _, error = api_manager.search_senate_lda(
                query=query,
                search_type=search_type,
                filters=filters,
                page=1,
                page_size=1000  # Get a larger set of results for export
            )
        elif data_source == 'nyc':
            results, _, _, error = api_manager.search_nyc_lobbying(
                query=query,
                search_type=search_type,
                filters=filters,
                page=1,
                page_size=1000
            )
        elif data_source == 'nyc_checkbook':
            results, _, _, error = api_manager.search_nyc_checkbook(
                query=query,
                search_type=search_type,
                filters=filters,
                page=1,
                page_size=1000
            )
        else:
            error = f"Invalid data source: {data_source}"
    except Exception as e:
        logger.error(f"Export error: {str(e)}")
        logger.error(traceback.format_exc())
        error = f"Error exporting results: {str(e)}"
    
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
        fields = ['filing_uuid', 'filing_type', 'filing_year', 'registrant.name', 'client.name', 'amount', 'start_date', 'end_date']
        headers = ['Contract ID', 'Type', 'Year', 'Vendor', 'Agency', 'Amount', 'Start Date', 'End Date']
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

@app.route('/about')
def about():
    """About page with information about the application."""
    # Get API status to show on about page
    api_status = api_manager.test_api_connections()
    return render_template('about.html', api_status=api_status)

@app.route('/sources')
def sources():
    """Page with information about the data sources."""
    # Get API status to show on sources page
    api_status = api_manager.test_api_connections()
    return render_template('sources.html', api_status=api_status)

@app.route('/diagnostics', methods=['GET'])
def diagnostics():
    """API diagnostics endpoint for all data sources."""
    # Test all API connections
    results = api_manager.test_api_connections()
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