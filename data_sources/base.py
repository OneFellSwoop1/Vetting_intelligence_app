# data_sources/base.py
from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Any, Tuple

class LobbyingDataSource(ABC):
    """Base class for all lobbying data sources."""
    
    @property
    @abstractmethod
    def source_name(self) -> str:
        """Return the name of this data source."""
        pass
    
    @property
    @abstractmethod
    def government_level(self) -> str:
        """Return the level of government (Federal, State, Local)."""
        pass
    
    @abstractmethod
    def search_filings(self, query: str, filters: Optional[Dict[str, Any]] = None, 
                      page: int = 1, page_size: int = 10) -> Tuple[List[Dict], int, Dict, Optional[str]]:
        """
        Search for lobbying filings with the given parameters.
        
        Args:
            query: The search query (person or entity name)
            filters: Additional filters to apply to the search
            page: Page number for pagination
            page_size: Number of results per page
            
        Returns:
            tuple: (results, count, pagination_info, error)
        """
        pass
    
    @abstractmethod
    def get_filing_detail(self, filing_id: str) -> Tuple[Optional[Dict], Optional[str]]:
        """
        Get detailed information about a specific filing.
        
        Args:
            filing_id: The unique identifier for the filing
            
        Returns:
            tuple: (filing_data, error)
        """
        pass
    
    @abstractmethod
    def fetch_visualization_data(self, query: str, filters: Optional[Dict[str, Any]] = None) -> Tuple[Optional[Dict], Optional[str]]:
        """
        Fetch data specifically for visualization purposes.
        
        Args:
            query: The search query (person or entity name)
            filters: Additional filters to apply to the search
            
        Returns:
            tuple: (visualization_data, error)
        """
        pass