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
            charts["spending_trend"] = visualization_data["spending_trend"]
        else:
            # Generate from results if not in visualization_data
            spending_data = []
            for filing in results:
                date = filing.get("filing_date") or filing.get("dt_posted")
                amount = filing.get("amount") or filing.get("income") or filing.get("expenses")
                
                if date and amount:
                    try:
                        # Try to parse date if it's a string
                        if isinstance(date, str):
                            date = datetime.strptime(date, "%Y-%m-%d").strftime("%Y-%m")
                        
                        # Convert amount to float if it's a string
                        if isinstance(amount, str):
                            amount = float(amount.replace("$", "").replace(",", ""))
                        
                        spending_data.append((date, amount))
                    except (ValueError, TypeError):
                        # Skip entries with invalid date or amount
                        pass
            
            # Group by month/year and sum amounts
            spending_by_period = defaultdict(float)
            for date, amount in spending_data:
                spending_by_period[date] += amount
            
            # Sort by date
            sorted_spending = sorted(spending_by_period.items())
            
            charts["spending_trend"] = {
                "labels": [date for date, _ in sorted_spending],
                "values": [amount for _, amount in sorted_spending]
            }
        
        # Generate issue areas chart (if available)
        if "issue_areas" in visualization_data:
            charts["issue_areas"] = visualization_data["issue_areas"]
        else:
            # Generate from results if not in visualization_data
            issues_counter = Counter()
            for filing in results:
                activities = filing.get("lobbying_activities", [])
                for activity in activities:
                    issue = activity.get("general_issue_code_display")
                    if issue:
                        issues_counter[issue] += 1
            
            # Get top 10
            top_issues = issues_counter.most_common(10)
            charts["issue_areas"] = {
                "labels": [issue for issue, _ in top_issues],
                "values": [count for _, count in top_issues]
            }
        
        # Generate lobbying methods chart based on government entities
        government_entities = Counter()
        for filing in results:
            activities = filing.get("lobbying_activities", [])
            for activity in activities:
                entities = activity.get("government_entities", [])
                for entity in entities:
                    entity_name = entity.get("name", "Unknown")
                    government_entities[entity_name] += 1
        
        # Get top 10
        top_entities = government_entities.most_common(10)
        charts["government_entities"] = {
            "labels": [entity for entity, _ in top_entities],
            "values": [count for _, count in top_entities]
        }
        
        # Generate insights
        insights = self._generate_insights(query, results, charts)
        
        return {
            "charts": charts,
            "insights": insights
        }
    
    def _generate_insights(self, query, results, charts):
        """
        Generate text insights from the visualization data.
        
        Args:
            query: Search query
            results: Search results
            charts: Generated chart data
            
        Returns:
            List of insight strings
        """
        insights = []
        
        # Count total filings
        total_filings = len(results)
        insights.append(f"Found {total_filings} filings related to '{query}'.")
        
        # Years trend
        if "years_data" in charts and charts["years_data"]["labels"]:
            years = charts["years_data"]["labels"]
            counts = charts["years_data"]["values"]
            
            if len(years) > 1:
                trend = "increasing" if counts[-1] > counts[0] else "decreasing"
                insights.append(f"Filing activity has been {trend} from {years[0]} to {years[-1]}.")
            
            max_year_index = counts.index(max(counts))
            max_year = years[max_year_index]
            insights.append(f"The highest number of filings was in {max_year}.")
        
        # Top entities
        if "top_entities" in charts and charts["top_entities"]["labels"]:
            top_entity = charts["top_entities"]["labels"][0]
            insights.append(f"The most active entity is '{top_entity}'.")
        
        # Spending insights
        if "spending_trend" in charts and charts["spending_trend"]["values"]:
            values = charts["spending_trend"]["values"]
            total_spending = sum(values)
            avg_spending = total_spending / len(values) if values else 0
            
            insights.append(f"Total reported spending is ${total_spending:,.2f}.")
            insights.append(f"Average spending per period is ${avg_spending:,.2f}.")
        
        # Issue areas
        if "issue_areas" in charts and charts["issue_areas"]["labels"]:
            top_issue = charts["issue_areas"]["labels"][0]
            insights.append(f"The most common issue area is '{top_issue}'.")
        
        return insights
    
    def generate_charts_as_base64(self, visualization_data):
        """
        Generate chart images as base64 encoded strings.
        
        Args:
            visualization_data: Dictionary with chart data
            
        Returns:
            Dictionary with chart images as base64 strings
        """
        chart_images = {}
        
        # Years Activity Bar Chart
        if "years_data" in visualization_data:
            years_data = visualization_data["years_data"]
            chart_images["years_chart"] = self._create_bar_chart(
                years_data["labels"],
                years_data["values"],
                "Filings by Year",
                "Year",
                "Number of Filings",
                self.colors["primary"]
            )
        
        # Top Entities Bar Chart
        if "top_entities" in visualization_data:
            entities_data = visualization_data["top_entities"]
            chart_images["entities_chart"] = self._create_horizontal_bar_chart(
                entities_data["labels"],
                entities_data["values"],
                "Top Entities",
                "Entity",
                "Number of Filings",
                self.colors["secondary"]
            )
        
        # Spending Trend Line Chart
        if "spending_trend" in visualization_data:
            spending_data = visualization_data["spending_trend"]
            chart_images["spending_chart"] = self._create_line_chart(
                spending_data["labels"],
                spending_data["values"],
                "Spending Trend",
                "Date",
                "Amount ($)",
                self.colors["accent"]
            )
        
        # Issue Areas Pie Chart
        if "issue_areas" in visualization_data:
            issues_data = visualization_data["issue_areas"]
            chart_images["issues_chart"] = self._create_pie_chart(
                issues_data["labels"],
                issues_data["values"],
                "Issue Areas"
            )
        
        # Government Entities Bar Chart
        if "government_entities" in visualization_data:
            gov_data = visualization_data["government_entities"]
            chart_images["government_chart"] = self._create_horizontal_bar_chart(
                gov_data["labels"],
                gov_data["values"],
                "Government Entities Contacted",
                "Entity",
                "Frequency",
                self.colors["success"]
            )
        
        return chart_images
    
    def _create_bar_chart(self, labels, values, title, xlabel, ylabel, color):
        """Create a vertical bar chart and return as base64 string."""
        plt.figure(figsize=(10, 6))
        bars = plt.bar(labels, values, color=color)
        
        # Add value labels on top of bars
        for bar in bars:
            height = bar.get_height()
            plt.text(
                bar.get_x() + bar.get_width()/2., height + 0.1,
                str(int(height)), ha='center', va='bottom'
            )
        
        plt.title(title)
        plt.xlabel(xlabel)
        plt.ylabel(ylabel)
        plt.grid(axis='y', linestyle='--', alpha=0.7)
        plt.xticks(rotation=45)
        plt.tight_layout()
        
        # Convert to base64
        buffer = io.BytesIO()
        plt.savefig(buffer, format='png', dpi=100)
        plt.close()
        buffer.seek(0)
        
        return base64.b64encode(buffer.getvalue()).decode('utf-8')
    
    def _create_horizontal_bar_chart(self, labels, values, title, xlabel, ylabel, color):
        """Create a horizontal bar chart and return as base64 string."""
        plt.figure(figsize=(10, 8))
        
        # Limit to top 10 and reverse for better display
        if len(labels) > 10:
            labels = labels[:10]
            values = values[:10]
        
        # Reverse for bottom-to-top display
        labels = labels[::-1]
        values = values[::-1]
        
        bars = plt.barh(labels, values, color=color)
        
        # Add value labels
        for bar in bars:
            width = bar.get_width()
            plt.text(
                width + 0.1, bar.get_y() + bar.get_height()/2.,
                str(int(width)), va='center'
            )
        
        plt.title(title)
        plt.xlabel(ylabel)
        plt.ylabel(xlabel)
        plt.grid(axis='x', linestyle='--', alpha=0.7)
        plt.tight_layout()
        
        # Convert to base64
        buffer = io.BytesIO()
        plt.savefig(buffer, format='png', dpi=100)
        plt.close()
        buffer.seek(0)
        
        return base64.b64encode(buffer.getvalue()).decode('utf-8')
    
    def _create_line_chart(self, labels, values, title, xlabel, ylabel, color):
        """Create a line chart and return as base64 string."""
        plt.figure(figsize=(10, 6))
        plt.plot(labels, values, marker='o', linestyle='-', color=color)
        
        # Format y-axis with dollar sign
        plt.ticklabel_format(axis='y', style='plain')
        
        plt.title(title)
        plt.xlabel(xlabel)
        plt.ylabel(ylabel)
        plt.grid(True, linestyle='--', alpha=0.7)
        plt.xticks(rotation=45)
        plt.tight_layout()
        
        # Convert to base64
        buffer = io.BytesIO()
        plt.savefig(buffer, format='png', dpi=100)
        plt.close()
        buffer.seek(0)
        
        return base64.b64encode(buffer.getvalue()).decode('utf-8')
    
    def _create_pie_chart(self, labels, values, title):
        """Create a pie chart and return as base64 string."""
        plt.figure(figsize=(10, 8))
        
        # Limit to top 8 categories, group others
        if len(labels) > 8:
            top_values = values[:7]
            other_value = sum(values[7:])
            top_labels = labels[:7]
            top_labels.append('Other')
            top_values.append(other_value)
            labels = top_labels
            values = top_values
        
        # Use a list of colors from our color scheme
        colors = [
            self.colors["primary"],
            self.colors["secondary"],
            self.colors["accent"],
            self.colors["neutral"],
            self.colors["success"],
            self.colors["warning"],
            "#ec4899",  # Tailwind pink-500
            "#a3e635",  # Tailwind lime-500
        ]
        
        plt.pie(
            values, 
            labels=labels, 
            autopct='%1.1f%%',
            startangle=90, 
            shadow=False, 
            colors=colors[:len(labels)]
        )
        plt.axis('equal')  # Equal aspect ratio ensures that pie is drawn as a circle
        plt.title(title)
        plt.tight_layout()
        
        # Convert to base64
        buffer = io.BytesIO()
        plt.savefig(buffer, format='png', dpi=100)
        plt.close()
        buffer.seek(0)
        
        return base64.b64encode(buffer.getvalue()).decode('utf-8')