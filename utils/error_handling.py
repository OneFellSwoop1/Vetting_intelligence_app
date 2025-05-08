# utils/error_handling.py
"""
Error handling utilities for the Vetting Intelligence Hub.
"""

import logging
import functools
import traceback
from flask import flash, redirect, url_for, request
import requests
import json

logger = logging.getLogger('vetting_hub')

def api_error_handler(f):
    """
    Decorator to handle API errors gracefully in routes.
    Catches exceptions, logs them, and displays a flash message.
    """
    @functools.wraps(f)
    def decorated_function(*args, **kwargs):
        try:
            return f(*args, **kwargs)
        except Exception as e:
            logger.error(f"Error in {f.__name__}: {str(e)}")
            logger.error(traceback.format_exc())
            flash(f"An error occurred: {str(e)}", "error")
            return redirect(url_for('index'))
    return decorated_function

def validate_search_params(params):
    """
    Validate search parameters to ensure they're suitable for API requests.
    
    Args:
        params: Dictionary of search parameters
        
    Returns:
        (valid, error_message) tuple
    """
    # Check required parameters
    if not params.get('query'):
        return False, "Search query is required"
    
    # Validate pagination parameters
    try:
        if 'page' in params and int(params['page']) < 1:
            return False, "Page number must be greater than 0"
        if 'page_size' in params and int(params['page_size']) < 1:
            return False, "Page size must be greater than 0"
    except ValueError:
        return False, "Invalid pagination parameters"
    
    # Check for injection attempts or malicious queries
    query = params.get('query', '')
    if any(char in query for char in ['<', '>', ';', '$', '|', '&', '`']):
        return False, "Invalid characters in search query"
    
    return True, None

def handle_api_response(response, service_name):
    """
    Process an API response and handle errors.
    
    Args:
        response: Requests response object
        service_name: Name of the API service for logging
        
    Returns:
        (data, error) tuple
    """
    try:
        if response.status_code == 200:
            return response.json(), None
        elif response.status_code == 401:
            logger.error(f"{service_name} API authentication error: {response.status_code}")
            return None, "Authentication error. Check your API key."
        elif response.status_code == 429:
            logger.error(f"{service_name} API rate limit exceeded: {response.status_code}")
            return None, "Rate limit exceeded. Please try again later."
        else:
            logger.error(f"{service_name} API error: {response.status_code} - {response.text[:200]}")
            return None, f"API error: {response.status_code}"
    except json.JSONDecodeError:
        logger.error(f"{service_name} API returned invalid JSON: {response.text[:200]}")
        return None, "Invalid response from the API."
    except Exception as e:
        logger.error(f"Error processing {service_name} API response: {str(e)}")
        return None, f"Error processing API response: {str(e)}"

def diagnose_api_issue(query, search_type, filters, api_key):
    """
    Run diagnostics to identify API issues.
    
    Args:
        query: Search query
        search_type: Type of search (registrant, client, lobbyist)
        filters: Additional filters
        api_key: API key for authentication
        
    Returns:
        Dictionary with diagnostic results
    """
    results = {
        "query": query,
        "search_type": search_type,
        "filters": filters,
        "tests": [],
        "suggestions": []
    }
    
    # Test basic connectivity
    try:
        headers = {
            'x-api-key': api_key,
            'Accept': 'application/json',
            'User-Agent': 'VettingIntelligenceHub/1.0'
        }
        
        # Test with minimal parameters
        url = "https://lda.senate.gov/api/v1/filings/"
        response = requests.get(url, headers=headers, params={"filing_year": 2023, "limit": 1}, timeout=30)
        
        results["tests"].append({
            "name": "Basic connectivity",
            "result": "success" if response.status_code == 200 else "error",
            "status_code": response.status_code,
            "details": "Connection successful" if response.status_code == 200 else response.text[:200]
        })
        
        if response.status_code != 200:
            results["suggestions"].append("Check your API key and network connection")
    except Exception as e:
        results["tests"].append({
            "name": "Basic connectivity",
            "result": "exception",
            "details": str(e)
        })
        results["suggestions"].append("Check your network connection and try again")
    
    # Test search query
    search_patterns = [
        {"name": "General search", "params": {"search": query, "limit": 5}},
        {"name": "Registrant search", "params": {"registrant_name": query, "limit": 5}},
        {"name": "Client search", "params": {"client_name": query, "limit": 5}}
    ]
    
    for pattern in search_patterns:
        try:
            url = "https://lda.senate.gov/api/v1/filings/"
            response = requests.get(url, headers=headers, params=pattern["params"], timeout=30)
            
            # Process response
            if response.status_code == 200:
                data = response.json()
                count = data.get("count", 0)
                
                if count > 0:
                    result = "success"
                    details = f"Found {count} results"
                else:
                    result = "no_results"
                    details = "Query executed successfully but found no results"
            else:
                result = "error"
                details = f"Status code: {response.status_code}, Response: {response.text[:200]}"
            
            results["tests"].append({
                "name": pattern["name"],
                "result": result,
                "status_code": response.status_code,
                "details": details
            })
        except Exception as e:
            results["tests"].append({
                "name": pattern["name"],
                "result": "exception",
                "details": str(e)
            })
    
    # Generate suggestions based on test results
    success_tests = [test for test in results["tests"] if test["result"] == "success"]
    failed_tests = [test for test in results["tests"] if test["result"] == "error"]
    
    if not success_tests and failed_tests:
        results["suggestions"].append("All tests failed. Check your API key and try again.")
    elif not success_tests:
        results["suggestions"].append("No results found. Try a different search term or broader filters.")
    else:
        best_test = max(success_tests, key=lambda x: x.get("count", 0) if "count" in x else 0)
        results["suggestions"].append(f"Best search approach: {best_test['name']}")
    
    return results