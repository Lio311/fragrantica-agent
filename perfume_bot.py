import os
import requests
from bs4 import BeautifulSoup
import sys

# --- הגדרות ---
NEWS_URL = "https://www.fragrantica.com/news/new-fragrances/"
LAST_SEEN_FILE = "last_seen_perfume.txt"

# כותרות דפדפן (חובה למניעת חסימה)
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.google.com/"
}

# --- שליפת מפתחות Pushover משתני הסביבה ---
# שים לב: שיניתי את השמות שיתאימו ל-Pushover
PUSHOVER_USER_KEY = os.environ.get("PUSHOVER_USER_KEY")
PUSHOVER_API_TOKEN = os.environ.get("PUSHOVER_API_TOKEN")

def send_pushover_notification(title, message, url_link=None):
    """שולח התראה לטלפון באמצעות Pushover"""
    
    if not PUSHOVER_USER_KEY or not PUSHOVER_API_TOKEN:
        print("❌ שגיאה: חסרים מפתחות Pushover (USER_KEY או API_TOKEN).")
        return

    # הכתובת של ה-API
    endpoint = "https://api.pushover.net/1/messages.json"
    
    # בניית הפיילאוד (המידע שנשלח)
    payload = {
        "token": PUSHOVER_API_TOKEN,  # המפתח של האפליקציה שיצרת
        "user": PUSHOVER_USER_KEY,    # המפתח האישי שלך
        "title": title,
        "message": message,
        "html": 1,                    # מאפשר עיצוב HTML כמו <b>
        "sound": "cosmic",            # צליל מגניב (אפשר לשנות ל-pushover, bike, etc)
        "priority": 0                 # עדיפות רגילה
    }

    # אם יש לינק, נוסיף אותו כשדה ייעודי (יותר נוח ללחיצה בהתראה)
    if url_link:
        payload["url"] = url_link
        payload["url_title"] = "👉 לחץ למעבר לכתבה"

    try:
        response = requests.post(endpoint, data=payload, timeout=10)
        
        if response.status_code == 200:
            print("✅ התראת Pushover נשלחה בהצלחה!")
        else:
            print(f"❌ שגיאה בשליחת Pushover: {response.text}")
            
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

def get_latest_article(soup):
    candidates = []
    for a in soup.find_all('a', href=True):
        href = a['href']
        text = a.get_text(strip=True)
        
        if '/news/' in href and href != '/news/new-fragrances/' and len(text) > 10:
            full_link = "https://www.fragrantica.com" + href if not href.startswith('http') else href
            if not any(c['link'] == full_link for c in candidates):
                candidates.append({'title': text, 'link': full_link})
    
    if candidates:
        return candidates[0]
    return None

def main():
    print("🚀 הבוט מתחיל בסריקת Fragrantica (Pushover Edition)...")
    
    try:
        response = requests.get(NEWS_URL, headers=HEADERS, timeout=15)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, 'html.parser')
        latest_item = get_latest_article(soup)
        
        if not latest_item:
            print("⚠️ לא נמצאו כתבות.")
            return

        latest_title = latest_item['title']
        latest_link = latest_item['link']
        
        print(f"👀 כתבה אחרונה: {latest_title}")
        
        last_seen = get_last_seen_link()
        
        if latest_link != last_seen:
            print("✨ זיהוי חדש! שולח Pushover...")
            
            # הכנת הטקסט להודעה
            msg_body = (
                f"נמצא בושם/כתבה חדשה באתר:<br>"
                f"<b>{latest_title}</b>"
            )
            
            # שליחה
            send_pushover_notification(
                title="🧴 בושם חדש ב-Fragrantica!",
                message=msg_body,
                url_link=latest_link
            )
            
            save_last_seen_link(latest_link)
        else:
            print("😴 אין חדש.")

    except Exception as e:
        print(f"❌ שגיאה קריטית: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
