import os
import time
import random
import sys
import psycopg2 # לחיבור ל-Neon
import requests # לשליחת התמונה ל-Pushover
from curl_cffi import requests as cffi_requests # לגלישה באתר (עקיפת חסימות)
from bs4 import BeautifulSoup

# --- הגדרות ---
HOMEPAGE_URL = "https://www.fragrantica.com/"

# --- שליפת משתני סביבה ---
PUSHOVER_USER_KEY = os.environ.get("PUSHOVER_USER_KEY")
PUSHOVER_API_TOKEN = os.environ.get("PUSHOVER_API_TOKEN")
DATABASE_URL = os.environ.get("DATABASE_URL")

def save_to_db(name, brand, link, image_url):
    """שומר את הבושם החדש ב-Neon DB"""
    if not DATABASE_URL:
        print("⚠️ לא הוגדר DATABASE_URL, מדלג על שמירה ב-DB.")
        return

    try:
        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor()
        
        # שימוש ב-ON CONFLICT כדי למנוע קריסה אם הבושם כבר קיים
        query = """
            INSERT INTO perfumes (name, brand, link, image_url)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (link) DO NOTHING;
        """
        cur.execute(query, (name, brand, link, image_url))
        
        conn.commit()
        cur.close()
        conn.close()
        print("💾 הבושם נשמר בהצלחה בבסיס הנתונים (Neon).")
        
    except Exception as e:
        print(f"❌ שגיאה בשמירה ל-DB: {e}")

def send_pushover_image(title, message, image_url, url_link=None):
    """מוריד את התמונה ושולח אותה כהתראה ויזואלית ל-Pushover"""
    if not PUSHOVER_USER_KEY or not PUSHOVER_API_TOKEN:
        print("❌ חסרים מפתחות Pushover.")
        return

    # 1. הורדת התמונה מפרגרנטיקה (חייב להשתמש ב-cffi כדי לא להיחסם בהורדה)
    files = {}
    try:
        if image_url:
            print(f"📸 מוריד תמונה: {image_url}")
            img_response = cffi_requests.get(image_url, impersonate="chrome", timeout=10)
            if img_response.status_code == 200:
                # מכין את הקובץ לשליחה
                files = {
                    "attachment": ("perfume.jpg", img_response.content, "image/jpeg")
                }
    except Exception as e:
        print(f"⚠️ לא הצלחתי להוריד את התמונה: {e}")

    # 2. שליחת ההתראה ל-Pushover
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
        # שליחה ב-multipart/form-data בגלל התמונה
        response = requests.post(endpoint, data=data, files=files, timeout=20)
        if response.status_code == 200:
            print("✅ התראה נשלחה ל-Pushover (עם תמונה)!")
        else:
            print(f"❌ שגיאה מ-Pushover: {response.text}")
    except Exception as e:
        print(f"❌ שגיאה בשליחה ל-Pushover: {e}")

def check_db_exists(link):
    """בודק אם הלינק כבר קיים ב-DB"""
    if not DATABASE_URL:
        # Fallback לקובץ טקסט אם אין DB מוגדר (ליתר ביטחון)
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

def get_latest_perfume_data(soup):
    """חילוץ נתונים חכם מהקרוסלה"""
    try:
        candidates = soup.find_all("a", href=True)
        
        for link in candidates:
            href = link['href']
            
            # מסנן רק בשמים
            if '/perfume/' in href and '.html' in href and '/news/' not in href and '/designers/' not in href:
                
                full_link = "https://www.fragrantica.com" + href if not href.startswith('http') else href
                
                # --- חילוץ שם ---
                img_tag = link.find("img")
                image_url = img_tag['src'] if img_tag else None
                
                # עדיפות ל-ALT כי הוא נקי יותר
                perfume_name = ""
                if img_tag and img_tag.get('alt'):
                    perfume_name = img_tag['alt']
                
                # אם אין ALT, לוקח טקסט עם רווחים כדי למנוע הדבקות
                if not perfume_name:
                    perfume_name = link.get_text(separator=" ", strip=True)

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
                
                # ניקוי: אם שם הבושם כבר מכיל את המותג בהתחלה (למשל "Dior Sauvage"), ננקה את הכפילות מהשם
                if brand_name and perfume_name.lower().startswith(brand_name.lower()):
                    # מסיר את המותג מתחילת השם
                    perfume_name = perfume_name[len(brand_name):].strip()

                return {
                    'name': perfume_name,
                    'brand': brand_name,
                    'link': full_link,
                    'image': image_url
                }
        return None

    except Exception as e:
        print(f"❌ שגיאה בניתוח ה-HTML: {e}")
        return None

def main():
    # --- תיקון לחיסכון בדקות ריצה ---
    # מגריל זמן בין 10 שניות ל-50 שניות בלבד
    sleep_seconds = random.randint(10, 50)
    
    print(f"⏳ ממתין {sleep_seconds} שניות (כדי לא להיות רובוט מושלם)...")
    time.sleep(sleep_seconds)
    
    print("🚀 מתעורר ומתחיל סריקה (DB + Image Mode)...")
    
    try:
        response = cffi_requests.get(HOMEPAGE_URL, impersonate="chrome", timeout=20)
        if response.status_code != 200:
            print(f"❌ שגיאה בגישה לאתר: {response.status_code}")
            sys.exit(1)
        
        soup = BeautifulSoup(response.text, 'html.parser')
        perfume = get_latest_perfume_data(soup)
        
        if not perfume:
            print("⚠️ לא נמצא בושם בעמוד.")
            return

        print(f"👀 נמצא: {perfume['name']} - {perfume['brand']}")
        
        if check_db_exists(perfume['link']):
            print("😴 הבושם הזה כבר קיים ב-DB.")
        else:
            print("✨ בושם חדש! מבצע שמירה ושליחה...")
            
            # שמירה ל-DB
            save_to_db(perfume['name'], perfume['brand'], perfume['link'], perfume['image'])
            
            # עיצוב ההודעה עם מקף מפריד
            msg_title = "New Fragrance Alert"
            if perfume['brand']:
                msg_body = f"New Perfume: {perfume['name']} - {perfume['brand']}"
            else:
                msg_body = f"New Perfume: {perfume['name']}"
            
            send_pushover_image(
                title=msg_title,
                message=msg_body,
                image_url=perfume['image'],
                url_link=perfume['link']
            )

    except Exception as e:
        print(f"❌ קריסה כללית: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
