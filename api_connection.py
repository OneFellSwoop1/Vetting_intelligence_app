# api_connection.py
"""
API connection utilities for the Vetting Intelligence Hub.

This module provides robust connections to various data APIs:
1. Senate LDA API (federal lobbying data)
2. NYC Lobbying OpenData API
3. CheckbookNYC OpenData API

It implements better error handling, improved authentication, and 
ensures we use real API data instead of falling back to mock data.
"""

import os
import requests
import logging
import json
import time
import urllib.parse
from datetime import datetime
from typing import Dict, List, Any, Tuple, Optional
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# Set up logging
logger = logging.getLogger('api_connection')

class APIConnectionManager:
    """Manages connections to various lobbying data APIs."""
    
    def __init__(self, api_keys: Dict[str, str] = None):
        """
        Initialize the API connection manager with API keys.
        
        Args:
            api_keys: Dictionary of API keys with keys 'lda_api_key', 'nyc_api_token', etc.
        """
        self.api_keys = api_keys or {}
        self.sessions = {}
        
        # Load API keys from environment if not provided
        if not self.api_keys.get('lda_api_key'):
            self.api_keys['lda_api_key'] = os.getenv('LDA_API_KEY')
        
        if not self.api_keys.get('nyc_api_token'):
            self.api_keys['nyc_api_token'] = os.getenv('NYC_API_APP_TOKEN')
            self.api_keys['nyc_api_secret'] = os.getenv('NYC_API_SECRET')
        
        # Initialize sessions for each API
        self._init_sessions()
    
    def _init_sessions(self):
        """Initialize request sessions with proper retry handling."""
        # Senate LDA API session
        self.sessions['senate_lda'] = self._create_session()
        if self.api_keys.get('lda_api_key'):
            self.sessions['senate_lda'].headers.update({
                'x-api-key': self.api_keys['lda_api_key'],
                'Accept': 'application/json'
            })
        
        # NYC OpenData API sessions
        self.sessions['nyc_opendata'] = self._create_session()
        if self.api_keys.get('nyc_api_token'):
            self.sessions['nyc_opendata'].headers.update({
                'X-App-Token': self.api_keys['nyc_api_token'],
                'Accept': 'application/json'
            })
    
    def _create_session(self):
        """Create a requests session with retry handling."""
        session = requests.Session()
        
        # Configure retries for robustness
        retries = Retry(
            total=3,
            backoff_factor=0.5,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["HEAD", "GET", "OPTIONS"]
        )
        
        # Add adapter to session
        adapter = HTTPAdapter(max_retries=retries)
        session.mount("https://", adapter)
        session.mount("http://", adapter)
        
        return session
    
    def test_api_connections(self) -> Dict[str, Dict[str, Any]]:
        """
        Test connections to all configured APIs.
        
        Returns:
            Dictionary of results for each API connection test
        """
        results = {}
        
        # Test Senate LDA API
        senate_result = self.test_senate_lda_connection()
        results['senate_lda'] = senate_result
        
        # Test NYC Lobbying API
        nyc_result = self.test_nyc_lobbying_connection()
        results['nyc_lobbying'] = nyc_result
        
        # Test CheckbookNYC API
        checkbook_result = self.test_checkbook_nyc_connection()
        results['nyc_checkbook'] = checkbook_result
        
        return results
    
    def test_senate_lda_connection(self) -> Dict[str, Any]:
        """
        Test connection to Senate LDA API.
        
        Returns:
            Dict with status and any error information
        """
        result = {
            'status': 'untested',
            'message': 'Connection not tested',
            'error': None
        }
        
        if not self.api_keys.get('lda_api_key'):
            result['status'] = 'config_error'
            result['message'] = 'LDA API key not configured'
            return result
        
        session = self.sessions['senate_lda']
        try:
            # Try a simple request
            url = "https://lda.senate.gov/api/v1/filings/"
            response = session.get(
                url, 
                params={"filing_year": 2023, "limit": 1},
                timeout=30
            )
            
            if response.status_code == 200:
                data = response.json()
                count = data.get("count", 0)
                result['status'] = 'ok'
                result['message'] = f"Connection successful. Found {count} filings."
            else:
                result['status'] = 'error'
                result['message'] = f"API request failed with status code: {response.status_code}"
                result['error'] = response.text[:200]
        except Exception as e:
            result['status'] = 'exception'
            result['message'] = f"Exception occurred: {str(e)}"
            result['error'] = str(e)
        
        return result
    
    def test_nyc_lobbying_connection(self) -> Dict[str, Any]:
        """
        Test connection to NYC Lobbying OpenData API.
        
        Returns:
            Dict with status and any error information
        """
        result = {
            'status': 'untested',
            'message': 'Connection not tested',
            'error': None
        }
        
        # NYC Lobbying API doesn't strictly require an app token, but it's better with one
        session = self.sessions['nyc_opendata']
        
        try:
            # Try a simple request to the NYC Lobbying dataset
            url = "https://data.cityofnewyork.us/resource/fmf3-knd8.json"
            response = session.get(
                url, 
                params={"$limit": 1},
                timeout=30
            )
            
            if response.status_code == 200:
                data = response.json()
                result['status'] = 'ok'
                result['message'] = f"Connection successful. Retrieved {len(data)} records."
            else:
                result['status'] = 'error'
                result['message'] = f"API request failed with status code: {response.status_code}"
                result['error'] = response.text[:200]
        except Exception as e:
            result['status'] = 'exception'
            result['message'] = f"Exception occurred: {str(e)}"
            result['error'] = str(e)
        
        return result
    
    def test_checkbook_nyc_connection(self) -> Dict[str, Any]:
        """
        Test connection to CheckbookNYC OpenData API.
        
        Returns:
            Dict with status and any error information
        """
        result = {
            'status': 'untested',
            'message': 'Connection not tested',
            'error': None
        }
        
        session = self.sessions['nyc_opendata']
        
        try:
            # Try a simple request to the CheckbookNYC dataset
            url = "https://data.cityofnewyork.us/resource/mxwn-eh3b.json"
            response = session.get(
                url, 
                params={"$limit": 1},
                timeout=30
            )
            
            if response.status_code == 200:
                data = response.json()
                result['status'] = 'ok'
                result['message'] = f"Connection successful. Retrieved {len(data)} records."
            else:
                result['status'] = 'error'
                result['message'] = f"API request failed with status code: {response.status_code}"
                result['error'] = response.text[:200]
        except Exception as e:
            result['status'] = 'exception'
            result['message'] = f"Exception occurred: {str(e)}"
            result['error'] = str(e)
        
        return result
    
    # Senate LDA API Methods
    def search_senate_lda(self, query: str, search_type: str = 'registrant', 
                          filters: Dict[str, Any] = None, page: int = 1, 
                          page_size: int = 25) -> Tuple[List[Dict], int, Dict, Optional[str]]:
        """
        Search the Senate LDA API for lobbying filings.
        
        Args:
            query: Search query (name of registrant, client, or lobbyist)
            search_type: Type of search ('registrant', 'client', or 'lobbyist')
            filters: Additional filters (filing_year, filing_type, etc.)
            page: Page number for pagination
            page_size: Number of results per page
            
        Returns:
            Tuple of (results, count, pagination_info, error)
        """
        if not self.api_keys.get('lda_api_key'):
            return [], 0, {}, "Senate LDA API key not configured"
        
        if not query:
            return [], 0, {}, "Search query is required"
        
        filters = filters or {}
        session = self.sessions['senate_lda']
        url = "https://lda.senate.gov/api/v1/filings/"
        
        # Build query parameters
        params = {
            'page': page,
            'limit': page_size
        }
        
        # Based on search type, set specific parameters
        # This works better than the general 'search' parameter
        if search_type == 'registrant':
            params['registrant_name'] = query
        elif search_type == 'client':
            params['client_name'] = query
        elif search_type == 'lobbyist':
            params['lobbyist_name'] = query
        else:
            # Default to registrant name
            params['registrant_name'] = query
        
        # Add filing year filter (required by API)
        if 'filing_year' in filters and filters['filing_year'] != 'all':
            params['filing_year'] = filters['filing_year']
        else:
            # Default to current year if not specified
            params['filing_year'] = datetime.now().year
        
        # Add filing type filter if specified
        if 'filing_type' in filters and filters['filing_type'] != 'all':
            params['filing_type'] = filters['filing_type']
        
        # Add other filters
        for key in ['year_from', 'year_to', 'issue_code', 'government_entity', 'amount_min']:
            if key in filters and filters[key]:
                params[key] = filters[key]
        
        try:
            # Make API request
            response = session.get(url, params=params, timeout=45)
            
            if response.status_code == 200:
                data = response.json()
                results = data.get('results', [])
                count = data.get('count', 0)
                
                # Calculate pagination info
                total_pages = (total_count + page_size - 1) // page_size
                pagination = {
                    "count": total_count,
                    "page": page,
                    "page_size": page_size,
                    "total_pages": total_pages,
                    "has_next": page < total_pages,
                    "has_prev": page > 1
                }
                
                # Process the results to match our standard format
                processed_results = []
                for item in data:
                    processed_filing = self._process_nyc_lobbying_filing(item)
                    processed_results.append(processed_filing)
                
                return processed_results, total_count, pagination, None
            else:
                error_msg = f"API request failed with status code: {response.status_code}"
                return [], 0, {}, error_msg
                
        except Exception as e:
            error_msg = f"Error searching NYC Lobbying API: {str(e)}"
            return [], 0, {}, error_msg
    
    def _process_nyc_lobbying_filing(self, filing: Dict) -> Dict:
        """Process and normalize NYC Lobbying data."""
        # Generate a unique ID if not present
        filing_id = filing.get('id') or filing.get('record_id') or f"NYC-{filing.get('year')}-{hash(filing.get('lobbyist_name', '') + filing.get('client_name', '')) % 100000}"
        
        # Map NYC lobbying data to our standard format
        processed = {
            'id': filing_id,
            'filing_uuid': filing_id,
            'filing_type': filing.get('filing_type', 'ANNUAL'),
            'filing_type_display': filing.get('filing_type', 'Annual Filing'),
            'filing_year': filing.get('year'),
            'filing_period': f"January 1 - December 31, {filing.get('year')}",
            'period_display': f"Annual Filing {filing.get('year')}",
            'registrant': {
                'name': filing.get('lobbyist_name'),
                'description': 'Lobbying Firm',
                'contact': filing.get('principal_name')
            },
            'client': {
                'name': filing.get('client_name'),
                'description': filing.get('client_business_nature')
            },
            'lobbying_activities': self._extract_nyc_lobbying_activities(filing),
            'filing_date': filing.get('start_date') or f"{filing.get('year')}-01-01",
            'document_url': None,  # NYC data doesn't provide direct document links
            'income': self._parse_nyc_amount(filing.get('compensation_amount')),
            'expenses': self._parse_nyc_amount(filing.get('reimbursed_expenses_amount')),
            'amount': self._parse_nyc_amount(filing.get('compensation_amount')) or self._parse_nyc_amount(filing.get('reimbursed_expenses_amount')),
            'amount_reported': bool(filing.get('compensation_amount') or filing.get('reimbursed_expenses_amount')),
        }
        
        return processed
    
    def _extract_nyc_lobbying_activities(self, filing: Dict) -> List[Dict]:
        """Extract lobbying activities from NYC Lobbying data."""
        activities = []
        
        # Create a summary activity that includes all available information
        if filing.get('purpose_of_lobbying') or filing.get('subjects') or filing.get('bill_details'):
            activity = {
                'description': filing.get('purpose_of_lobbying') or "Lobbying on various matters",
                'general_issue_code_display': filing.get('subjects') or "Various Issues",
                'government_entities': []
            }
            
            # Add government entities if available
            if filing.get('agency_lobbied'):
                agencies = filing.get('agency_lobbied').split(',') if isinstance(filing.get('agency_lobbied'), str) else [filing.get('agency_lobbied')]
                for agency in agencies:
                    if agency and agency.strip():
                        activity['government_entities'].append({
                            'name': agency.strip(),
                            'type': 'NYC Agency'
                        })
            
            activities.append(activity)
        
        return activities
    
    def _parse_nyc_amount(self, amount_str: str) -> Optional[float]:
        """Parse NYC dollar amount strings to float."""
        if not amount_str:
            return None
            
        try:
            # Remove dollar signs, commas, etc.
            cleaned = amount_str.replace('pages = (count + page_size - 1) // page_size
                pagination = {
                    "count": count,
                    "page": page,
                    "page_size": page_size,
                    "total_pages": total_pages,
                    "has_next": page < total_pages,
                    "has_prev": page > 1
                }
                
                # Process results to ensure consistent format
                processed_results = []
                for filing in results:
                    processed_filing = self._process_senate_filing(filing)
                    processed_results.append(processed_filing)
                
                return processed_results, count, pagination, None
            else:
                error_msg = f"API request failed with status code: {response.status_code}"
                if response.status_code == 401:
                    error_msg = "API authentication failed. Check your API key."
                elif response.status_code == 429:
                    error_msg = "API rate limit exceeded. Please try again later."
                
                return [], 0, {}, error_msg
                
        except Exception as e:
            error_msg = f"Error searching Senate LDA API: {str(e)}"
            return [], 0, {}, error_msg
    
    def _process_senate_filing(self, filing: Dict) -> Dict:
        """Process and normalize Senate LDA filing data."""
        processed = {
            'id': filing.get('filing_uuid'),
            'filing_uuid': filing.get('filing_uuid'),
            'filing_type': filing.get('filing_type'),
            'filing_type_display': filing.get('filing_type_display'),
            'filing_year': filing.get('filing_year'),
            'filing_period': filing.get('filing_period'),
            'period_display': filing.get('filing_period_display'),
            'registrant': {
                'name': filing.get('registrant', {}).get('name'),
                'description': filing.get('registrant', {}).get('description'),
                'contact': filing.get('registrant', {}).get('contact_name')
            },
            'client': {
                'name': filing.get('client', {}).get('name'),
                'description': filing.get('client', {}).get('general_description')
            },
            'lobbying_activities': filing.get('lobbying_activities', []),
            'filing_date': filing.get('dt_posted'),
            'document_url': filing.get('filing_document_url'),
            'income': filing.get('income'),
            'expenses': filing.get('expenses'),
            'amount': filing.get('income') or filing.get('expenses'),
            'amount_reported': bool(filing.get('income') or filing.get('expenses')),
        }
        
        return processed
    
    def get_senate_filing_detail(self, filing_id: str) -> Tuple[Optional[Dict], Optional[str]]:
        """
        Get detailed information about a specific Senate LDA filing.
        
        Args:
            filing_id: The unique identifier for the filing
            
        Returns:
            Tuple of (filing_data, error)
        """
        if not self.api_keys.get('lda_api_key'):
            return None, "Senate LDA API key not configured"
        
        session = self.sessions['senate_lda']
        url = f"https://lda.senate.gov/api/v1/filings/{filing_id}/"
        
        try:
            response = session.get(url, timeout=30)
            
            if response.status_code == 200:
                filing = response.json()
                return self._process_senate_filing(filing), None
            else:
                error_msg = f"API request failed with status code: {response.status_code}"
                return None, error_msg
                
        except Exception as e:
            error_msg = f"Error retrieving filing detail: {str(e)}"
            return None, error_msg
    
    # NYC Lobbying API Methods
    def search_nyc_lobbying(self, query: str, search_type: str = 'registrant', 
                           filters: Dict[str, Any] = None, page: int = 1, 
                           page_size: int = 25) -> Tuple[List[Dict], int, Dict, Optional[str]]:
        """
        Search the NYC Lobbying OpenData API.
        
        Args:
            query: Search query (name of registrant, client, or lobbyist)
            search_type: Type of search ('registrant', 'client', or 'lobbyist')
            filters: Additional filters (filing_year, etc.)
            page: Page number for pagination
            page_size: Number of results per page
            
        Returns:
            Tuple of (results, count, pagination_info, error)
        """
        if not query:
            return [], 0, {}, "Search query is required"
        
        filters = filters or {}
        session = self.sessions['nyc_opendata']
        url = "https://data.cityofnewyork.us/resource/fmf3-knd8.json"
        
        try:
            # Build query using SoQL (Socrata Query Language)
            # For NYC OpenData, we need to use $where clauses
            where_clauses = []
            
            # Handle search types for eLobbyist data
            if search_type == 'registrant':
                where_clauses.append(f"UPPER(lobbyist_name) LIKE '%{query.upper()}%'")
            elif search_type == 'client':
                where_clauses.append(f"UPPER(client_name) LIKE '%{query.upper()}%'")
            elif search_type == 'lobbyist':
                # For individual lobbyist searches, we would use principal lobbyist name
                where_clauses.append(f"UPPER(principal_name) LIKE '%{query.upper()}%'")
            else:
                # Default to a broader search across multiple fields
                where_clauses.append(f"UPPER(lobbyist_name) LIKE '%{query.upper()}%' OR UPPER(client_name) LIKE '%{query.upper()}%'")
            
            # Add year filter if specified
            if 'filing_year' in filters and filters['filing_year'] != 'all':
                where_clauses.append(f"year = '{filters['filing_year']}'")
            
            # Combine all WHERE clauses
            where_clause = " AND ".join(where_clauses)
            
            # Set up pagination
            offset = (page - 1) * page_size
            
            # Build parameters
            params = {
                "$where": where_clause,
                "$limit": page_size,
                "$offset": offset,
                "$order": "year DESC"
            }
            
            # First, get total count
            count_params = params.copy()
            count_params["$select"] = "COUNT(*) AS count"
            count_response = session.get(url, params=count_params, timeout=30)
            
            if count_response.status_code != 200:
                return [], 0, {}, f"Error getting result count: {count_response.status_code}"
            
            # Parse count
            count_data = count_response.json()
            total_count = int(count_data[0]['count']) if count_data else 0
            
            # Get actual results
            response = session.get(url, params=params, timeout=30)
            
            if response.status_code == 200:
                data = response.json()
                
                # Calculate pagination info
                total_, '').replace(',', '').strip()
            if cleaned:
                return float(cleaned)
            return None
        except (ValueError, AttributeError):
            return None
            
    def get_nyc_lobbying_detail(self, filing_id: str) -> Tuple[Optional[Dict], Optional[str]]:
        """
        Get detailed information about a specific NYC Lobbying filing.
        
        Args:
            filing_id: The unique identifier for the filing
            
        Returns:
            Tuple of (filing_data, error)
        """
        session = self.sessions['nyc_opendata']
        url = "https://data.cityofnewyork.us/resource/fmf3-knd8.json"
        
        try:
            # Extract the numeric ID part if present
            id_parts = filing_id.split('-')
            search_id = id_parts[-1] if len(id_parts) > 1 else filing_id
            
            # Try to find the record by ID
            params = {
                "$where": f"id = '{search_id}' OR record_id = '{search_id}'"
            }
            
            response = session.get(url, params=params, timeout=30)
            
            if response.status_code == 200:
                data = response.json()
                if data and len(data) > 0:
                    filing = data[0]
                    return self._process_nyc_lobbying_filing(filing), None
                else:
                    return None, "Filing not found"
            else:
                error_msg = f"API request failed with status code: {response.status_code}"
                return None, error_msg
                
        except Exception as e:
            error_msg = f"Error retrieving filing detail: {str(e)}"
            return None, error_msg
    
    # CheckbookNYC API Methods
    def search_nyc_checkbook(self, query: str, search_type: str = 'vendor', 
                            filters: Dict[str, Any] = None, page: int = 1, 
                            page_size: int = 25) -> Tuple[List[Dict], int, Dict, Optional[str]]:
        """
        Search the CheckbookNYC OpenData API.
        
        Args:
            query: Search query (name of vendor, agency, etc.)
            search_type: Type of search ('vendor' or 'agency')
            filters: Additional filters (fiscal_year, etc.)
            page: Page number for pagination
            page_size: Number of results per page
            
        Returns:
            Tuple of (results, count, pagination_info, error)
        """
        if not query:
            return [], 0, {}, "Search query is required"
        
        filters = filters or {}
        session = self.sessions['nyc_opendata']
        url = "https://data.cityofnewyork.us/resource/mxwn-eh3b.json"
        
        try:
            # Build query using SoQL (Socrata Query Language)
            where_clauses = []
            
            # Handle search types for CheckbookNYC data
            if search_type == 'vendor':
                where_clauses.append(f"UPPER(payee_name) LIKE '%{query.upper()}%'")
            elif search_type == 'agency':
                where_clauses.append(f"UPPER(agency_name) LIKE '%{query.upper()}%'")
            else:
                # Default to a broader search across multiple fields
                where_clauses.append(f"UPPER(payee_name) LIKE '%{query.upper()}%' OR UPPER(agency_name) LIKE '%{query.upper()}%'")
            
            # Add year filter if specified
            if 'filing_year' in filters and filters['filing_year'] != 'all':
                where_clauses.append(f"fiscal_year = {filters['filing_year']}")
            
            # Add contract type filter if specified
            if 'filing_type' in filters and filters['filing_type'] != 'all':
                where_clauses.append(f"contract_type = '{filters['filing_type']}'")
            
            # Add minimum amount filter if specified
            if 'amount_min' in filters and filters['amount_min']:
                try:
                    min_amount = float(filters['amount_min'])
                    where_clauses.append(f"contract_amount > {min_amount}")
                except (ValueError, TypeError):
                    pass
            
            # Combine all WHERE clauses
            where_clause = " AND ".join(where_clauses)
            
            # Set up pagination
            offset = (page - 1) * page_size
            
            # Build parameters
            params = {
                "$where": where_clause,
                "$limit": page_size,
                "$offset": offset,
                "$order": "end_date DESC"
            }
            
            # First, get total count
            count_params = params.copy()
            count_params["$select"] = "COUNT(*) AS count"
            count_response = session.get(url, params=count_params, timeout=30)
            
            if count_response.status_code != 200:
                return [], 0, {}, f"Error getting result count: {count_response.status_code}"
            
            # Parse count
            count_data = count_response.json()
            total_count = int(count_data[0]['count']) if count_data else 0
            
            # Get actual results
            response = session.get(url, params=params, timeout=30)
            
            if response.status_code == 200:
                data = response.json()
                
                # Calculate pagination info
                total_pages = (total_count + page_size - 1) // page_size
                pagination = {
                    "count": total_count,
                    "page": page,
                    "page_size": page_size,
                    "total_pages": total_pages,
                    "has_next": page < total_pages,
                    "has_prev": page > 1
                }
                
                # Process the results to match our standard format
                processed_results = []
                for item in data:
                    processed_contract = self._process_nyc_checkbook_contract(item)
                    processed_results.append(processed_contract)
                
                return processed_results, total_count, pagination, None
            else:
                error_msg = f"API request failed with status code: {response.status_code}"
                return [], 0, {}, error_msg
                
        except Exception as e:
            error_msg = f"Error searching CheckbookNYC API: {str(e)}"
            return [], 0, {}, error_msg
    
    def _process_nyc_checkbook_contract(self, contract: Dict) -> Dict:
        """Process and normalize CheckbookNYC contract data."""
        # Generate a unique ID if not present
        contract_id = contract.get('contract_id') or f"NYC-CT-{hash(contract.get('payee_name', '') + contract.get('agency_name', '')) % 100000}"
        
        # Format contract type display
        contract_type = contract.get('contract_type', '')
        contract_type_display = {
            'EXPENSE': 'Expense Contract',
            'REVENUE': 'Revenue Contract',
            'GRANT': 'Grant Agreement',
            'CAPITAL': 'Capital Project'
        }.get(contract_type, contract_type)
        
        # Map CheckbookNYC data to our standard format
        processed = {
            'id': contract_id,
            'filing_uuid': contract_id,
            'filing_type': contract.get('contract_type'),
            'filing_type_display': contract_type_display,
            'filing_year': contract.get('fiscal_year'),
            'filing_period': f"{contract.get('start_date', 'Unknown')} - {contract.get('end_date', 'Unknown')}",
            'period_display': f"{contract.get('start_date', 'Unknown')} - {contract.get('end_date', 'Unknown')}",
            'registrant': {
                'name': contract.get('payee_name'),
                'description': 'Vendor/Contractor',
                'contact': contract.get('contact_name')
            },
            'client': {
                'name': contract.get('agency_name'),
                'description': 'NYC Government Agency'
            },
            'lobbying_activities': [
                {
                    'description': contract.get('purpose') or contract.get('contract_description') or "City contract",
                    'general_issue_code_display': contract_type_display,
                    'government_entities': [
                        {
                            'name': contract.get('agency_name'),
                            'type': 'NYC Agency'
                        }
                    ]
                }
            ],
            'filing_date': contract.get('start_date') or contract.get('registration_date'),
            'document_url': f"https://www.checkbooknyc.com/contract_details/{contract_id}",
            'income': self._parse_nyc_amount(contract.get('maximum_contract_amount')),
            'expenses': None,
            'amount': self._parse_nyc_amount(contract.get('maximum_contract_amount')),
            'amount_reported': bool(contract.get('maximum_contract_amount')),
            
            # Additional CheckbookNYC-specific fields
            'start_date': contract.get('start_date'),
            'end_date': contract.get('end_date'),
            'original_amount': self._parse_nyc_amount(contract.get('original_contract_amount')),
            'current_amount': self._parse_nyc_amount(contract.get('maximum_contract_amount')),
        }
        
        return processed
            
    def get_nyc_checkbook_detail(self, contract_id: str) -> Tuple[Optional[Dict], Optional[str]]:
        """
        Get detailed information about a specific CheckbookNYC contract.
        
        Args:
            contract_id: The unique identifier for the contract
            
        Returns:
            Tuple of (contract_data, error)
        """
        session = self.sessions['nyc_opendata']
        url = "https://data.cityofnewyork.us/resource/mxwn-eh3b.json"
        
        try:
            # Extract the numeric ID part if present
            id_parts = contract_id.split('-')
            search_id = id_parts[-1] if len(id_parts) > 1 else contract_id
            
            # Try to find the record by ID
            params = {
                "$where": f"contract_id = '{search_id}'"
            }
            
            response = session.get(url, params=params, timeout=30)
            
            if response.status_code == 200:
                data = response.json()
                if data and len(data) > 0:
                    contract = data[0]
                    return self._process_nyc_checkbook_contract(contract), None
                else:
                    return None, "Contract not found"
            else:
                error_msg = f"API request failed with status code: {response.status_code}"
                return None, error_msg
                
        except Exception as e:
            error_msg = f"Error retrieving contract detail: {str(e)}"
            return None, error_msg


