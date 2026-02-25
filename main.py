import os
import re
import time
import random
import schedule  # Added for timer logic
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from datetime import datetime, timezone
import psycopg2

from backup import create_db_dump

# Read settings from environment
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD", "secretpassword")
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_NAME = os.getenv("DB_NAME", "autoria_db")
SCRAPE_TIME = os.getenv("SCRAPE_TIME", "12:00")
DUMP_TIME = os.getenv("DUMP_TIME", "12:00")

BASE_URL = "https://auto.ria.com/uk/search/?search_type=2&abroad=0&customs_cleared=1&page={}"

# Database connection
conn = psycopg2.connect(
    dbname=DB_NAME, user=DB_USER, password=DB_PASSWORD, host=DB_HOST, port=5432
)
conn.autocommit = True


def init_db():
    with conn.cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS car_links (
                id SERIAL PRIMARY KEY,
                url TEXT UNIQUE NOT NULL,
                status VARCHAR(20) DEFAULT 'new'
            );
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS cars (
                id SERIAL PRIMARY KEY,
                url TEXT UNIQUE NOT NULL,
                title TEXT,
                price_usd INTEGER,
                odometer INTEGER,
                username TEXT,
                phone_number BIGINT,
                image_url TEXT,
                images_count INTEGER,
                car_number TEXT,
                car_vin TEXT,
                datetime_found TIMESTAMP
            );
        """)
    print("Tables initialized successfully.")


def create_driver():
    """Creates an instance of undetected-chromedriver with proxy support."""
    options = uc.ChromeOptions()

    # Mandatory settings for running in Docker
    options.add_argument("--headless=new")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")

    # Fetch proxy from environment
    proxy = os.getenv("PROXY_URL")
    if proxy:
        # Note: Selenium expects the format ip:port here (without http:// or credentials)
        # Example: 192.168.1.1:8080
        print(f"🌍 Using proxy: {proxy}")
        options.add_argument(f'--proxy-server={proxy}')

    driver = uc.Chrome(options=options)
    return driver


def save_link(url):
    with conn.cursor() as cur:
        cur.execute("INSERT INTO car_links (url) VALUES (%s) ON CONFLICT DO NOTHING", (url,))


def gather_links_from_page(driver, page):
    print(f"🔍 Searching for cars on page {page}...")
    wait = WebDriverWait(driver, 10)

    try:
        driver.get(BASE_URL.format(page))
        time.sleep(random.uniform(2.5, 4.5))

        try:
            wait.until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, "a.product-card")))
            cards = driver.find_elements(By.CSS_SELECTOR, "a.product-card")

            if not cards:
                return False

            for card in cards:
                href = card.get_attribute("href")
                if href:
                    save_link(href)

            print(f"✔ Collected links from {len(cards)} cards.")
            return True

        except Exception:
            print(f"❌ No cards found. Page title: '{driver.title}'")
            return False

    except Exception as e:
        print(f"Error loading page {page}: {e}")
        return False


def fetch_new_links():
    with conn.cursor() as cur:
        cur.execute("SELECT id, url FROM car_links WHERE status='new'")
        return cur.fetchall()


def mark_processed(link_id):
    with conn.cursor() as cur:
        cur.execute("UPDATE car_links SET status='processed' WHERE id=%s", (link_id,))


def save_car(data):
    with conn.cursor() as cur:
        cur.execute("""
        INSERT INTO cars (url,title,price_usd,odometer,username,phone_number,image_url,images_count,car_number,car_vin,datetime_found)
        VALUES (%(url)s,%(title)s,%(price_usd)s,%(odometer)s,%(username)s,%(phone_number)s,%(image_url)s,%(images_count)s,%(car_number)s,%(car_vin)s,%(datetime_found)s)
        ON CONFLICT (url) DO NOTHING
        """, data)


def parse_car(driver, link):
    link_id, url = link
    print(f"🔄 Processing: {url}")
    wait = WebDriverWait(driver, 15)

    try:
        driver.get(url)

        if "підозрілих" in driver.title.lower() or "cloudflare" in driver.title.lower() or "перевірка" in driver.title.lower():
            print("🛑 WARNING: Protection triggered! Bot is blocked on this page.")
            return False

        wait.until(EC.presence_of_element_located((By.TAG_NAME, "h1")))
        title = driver.find_element(By.TAG_NAME, "h1").text.strip()

        try:
            price = int(re.sub(r"\D", "", driver.find_element(By.CSS_SELECTOR, "strong").text))
        except:
            price = 0

        try:
            odo_text = driver.find_element(By.XPATH, "//span[contains(text(),'тис')]").text
        except:
            odo_text = None
        odometer = int(re.sub(r"\D", "", odo_text.replace("тис", ""))) * 1000 if odo_text else 0

        try:
            username = driver.find_element(By.CSS_SELECTOR, ".seller_info_name, .titleM").text
        except:
            username = "Not specified"

        try:
            image_url = driver.find_element(By.CSS_SELECTOR, "picture img").get_attribute("src")
        except:
            image_url = ""

        try:
            car_number = driver.find_element(By.CSS_SELECTOR, "div.car-number span.common-text").text
        except:
            car_number = ""

        try:
            car_vin = driver.find_element(By.CSS_SELECTOR, "#badgesVin .badge.common-text").text
        except:
            car_vin = ""

        phone = None
        try:
            phone_button = driver.find_element(By.CSS_SELECTOR,
                                               "button.size-large.conversion[data-action='showBottomPopUp']")
            driver.execute_script("arguments[0].click();", phone_button)
            time.sleep(random.uniform(1.0, 2.5))
            wait.until(EC.presence_of_element_located((By.XPATH, "//a[contains(@href,'tel:')]")))
            phone_raw = driver.find_element(By.XPATH, "//a[contains(@href,'tel:')]").get_attribute("href")
            phone = int(re.sub(r"\D", "", phone_raw))
        except Exception:
            pass

        save_car({
            "url": url, "title": title, "price_usd": price, "odometer": odometer, "username": username,
            "phone_number": phone, "image_url": image_url, "images_count": 1 if image_url else 0,
            "car_number": car_number, "car_vin": car_vin, "datetime_found": datetime.now(timezone.utc)
        })
        mark_processed(link_id)
        print(f"✔ Saved: {title} ({price}$)")
        return True

    except Exception as e:
        print(f"❌ Failed to parse page. Title: '{driver.title}'")
        return False


def scrape_cars(driver):
    links = fetch_new_links()
    if not links:
        print("All cars from this page are already in the database. Moving on!")
        return

    print(f"Found {len(links)} new links. Starting processing one by one...")

    for i, link in enumerate(links, 1):
        print(f"\n--- Car {i} of {len(links)} ---")
        success = parse_car(driver, link)

        if not success:
            pause_time = random.uniform(20, 35)
            print(f"⚠️ Cooling down for {int(pause_time)} seconds...")
            time.sleep(pause_time)
        else:
            time.sleep(random.uniform(3.0, 7.0))


def run_scraper_job():
    init_db()
    page = 1

    print("🚀 Launching undetected-chromedriver...")
    driver = create_driver()

    try:
        driver.get("https://auto.ria.com/uk/")
        time.sleep(random.uniform(3, 5))
    except:
        pass

    try:
        while True:
            print(f"\n==========================================")
            print(f" MOVING TO SEARCH PAGE {page}")
            print(f"==========================================")

            has_cards = gather_links_from_page(driver, page)

            if not has_cards:
                print("\n🏁 No more pages with cars (or temporarily blocked).")
                print("Ending scraping cycle.")
                break

            scrape_cars(driver)

            page += 1
            time.sleep(random.uniform(4.0, 8.0))

    finally:
        print("🛑 Closing browser.")
        driver.quit()


if __name__ == "__main__":
    print(f"App initialized. Scraper scheduled at {SCRAPE_TIME}, Dump at {DUMP_TIME}")

    # Schedule the jobs
    schedule.every().day.at(SCRAPE_TIME).do(run_scraper_job)
    schedule.every().day.at(DUMP_TIME).do(create_db_dump)

    # Keep the script running to execute scheduled tasks
    while True:
        schedule.run_pending()
        time.sleep(60)