import os
import requests
from bs4 import BeautifulSoup
import urllib.parse
import sys

# --- הגדרות ---
NEWS_URL = "https://www.fragrantica.com/news/new-fragrances/"
LAST_SEEN_FILE = "last_seen_perfume.txt"

# כותרות דפדפן (Headers) - קריטי כדי ש-Fragrantica יחשבו שאתה משתמש אמיתי
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.google.com/"
}

# --- שליפת הסודות ממשתני הסביבה (מוגדר ב-GitHub Settings) ---
PHONE_NUMBER = os.environ.get("PHONE_NUMBER")
API_KEY = os.environ.get("API_KEY")

def send_whatsapp_message(text):
    """שולח את ההודעה לוואטסאפ דרך CallMeBot"""
    if not PHONE_NUMBER or not API_KEY:
        print("❌ שגיאה: חסרים משתני סביבה (PHONE_NUMBER או API_KEY). בדוק את הגדרות ה-Secrets בגיטהאב.")
        return

    # קידוד הטקסט לפורמט שמתאים לקישור אינטרנט (URL Encoded)
    encoded_text = urllib.parse.quote(text)
    url = f"https://api.callmebot.com/whatsapp.php?phone={PHONE_NUMBER}&text={encoded_text}&apikey={API_KEY}"
    
    try:
        # שליחת הבקשה עם Timeout של 20 שניות למקרה שהשרת איטי
        response = requests.get(url, timeout=20)
        if response.status_code == 200:
            print("✅ הודעה נשלחה בהצלחה לוואטסאפ!")
        else:
            print(f"❌ שגיאה בשליחת ההודעה: {response.text}")
    except Exception as e:
        print(f"❌ שגיאה בחיבור ל-API של וואטסאפ: {e}")

def get_last_seen_link():
    """קורא מקובץ הטקסט את הלינק האחרון שראינו בפעם הקודמת"""
    if not os.path.exists(LAST_SEEN_FILE):
        return None
    with open(LAST_SEEN_FILE, "r", encoding="utf-8") as f:
        return f.read().strip()

def save_last_seen_link(link):
    """מעדכן את קובץ הטקסט בלינק החדש"""
    with open(LAST_SEEN_FILE, "w", encoding="utf-8") as f:
        f.write(link)

def get_latest_article(soup):
    """
    מוצא את הכתבה החדשה ביותר בעמוד.
    משתמש בלוגיקה שמסננת לינקים לא רלוונטיים ומחפשת כתבות חדשות.
    """
    candidates = []
    
    # עוברים על כל הלינקים בעמוד
    for a in soup.find_all('a', href=True):
        href = a['href']
        text = a.get_text(strip=True)
        
        # תנאי סינון: הלינק חייב להכיל 'news', לא להיות הלינק של העמוד עצמו, ולהיות בעל כותרת משמעותית
        if '/news/' in href and href != '/news/new-fragrances/' and len(text) > 10:
            
            # המרה ללינק מלא במקרה שמדובר בלינק יחסי
            full_link = "https://www.fragrantica.com" + href if not href.startswith('http') else href
            
            # בדיקה כדי לא להוסיף כפילויות לרשימה
            if not any(c['link'] == full_link for c in candidates):
                candidates.append({
                    'title': text,
                    'link': full_link
                })
    
    # בדרך כלל הכתבה הראשונה ב-DOM (במבנה ה-HTML) היא החדשה ביותר
    if candidates:
        return candidates[0]
    
    return None

def main():
    print("🚀 הבוט מתחיל בסריקת Fragrantica...")
    
    try:
        # 1. שליחת בקשה לאתר
        response = requests.get(NEWS_URL, headers=HEADERS, timeout=15)
        response.raise_for_status() # יעצור אם האתר מחזיר שגיאה (כמו 404 או 500)
        
        # 2. ניתוח ה-HTML
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # 3. מציאת הכתבה החדשה ביותר
        latest_item = get_latest_article(soup)
        
        if not latest_item:
            print("⚠️ אזהרה: לא נמצאו כתבות בעמוד. ייתכן שמבנה האתר השתנה.")
            # במקרה כזה אנחנו לא רוצים לשבור את הריצה, אלא רק לדווח
            return

        latest_title = latest_item['title']
        latest_link = latest_item['link']
        
        print(f"👀 הכתבה האחרונה שנמצאה באתר: {latest_title}")
        
        # 4. בדיקה מול ההיסטוריה
        last_seen = get_last_seen_link()
        
        if latest_link != last_seen:
            print("✨ זיהוי חדש! מעדכן ושולח הודעה...")
            
            # יצירת תוכן ההודעה
            message = (
                f"*עדכון בושם חדש ב-Fragrantica!* 🧴\n\n"
                f"🏷️ *כותרת:* {latest_title}\n"
                f"🔗 *לינק:* {latest_link}\n"
            )
            
            # שליחה ושמירה
            send_whatsapp_message(message)
            save_last_seen_link(latest_link)
        else:
            print("😴 אין חדש. הכתבה האחרונה כבר נשלחה בעבר.")

    except Exception as e:
        print(f"❌ שגיאה קריטית במהלך הריצה: {e}")
        sys.exit(1) # יציאה עם שגיאה כדי ש-GitHub Action יסמן אדום

if __name__ == "__main__":
    main()
