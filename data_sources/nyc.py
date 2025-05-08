# data_sources/nyc.py
"""
NYC Lobbying Data Source implementation for the Vetting Intelligence Hub.
This module integrates with the NYC Lobbying Bureau's API at https://lobbyistsearch.nyc.gov/
"""

import os
import json
import requests
import logging
import time
import urllib.parse
from datetime import datetime, timedelta
from collections import defaultdict, Counter
from requests.packages.urllib3.util.retry import Retry
from requests.adapters import HTTPAdapter
import traceback

from .base import LobbyingDataSource

# Set up logging
logger = logging.getLogger('nyc_lobbying')
logger.setLevel(logging.INFO)

class NYCLobbyingDataSource(LobbyingDataSource):
    """NYC Lobbying Bureau database data source."""
    
    FILING_TYPES = {
        'ANNUAL': 'Annual Report',
        'PERIODIC': 'Periodic Report',
        'REGISTRATION': 'Registration',
        'TERMINATION': 'Termination'
    }
    
    def __init__(self, api_base_url="https://lobbyistsearch.nyc.gov/api/v1", use_mock_data=False):
        """
        Initialize the NYC Lobbying Bureau data source.
        
        Args:
            api_base_url: Base URL for the NYC Lobbying API
            use_mock_data: If True, use mock data instead of real API calls (for testing)
        """
        self.api_base_url = api_base_url.rstrip('/')
        self.use_mock_data = use_mock_data
        
        # Configure session with retries and timeouts
        self.session = requests.Session()
        retries = Retry(
            total=3,
            backoff_factor=0.5,
            status_forcelist=[500, 502, 503, 504]
        )
        self.session.mount('https://', HTTPAdapter(max_retries=retries))
        self.session.headers.update({
            'Accept': 'application/json',
            'User-Agent': 'VettingIntelligenceHub/1.0'
        })
        
    def search_filings(self, query, filters=None, page=1, page_size=25):
        """
        Search for lobbying filings in the NYC Lobbying database.
        
        Args:
            query: Search term (person or organization name)
            filters: Additional filters to apply to the search
            page: Page number for pagination
            page_size: Number of results per page
            
        Returns:
            tuple: (results, count, pagination_info, error)
        """
        if not query:
            return [], 0, {"total_pages": 0}, "Search query is required"
            
        if filters is None:
            filters = {}
        
        # If using mock data, return mocked results
        if self.use_mock_data:
            logger.info(f"Using mock data for query: '{query}'")
            return self._mock_search_results(query, filters, page, page_size)
            
        try:
            # Process the query to improve results
            processed_query = query.strip()
            logger.info(f"Searching NYC Lobbying API with processed query: '{processed_query}'")
            
            # Build query parameters for the API
            params = {
                'page': page,
                'limit': page_size,
                'searchTerms': processed_query
            }
            
            # Determine search endpoint based on search type
            search_type = filters.get('search_type', 'registrant').lower()
            endpoint = ""
            
            if search_type == 'registrant':
                endpoint = "/lobbyists"
            elif search_type == 'client':
                endpoint = "/clients"
            elif search_type == 'lobbyist':
                endpoint = "/principal-officers"  # Individual lobbyists are "principal officers" in NYC system
            else:
                # Default to registrant search
                endpoint = "/lobbyists"
            
            # Add filing year filter
            if 'filing_year' in filters and filters['filing_year'] != 'all':
                params['filingYear'] = filters['filing_year']
            
            # Add filing type filter
            if 'filing_type' in filters and filters['filing_type'].lower() != 'all':
                params['filingType'] = filters['filing_type']
            
            # Make the API request
            logger.info(f"Making API request to {self.api_base_url}{endpoint} with params: {params}")
            
            response = self.session.get(
                f"{self.api_base_url}{endpoint}",
                params=params,
                timeout=30
            )
            
            logger.info(f"API Response Status: {response.status_code}")
            
            if response.status_code == 200:
                try:
                    data = response.json()
                    results = data.get('results', [])
                    count = data.get('count', 0)
                    
                    # If we got results, calculate pagination info
                    if count > 0:
                        # Calculate pagination info
                        total_pages = (count + page_size - 1) // page_size  # Ceiling division
                        pagination = {
                            "count": count,
                            "page": page,
                            "page_size": page_size,
                            "total_pages": total_pages,
                            "has_next": page < total_pages,
                            "has_prev": page > 1
                        }
                        
                        # Process the results to ensure they're ready for display
                        processed_results = []
                        for result in results:
                            # For registrant/firm results, fetch their filings
                            if endpoint == "/lobbyists":
                                filings = self._get_lobbyist_filings(result.get("id"), filters)
                                processed_results.extend(filings)
                            # For client results, fetch their filings
                            elif endpoint == "/clients":
                                filings = self._get_client_filings(result.get("id"), filters)
                                processed_results.extend(filings)
                            # For individual lobbyist results, fetch their filings
                            elif endpoint == "/principal-officers":
                                filings = self._get_principal_filings(result.get("id"), filters)
                                processed_results.extend(filings)
                        
                        # Sort results by date if available
                        processed_results.sort(
                            key=lambda x: x.get("filing_date", "1900-01-01"),
                            reverse=True  # Most recent first
                        )
                        
                        # Limit to requested page size
                        start_idx = (page - 1) * page_size
                        end_idx = start_idx + page_size
                        paged_results = processed_results[start_idx:end_idx]
                        
                        return paged_results, len(processed_results), pagination, None
                    else:
                        # No results found
                        logger.info(f"No results found for query: '{processed_query}'")
                        return [], 0, {"total_pages": 0, "page": page}, None
                
                except (json.JSONDecodeError, KeyError) as e:
                    error_message = f"Failed to parse API response: {str(e)}"
                    logger.error(error_message)
                    return [], 0, {}, error_message
            else:
                error_message = f"API request failed with status code: {response.status_code}"
                logger.error(error_message)
                return [], 0, {}, error_message
                
        except requests.exceptions.RequestException as e:
            error_message = f"Request exception: {str(e)}"
            logger.error(error_message)
            return [], 0, {}, error_message
        except Exception as e:
            error_message = f"Unexpected error: {str(e)}"
            logger.error(error_message)
            logger.error(traceback.format_exc())
            return [], 0, {}, error_message

    def _get_lobbyist_filings(self, lobbyist_id, filters=None):
        """Fetch filings for a specific lobbyist/firm."""
        try:
            if self.use_mock_data:
                # Generate mock filings
                return self._mock_filings_for_entity(lobbyist_id, "lobbyist", filters)
            
            # Real API call
            params = {}
            if filters and 'filing_year' in filters and filters['filing_year'] != 'all':
                params['filingYear'] = filters['filing_year']
            
            response = self.session.get(
                f"{self.api_base_url}/lobbyists/{lobbyist_id}/filings",
                params=params,
                timeout=30
            )
            
            if response.status_code == 200:
                filings_data = response.json().get('results', [])
                return [self._process_nyc_filing(filing) for filing in filings_data]
            else:
                logger.error(f"Failed to fetch filings for lobbyist {lobbyist_id}: {response.status_code}")
                return []
        except Exception as e:
            logger.error(f"Error fetching lobbyist filings: {str(e)}")
            return []
    
    def _get_client_filings(self, client_id, filters=None):
        """Fetch filings for a specific client."""
        try:
            if self.use_mock_data:
                # Generate mock filings
                return self._mock_filings_for_entity(client_id, "client", filters)
            
            # Real API call
            params = {}
            if filters and 'filing_year' in filters and filters['filing_year'] != 'all':
                params['filingYear'] = filters['filing_year']
            
            response = self.session.get(
                f"{self.api_base_url}/clients/{client_id}/filings",
                params=params,
                timeout=30
            )
            
            if response.status_code == 200:
                filings_data = response.json().get('results', [])
                return [self._process_nyc_filing(filing) for filing in filings_data]
            else:
                logger.error(f"Failed to fetch filings for client {client_id}: {response.status_code}")
                return []
        except Exception as e:
            logger.error(f"Error fetching client filings: {str(e)}")
            return []
    
    def _get_principal_filings(self, principal_id, filters=None):
        """Fetch filings for a specific principal officer (individual lobbyist)."""
        try:
            if self.use_mock_data:
                # Generate mock filings
                return self._mock_filings_for_entity(principal_id, "principal", filters)
            
            # Real API call
            params = {}
            if filters and 'filing_year' in filters and filters['filing_year'] != 'all':
                params['filingYear'] = filters['filing_year']
            
            response = self.session.get(
                f"{self.api_base_url}/principal-officers/{principal_id}/filings",
                params=params,
                timeout=30
            )
            
            if response.status_code == 200:
                filings_data = response.json().get('results', [])
                return [self._process_nyc_filing(filing) for filing in filings_data]
            else:
                logger.error(f"Failed to fetch filings for principal {principal_id}: {response.status_code}")
                return []
        except Exception as e:
            logger.error(f"Error fetching principal filings: {str(e)}")
            return []

    def _process_nyc_filing(self, filing):
        """Process and normalize NYC filing data to match our standard format."""
        try:
            # Extract client and registrant info if available
            client = {}
            registrant = {}
            
            if 'client' in filing:
                client = {
                    'id': filing['client'].get('id'),
                    'name': filing['client'].get('name'),
                    'address': filing['client'].get('address', {}).get('streetAddress'),
                    'description': filing['client'].get('businessNature')
                }
            
            if 'lobbyist' in filing:
                registrant = {
                    'id': filing['lobbyist'].get('id'),
                    'name': filing['lobbyist'].get('name'),
                    'address': filing['lobbyist'].get('address', {}).get('streetAddress'),
                    'contact': filing['lobbyist'].get('contactName')
                }
            
            # Extract activities
            activities = []
            if 'subjects' in filing:
                for subject in filing['subjects']:
                    activity = {
                        'description': subject.get('description', 'No description available'),
                        'general_issue_code': subject.get('category'),
                        'general_issue_code_display': subject.get('category')
                    }
                    
                    # Add agencies if available
                    if 'agencies' in subject:
                        activity['government_entities'] = [{'name': agency['name']} for agency in subject['agencies']]
                    
                    activities.append(activity)
            
            # Process filing date
            filing_date = filing.get('reportingPeriod', {}).get('periodEnd') or filing.get('filingDate')
            if not filing_date:
                filing_date = datetime.now().strftime('%Y-%m-%d')
            
            # Map to standardized format
            processed_filing = {
                'id': filing.get('id'),
                'filing_uuid': filing.get('id'),
                'filing_type': filing.get('filingType'),
                'filing_type_display': self.FILING_TYPES.get(filing.get('filingType'), filing.get('filingType')),
                'filing_year': filing.get('filingYear'),
                'filing_period': filing.get('reportingPeriod', {}).get('name', 'Unknown'),
                'period_display': filing.get('reportingPeriod', {}).get('name', 'Unknown'),
                'dt_posted': filing_date,
                'filing_date': filing_date,
                'registrant': registrant,
                'client': client,
                'income': filing.get('compensation', {}).get('amount'),
                'expenses': filing.get('expenses', {}).get('total'),
                'lobbying_activities': activities,
                'document_url': filing.get('documentUrl')
            }
            
            return processed_filing
        except Exception as e:
            logger.error(f"Error processing NYC filing: {str(e)}")
            return {}

    def get_filing_detail(self, filing_id):
        """
        Get detailed information about a specific filing.
        
        Args:
            filing_id: The unique identifier for the filing
            
        Returns:
            tuple: (filing_data, error)
        """
        if self.use_mock_data or '-' in filing_id and len(filing_id.split('-')[0]) <= 4:
            return self._mock_filing_detail(filing_id), None
            
        try:
            response = self.session.get(
                f"{self.api_base_url}/filings/{filing_id}",
                timeout=30
            )
            
            if response.status_code == 200:
                filing = response.json()
                return self._process_nyc_filing(filing), None
                
            error_msg = f"API request failed with status {response.status_code}"
            logger.error(error_msg)
            
            # Fall back to mock data if API request fails
            logger.info(f"Falling back to mock filing detail for ID: '{filing_id}'")
            return self._mock_filing_detail(filing_id), None
            
        except requests.exceptions.RequestException as e:
            error_msg = f"Network error retrieving filing detail: {str(e)}"
            logger.error(error_msg)
            
            # Fall back to mock data if API request fails
            logger.info(f"Falling back to mock filing detail for ID: '{filing_id}'")
            return self._mock_filing_detail(filing_id), None
        except Exception as e:
            error_msg = f"Unexpected error retrieving filing detail: {str(e)}"
            logger.error(error_msg)
            
            # Fall back to mock data if API request fails
            logger.info(f"Falling back to mock filing detail for ID: '{filing_id}'")
            return self._mock_filing_detail(filing_id), None

    def _mock_search_results(self, query, filters=None, page=1, page_size=25):
        """Generate mock search results based on the query."""
        import random
        import hashlib
        
        query = query.lower().strip()
        
        # Create a unique result set based on the query
        mock_results = []
        
        # Calculate a deterministic but different number for each query
        hash_obj = hashlib.md5(query.encode())
        hash_val = int(hash_obj.hexdigest(), 16)
        random.seed(hash_val)
        
        # Generate a random result count based on the query
        base_count = 20 + (hash_val % 100)
        
        # Lists of common NYC entities
        nyc_firms = [
            'Capalino+Company', 'Pitta Bishop & Del Giorno LLC', 'Constantinople & Vallone Consulting LLC',
            'Kasirer LLC', 'Geto & de Milly Inc.', 'Greenberg Traurig, LLP', 'Bolton-St. Johns LLC',
            'Fried, Frank, Harris, Shriver & Jacobson LLP', 'Manatt, Phelps & Phillips, LLP',
            'Davidoff Hutcher & Citron LLP', 'Mercury Public Affairs, LLC', 'Cozen O\'Connor Public Strategies',
            f'{query.title()} Associates', 'NYC Advocates', f'Metropolitan {query.title()} Group'
        ]
        
        nyc_clients = [
            'Real Estate Board of New York', 'Airbnb, Inc.', 'Uber Technologies Inc.',
            'New York University', 'Columbia University', 'Mount Sinai Hospital',
            'Madison Square Garden Entertainment Corp.', 'The Related Companies, L.P.',
            'SL Green Realty Corp.', 'Vornado Realty Trust', 'Extell Development Company',
            'New York Building Congress', 'Tishman Speyer', f'{query.title()} New York LLC'
        ]
        
        nyc_agencies = [
            'Office of the Mayor', 'Department of City Planning', 'Department of Buildings',
            'New York City Council', 'Department of Housing Preservation and Development',
            'Economic Development Corporation', 'Department of Transportation',
            'Department of Environmental Protection', 'Department of Health and Mental Hygiene',
            'Department of Education', 'Department of Parks and Recreation',
            'Department of Consumer and Worker Protection'
        ]
        
        nyc_issues = [
            'Land Use', 'Zoning', 'Housing', 'Transportation', 'Economic Development',
            'Health', 'Education', 'Environment', 'Public Safety', 'Finance',
            'Technology', 'Social Services', 'Contracts', 'Procurement'
        ]
        
        # Create mock results
        start_index = (page - 1) * page_size
        for i in range(min(page_size, max(0, base_count - start_index))):
            real_index = start_index + i
            
            # Create a unique ID for this filing
            filing_id = f"NYC-{hash_val % 10000}-{real_index:04d}"
            
            # Select company names based on index and query
            client_name = nyc_clients[real_index % len(nyc_clients)]
            registrant_name = nyc_firms[real_index % len(nyc_firms)]
            
            # Generate subject areas
            subjects = []
            num_subjects = random.randint(1, 3)
            selected_issues = random.sample(nyc_issues, num_subjects)
            
            for issue in selected_issues:
                subject = {
                    'description': f"Matters related to {issue.lower()} for {client_name}",
                    'general_issue_code': issue.upper().replace(' ', '_'),
                    'general_issue_code_display': issue
                }
                
                # Add agencies
                num_agencies = random.randint(1, 3)
                subject['government_entities'] = []
                for _ in range(num_agencies):
                    agency = random.choice(nyc_agencies)
                    subject['government_entities'].append({'name': agency})
                
                subjects.append(subject)
            
            # Generate a random filing date within the selected year
            filing_year = filters.get('filing_year', 2023) if filters else 2023
            try:
                filing_year = int(filing_year)
            except (ValueError, TypeError):
                filing_year = 2023
                
            filing_month = random.randint(1, 12)
            filing_day = random.randint(1, 28)
            filing_date = f"{filing_year}-{filing_month:02d}-{filing_day:02d}"
            
            # Generate a random amount
            compensation = round(random.randint(5, 30) * 10000, -3)
            expenses = round(random.randint(1, 5) * 1000, -2)
            
            # Create the mock filing
            filing = {
                'id': filing_id,
                'filing_uuid': filing_id,
                'filing_type': random.choice(list(self.FILING_TYPES.keys())),
                'filing_year': filing_year,
                'filing_period': f"January 1 - December 31, {filing_year}",
                'period_display': f"January 1 - December 31, {filing_year}",
                'dt_posted': filing_date,
                'filing_date': filing_date,
                'client': {
                    'id': f"c-{hash(client_name) % 100000}",
                    'name': client_name,
                    'description': f"Company involved in {subjects[0]['general_issue_code_display'].lower()}"
                },
                'registrant': {
                    'id': f"r-{hash(registrant_name) % 100000}",
                    'name': registrant_name,
                    'description': 'Lobbying Firm',
                    'contact': f"{random.choice(['John', 'Sarah', 'Michael', 'Jennifer'])} {random.choice(['Smith', 'Johnson', 'Williams', 'Brown'])}"
                },
                'income': compensation,
                'expenses': expenses,
                'lobbying_activities': subjects,
                'document_url': f"https://example.com/nyc/filings/{filing_id}.pdf",
                # Add metadata to clearly identify as mock data
                'meta': {
                    'is_mock': True,
                    'original_query': query
                }
            }
            
            mock_results.append(filing)
        
        # Calculate pagination info
        total_pages = (base_count + page_size - 1) // page_size
        
        pagination = {
            "total_pages": total_pages,
            "page": page,
            "has_next": page < total_pages,
            "has_prev": page > 1,
            "count": base_count,
            "page_size": page_size
        }
        
        logger.info(f"Generated {len(mock_results)} mock NYC results for '{query}' (page {page} of {total_pages}, total: {base_count})")
        
        return mock_results, base_count, pagination, None

    def _mock_filings_for_entity(self, entity_id, entity_type, filters=None):
        """Generate mock filings for an entity (lobbyist, client, or principal)."""
        import random
        import hashlib
        
        # Seed with entity ID for consistent results
        random.seed(hash(entity_id))
        
        # Generate a realistic number of filings
        num_filings = random.randint(3, 15)
        
        # Filter by year if specified
        filing_year = filters.get('filing_year', None) if filters else None
        try:
            filing_year = int(filing_year) if filing_year and filing_year != 'all' else None
        except (ValueError, TypeError):
            filing_year = None
        
        filings = []
        
        # Generate NYC agencies
        nyc_agencies = [
            'Office of the Mayor', 'Department of City Planning', 'Department of Buildings',
            'New York City Council', 'Department of Housing Preservation and Development',
            'Economic Development Corporation', 'Department of Transportation',
            'Department of Environmental Protection', 'Department of Health and Mental Hygiene'
        ]
        
        # Generate NYC issues
        nyc_issues = [
            'Land Use', 'Zoning', 'Housing', 'Transportation', 'Economic Development',
            'Health', 'Education', 'Environment', 'Public Safety', 'Finance'
        ]
        
        # Generate filings for different years (2020-2023)
        years = [2020, 2021, 2022, 2023]
        if filing_year:
            years = [filing_year]
        
        for year in years:
            # Skip if a specific year was requested and this isn't it
            if filing_year and year != filing_year:
                continue
                
            # Generate 1-3 filings per year
            year_filings = random.randint(1, 3)
            for i in range(year_filings):
                # Generate filing date
                month = random.randint(1, 12)
                day = random.randint(1, 28)
                date = f"{year}-{month:02d}-{day:02d}"
                
                # Generate ID
                filing_id = f"NYC-{entity_id}-{year}-{i}"
                
                # Generate client and registrant based on entity type
                client = {}
                registrant = {}
                
                client_name = f"Client {random.randint(1000, 9999)}"
                registrant_name = f"Lobbyist {random.randint(1000, 9999)}"
                
                if entity_type == 'client':
                    client = {
                        'id': entity_id,
                        'name': f"Client {entity_id}",
                        'description': f"Company involved in {random.choice(nyc_issues).lower()}"
                    }
                    registrant = {
                        'id': f"r-{random.randint(10000, 99999)}",
                        'name': registrant_name,
                        'description': 'Lobbying Firm',
                        'contact': f"{random.choice(['John', 'Sarah', 'Michael', 'Jennifer'])} {random.choice(['Smith', 'Johnson', 'Williams', 'Brown'])}"
                    }
                else:  # lobbyist or principal
                    client = {
                        'id': f"c-{random.randint(10000, 99999)}",
                        'name': client_name,
                        'description': f"Company involved in {random.choice(nyc_issues).lower()}"
                    }
                    registrant = {
                        'id': entity_id,
                        'name': f"Lobbyist {entity_id}",
                        'description': 'Lobbying Firm',
                        'contact': f"{random.choice(['John', 'Sarah', 'Michael', 'Jennifer'])} {random.choice(['Smith', 'Johnson', 'Williams', 'Brown'])}"
                    }
                
                # Generate subjects/activities
                subjects = []
                num_subjects = random.randint(1, 3)
                selected_issues = random.sample(nyc_issues, num_subjects)
                
                for issue in selected_issues:
                    subject = {
                        'description': f"Matters related to {issue.lower()} for {client['name']}",
                        'general_issue_code': issue.upper().replace(' ', '_'),
                        'general_issue_code_display': issue
                    }
                    
                    # Add agencies
                    num_agencies = random.randint(1, 3)
                    subject['government_entities'] = []
                    for _ in range(num_agencies):
                        agency = random.choice(nyc_agencies)
                        subject['government_entities'].append({'name': agency})
                    
                    subjects.append(subject)
                
                # Generate amounts
                compensation = round(random.randint(5, 30) * 10000, -3)
                expenses = round(random.randint(1, 5) * 1000, -2)
                
                # Create filing
                filing = {
                    'id': filing_id,
                    'filing_uuid': filing_id,
                    'filing_type': random.choice(list(self.FILING_TYPES.keys())),
                    'filing_type_display': random.choice(list(self.FILING_TYPES.values())),
                    'filing_year': year,
                    'filing_period': f"January 1 - December 31, {year}",
                    'period_display': f"January 1 - December 31, {year}",
                    'dt_posted': date,
                    'filing_date': date,
                    'client': client,
                    'registrant': registrant,
                    'income': compensation,
                    'expenses': expenses,
                    'lobbying_activities': subjects,
                    'document_url': f"https://example.com/nyc/filings/{filing_id}.pdf",
                    # Add metadata to clearly identify as mock data
                    'meta': {
                        'is_mock': True
                    }
                }
                
                filings.append(filing)
        
        return filings

    def _mock_filing_detail(self, filing_id):
        """Generate a mock filing detail for a specific ID."""
        import random
        import hashlib
        
        # Seed with filing ID for consistent results
        random.seed(hash(filing_id))
        
        # Parse parts from the ID if possible
        parts = filing_id.split('-')
        year = 2023
        if len(parts) > 2:
            try:
                year = int(parts[2])
            except (IndexError, ValueError):
                pass
        
        # Generate NYC agencies
        nyc_agencies = [
            'Office of the Mayor', 'Department of City Planning', 'Department of Buildings',
            'New York City Council', 'Department of Housing Preservation and Development',
            'Economic Development Corporation', 'Department of Transportation',
            'Department of Environmental Protection', 'Department of Health and Mental Hygiene',
            'Department of Education', 'Department of Parks and Recreation',
            'Department of Consumer and Worker Protection'
        ]
        
        # Generate NYC issues
        nyc_issues = [
            'Land Use', 'Zoning', 'Housing', 'Transportation', 'Economic Development',
            'Health', 'Education', 'Environment', 'Public Safety', 'Finance',
            'Technology', 'Social Services', 'Contracts', 'Procurement'
        ]
        
        # Generate client and registrant
        client_name = f"NYC Client {random.randint(1000, 9999)}"
        registrant_name = f"NYC Lobbyist Firm {random.randint(1000, 9999)}"
        
        client = {
            'id': f"c-{random.randint(10000, 99999)}",
            'name': client_name,
            'description': f"Company involved in {random.choice(nyc_issues).lower()}",
            'address': f"{random.randint(100, 999)} Madison Avenue, New York, NY 10022"
        }
        
        registrant = {
            'id': f"r-{random.randint(10000, 99999)}",
            'name': registrant_name,
            'description': 'Lobbying and Government Relations Firm',
            'contact': f"{random.choice(['John', 'Sarah', 'Michael', 'Jennifer'])} {random.choice(['Smith', 'Johnson', 'Williams', 'Brown'])}",
            'address': f"{random.randint(100, 999)} 3rd Avenue, Suite {random.randint(100, 999)}, New York, NY 10017"
        }
        
        # Generate random filing period and date
        filing_month = random.randint(1, 12)
        filing_day = random.randint(1, 28)
        filing_date = f"{year}-{filing_month:02d}-{filing_day:02d}"
        filing_period = f"January 1 - December 31, {year}"
        
        # Generate random filing type
        filing_type = random.choice(list(self.FILING_TYPES.keys()))
        
        # Generate subjects/activities
        subjects = []
        num_subjects = random.randint(1, 4)
        selected_issues = random.sample(nyc_issues, min(num_subjects, len(nyc_issues)))
        
        for issue in selected_issues:
            # Select 1-3 agencies for this issue
            selected_agencies = random.sample(nyc_agencies, min(random.randint(1, 3), len(nyc_agencies)))
            
            government_entities = []
            for agency in selected_agencies:
                government_entities.append({
                    'name': agency,
                    'type': 'City Agency'
                })
            
            # Create a description
            description = f"Matters related to {issue.lower()} regulations and policies affecting {client_name}."
            
            subjects.append({
                'description': description,
                'general_issue_code': issue.upper().replace(' ', '_'),
                'general_issue_code_display': issue,
                'government_entities': government_entities
            })
        
        # Generate random compensation and expenses
        compensation = round(random.randint(20, 100) * 1000, -3)
        expenses = round(random.randint(1, 10) * 1000, -2)
        
        # Create mock filing detail
        filing_detail = {
            'id': filing_id,
            'filing_uuid': filing_id,
            'filing_type': filing_type,
            'filing_type_display': self.FILING_TYPES.get(filing_type, filing_type),
            'filing_year': year,
            'filing_period': filing_period,
            'period_display': filing_period,
            'dt_posted': filing_date,
            'filing_date': filing_date,
            'registrant': registrant,
            'client': client,
            'income': compensation,
            'expenses': expenses,
            'amount': compensation,
            'amount_reported': True,
            'lobbying_activities': subjects,
            'document_url': f"https://example.com/nyc/filings/{filing_id}.pdf",
            # Add metadata to clearly identify as mock data
            'meta': {
                'is_mock': True
            }
        }
        
        return filing_detail
    
    def fetch_visualization_data(self, query, filters=None):
        """
        Fetch data for visualizations.
        
        Args:
            query: Search term (person or organization name)
            filters: Additional filters to apply to the search
            
        Returns:
            tuple: (visualization_data, error)
        """
        try:
            # Get a larger set of results for visualization
            results, count, _, error = self.search_filings(
                query, 
                filters=filters,
                page=1, 
                page_size=100
            )
            
            if error or not results:
                return None, error if error else "No data found for visualization"
            
            # Prepare data for visualization
            years_data = defaultdict(int)
            registrants_data = defaultdict(int)
            agencies_data = defaultdict(int)
            issues_data = defaultdict(int)
            amounts_data = []
            
            # Process results
            for filing in results:
                # Track filing years
                if filing.get("filing_year"):
                    try:
                        year = str(filing["filing_year"]).strip()
                        if year.isdigit():
                            years_data[year] += 1
                    except (ValueError, TypeError):
                        pass
                
                # Track registrants
                if filing.get("registrant") and filing["registrant"].get("name"):
                    registrants_data[filing["registrant"]["name"]] += 1
                
                # Track amounts if available
                if filing.get("income") and filing.get("filing_date"):
                    try:
                        amount = float(filing["income"])
                        amounts_data.append((filing["filing_date"], amount))
                    except (ValueError, TypeError):
                        pass
                
                # Track issues and agencies
                activities = filing.get("lobbying_activities", [])
                for activity in activities:
                    issue = activity.get("general_issue_code_display")
                    if issue:
                        issues_data[issue] += 1
                    
                    govt_entities = activity.get("government_entities", [])
                    for entity in govt_entities:
                        agency = entity.get("name")
                        if agency:
                            agencies_data[agency] += 1
            
            # Sort years data
            sorted_years = sorted(years_data.items())
            years_chart = {
                "labels": [year for year, _ in sorted_years],
                "values": [count for _, count in sorted_years]
            }
            
            # Get top registrants
            top_registrants = sorted(registrants_data.items(), key=lambda x: x[1], reverse=True)[:10]
            registrants_chart = {
                "labels": [name for name, _ in top_registrants],
                "values": [count for _, count in top_registrants]
            }
            
            # Get top agencies
            top_agencies = sorted(agencies_data.items(), key=lambda x: x[1], reverse=True)[:10]
            agencies_chart = {
                "labels": [name for name, _ in top_agencies],
                "values": [count for _, count in top_agencies]
            }
            
            # Get top issues
            top_issues = sorted(issues_data.items(), key=lambda x: x[1], reverse=True)[:10]
            issues_chart = {
                "labels": [name for name, _ in top_issues],
                "values": [count for _, count in top_issues]
            }
            
            # Process spending data
            spending_by_period = defaultdict(float)
            for date, amount in amounts_data:
                # Convert to year-month format
                if isinstance(date, str):
                    try:
                        date_obj = datetime.strptime(date, "%Y-%m-%d")
                        period = date_obj.strftime("%Y-%m")
                    except:
                        # If parse fails, use the year part
                        period = date[:4] if len(date) >= 4 else "Unknown"
                else:
                    period = "Unknown"
                
                spending_by_period[period] += amount
            
            # Sort by period
            sorted_spending = sorted(spending_by_period.items())
            spending_chart = {
                "labels": [period for period, _ in sorted_spending],
                "values": [amount for _, amount in sorted_spending]
            }
            
            visualization_data = {
                "years_data": years_chart,
                "top_entities": registrants_chart,
                "spending_trend": spending_chart,
                "issue_areas": issues_chart,
                "government_entities": agencies_chart
            }
            
            return visualization_data, None
            
        except Exception as e:
            logger.error(f"Error generating visualization data: {str(e)}")
            return None, f"An error occurred while generating visualization data: {str(e)}"
    
    @property
    def source_name(self) -> str:
        """Return the name of this data source."""
        return "NYC Lobbying"
    
    @property
    def government_level(self) -> str:
        """Return the level of government (Federal, State, Local)."""
        return "Local"