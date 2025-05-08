# utils/visualization.py
"""
Data visualization utilities for the Vetting Intelligence Hub.
"""

import io
import base64
import logging
import matplotlib
matplotlib.use('Agg')  # Use non-interactive backend
import matplotlib.pyplot as plt
import numpy as np
from collections import defaultdict, Counter
from datetime import datetime

# Configure logging
logger = logging.getLogger('vetting_hub.visualization')

class LobbyingVisualizer:
    """Class to generate visualizations from lobbying data."""
    
    def __init__(self):
        """Initialize the visualizer with default settings."""
        # Set default style for plots
        plt.style.use('seaborn-v0_8-whitegrid')
        
        # Set default colors
        self.colors = {
            'primary': '#0ea5e9',    # Tailwind blue-500
            'secondary': '#f59e0b',  # Tailwind amber-500
            'accent': '#8b5cf6',     # Tailwind violet-500
            'neutral': '#6b7280',    # Tailwind gray-500
            'success': '#10b981',    # Tailwind emerald-500
            'warning': '#f97316',    # Tailwind orange-500
        }
        
        # Set default font size
        plt.rcParams.update({
            'font.size': 10,
            'axes.titlesize': 14,
            'axes.labelsize': 12,
            'xtick.labelsize': 10,
            'ytick.labelsize': 10,
            'legend.fontsize': 10,
        })
    
    def generate_visualizations(self, query, results, visualization_data):
        """
        Generate visualizations from search results.
        
        Args:
            query: Search query
            results: List of lobbying filings or contracts
            visualization_data: Preprocessed data for visualization
            
        Returns:
            Dictionary with charts and insights
        """
        charts = {}
        
        # Process the visualization data
        if not visualization_data:
            return {"error": "No data available for visualization"}
        
        # Generate years chart data (if available)
        if "years_data" in visualization_data:
            years_data = visualization_data["years_data"]
            charts["years_data"] = years_data
        else:
            # Generate from results if not in visualization_data
            years_counter = Counter()
            for filing in results:
                if filing.get("filing_year"):
                    years_counter[str(filing["filing_year"])] += 1
            
            # Sort by year
            sorted_years = sorted(years_counter.items())
            charts["years_data"] = {
                "labels": [year for year, _ in sorted_years],
                "values": [count for _, count in sorted_years]
            }
        
        # Generate top entities chart (if available)
        if "top_entities" in visualization_data:
            charts["top_entities"] = visualization_data["top_entities"]
        else:
            # Generate from results if not in visualization_data
            entities_counter = Counter()
            for filing in results:
                if filing.get("registrant") and filing["registrant"].get("name"):
                    entities_counter[filing["registrant"]["name"]] += 1
            
            # Get top 10
            top_entities = entities_counter.most_common(10)
            charts["top_entities"] = {
                "labels": [name for name, _ in top_entities],
                "values": [count for _, count in top_entities]
            }
        
        # Generate spending trend data (if available)
        if "spending_trend" in visualization_data:
            charts["spending_trend"] =