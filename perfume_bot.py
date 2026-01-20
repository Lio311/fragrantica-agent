import os
from curl_cffi import requests as cffi_requests # לגלישה באתר (עקיפת חסימות)
import requests # לשליחת התמונה ל-Pushover
from bs4 import BeautifulSoup
import sys
import psycopg2 # לחיבור ל-Neon
from urllib.parse import urlparse

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
    """בודק אם הלינק כבר קיים ב-DB (במקום קובץ טקסט)"""
    if not DATABASE_URL:
        # Fallback: אם אין DB, נשתמש בקובץ טקסט כמו קודם
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
    """
    מנסה לחלץ בצורה חכמה: שם, מותג, תמונה ולינק מהקרוסלה
    """
    try:
        # אסטרטגיה: חיפוש הלינק הראשון שהוא בושם
        candidates = soup.find_all("a", href=True)
        
        for link in candidates:
            href = link['href']
            
            if '/perfume/' in href and '.html' in href and '/news/' not in href and '/designers/' not in href:
                
                full_link = "https://www.fragrantica.com" + href if not href.startswith('http') else href
                
                # --- חילוץ נתונים ---
                
                # 1. תמונה (בדרך כלל נמצאת בתוך הלינק)
                img_tag = link.find("img")
                image_url = img_tag['src'] if img_tag else None
                
                # 2. שם הבושם (בדרך כלל הטקסט מתחת לתמונה או ה-Alt)
                perfume_name = link.get_text(strip=True)
                if not perfume_name and img_tag and img_tag.get('alt'):
                    perfume_name = img_tag['alt']
                
                # 3. שם המותג (החלק הטריקי)
                # המותג נמצא בדרך כלל באלמנט שכן ("span" או "small") באותו קונטיינר של הלינק
                brand_name = "Unknown Brand"
                
                # ניסיון למצוא את המותג ע"י הליכה "אחורה" ב-DOM או חיפוש בסביבה הקרובה
                # בדרך כלל המבנה הוא: Cell -> Small(Brand) -> A(Name+Img)
                parent_cell = link.find_parent("div") # מנסה למצוא את הקונטיינר
                if parent_cell:
                    # מחפש טקסט קטן או לינק למותג בתוך אותו תא
                    brand_candidate = parent_cell.find("small") or parent_cell.find("span")
                    if brand_candidate:
                        brand_name = brand_candidate.get_text(strip=True)
                    else:
                        # לפעמים המותג הוא לינק נפרד לפני הבושם
                        prev_link = link.find_previous_sibling("a")
                        if prev_link and '/designers/' in prev_link.get('href', ''):
                            brand_name = prev_link.get_text(strip=True)

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
    print("🚀 מתחיל סריקה (DB + Image Mode)...")
    
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

        print(f"👀 נמצא: {perfume['name']} ({perfume['brand']})")
        
        # בדיקה האם הבושם כבר קיים ב-DB
        if check_db_exists(perfume['link']):
            print("😴 הבושם הזה כבר קיים ב-DB.")
        else:
            print("✨ בושם חדש! מבצע שמירה ושליחה...")
            
            # 1. שמירה ל-DB
            save_to_db(perfume['name'], perfume['brand'], perfume['link'], perfume['image'])
            
            # 2. הכנת הטקסט להתראה (בלי אימוג'ים, לפי הפורמט שביקשת)
            # פורמט: New Perfume: שם הבושם (רווח) שם המותג
            msg_title = "New Fragrance Alert"
            msg_body = f"New Perfume: {perfume['name']} {perfume['brand']}"
            
            # 3. שליחה ל-Pushover עם תמונה
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
