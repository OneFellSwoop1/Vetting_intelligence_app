import os
import pytest
import requests

BASE_URL = os.getenv("API_BASE_URL", "http://localhost:5001")

@pytest.mark.parametrize("data_source,query", [
    ("senate", "test"),
    ("nyc_checkbook", "test")
])
def test_api_search(data_source, query):
    url = f"{BASE_URL}/api/search"
    params = {
        "query": query,
        "data_source": data_source
    }
    response = requests.get(url, params=params)
    assert response.status_code == 200, f"{data_source} search failed: {response.text}"
    data = response.json()
    assert data.get("success"), f"{data_source} search not successful: {data}"
    assert isinstance(data.get("results"), list), f"{data_source} results not a list: {data}"
    print(f"{data_source} returned {len(data['results'])} results.") 