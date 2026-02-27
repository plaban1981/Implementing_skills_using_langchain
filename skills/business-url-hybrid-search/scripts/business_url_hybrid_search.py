import os
import json
import requests
from urllib.parse import urlparse
from serpapi import GoogleSearch

# List of common directory/social domains to exclude when looking for an official business URL
EXCLUDED_DOMAINS = {
    'yelp.com', 'yellowpages.com', 'facebook.com', 'instagram.com', 
    'twitter.com', 'linkedin.com', 'tripadvisor.com', 'mapquest.com', 
    'foursquare.com', 'bbb.org', 'groupon.com', 'angieslist.com', 
    'thumbtack.com', 'whitepages.com', 'superpages.com', 'booking.com',
    'expedia.com', 'hotels.com', 'opentable.com', 'zomato.com',
    'ubereats.com', 'doordash.com', 'grubhub.com', 'pinterest.com',
    'youtube.com', 'tiktok.com', 'wikipedia.org'
}

def is_valid_official_url(url: str) -> bool:
    """
    Checks if a URL is likely an official business site rather than a directory listing.
    """
    if not url:
        return False
    try:
        parsed = urlparse(url)
        domain = parsed.netloc.lower()
        # Remove 'www.' for checking
        if domain.startswith('www.'):
            domain = domain[4:]
        
        # Check against excluded domains
        for excluded in EXCLUDED_DOMAINS:
            if domain == excluded or domain.endswith('.' + excluded):
                return False
        return True
    except Exception:
        return False

def search_serpapi(query: str, api_key: str) -> dict:
    """
    Queries SerpAPI for the business.
    Returns a dict with 'knowledge_graph_url' and 'organic_urls'.
    """
    results = {
        "knowledge_graph_url": None,
        "organic_urls": []
    }
    
    if not api_key:
        return results

    try:
        params = {
            "engine": "google",
            "q": query,
            "api_key": api_key,
            "num": 5  # We only need top results
        }
        search = GoogleSearch(params)
        data = search.get_dict()

        # 1. Check Knowledge Graph (High Confidence)
        if "knowledge_graph" in data:
            kg = data["knowledge_graph"]
            if "website" in kg:
                results["knowledge_graph_url"] = kg["website"]

        # 2. Check Organic Results
        if "organic_results" in data:
            for result in data["organic_results"]:
                link = result.get("link")
                if link:
                    results["organic_urls"].append(link)

    except Exception as e:
        print(f"SerpAPI Error: {e}")

    return results

def search_dataforseo(query: str, login: str, password: str) -> list:
    """
    Queries DataForSEO (Google Organic Live) for the business.
    Returns a list of organic URLs.
    """
    organic_urls = []
    
    if not login or not password:
        return organic_urls

    try:
        url = "https://api.dataforseo.com/v3/serp/google/organic/live/advanced"
        payload = [{
            "language_code": "en",
            "location_code": 2840, # United States (Broad default)
            "keyword": query
        }]
        headers = {
            'content-type': 'application/json'
        }

        response = requests.post(url, auth=(login, password), data=json.dumps(payload), headers=headers)
        
        if response.status_code == 200:
            res_json = response.json()
            tasks = res_json.get('tasks', [])
            if tasks and len(tasks) > 0:
                result_items = tasks[0].get('result', [])
                if result_items and len(result_items) > 0:
                    items = result_items[0].get('items', [])
                    for item in items:
                        if item.get('type') == 'organic':
                            link = item.get('url')
                            if link:
                                organic_urls.append(link)
    except Exception as e:
        print(f"DataForSEO Error: {e}")

    return organic_urls

def run_business_url_hybrid_search(input_value: str) -> dict:
    """
    Performs a hybrid search using SerpAPI and DataForSEO to find a business's official URL.
    
    Args:
        input_value (str): A string containing "Business Name and Address".
        
    Returns:
        dict: {
            "success": bool,
            "business_url": str or None,
            "source": str (e.g., "knowledge_graph", "organic_cross_reference", etc.),
            "candidates_checked": list
        }
    """
    
    # Configuration
    serpapi_key = os.getenv("SERPAPI_API_KEY")
    dfs_login = os.getenv("DATAFORSEO_LOGIN")
    dfs_password = os.getenv("DATAFORSEO_PASSWORD")

    if not input_value:
        return {"success": False, "error": "Input value is empty"}

    # Construct query
    # We append "official website" to help guide the search engine towards the main domain
    search_query = f"{input_value} official website"

    # 1. Execute Searches
    serp_results = search_serpapi(search_query, serpapi_key)
    dfs_urls = search_dataforseo(search_query, dfs_login, dfs_password)

    # 2. Analyze Results
    
    # Priority A: Knowledge Graph Website (Highest Confidence)
    # Google's Knowledge Graph usually links directly to the verified business owner.
    if serp_results.get("knowledge_graph_url"):
        kg_url = serp_results["knowledge_graph_url"]
        if is_valid_official_url(kg_url):
            return {
                "success": True,
                "business_url": kg_url,
                "source": "serpapi_knowledge_graph",
                "candidates_checked": [kg_url]
            }

    # Priority B: Cross-Referencing Organic Results
    # Combine lists, prioritizing SerpAPI organic then DataForSEO organic
    combined_candidates = []
    
    # Interleave results to give fair weight if both exist, or just extend
    # Here we prioritize SerpAPI organic first, then DataForSEO
    combined_candidates.extend(serp_results.get("organic_urls", []))
    combined_candidates.extend(dfs_urls)

    # Remove duplicates while preserving order
    seen = set()
    unique_candidates = []
    for url in combined_candidates:
        if url not in seen:
            unique_candidates.append(url)
            seen.add(url)

    # Filter candidates
    for url in unique_candidates:
        if is_valid_official_url(url):
            return {
                "success": True,
                "business_url": url,
                "source": "hybrid_organic_search",
                "candidates_checked": unique_candidates[:5] # Return top 5 checked for context
            }

    # Priority C: Fallback
    # If no "valid" official URL found (e.g., only Facebook pages found), 
    # we might return the top result if it exists, but mark success as False or low confidence.
    # For this strict implementation, we return failure if no non-directory site is found.
    
    return {
        "success": False,
        "business_url": None,
        "error": "No official website found among top results.",
        "candidates_checked": unique_candidates[:5]
    }

if __name__ == "__main__":
    import sys
    
    # Simple CLI entry point
    if len(sys.argv) > 1:
        input_str = sys.argv[1]
    else:
        # Default test case if no args provided
        input_str = "The French Laundry 6640 Washington St, Yountville, CA"
        print(f"No input provided. Using test case: {input_str}")

    result = run_business_url_hybrid_search(input_str)
    print(json.dumps(result, indent=2))