# Helper function to create a connection manager
def create_api_connection_manager():
    """Create and initialize an API connection manager with environment variables."""
    api_keys = {
        'lda_api_key': os.environ.get('LDA_API_KEY'),
        'nyc_api_token': os.environ.get('NYC_API_APP_TOKEN'),
        'nyc_api_secret': os.environ.get('NYC_API_SECRET')
    }
    
    return APIConnectionManager(api_keys)pages = (count + page_size - 1) // page_size
                pagination = {
                    "count": count,
                    "page": page,
                    "page_size": page_size,
                    "total_pages": total_pages,
                    "has_next": page < total_pages,
                    "has_prev": page > 1
                }
                
                # Process results to ensure consistent format
                processed_results = []
                for filing in results:
                    processed_filing = self._process_senate_filing(filing)
                    processed_results.append(processed_filing)
                
                return processed_results, count, pagination, None
            else:
                error_msg = f"API request failed with status code: {response.status_code}"
                if response.status_code == 401:
                    error_msg = "API authentication failed. Check your API key."
                elif response.status_code == 429:
                    error_msg = "API rate limit exceeded. Please try again later."
                
                return [], 0, {}, error_msg
                
        except Exception as e:
            error_msg = f"Error searching Senate LDA API: {str(e)}"
            return [], 0, {}, error_msg
    
    def _process_senate_filing(self, filing: Dict) -> Dict:
        """Process and normalize Senate LDA filing data."""
        processed = {
            'id': filing.get('filing_uuid'),
            'filing_uuid': filing.get('filing_uuid'),
            'filing_type': filing.get('filing_type'),
            'filing_type_display': filing.get('filing_type_display'),
            'filing_year': filing.get('filing_year'),
            'filing_period': filing.get('filing_period'),
            'period_display': filing.get('filing_period_display'),
            'registrant': {
                'name': filing.get('registrant', {}).get('name'),
                'description': filing.get('registrant', {}).get('description'),
                'contact': filing.get('registrant', {}).get('contact_name')
            },
            'client': {
                'name': filing.get('client', {}).get('name'),
                'description': filing.get('client', {}).get('general_description')
            },
            'lobbying_activities': filing.get('lobbying_activities', []),
            'filing_date': filing.get('dt_posted'),
            'document_url': filing.get('filing_document_url'),
            'income': filing.get('income'),
            'expenses': filing.get('expenses'),
            'amount': filing.get('income') or filing.get('expenses'),
            'amount_reported': bool(filing.get('income') or filing.get('expenses')),
        }
        
        return processed
    
    def get_senate_filing_detail(self, filing_id: str) -> Tuple[Optional[Dict], Optional[str]]:
        """
        Get detailed information about a specific Senate LDA filing.
        
        Args:
            filing_id: The unique identifier for the filing
            
        Returns:
            Tuple of (filing_data, error)
        """
        if not self.api_keys.get('lda_api_key'):
            return None, "Senate LDA API key not configured"
        
        session = self.sessions['senate_lda']
        url = f"https://lda.senate.gov/api/v1/filings/{filing_id}/"
        
        try:
            response = session.get(url, timeout=30)
            
            if response.status_code == 200:
                filing = response.json()
                return self._process_senate_filing(filing), None
            else:
                error_msg = f"API request failed with status code: {response.status_code}"
                return None, error_msg
                
        except Exception as e:
            error_msg = f"Error retrieving filing detail: {str(e)}"
            return None, error_msg
    
    # NYC Lobbying API Methods
    def search_nyc_lobbying(self, query: str, search_type: str = 'registrant', 
                           filters: Dict[str, Any] = None, page: int = 1, 
                           page_size: int = 25) -> Tuple[List[Dict], int, Dict, Optional[str]]:
        """
        Search the NYC Lobbying OpenData API.
        
        Args:
            query: Search query (name of registrant, client, or lobbyist)
            search_type: Type of search ('registrant', 'client', or 'lobbyist')
            filters: Additional filters (filing_year, etc.)
            page: Page number for pagination
            page_size: Number of results per page
            
        Returns:
            Tuple of (results, count, pagination_info, error)
        """
        if not query:
            return [], 0, {}, "Search query is required"
        
        filters = filters or {}
        session = self.sessions['nyc_opendata']
        url = "https://data.cityofnewyork.us/resource/fmf3-knd8.json"
        
        try:
            # Build query using SoQL (Socrata Query Language)
            # For NYC OpenData, we need to use $where clauses
            where_clauses = []
            
            # Handle search types for eLobbyist data
            if search_type == 'registrant':
                where_clauses.append(f"UPPER(lobbyist_name) LIKE '%{query.upper()}%'")
            elif search_type == 'client':
                where_clauses.append(f"UPPER(client_name) LIKE '%{query.upper()}%'")
            elif search_type == 'lobbyist':
                # For individual lobbyist searches, we would use principal lobbyist name
                where_clauses.append(f"UPPER(principal_name) LIKE '%{query.upper()}%'")
            else:
                # Default to a broader search across multiple fields
                where_clauses.append(f"UPPER(lobbyist_name) LIKE '%{query.upper()}%' OR UPPER(client_name) LIKE '%{query.upper()}%'")
            
            # Add year filter if specified
            if 'filing_year' in filters and filters['filing_year'] != 'all':
                where_clauses.append(f"year = '{filters['filing_year']}'")
            
            # Combine all WHERE clauses
            where_clause = " AND ".join(where_clauses)
            
            # Set up pagination
            offset = (page - 1) * page_size
            
            # Build parameters
            params = {
                "$where": where_clause,
                "$limit": page_size,
                "$offset": offset,
                "$order": "year DESC"
            }
            
            # First, get total count
            count_params = params.copy()
            count_params["$select"] = "COUNT(*) AS count"
            count_response = session.get(url, params=count_params, timeout=30)
            
            if count_response.status_code != 200:
                return [], 0, {}, f"Error getting result count: {count_response.status_code}"
            
            # Parse count
            count_data = count_response.json()
            total_count = int(count_data[0]['count']) if count_data else 0
            
            # Get actual results
            response = session.get(url, params=params, timeout=30)
            
            if response.status_code == 200:
                data = response.json()
                
                # Calculate pagination info
                total_