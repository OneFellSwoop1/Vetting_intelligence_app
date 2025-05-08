// static/js/search_form.js
/**
 * Search form functionality for the Vetting Intelligence Hub
 */

document.addEventListener('DOMContentLoaded', function() {
  // Elements
  const searchForm = document.getElementById('searchForm');
  const advancedToggle = document.getElementById('advancedToggle');
  const advancedOptions = document.getElementById('advancedOptions');
  const dataSourceSelect = document.getElementById('data_source');
  const searchTypeSelect = document.getElementById('search_type');
  const yearFilterSelect = document.getElementById('year_filter');
  const tableFilter = document.getElementById('tableFilter');
  const resultsTable = document.getElementById('resultsTable');
  
  // Toggle advanced options
  if (advancedToggle && advancedOptions) {
    advancedToggle.addEventListener('click', function() {
      advancedOptions.classList.toggle('hidden');
      
      if (advancedOptions.classList.contains('hidden')) {
        advancedToggle.textContent = 'Show Advanced Options';
      } else {
        advancedToggle.textContent = 'Hide Advanced Options';
      }
    });
  }
  
  // Handle data source change to update available options
  if (dataSourceSelect) {
    dataSourceSelect.addEventListener('change', function() {
      updateFieldsBasedOnDataSource(this.value);
    });
    
    // Initialize on page load
    updateFieldsBasedOnDataSource(dataSourceSelect.value);
  }
  
  // Handle year filter change to navigate to filtered results
  if (yearFilterSelect) {
    yearFilterSelect.addEventListener('change', function() {
      // Get current URL
      const url = new URL(window.location.href);
      
      // Update the filing_year parameter
      url.searchParams.set('filing_year', this.value);
      
      // Reset to page 1
      url.searchParams.set('page', '1');
      
      // Navigate to the new URL
      window.location.href = url.toString();
    });
  }
  
  // Filter table results
  if (tableFilter && resultsTable) {
    tableFilter.addEventListener('keyup', function() {
      const searchText = this.value.toLowerCase();
      const rows = resultsTable.querySelectorAll('tbody tr:not([id$="_details"])');
      
      rows.forEach(row => {
        const text = row.textContent.toLowerCase();
        const shouldShow = text.includes(searchText);
        
        // Toggle visibility
        row.style.display = shouldShow ? '' : 'none';
        
        // Hide any associated detail rows
        const rowId = row.id || '';
        if (rowId) {
          const detailsRow = document.getElementById(rowId + '_details');
          if (detailsRow) {
            detailsRow.style.display = 'none';
          }
        }
      });
    });
  }
  
  // Function to toggle detail rows
  window.toggleDetails = function(detailsId) {
    const detailsRow = document.getElementById(detailsId);
    if (detailsRow) {
      const isHidden = detailsRow.classList.contains('hidden');
      detailsRow.classList.toggle('hidden', !isHidden);
    }
  };
  
  // Function to update fields based on selected data source
  function updateFieldsBasedOnDataSource(dataSource) {
    // Default options for search type
    const defaultOptions = [
      { value: 'registrant', text: 'Registrant/Lobbyist' },
      { value: 'client', text: 'Client' },
      { value: 'lobbyist', text: 'Individual Lobbyist' }
    ];
    
    // NYC Checkbook specific options
    const checkbookOptions = [
      { value: 'vendor', text: 'Vendor/Contractor' },
      { value: 'agency', text: 'City Agency' }
    ];
    
    // Reset search type options
    if (searchTypeSelect) {
      // Clear existing options
      searchTypeSelect.innerHTML = '';
      
      // Add appropriate options based on data source
      const options = dataSource === 'nyc_checkbook' ? checkbookOptions : defaultOptions;
      
      options.forEach(option => {
        const optionElement = document.createElement('option');
        optionElement.value = option.value;
        optionElement.textContent = option.text;
        searchTypeSelect.appendChild(optionElement);
      });
    }
    
    // Show/hide specific fields based on data source
    const nycFields = document.querySelectorAll('.nyc-specific');
    const federalFields = document.querySelectorAll('.federal-specific');
    const checkbookFields = document.querySelectorAll('.checkbook-specific');
    
    if (nycFields) {
      nycFields.forEach(field => {
        field.style.display = (dataSource === 'nyc') ? 'block' : 'none';
      });
    }
    
    if (federalFields) {
      federalFields.forEach(field => {
        field.style.display = (dataSource === 'senate') ? 'block' : 'none';
      });
    }
    
    if (checkbookFields) {
      checkbookFields.forEach(field => {
        field.style.display = (dataSource === 'nyc_checkbook') ? 'block' : 'none';
      });
    }
  }
});