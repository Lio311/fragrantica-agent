import os
import time
import random
import sys
import psycopg2
import requests
from curl_cffi import requests as cffi_requests
from bs4 import BeautifulSoup

# --- הגדרות ---
HOMEPAGE_URL = "https://www.fragrantica.com/"

# --- משתני סביבה ---
PUSHOVER_USER_KEY = os.environ.get("PUSHOVER_USER_KEY")
PUSHOVER_API_TOKEN = os.environ.get("PUSHOVER_API_TOKEN")
DATABASE_URL = os.environ.get("DATABASE_URL")

def save_to_db(name, brand, link, image_url):
    """שומר בושם ב-DB"""
    if not DATABASE_URL:
        print("⚠️ לא הוגדר DATABASE_URL.")
        return

    try:
        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor()
        query = """
            INSERT INTO perfumes (name, brand, link, image_url)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (link) DO NOTHING;
        """
        cur.execute(query, (name, brand, link, image_url))
        conn.commit()
        cur.close()
        conn.close()
        print(f"💾 נשמר ב-DB: {name}")
    except Exception as e:
        print(f"❌ שגיאה בשמירה ל-DB: {e}")

def send_pushover_image(title, message, image_url, url_link=None):
    """שולח התראה עם תמונה"""
    if not PUSHOVER_USER_KEY or not PUSHOVER_API_TOKEN:
        return

    files = {}
    try:
        if image_url:
            # מוריד את התמונה לזכרון
            img_response = cffi_requests.get(image_url, impersonate="chrome", timeout=10)
            if img_response.status_code == 200:
                files = {
                    "attachment": ("perfume.jpg", img_response.content, "image/jpeg")
                }
    except Exception as e:
        print(f"⚠️ שגיאה בהורדת תמונה: {e}")

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
        print("✅ התראה נשלחה!")
    except Exception as e:
        print(f"❌ שגיאה בשליחה ל-Pushover: {e}")

def check_db_exists(link):
    """בודק אם הלינק קיים ב-DB"""
    if not DATABASE_URL:
        # Fallback לקובץ אם אין DB
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
        print(f"⚠️ שגיאה בבדיקת DB: {e}")
        return False

def get_perfumes_list(soup):
    """
    סורק את העמוד ומחזיר רשימה של עד 40 בשמים ייחודיים
    """
    perfumes_found = []
    seen_links = set() # למנוע כפילויות בתוך אותה ריצה

    try:
        candidates = soup.find_all("a", href=True)
        
        for link in candidates:
            href = link['href']
            
            # סינון: לינק לבושם בלבד
            if '/perfume/' in href and '.html' in href and '/news/' not in href and '/designers/' not in href:
                
                full_link = "https://www.fragrantica.com" + href if not href.startswith('http') else href
                
                # אם כבר אספנו את הלינק הזה בריצה הזו, מדלגים
                if full_link in seen_links:
                    continue

                # --- חילוץ נתונים ---
                img_tag = link.find("img")
                image_url = img_tag['src'] if img_tag else None
                
                # חילוץ שם (עדיפות ל-ALT)
                perfume_name = ""
                if img_tag and img_tag.get('alt'):
                    perfume_name = img_tag['alt']
                
                if not perfume_name:
                    perfume_name = link.get_text(separator=" ", strip=True)
                
                # --- תיקון: הסרת המילה "perfume" ---
                # מנקה רווחים כפולים ומילים מיותרות
                if perfume_name.lower().startswith("perfume"):
                    # מוחק את ה-7 תווים הראשונים ("perfume") ואת הרווחים שאחרי
                    perfume_name = perfume_name[7:].strip()

                # --- חילוץ מותג ---
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
                
                # ניקוי כפילות מותג בתוך השם
                if brand_name and perfume_name.lower().startswith(brand_name.lower()):
                    perfume_name = perfume_name[len(brand_name):].strip()

                # הוספה לרשימה
                perfume_data = {
                    'name': perfume_name,
                    'brand': brand_name,
                    'link': full_link,
                    'image': image_url
                }
                
                perfumes_found.append(perfume_data)
                seen_links.add(full_link)
                
                # הגבלה ל-40 בשמים כדי לא להעמיס
                if len(perfumes_found) >= 40:
                    break
        
        return perfumes_found

    except Exception as e:
        print(f"❌ שגיאה בניתוח ה-HTML: {e}")
        return []

def main():
    # המתנה קצרה כדי לא להיחסם (10-50 שניות)
    sleep_seconds = random.randint(10, 50)
    print(f"⏳ ממתין {sleep_seconds} שניות...")
    time.sleep(sleep_seconds)
    
    print("🚀 מתחיל סריקה של כל הקרוסלה (עד 40 בשמים)...")
    
    try:
        response = cffi_requests.get(HOMEPAGE_URL, impersonate="chrome", timeout=20)
        if response.status_code != 200:
            print(f"❌ שגיאה: {response.status_code}")
            sys.exit(1)
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # שלב 1: איסוף כל הבשמים מהעמוד
        all_perfumes = get_perfumes_list(soup)
        
        print(f"🔎 נמצאו {len(all_perfumes)} בשמים פוטנציאליים בעמוד.")
        
        new_count = 0
        
        # שלב 2: מעבר על הרשימה ובדיקה מול ה-DB
        for perfume in all_perfumes:
            
            if check_db_exists(perfume['link']):
                # קיים ב-DB - מדלגים בשקט
                continue
            
            # אם הגענו לפה - זה בושם חדש!
            print(f"✨ חדש! {perfume['brand']} - {perfume['name']}")
            
            # שמירה
            save_to_db(perfume['name'], perfume['brand'], perfume['link'], perfume['image'])
            
            # בניית הודעה (מותג - שם)
            msg_title = "New Fragrance Alert"
            if perfume['brand']:
                msg_body = f"{perfume['brand']} - {perfume['name']}"
            else:
                msg_body = f"{perfume['name']}"
            
            # שליחה
            send_pushover_image(
                title=msg_title,
                message=msg_body,
                image_url=perfume['image'],
                url_link=perfume['link']
            )
            
            new_count += 1
            # המתנה קטנטנה בין שליחות כדי לא להציף את Pushover אם יש הרבה
            time.sleep(1)

        if new_count == 0:
            print("😴 לא נמצאו בשמים חדשים שלא קיימים ב-DB.")
        else:
            print(f"🎉 סה\"כ נוספו {new_count} בשמים חדשים.")

    except Exception as e:
        print(f"❌ קריסה: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
