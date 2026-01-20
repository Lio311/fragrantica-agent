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

    # 1. הורדת התמונה מפרגרנטיקה
    files = {}
    try:
        if image_url:
            print(f"📸 מוריד תמונה: {image_url}")
            img_response = cffi_requests.get(image_url, impersonate="chrome", timeout=10)
            if img_response.status_code == 200:
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
    """חילוץ שם, מותג, תמונה ולינק - עם הפרדה טובה יותר"""
    try:
        candidates = soup.find_all("a", href=True)
        
        for link in candidates:
            href = link['href']
            
            if '/perfume/' in href and '.html' in href and '/news/' not in href and '/designers/' not in href:
                
                full_link = "https://www.fragrantica.com" + href if not href.startswith('http') else href
                
                # --- חילוץ שם הבושם ---
                img_tag = link.find("img")
                image_url = img_tag['src'] if img_tag else None
                
                # עדיפות 1: לקחת את השם מתוך ה-ALT של התמונה (שם זה בדרך כלל נקי)
                perfume_name = ""
                if img_tag and img_tag.get('alt'):
                    perfume_name = img_tag['alt']
                
                # עדיפות 2: אם אין ALT, לוקחים את הטקסט אבל נזהרים מהדבקות
                if not perfume_name:
                    # שימוש ב-separator כדי להבטיח רווח אם יש אלמנטים צמודים
                    perfume_name = link.get_text(separator=" ", strip=True)

                # --- חילוץ שם המותג ---
                brand_name = ""
                parent_cell = link.find_parent("div")
                if parent_cell:
                    # מנסה למצוא תגית small או span ליד הלינק
                    brand_candidate = parent_cell.find("small") or parent_cell.find("span")
                    if brand_candidate:
                        brand_name = brand_candidate.get_text(strip=True)
                    else:
                        # לפעמים המותג הוא לינק נפרד לפני הבושם
                        prev_link = link.find_previous_sibling("a")
                        if prev_link and '/designers/' in prev_link.get('href', ''):
                            brand_name = prev_link.get_text(strip=True)
                
                # ניקוי: אם שם הבושם בטעות מכיל את שם המותג בהתחלה (קורה לפעמים), נחתוך אותו
                if brand_name and perfume_name.startswith(brand_name):
                    perfume_name = perfume_name.replace(brand_name, "", 1).strip()

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
    # השהייה רנדומלית
    sleep_seconds = random.randint(60, 600)
    minutes = sleep_seconds // 60
    seconds = sleep_seconds % 60
    
    print(f"⏳ הבוט נכנס להמתנה של {minutes} דקות ו-{seconds} שניות...")
    time.sleep(sleep_seconds)
    
    print("🚀 מתעורר ומתחיל סריקה...")
    
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

        # הדפסה ללוג כדי לוודא שההפרדה עובדת
        print(f"👀 נמצא: [בושם: {perfume['name']}] [מותג: {perfume['brand']}]")
        
        if check_db_exists(perfume['link']):
            print("😴 הבושם הזה כבר קיים ב-DB.")
        else:
            print("✨ בושם חדש! מבצע שמירה ושליחה...")
            
            save_to_db(perfume['name'], perfume['brand'], perfume['link'], perfume['image'])
            
            # בניית הודעה עם רווח יזום
            msg_title = "New Fragrance Alert"
            
            # כאן התיקון הקריטי למחרוזת: אנחנו שמים רווח בכוח בין המשתנים
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
