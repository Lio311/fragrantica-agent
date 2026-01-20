import os
import time
import random
import sys
import psycopg2
import requests
from curl_cffi import requests as cffi_requests
from bs4 import BeautifulSoup

# --- Configuration ---
HOMEPAGE_URL = "https://www.fragrantica.com/"

# List of words the bot might confuse for a brand
INVALID_BRANDS = ["Latest Reviews", "New Reviews", "Fragrantica", "News", "Community"]

# --- Environment Variables ---
PUSHOVER_USER_KEY = os.environ.get("PUSHOVER_USER_KEY")
PUSHOVER_API_TOKEN = os.environ.get("PUSHOVER_API_TOKEN")
DATABASE_URL = os.environ.get("DATABASE_URL")

def save_to_db(name, brand, link, image_url):
    """Saves perfume to the DB"""
    if not DATABASE_URL:
        print("⚠️ DATABASE_URL not defined.")
        return

    try:
        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor()
        # Use ON CONFLICT to prevent crash if perfume already exists
        query = """
            INSERT INTO perfumes (name, brand, link, image_url)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (link) DO NOTHING;
        """
        cur.execute(query, (name, brand, link, image_url))
        conn.commit()
        cur.close()
        conn.close()
        print(f"💾 Saved to DB: {name}")
    except Exception as e:
        print(f"❌ Error saving to DB: {e}")

def send_pushover_image(title, message, image_url, url_link=None):
    """Sends notification with an image"""
    if not PUSHOVER_USER_KEY or not PUSHOVER_API_TOKEN:
        return

    files = {}
    try:
        if image_url:
            img_response = cffi_requests.get(image_url, impersonate="chrome", timeout=10)
            if img_response.status_code == 200:
                files = {
                    "attachment": ("perfume.jpg", img_response.content, "image/jpeg")
                }
    except Exception as e:
        print(f"⚠️ Error downloading image: {e}")

    endpoint = "https://api.pushover.net/1/messages.json"
    data = {
        "token": PUSHOVER_API_TOKEN,
        "user": PUSHOVER_USER_KEY,
        "title": title,
        "message": message,
        "priority": 0
    }
    
    if url_link:
        data["url"] = url_link
        data["url_title"] = "Click to view on Fragrantica"

    try:
        requests.post(endpoint, data=data, files=files, timeout=20)
        print("✅ Notification sent!")
    except Exception as e:
        print(f"❌ Error sending to Pushover: {e}")

def check_db_exists(link):
    """Checks if the link exists in the DB"""
    if not DATABASE_URL:
        # Fallback to file if DB is missing
        if os.path.exists("last_seen_perfume.txt"):
            with open("last_seen_perfume.txt", "r") as f:
                return f.read().strip() == link
        return False

    try:
        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor()
        cur.execute("SELECT 1 FROM perfumes WHERE link = %s", (link,))
        exists = cur.fetchone() is not None
        cur.close()
        conn.close()
        return exists
    except Exception as e:
        print(f"⚠️ Error checking DB: {e}")
        return False

def get_perfumes_list(soup):
    """
    Scans the page and returns a list of up to 40 unique perfumes
    """
    perfumes_found = []
    seen_links = set()

    try:
        candidates = soup.find_all("a", href=True)
        
        for link in candidates:
            href = link['href']
            
            # Filter: Perfume links only
            if '/perfume/' in href and '.html' in href and '/news/' not in href and '/designers/' not in href:
                
                full_link = "https://www.fragrantica.com" + href if not href.startswith('http') else href
                
                if full_link in seen_links:
                    continue

                # --- Data Extraction ---
                img_tag = link.find("img")
                image_url = img_tag['src'] if img_tag else None
                
                # Extract Name (Priority to ALT)
                perfume_name = ""
                if img_tag and img_tag.get('alt'):
                    perfume_name = img_tag['alt']
                
                if not perfume_name:
                    perfume_name = link.get_text(separator=" ", strip=True)
                
                # Remove the word "perfume" from the beginning
                if perfume_name.lower().startswith("perfume"):
                    perfume_name = perfume_name[7:].strip()

                # --- Extract Brand ---
                brand_name = ""
                parent_cell = link.find_parent("div")
                if parent_cell:
                    brand_candidate = parent_cell.find("small") or parent_cell.find("span")
                    if brand_candidate:
                        brand_name = brand_candidate.get_text(strip=True)
                    else:
                        prev_link = link.find_previous_sibling("a")
                        if prev_link and '/designers/' in prev_link.get('href', ''):
                            brand_name = prev_link.get_text(strip=True)
                
                # === New Fix: Filter invalid brands ===
                # If the brand is "Latest Reviews", reset it
                if brand_name in INVALID_BRANDS:
                    brand_name = "" 
                
                # If you prefer not to save perfumes from the reviews section at all,
                # uncomment the following lines:
                # if brand_name == "":
                #    continue

                # Clean brand duplication within the name
                if brand_name and perfume_name.lower().startswith(brand_name.lower()):
                    perfume_name = perfume_name[len(brand_name):].strip()

                perfume_data = {
                    'name': perfume_name,
                    'brand': brand_name,
                    'link': full_link,
                    'image': image_url
                }
                
                perfumes_found.append(perfume_data)
                seen_links.add(full_link)
                
                if len(perfumes_found) >= 40:
                    break
        
        return perfumes_found

    except Exception as e:
        print(f"❌ HTML parsing error: {e}")
        return []

def main():
    sleep_seconds = random.randint(10, 50)
    print(f"⏳ Waiting {sleep_seconds} seconds...")
    time.sleep(sleep_seconds)
    
    print("🚀 Starting scan (filtering Latest Reviews)...")
    
    try:
        response = cffi_requests.get(HOMEPAGE_URL, impersonate="chrome", timeout=20)
        if response.status_code != 200:
            print(f"❌ Error: {response.status_code}")
            sys.exit(1)
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        all_perfumes = get_perfumes_list(soup)
        print(f"🔎 Found {len(all_perfumes)} potential perfumes.")
        
        new_count = 0
        
        for perfume in all_perfumes:
            if check_db_exists(perfume['link']):
                continue
            
            # Logic for displaying brand name in the message
            display_text = ""
            if perfume['brand']:
                display_text = f"{perfume['brand']} - {perfume['name']}"
            else:
                display_text = f"{perfume['name']}"

            print(f"✨ New! {display_text}")
            
            save_to_db(perfume['name'], perfume['brand'], perfume['link'], perfume['image'])
            
            send_pushover_image(
                title="New Fragrance Alert",
                message=display_text,
                image_url=perfume['image'],
                url_link=perfume['link']
            )
            
            new_count += 1
            time.sleep(1)

        if new_count == 0:
            print("😴 No new perfumes found.")
        else:
            print(f"🎉 Added {new_count} perfumes.")

    except Exception as e:
        print(f"❌ Crash: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
