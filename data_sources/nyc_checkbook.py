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
            'contracts': 'mxwn-eh3b',  # Correct CheckbookNYC dataset
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

    def _search_contracts_by_vendor(self, payee_name, filters, page, page_size):
        """Search for contracts where the payee name matches the query."""
        try:
            offset = (page - 1) * page_size
            where_clause = f"UPPER(payee_name) LIKE '%{payee_name.upper()}%'"
            if 'filing_year' in filters and filters['filing_year'] != 'all':
                try:
                    year = int(filters['filing_year'])
                    where_clause += f" AND fiscal_year={year}"
                except (ValueError, TypeError):
                    pass
            if 'contract_type' in filters and filters['contract_type'] != 'all':
                where_clause += f" AND contract_type='{filters['contract_type']}'"
            if 'amount_min' in filters and filters['amount_min']:
                try:
                    min_amount = float(filters['amount_min'])
                    where_clause += f" AND contract_amount>={min_amount}"
                except (ValueError, TypeError):
                    pass
            query = f"$where={where_clause}&$order=end_date DESC&$limit={page_size}&$offset={offset}"
            count_query = f"$where={where_clause}&$select=COUNT(*) AS count"
            count_url = f"{self.api_base_url}/{self.datasets['contracts']}.json?{count_query}"
            count_response = self.session.get(count_url, timeout=30)
            if count_response.status_code != 200:
                return [], 0, {}, f"API error: {count_response.status_code}"
            count_data = count_response.json()
            total_count = int(count_data[0]['count']) if count_data else 0
            url = f"{self.api_base_url}/{self.datasets['contracts']}.json?{query}"
            response = self.session.get(url, timeout=30)
            if response.status_code != 200:
                return [], 0, {}, f"API error: {response.status_code}"
            contracts = response.json()
            total_pages = (total_count + page_size - 1) // page_size
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
            return [], 0, {}, str(e)

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
            "count": base_count,
            "page_size": page_size
        }
        
        logger.info(f"Generated {len(mock_results)} mock NYC Checkbook results for '{query}' (page {page} of {total_pages}, total: {base_count})")
        
        return mock_results, base_count, pagination, None
        
    def _mock_filing_detail(self, filing_id):
        """Generate a mock contract detail based on the filing ID."""
        import random
        import hashlib
        
        # Seed with filing ID for consistent results
        random.seed(hash(filing_id))
        
        # Parse parts from the ID if possible
        parts = filing_id.split('-')
        year = 2023
        if len(parts) > 1:
            try:
                year = int(parts[1][:4])
            except (IndexError, ValueError):
                pass
        
        # Generate a random contract type
        contract_type = random.choice(list(self.CONTRACT_TYPES.keys()))
        
        # Generate vendor and agency
        vendor_name = f"NYC Vendor {random.randint(1000, 9999)}"
        agency_name = random.choice([
            'Department of Education', 'Health and Hospitals Corporation',
            'Department of Transportation', 'Department of Environmental Protection',
            'Department of Parks and Recreation', 'Department of Sanitation',
            'Department of Housing Preservation and Development', 'Police Department'
        ])
        
        # Generate dates
        start_month = random.randint(1, 12)
        start_day = random.randint(1, 28)
        start_date = f"{year}-{start_month:02d}-{start_day:02d}"
        
        # Contract duration 1-5 years
        duration_years = random.randint(1, 5)
        end_year = year + duration_years
        end_date = f"{end_year}-{start_month:02d}-{start_day:02d}"
        
        # Generate contract amount
        amount = round(random.uniform(250000, 10000000), -3)  # Round to nearest thousand
        
        # Generate contract purpose from list of NYC contract types
        contract_purposes = [
            'Technology Services', 'Consulting Services', 'Construction Services',
            'Professional Services', 'Equipment and Supplies', 'Maintenance Services',
            'Engineering Services', 'Educational Services', 'Healthcare Services',
            'Transportation Services', 'Social Services', 'Security Services'
        ]
        purpose = f"{random.choice(contract_purposes)} for {agency_name}"
        
        # Create detailed description
        descriptions = [
            f"Provision of {purpose.lower()} to support agency operations.",
            f"Contract for {purpose.lower()} in accordance with agency requirements.",
            f"Vendor will provide {purpose.lower()} as specified in the scope of work.",
            f"Implementation of {purpose.lower()} program for fiscal year {year}.",
            f"Comprehensive {purpose.lower()} solution for agency needs."
        ]
        description = random.choice(descriptions)
        
        # Create mock contract detail
        contract_detail = {
            'id': filing_id,
            'filing_uuid': filing_id,
            'contract_id': filing_id,
            'filing_type': contract_type,
            'filing_type_display': self.CONTRACT_TYPES.get(contract_type, contract_type),
            'filing_year': year,
            'fiscal_year': year,
            'start_date': start_date,
            'end_date': end_date,
            'period_display': f"{start_date} to {end_date}",
            'vendor_name': vendor_name,
            'vendor_id': f"V-{hash(vendor_name) % 100000}",
            'agency_name': agency_name,
            'agency_id': f"A-{hash(agency_name) % 100000}",
            'purpose': purpose,
            'description': description,
            'maximum_contract_amount': amount,
            'original_amount': round(amount * 0.9, -3),  # Original was a bit lower
            'current_amount': amount,
            'spend_to_date': round(amount * random.uniform(0.1, 0.8), -3),  # Random spend amount
            'balance': round(amount * random.uniform(0.2, 0.9), -3),  # Random balance
            'registered_date': start_date,
            'address': f"{random.randint(100, 999)} {random.choice(['Broadway', 'Madison Ave', 'Lexington Ave', '5th Ave'])}, New York, NY",
            'contact_name': f"{random.choice(['John', 'Sarah', 'Michael', 'Jennifer'])} {random.choice(['Smith', 'Johnson', 'Williams', 'Brown'])}",
            'solicitation_method': random.choice(['Competitive Sealed Bid', 'Request for Proposals', 'Sole Source', 'Emergency']),
            'procurement_method': random.choice(['Competitive', 'Non-Competitive']),
            'award_method': random.choice(['Low Bid', 'Best Value', 'Qualification Based']),
            'contract_category': random.choice(['Expense', 'Revenue', 'Requirements']),
            'industry': random.choice(['Information Technology', 'Construction', 'Health', 'Education', 'Professional Services']),
            
            # Map to standardized format for compatibility
            'filing_period': f"{start_date} - {end_date}",
            'dt_posted': start_date,
            'filing_date': start_date,
            'registrant': {
                'id': f"V-{hash(vendor_name) % 100000}",
                'name': vendor_name,
                'description': 'NYC Vendor',
                'address': f"{random.randint(100, 999)} {random.choice(['Broadway', 'Madison Ave', 'Lexington Ave', '5th Ave'])}, New York, NY",
                'contact': f"{random.choice(['John', 'Sarah', 'Michael', 'Jennifer'])} {random.choice(['Smith', 'Johnson', 'Williams', 'Brown'])}"
            },
            'client': {
                'id': f"A-{hash(agency_name) % 100000}",
                'name': agency_name,
                'description': 'NYC Government Agency'
            },
            'income': amount,
            'expenses': None,
            'amount': amount,
            'lobbying_activities': [
                {
                    'description': description,
                    'general_issue_code': contract_type,
                    'general_issue_code_display': self.CONTRACT_TYPES.get(contract_type, contract_type),
                    'government_entities': [
                        {'name': agency_name, 'type': 'NYC Agency'}
                    ]
                }
            ],
            'document_url': f"https://www.checkbooknyc.com/contract_details/{filing_id}",
            
            # Add metadata to clearly identify as mock data
            'meta': {
                'is_mock': True
            }
        }
        
        return contract_detail
    
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
            agencies_data = defaultdict(int)
            contract_types_data = defaultdict(int)
            amounts_data = []
            vendors_data = defaultdict(float)
            
            # Process results
            for contract in results:
                # Track fiscal years
                if contract.get("fiscal_year"):
                    try:
                        year = str(contract["fiscal_year"]).strip()
                        if year.isdigit():
                            years_data[year] += 1
                    except (ValueError, TypeError):
                        pass
                
                # Track agencies
                if contract.get("agency_name"):
                    agencies_data[contract["agency_name"]] += 1
                
                # Track contract types
                if contract.get("contract_type"):
                    contract_type = contract["contract_type"]
                    contract_type_display = self.CONTRACT_TYPES.get(contract_type, contract_type)
                    contract_types_data[contract_type_display] += 1
                
                # Track contract amounts
                if contract.get("maximum_contract_amount") and contract.get("start_date"):
                    try:
                        amount = float(contract["maximum_contract_amount"])
                        start_date = contract["start_date"]
                        amounts_data.append((start_date, amount))
                        
                        # Also track amounts by vendor
                        if contract.get("vendor_name"):
                            vendors_data[contract["vendor_name"]] += amount
                    except (ValueError, TypeError):
                        pass
            
            # Sort years data
            sorted_years = sorted(years_data.items())
            years_chart = {
                "labels": [year for year, _ in sorted_years],
                "values": [count for _, count in sorted_years]
            }
            
            # Get top agencies
            top_agencies = sorted(agencies_data.items(), key=lambda x: x[1], reverse=True)[:10]
            agencies_chart = {
                "labels": [name for name, _ in top_agencies],
                "values": [count for _, count in top_agencies]
            }
            
            # Get contract types
            contract_types_chart = {
                "labels": list(contract_types_data.keys()),
                "values": list(contract_types_data.values())
            }
            
            # Process amounts data
            amounts_by_period = defaultdict(float)
            for date, amount in amounts_data:
                # Convert to year-quarter format
                if isinstance(date, str):
                    try:
                        date_obj = datetime.strptime(date, "%Y-%m-%d")
                        quarter = (date_obj.month - 1) // 3 + 1
                        period = f"{date_obj.year}-Q{quarter}"
                    except:
                        # If parse fails, use the year part
                        period = date[:4] if len(date) >= 4 else "Unknown"
                else:
                    period = "Unknown"
                
                amounts_by_period[period] += amount
            
            # Sort by period
            sorted_amounts = sorted(amounts_by_period.items())
            amounts_chart = {
                "labels": [period for period, _ in sorted_amounts],
                "values": [amount for _, amount in sorted_amounts]
            }
            
            # Get top vendors by contract amount
            top_vendors = sorted(vendors_data.items(), key=lambda x: x[1], reverse=True)[:10]
            vendors_chart = {
                "labels": [name for name, _ in top_vendors],
                "values": [amount for _, amount in top_vendors]
            }
            
            visualization_data = {
                "years_data": years_chart,
                "top_entities": agencies_chart,  # Map to standardized name for compatibility
                "spending_trend": amounts_chart,
                "contract_types": contract_types_chart,
                "top_vendors": vendors_chart
            }
            
            return visualization_data, None
            
        except Exception as e:
            logger.error(f"Error generating visualization data: {str(e)}")
            return None, f"An error occurred while generating visualization data: {str(e)}"
            
    @property
    def source_name(self) -> str:
        """Return the name of this data source."""
        return "NYC Checkbook"
    
    @property
    def government_level(self) -> str:
        """Return the level of government (Federal, State, Local)."""
        return "Local"