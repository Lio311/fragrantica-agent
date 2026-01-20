import os
from curl_cffi import requests # שים לב לשינוי כאן!
from bs4 import BeautifulSoup
import sys

# --- הגדרות ---
NEWS_URL = "https://www.fragrantica.com/news/new-fragrances/"
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
        "sound": "cosmic",
        "priority": 0
    }

    if url_link:
        payload["url"] = url_link
        payload["url_title"] = "👉 לחץ למעבר לכתבה"

    try:
        # Pushover לא דורש עקיפות מיוחדות, אפשר להשתמש ב-requests הרגיל או החדש
        response = requests.post(endpoint, data=payload, timeout=10)
        if response.status_code == 200:
            print("✅ התראת Pushover נשלחה!")
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
    print("🚀 הבוט מתחיל בסריקה (TLS Impersonation Mode)...")
    
    try:
        # --- השינוי הגדול: התחזות לדפדפן כרום אמיתי ---
        # impersonate="chrome" גורם לבקשה להיראות זהה ב-100% לדפדפן כרום
        response = requests.get(NEWS_URL, impersonate="chrome", timeout=20)
        
        # אם עדיין מקבלים 403, ננסה להתחזות לספארי (לפעמים עובד טוב יותר)
        if response.status_code == 403:
            print("⚠️ ניסיון ראשון נחסם. מנסה להתחזות ל-Safari...")
            response = requests.get(NEWS_URL, impersonate="safari", timeout=20)

        if response.status_code != 200:
            print(f"❌ שגיאה סופית בגישה לאתר: {response.status_code}")
            sys.exit(1)
        
        soup = BeautifulSoup(response.text, 'html.parser')
        latest_item = get_latest_article(soup)
        
        if not latest_item:
            print("⚠️ לא נמצאו כתבות (אולי המבנה השתנה, או שנחסמנו בצורה שקטה).")
            return

        latest_title = latest_item['title']
        latest_link = latest_item['link']
        
        print(f"👀 כתבה אחרונה שנמצאה: {latest_title}")
        
        last_seen = get_last_seen_link()
        
        if latest_link != last_seen:
            print("✨ זיהוי חדש! שולח התראה...")
            msg_body = f"נמצא בושם/כתבה חדשה באתר:<br><b>{latest_title}</b>"
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
