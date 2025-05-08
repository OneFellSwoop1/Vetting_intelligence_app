# data_sources/nyc_checkbook.py
"""
CheckbookNYC Data Source implementation for the Vetting Intelligence Hub.
This module integrates with the NYC Checkbook (spending transparency) API.
"""

import os
import json
import requests
import logging
import time
import urllib.parse
from datetime import datetime, timedelta
from collections import defaultdict
from requests.packages.urllib3.util.retry import Retry
from requests.adapters import HTTPAdapter
import traceback

from .base import LobbyingDataSource

# Set up logging
logger = logging.getLogger('nyc_checkbook')
logger.setLevel(logging.INFO)

class NYCCheckbookDataSource(LobbyingDataSource):
    """NYC Checkbook (contract & spending) database data source."""
    
    CONTRACT_TYPES = {
        'EXPENSE': 'Expense Contract',
        'REVENUE': 'Revenue Contract',
        'AWARD': 'Award Agreement',
        'GRANT': 'Grant Agreement',
        'CAPITAL': 'Capital Project'
    }
    
    def __init__(self, api_base_url="https://data.cityofnewyork.us/resource", api_app_token=None, use_mock_data=False):
        """
        Initialize the NYC Checkbook data source.
        
        Args:
            api_base_url: Base URL for the NYC Open Data API
            api_app_token: Optional app token for increased rate limits 
            use_mock_data: If True, use mock data instead of real API calls (for testing)
        """
        self.api_base_url = api_base_url.rstrip('/')
        self.api_app_token = api_app_token
        self.use_mock_data = use_mock_data
        
        # Define dataset IDs for NYC Checkbook data
        self.datasets = {
            'contracts': '6vm5-bzd6',  # Active Expense Contracts
            'spending': 'bmes-97ch',   # Spending by Contract
            'payroll': 'k397-673e',    # Citywide Payroll Data
            'capital': 'rssh-rpwd',    # Capital Projects
            'vendors': '8qd4-ycjj'     # Vendor Information
        }
        
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
        
        # Add API token if provided
        if self.api_app_token:
            self.session.headers.update({
                'X-App-Token': self.api_app_token
            })
        
    def search_filings(self, query, filters=None, page=1, page_size=25):
        """
        Search for contracts and spending in the NYC Checkbook database.
        
        Args:
            query: Search term (vendor/contractor name)
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
            logger.info(f"Searching NYC Checkbook with processed query: '{processed_query}'")
            
            # Determine search type and dataset
            search_type = filters.get('search_type', 'vendor').lower()
            
            if search_type == 'vendor':
                # Search for contracts by vendor name
                results, count, pagination, error = self._search_contracts_by_vendor(processed_query, filters, page, page_size)
            elif search_type == 'agency':
                # Search for contracts by agency
                results, count, pagination, error = self._search_contracts_by_agency(processed_query, filters, page, page_size)
            else:
                # Default to searching by vendor name
                results, count, pagination, error = self._search_contracts_by_vendor(processed_query, filters, page, page_size)
            
            if error:
                logger.error(f"Error searching NYC Checkbook: {error}")
                return [], 0, {}, error
            
            # Format the results to match our standard structure
            processed_results = [self._process_contract_data(contract) for contract in results]
            
            return processed_results, count, pagination, None
                
        except requests.exceptions.RequestException as e:
            error_message = f"Request exception: {str(e)}"
            logger.error(error_message)
            return [], 0, {}, error_message
        except Exception as e:
            error_message = f"Unexpected error: {str(e)}"
            logger.error(error_message)
            logger.error(traceback.format_exc())
            return [], 0, {}, error_message

    def _search_contracts_by_vendor(self, vendor_name, filters, page, page_size):
        """Search for contracts where the vendor name matches the query."""
        try:
            # Construct SoQL query (Socrata Open Data Query Language)
            offset = (page - 1) * page_size
            
            # Build WHERE clause for vendor name (using LIKE for partial matching)
            where_clause = f"UPPER(vendor_name) LIKE '%{vendor_name.upper()}%'"
            
            # Add year filter if specified
            if 'filing_year' in filters and filters['filing_year'] != 'all':
                try:
                    year = int(filters['filing_year'])
                    where_clause += f" AND fiscal_year={year}"
                except (ValueError, TypeError):
                    pass
            
            # Add specific filters based on contract data
            if 'contract_type' in filters and filters['contract_type'] != 'all':
                where_clause += f" AND contract_type='{filters['contract_type']}'"
            
            if 'amount_min' in filters and filters['amount_min']:
                try:
                    min_amount = float(filters['amount_min'])
                    where_clause += f" AND maximum_contract_amount>={min_amount}"
                except (ValueError, TypeError):
                    pass
            
            # Construct the full SoQL query
            query = f"$where={where_clause}&$order=end_date DESC&$limit={page_size}&$offset={offset}"
            
            # Add count to get total number of matching records
            count_query = f"$where={where_clause}&$select=COUNT(*) AS count"
            
            # Execute count query
            count_url = f"{self.api_base_url}/{self.datasets['contracts']}.json?{count_query}"
            count_response = self.session.get(count_url, timeout=30)
            
            if count_response.status_code != 200:
                return [], 0, {}, f"API error: {count_response.status_code}"
            
            count_data = count_response.json()
            total_count = int(count_data[0]['count']) if count_data else 0
            
            # Execute main query
            url = f"{self.api_base_url}/{self.datasets['contracts']}.json?{query}"
            response = self.session.get(url, timeout=30)
            
            if response.status_code != 200:
                return [], 0, {}, f"API error: {response.status_code}"
            
            contracts = response.json()
            
            # Calculate pagination info
            total_pages = (total_count + page_size - 1) // page_size  # Ceiling division
            pagination = {
                "count": total_count,
                "page": page,
                "page_size": page_size,
                "total_pages": total_pages,
                "has_next": page < total_pages,
                "has_prev": page > 1
            }
            
            return contracts, total_count, pagination, None
            
        except Exception as e:
            error_message = f"Error searching contracts by vendor: {str(e)}"
            logger.error(error_message)
            return [], 0, {}, error_message

    def _search_contracts_by_agency(self, agency_name, filters, page, page_size):
        """Search for contracts where the agency matches the query."""
        try:
            # Construct SoQL query
            offset = (page - 1) * page_size
            
            # Build WHERE clause for agency name
            where_clause = f"UPPER(agency_name) LIKE '%{agency_name.upper()}%'"
            
            # Add year filter if specified
            if 'filing_year' in filters and filters['filing_year'] != 'all':
                try:
                    year = int(filters['filing_year'])
                    where_clause += f" AND fiscal_year={year}"
                except (ValueError, TypeError):
                    pass
            
            # Construct the full SoQL query
            query = f"$where={where_clause}&$order=end_date DESC&$limit={page_size}&$offset={offset}"
            
            # Add count to get total number of matching records
            count_query = f"$where={where_clause}&$select=COUNT(*) AS count"
            
            # Execute count query
            count_url = f"{self.api_base_url}/{self.datasets['contracts']}.json?{count_query}"
            count_response = self.session.get(count_url, timeout=30)
            
            if count_response.status_code != 200:
                return [], 0, {}, f"API error: {count_response.status_code}"
            
            count_data = count_response.json()
            total_count = int(count_data[0]['count']) if count_data else 0
            
            # Execute main query
            url = f"{self.api_base_url}/{self.datasets['contracts']}.json?{query}"
            response = self.session.get(url, timeout=30)
            
            if response.status_code != 200:
                return [], 0, {}, f"API error: {response.status_code}"
            
            contracts = response.json()
            
            # Calculate pagination info
            total_pages = (total_count + page_size - 1) // page_size  # Ceiling division
            pagination = {
                "count": total_count,
                "page": page,
                "page_size": page_size,
                "total_pages": total_pages,
                "has_next": page < total_pages,
                "has_prev": page > 1
            }
            
            return contracts, total_count, pagination, None
            
        except Exception as e:
            error_message = f"Error searching contracts by agency: {str(e)}"
            logger.error(error_message)
            return [], 0, {}, error_message

    def _process_contract_data(self, contract):
        """Process and normalize NYC Checkbook contract data to match our standard format."""
        try:
            # Extract client (agency) and registrant (vendor) info
            client = {
                'id': contract.get('agency_id'),
                'name': contract.get('agency_name'),
                'description': 'NYC Government Agency'
            }
            
            registrant = {
                'id': contract.get('vendor_id'),
                'name': contract.get('vendor_name'),
                'address': contract.get('address'),
                'contact': contract.get('contact_name')
            }
            
            # Extract activities
            activities = []
            activity = {
                'description': contract.get('purpose') or contract.get('contract_description') or "City contract",
                'general_issue_code': contract.get('contract_type'),
                'general_issue_code_display': self.CONTRACT_TYPES.get(
                    contract.get('contract_type'), contract.get('contract_type')
                )
            }
            
            # Add the agency as government entity
            if client.get('name'):
                activity['government_entities'] = [{'name': client['name']}]
            
            activities.append(activity)
            
            # Process dates
            start_date = contract.get('start_date')
            end_date = contract.get('end_date')
            
            # Map to standardized format
            processed_contract = {
                'id': contract.get('contract_id'),
                'filing_uuid': contract.get('contract_id'),
                'filing_type': contract.get('contract_type'),
                'filing_type_display': self.CONTRACT_TYPES.get(
                    contract.get('contract_type'), contract.get('contract_type')
                ),
                'filing_year': contract.get('fiscal_year'),
                'filing_period': f"{start_date} - {end_date}" if start_date and end_date else "N/A",
                'period_display': f"{start_date} - {end_date}" if start_date and end_date else "N/A",
                'dt_posted': contract.get('start_date') or contract.get('registered_date'),
                'filing_date': contract.get('start_date') or contract.get('registered_date'),
                'registrant': registrant,
                'client': client,
                'income': contract.get('maximum_contract_amount'),
                'expenses': None,
                'amount': contract.get('maximum_contract_amount'),
                'amount_reported': True if contract.get('maximum_contract_amount') else False,
                'lobbying_activities': activities,
                'document_url': f"https://www.checkbooknyc.com/contract_details/{contract.get('contract_id')}"
            }
            
            return processed_contract
        except Exception as e:
            logger.error(f"Error processing NYC Checkbook contract: {str(e)}")
            return {}

    def get_filing_detail(self, filing_id):
        """
        Get detailed information about a specific contract.
        
        Args:
            filing_id: The unique identifier for the contract
            
        Returns:
            tuple: (contract_data, error)
        """
        if self.use_mock_data or '-' in filing_id and len(filing_id.split('-')[0]) <= 4:
            return self._mock_filing_detail(filing_id), None
            
        try:
            # Construct SoQL query to get contract by ID
            query = f"$where=contract_id='{filing_id}'"
            
            # Execute query
            url = f"{self.api_base_url}/{self.datasets['contracts']}.json?{query}"
            response = self.session.get(url, timeout=30)
            
            if response.status_code == 200:
                contracts = response.json()
                if contracts:
                    contract = contracts[0]
                    # Process contract data
                    return self._process_contract_data(contract), None
                else:
                    return None, "Contract not found"
            else:
                error_msg = f"API request failed with status {response.status_code}"
                logger.error(error_msg)
                
                # Fall back to mock data if API request fails
                logger.info(f"Falling back to mock contract detail for ID: '{filing_id}'")
                return self._mock_filing_detail(filing_id), None
            
        except requests.exceptions.RequestException as e:
            error_msg = f"Network error retrieving contract detail: {str(e)}"
            logger.error(error_msg)
            
            # Fall back to mock data if API request fails
            return self._mock_filing_detail(filing_id), None
        except Exception as e:
            error_msg = f"Unexpected error retrieving contract detail: {str(e)}"
            logger.error(error_msg)
            
            # Fall back to mock data if API request fails
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
        base_count = 15 + (hash_val % 50)
        
        # Lists of common NYC agencies
        nyc_agencies = [
            'Department of Education', 'Health and Hospitals Corporation', 
            'Department of Transportation', 'Department of Environmental Protection',
            'Department of Parks and Recreation', 'Department of Sanitation',
            'Department of Housing Preservation and Development', 'Police Department',
            'Fire Department', 'Department of Correction',
            'Department of Information Technology and Telecommunications'
        ]
        
        # Lists of contract purposes
        contract_purposes = [
            'Technology Services', 'Consulting Services', 'Construction Services',
            'Professional Services', 'Equipment and Supplies', 'Maintenance Services',
            'Engineering Services', 'Educational Services', 'Healthcare Services',
            'Transportation Services', 'Social Services', 'Security Services'
        ]
        
        # Create mock results
        start_index = (page - 1) * page_size
        for i in range(min(page_size, max(0, base_count - start_index))):
            real_index = start_index + i
            
            # Create a unique ID for this contract
            contract_id = f"NYC-CT{hash_val % 10000}-{real_index:04d}"
            
            # Generate agency and vendor based on the query and index
            if filters and filters.get('search_type') == 'agency':
                # If searching by agency, use the query as agency name
                agency_name = f"{query.title()} {nyc_agencies[real_index % len(nyc_agencies)]}"
                vendor_name = f"Vendor {hash_val % 1000 + i}"
            else:
                # Default to searching by vendor name
                agency_name = nyc_agencies[real_index % len(nyc_agencies)]
                vendor_name = f"{query.title()} {['Inc.', 'LLC', 'Corp.', 'Group', 'Services'][i % 5]}"
            
            # Generate contract dates
            year = filters.get('filing_year', random.randint(2020, 2023)) if filters else random.randint(2020, 2023)
            try:
                year = int(year)
            except (ValueError, TypeError):
                year = random.randint(2020, 2023)
                
            start_month = random.randint(1, 12)
            start_day = random.randint(1, 28)
            start_date = f"{year}-{start_month:02d}-{start_day:02d}"
            
            # Contract duration 1-3 years
            duration_years = random.randint(1, 3)
            end_year = year + duration_years
            end_date = f"{end_year}-{start_month:02d}-{start_day:02d}"
            
            # Generate contract amount
            amount = round(random.uniform(100000, 5000000), -3)  # Round to nearest thousand
            
            # Select contract type
            contract_type = random.choice(list(self.CONTRACT_TYPES.keys()))
            
            # Generate contract purpose
            purpose = f"{contract_purposes[i % len(contract_purposes)]} for {agency_name}"
            
            # Create the mock contract
            contract = {
                'contract_id': contract_id,
                'contract_type': contract_type,
                'fiscal_year': year,
                'start_date': start_date,
                'end_date': end_date,
                'vendor_name': vendor_name,
                'vendor_id': f"V-{hash(vendor_name) % 100000}",
                'agency_name': agency_name,
                'agency_id': f"A-{hash(agency_name) % 100000}",
                'purpose': purpose,
                'maximum_contract_amount': amount,
                # Add additional fields
                'registered_date': start_date,
                'address': f"{random.randint(100, 999)} {random.choice(['Broadway', 'Madison Ave', 'Lexington Ave', '5th Ave'])}, New York, NY",
                'contact_name': f"{random.choice(['John', 'Sarah', 'Michael', 'Jennifer'])} {random.choice(['Smith', 'Johnson', 'Williams', 'Brown'])}",
                # Add metadata to clearly identify as mock data
                'meta': {
                    'is_mock': True,
                    'original_query': query
                }
            }
            
            mock_results.append(contract)
        
        # Calculate pagination info
        total_pages = (base_count + page_size - 1) // page_size
        
        pagination = {
            "total_pages": total_pages,
            "page": page,
            "has_next": page < total_pages,
            "has_prev": page > 1,
            "count": base_count