import os
from curl_cffi import requests
from bs4 import BeautifulSoup
import sys
import re

# --- הגדרות ---
HOMEPAGE_URL = "https://www.fragrantica.com/"
LAST_SEEN_FILE = "last_seen_perfume.txt"

# --- שליפת מפתחות Pushover ---
PUSHOVER_USER_KEY = os.environ.get("PUSHOVER_USER_KEY")
PUSHOVER_API_TOKEN = os.environ.get("PUSHOVER_API_TOKEN")

def send_pushover_notification(title, message, url_link=None):
    if not PUSHOVER_USER_KEY or not PUSHOVER_API_TOKEN:
        print("❌ שגיאה: חסרים מפתחות Pushover.")
        return

    endpoint = "https://api.pushover.net/1/messages.json"
    
    payload = {
        "token": PUSHOVER_API_TOKEN,
        "user": PUSHOVER_USER_KEY,
        "title": title,
        "message": message,
        "html": 1,
        "priority": 0
    }

    if url_link:
        payload["url"] = url_link
        payload["url_title"] = "👉 לחץ לעמוד הבושם"

    try:
        import requests as orig_requests
        orig_requests.post(endpoint, data=payload, timeout=10)
        print("✅ התראת Pushover נשלחה!")
    except Exception as e:
        print(f"❌ שגיאה בחיבור ל-Pushover: {e}")

def get_last_seen_link():
    if not os.path.exists(LAST_SEEN_FILE):
        return None
    with open(LAST_SEEN_FILE, "r", encoding="utf-8") as f:
        return f.read().strip()

def save_last_seen_link(link):
    with open(LAST_SEEN_FILE, "w", encoding="utf-8") as f:
        f.write(link)

def get_first_perfume_on_page(soup):
    """
    במקום לחפש כותרות, פשוט שולף את הלינק התקין הראשון לבושם שנמצא בעמוד.
    בפרגרנטיקה, הלינקים הראשונים בקוד הם תמיד מהקרוסלה של החדשים.
    """
    try:
        # מחפש את כל הלינקים בעמוד שמכילים /perfume/
        # ומסנן כתבות (/news/) או דפי חיפוש
        candidates = soup.find_all("a", href=True)
        
        print(f"🔍 נמצאו {len(candidates)} לינקים בעמוד. מסנן...")

        for link in candidates:
            href = link['href']
            
            # תנאי סינון קפדניים:
            # 1. חייב להיות לינק לבושם
            # 2. חייב להסתיים ב-.html
            # 3. אסור שיהיה לינק לכתבה
            # 4. אסור שיהיה לינק למותג (designers)
            if '/perfume/' in href and '.html' in href and '/news/' not in href and '/designers/' not in href:
                
                full_link = "https://www.fragrantica.com" + href if not href.startswith('http') else href
                
                # חילוץ שם הבושם
                perfume_name = link.get_text(strip=True)
                
                # אם אין טקסט בלינק, ננסה למצוא תמונה בתוכו (בדרך כלל בקרוסלה זה תמונה)
                if not perfume_name:
                    img = link.find("img")
                    if img and img.get('alt'):
                        perfume_name = img['alt']
                
                # מנגנון חירום: חילוץ שם מתוך הלינק עצמו
                if not perfume_name:
                    parts = href.split('/')
                    if len(parts) > 2:
                        raw_name = parts[-1].replace('.html', '')
                        perfume_name = re.sub(r'-\d+$', '', raw_name).replace('-', ' ')

                # מחזיר את הראשון שנמצא (וזהו, יוצאים מהפונקציה)
                return {
                    'title': perfume_name,
                    'link': full_link
                }
                
        return None

    except Exception as e:
        print(f"❌ שגיאה בניתוח ה-HTML: {e}")
        return None

def main():
    print("🚀 הבוט מתחיל בסריקה (מצב חיפוש לינקים ישיר)...")
    
    try:
        # הורדת העמוד
        response = requests.get(HOMEPAGE_URL, impersonate="chrome", timeout=20)
        
        if response.status_code != 200:
            print(f"❌ שגיאה בגישה לאתר: {response.status_code}")
            sys.exit(1)
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # הדפסת הכותרת של העמוד כדי לוודא שאנחנו במקום הנכון
        print(f"📄 כותרת העמוד שנסרק: {soup.title.string if soup.title else 'לא נמצאה כותרת'}")

        # הפעלת הלוגיקה החדשה
        newest_perfume = get_first_perfume_on_page(soup)
        
        if not newest_perfume:
            print("⚠️ מוזר מאוד. לא מצאתי שום לינק לבושם בעמוד הבית.")
            # הדפסת חלק מה-HTML לדיבוג (רק ה-500 תווים הראשונים) אם נכשל
            # print(soup.prettify()[:500]) 
            return

        latest_title = newest_perfume['title']
        latest_link = newest_perfume['link']
        
        print(f"👀 הבושם הראשון שנמצא: {latest_title}")
        
        last_seen = get_last_seen_link()
        
        if latest_link != last_seen:
            print("✨ שינוי זוהה! שולח התראה...")
            
            msg_body = (
                f"🎉 <b>בושם חדש (או שינוי בקרוסלה)!</b><br>"
                f"שם: {latest_title}<br>"
            )
            
            send_pushover_notification(
                title="New Perfume Alert 🧴",
                message=msg_body,
                url_link=latest_link
            )
            
            save_last_seen_link(latest_link)
        else:
            print("😴 זה אותו בושם כמו בפעם הקודמת.")

    except Exception as e:
        print(f"❌ קריסה כללית: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
