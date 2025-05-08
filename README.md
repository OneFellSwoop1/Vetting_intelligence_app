# Vetting Intelligence Hub (Formerly Lobbying Disclosure App)

A comprehensive web application for searching and analyzing lobbying disclosure data and government contracts from multiple sources at the federal, state, and local levels.

## 🚀 New Features & Enhancements

### UI Redesign with Tailwind CSS
- Modern, responsive interface optimized for all devices
- Professional color schemes and typography
- Interactive components and data visualizations
- Dark mode support

### New Data Sources
- **NYC Lobbying Bureau** data integration
- **CheckbookNYC** contracts and spending data
- Unified search interface across all data sources

### Additional Improvements
- Enhanced visualization capabilities
- Improved search with better matching algorithms
- Comprehensive error handling and fallback mechanisms
- Pagination with clear navigation
- Responsive tables and cards

## Setup

1. Clone the repository
2. Create a virtual environment: `python -m venv venv`
3. Activate the virtual environment:
   - Windows: `venv\Scripts\activate`
   - Mac/Linux: `source venv/bin/activate`
4. Install dependencies: `pip install -r requirements.txt`
5. Install Tailwind CSS:
   ```bash
   # Install Tailwind CSS via npm
   npm install -D tailwindcss@latest postcss@latest autoprefixer@latest
   # Initialize Tailwind CSS
   npx tailwindcss init
   # Build the Tailwind CSS file
   npx tailwindcss -i ./static/css/tailwind/input.css -o ./static/css/tailwind/output.css
   ```
6. Create a `.env` file with your API keys:
   ```
   LDA_API_KEY=your_senate_lda_api_key_here
   NYC_API_TOKEN=your_nyc_api_token_here
   ```
7. Run the application: `python app.py`
8. Access the application at http://localhost:5001

## Data Sources

### Federal (Active)
- **Senate LDA** - Senate Lobbying Disclosure Act database
  - Location: `data_sources/improved_senate_lda.py`
  - Status: Active and fully implemented

### NYC (New)
- **NYC Lobbying Bureau** - NYC Clerk's Office lobbying data
  - Location: `data_sources/nyc.py`
  - Status: Fully implemented
  - API: https://lobbyistsearch.nyc.gov/

- **CheckbookNYC** - NYC contract and spending data
  - Location: `data_sources/nyc_checkbook.py`
  - Status: Fully implemented
  - API: https://data.cityofnewyork.us/

### Planned (In Progress)
1. **House Disclosures (Federal)**
   - Location: `data_sources/house_disclosures.py`
   - Status: Initial implementation, not fully connected

2. **New York State Lobbying**
   - Location: `data_sources/ny_state.py`
   - Status: Initial structure only

## Features

- Search lobbying filings by registrant, client, or lobbyist name
- Search government contracts by vendor or agency
- View detailed filing and contract information
- Filter results by date, filing type, and other criteria
- Export results to CSV
- Visualize lobbying and contract trends with interactive charts
- Cross-reference entities across multiple databases

## Usage

### Basic Search
1. Enter a search term (company, organization, or individual name)
2. Select a search type (registrant, client, or lobbyist)
3. Select a data source (Federal, NYC Lobbying, or NYC Contracts)
4. Apply filters (optional)
5. Click "Search"

### Advanced Search
1. Click "Show Advanced Options" on the search form
2. Fill in additional filters like date range, issue area, etc.
3. Specify the data source and results per page
4. Click "Search"

### Visualizations
1. Search for an entity
2. Click "Visualize" on the results page
3. View charts showing lobbying activity, spending trends, and more

## Multi-Computer Development Workflow

To work on this project across multiple computers, follow the instructions in [DEVELOPMENT.md](DEVELOPMENT.md).

## NYC Data Integration

For detailed information about the NYC data sources and how to use them, see [NYC_INTEGRATION.md](NYC_INTEGRATION.md).

## Technologies Used

- **Backend**:
  - Flask (Python web framework)
  - Requests (API interactions)
  - Pandas (Data processing)

- **Frontend**:
  - Tailwind CSS (Styling)
  - Chart.js (Data visualization)
  - Vanilla JavaScript (Interactivity)

- **APIs**:
  - Senate LDA API (Federal lobbying)
  - NYC Lobbying Bureau API
  - NYC Open Data API (CheckbookNYC)

## License

This project is licensed under the MIT License - see the LICENSE file for details.