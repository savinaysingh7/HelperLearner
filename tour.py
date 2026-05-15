import requests
from bs4 import BeautifulSoup
import sys

BASE_URL = "http://127.0.0.1:8000"

def run_tour():
    session = requests.Session()
    
    # 1. Get the login page to get the CSRF token
    print("Fetching Login Page...")
    login_url = f"{BASE_URL}/accounts/login/"
    response = session.get(login_url)
    if response.status_code != 200:
        print(f"Failed to get login page: {response.status_code}")
        return
        
    soup = BeautifulSoup(response.text, 'html.parser')
    csrf_token = soup.find('input', {'name': 'csrfmiddlewaretoken'})['value']
    
    # 2. Login as Ananya Sharma
    print("\nLogging in as ananya_sharma...")
    login_data = {
        'username': 'ananya_sharma',
        'password': 'IndiaSeed@2026',
        'csrfmiddlewaretoken': csrf_token,
        'next': '/'
    }
    
    # Post login
    response = session.post(login_url, data=login_data, headers={'Referer': login_url})
    
    # 3. Check Dashboard / Profile
    print("\n--- User Dashboard ---")
    dashboard_url = f"{BASE_URL}/accounts/dashboard/"
    response = session.get(dashboard_url)
    soup = BeautifulSoup(response.text, 'html.parser')
    
    # Try to find stats (KP, Trust Score, INR Wallet)
    # The actual HTML structure might vary, so we'll look for common text or classes
    body_text = soup.get_text(separator='\n', strip=True)
    
    # Let's try to extract specific elements by class or ID if possible, but fallback to text search
    # We will print the title and some headers
    print(f"Page Title: {soup.title.string if soup.title else 'No Title'}")
    
    # Let's find specific cards or stats
    stats_divs = soup.find_all('div', class_=lambda x: x and 'stat' in x.lower())
    if stats_divs:
        for stat in stats_divs[:5]:
            print(f"- {stat.get_text(strip=True)}")
    else:
        # Fallback to finding all h2/h3 tags
        headings = soup.find_all(['h2', 'h3'])
        for h in headings[:10]:
            print(f"- {h.get_text(strip=True)}")
            
    # Look for wallet/KP info specifically
    for text in ["Knowledge Points", "Trust Score", "INR Balance", "Wallet"]:
        if text in body_text:
            print(f"Found mention of: {text}")

    # 4. Check Marketplace / Discovery
    print("\n--- Marketplace / Discovery ---")
    market_url = f"{BASE_URL}/" # or /discovery/
    response = session.get(market_url)
    soup = BeautifulSoup(response.text, 'html.parser')
    
    # Find list of jobs/requests
    cards = soup.find_all('div', class_=lambda x: x and ('card' in x.lower() or 'item' in x.lower()))
    print(f"Found {len(cards)} items on the discovery page.")
    
    for i, card in enumerate(cards[:5]): # show top 5
        title = card.find(['h2', 'h3', 'h4'])
        if title:
            title_text = title.get_text(strip=True)
            print(f"Item {i+1}: {title_text}")
            
    # Also find top links/navigation to show available features
    print("\n--- Available Navigation Links ---")
    nav = soup.find('nav')
    if nav:
        links = nav.find_all('a')
        for link in links:
            text = link.get_text(strip=True)
            if text:
                print(f"Nav: {text} -> {link.get('href')}")
    else:
        print("No navigation found.")

if __name__ == "__main__":
    try:
        run_tour()
    except Exception as e:
        print(f"Error during tour: {e}")
