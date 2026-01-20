import os
from curl_cffi import requests
from bs4 import BeautifulSoup
import sys
import re

# --- הגדרות ---
# סורקים את עמוד הבית, שם נמצאת הקרוסלה מהתמונה ששלחת
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

def get_newest_perfume_from_homepage(soup):
    """
    מחפש את האזור "New Perfumes" בעמוד הבית ושולף את הבושם הראשון משמאל.
    """
    try:
        # 1. חיפוש הכותרת "New Perfumes"
        # אנחנו מחפשים אלמנט שמכיל את הטקסט הזה
        header = soup.find(lambda tag: tag.name in ["h2", "h3", "h4", "h5", "div"] and "New Perfumes" in tag.text)
        
        if not header:
            print("⚠️ לא נמצאה הכותרת 'New Perfumes' בעמוד.")
            return None

        # 2. מציאת הקונטיינר הסמוך לכותרת (שם נמצאים הבשמים)
        # בדרך כלל הקרוסלה נמצאת ב-div שאחרי הכותרת או בתוך אותו קונטיינר אב
        # ננסה למצוא את הלינק לבושם הראשון שמופיע אחרי הכותרת
        
        # אוספים את כל הלינקים שמופיעים *אחרי* הכותרת בקוד
        all_links_after = header.find_all_next("a", href=True)
        
        for link in all_links_after[:20]: # בודקים רק את ה-20 הראשונים כדי לא להרחיק לכת
            href = link['href']
            
            # בדיקה שזה לינק לבושם (מכיל /perfume/ ומסתיים ב-.html)
            # וגם מוודאים שזה לא לינק לכתבה (/news/)
            if '/perfume/' in href and '.html' in href and '/news/' not in href:
                
                # מצאנו בושם! עכשיו ננסה לחלץ שם ומותג
                full_link = "https://www.fragrantica.com" + href if not href.startswith('http') else href
                
                # בדרך כלל בתוך הלינק יש תמונה וטקסט. ננסה לחלץ בצורה חכמה.
                perfume_name = link.get_text(strip=True)
                
                # אם הלינק מכיל רק תמונה, נחפש את הטקסט בלינק שצמוד אליו או ב-alt של התמונה
                img = link.find("img")
                if not perfume_name and img and img.get('alt'):
                    perfume_name = img['alt']
                
                # אם עדיין אין שם, נפרק את ה-URL
                if not perfume_name:
                    # מנסה לחלץ מתוך ה-URL: /perfume/Brand/Name-123.html
                    parts = href.split('/')
                    if len(parts) > 2:
                        raw_name = parts[-1].replace('.html', '')
                        # מנקה את המספרים בסוף
                        perfume_name = re.sub(r'-\d+$', '', raw_name).replace('-', ' ')

                return {
                    'title': perfume_name,
                    'link': full_link
                }
                
        return None

    except Exception as e:
        print(f"❌ שגיאה בניתוח ה-HTML: {e}")
        return None

def main():
    print("🚀 הבוט מתחיל בסריקת Homepage (מחפש בקבוקים חדשים)...")
    
    try:
        # שימוש ב-impersonate="chrome" כדי לעקוף את שגיאה 403
        response = requests.get(HOMEPAGE_URL, impersonate="chrome", timeout=20)
        
        if response.status_code != 200:
            print(f"❌ שגיאה בגישה לאתר: {response.status_code}")
            sys.exit(1)
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # הפעלת הלוגיקה החדשה
        newest_perfume = get_newest_perfume_from_homepage(soup)
        
        if not newest_perfume:
            print("⚠️ לא הצלחתי למצוא בושם במדור 'New Perfumes'.")
            return

        latest_title = newest_perfume['title']
        latest_link = newest_perfume['link']
        
        print(f"👀 הבושם הכי חדש שראיתי בקרוסלה: {latest_title}")
        
        last_seen = get_last_seen_link()
        
        # אם הלינק שונה ממה ששמרנו פעם קודמת = בושם חדש נכנס לקרוסלה
        if latest_link != last_seen:
            print("✨ בושם חדש זוהה! שולח התראה...")
            
            msg_body = (
                f"🎉 <b>בושם חדש עלה למאגר!</b><br>"
                f"שם: {latest_title}<br>"
            )
            
            send_pushover_notification(
                title="New Perfume Alert 🧴",
                message=msg_body,
                url_link=latest_link
            )
            
            save_last_seen_link(latest_link)
        else:
            print("😴 אין חדש בקרוסלה.")

    except Exception as e:
        print(f"❌ קריסה כללית: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
