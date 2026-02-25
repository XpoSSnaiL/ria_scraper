import asyncio
import aiohttp
from bs4 import BeautifulSoup
from database import save_car
import os
import re
import random

# Reduce concurrency limit to avoid triggering AutoRia protection
CONCURRENCY_LIMIT = int(os.getenv("CONCURRENCY_LIMIT", 5))

# Mask as a real browser (Google Chrome on Windows)
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "uk-UA,uk;q=0.9,en-US;q=0.8,en;q=0.7",
}

# Hardcoded list of proxies provided by you
PROXY_LIST = [
    "http://104.207.51.107:3129",
    "http://65.111.10.206:3129",
    "http://104.207.40.6:3129",
    "http://196.1.93.10:80",
    "http://152.230.215.123:80",
    "http://98.66.229.76:3128",
    "http://178.156.238.178:3128"
]


async def fetch_html(url: str, session: aiohttp.ClientSession, semaphore: asyncio.Semaphore, retries: int = 3):
    """Fetches HTML content with proxy rotation and retry logic."""
    async with semaphore:
        for attempt in range(retries):
            # Select a random proxy for this request
            proxy = random.choice(PROXY_LIST)

            try:
                # 15 seconds timeout because free proxies can hang indefinitely
                timeout = aiohttp.ClientTimeout(total=15)
                async with session.get(url, headers=HEADERS, proxy=proxy, timeout=timeout) as response:
                    if response.status == 200:
                        return await response.text()
                    elif response.status in [403, 429]:
                        print(f"⚠️ Proxy {proxy} blocked (Status {response.status}). Retrying...")
                    else:
                        print(f"Error {response.status} for {url} via {proxy}")

            except Exception as e:
                # Catch connection errors/timeouts without crashing the app
                print(f"❌ Connection failed via {proxy} on attempt {attempt + 1}: {type(e).__name__}")

            # Short delay before the next retry
            await asyncio.sleep(random.uniform(1, 3))

        print(f"🚨 Failed to fetch {url} after {retries} attempts.")
        return None


async def parse_car_page(url: str, html: str):
    soup = BeautifulSoup(html, 'lxml')

    try:
        # Search for the header (any h1 on the car page)
        title_tag = soup.find('h1')
        title = title_tag.text.strip() if title_tag else ""

        # If there is no title, it's a captcha or a broken link. Skip!
        if not title:
            print(f"⚠️ Empty page or captcha: {url}")
            return

        # Price
        price_usd = 0
        price_tag = soup.find('div', class_='price_value')
        if price_tag and price_tag.find('strong'):
            price_text = price_tag.find('strong').text.replace('$', '').replace(' ', '')
            price_usd = int(re.sub(r'\D', '', price_text)) if price_text else 0

        # Odometer (search for numbers next to the word "тис" / thousand)
        odometer = 0
        base_info = soup.find('div', class_='base-information') or soup.find('div', class_='technical-info')
        if base_info:
            odo_match = re.search(r'(\d+)\s*(тис|тыс)', base_info.text)
            if odo_match:
                odometer = int(odo_match.group(1)) * 1000

        # Seller
        seller_tag = soup.find('h4', class_='seller_info_name') or soup.find('div', class_='seller_info_name')
        username = seller_tag.text.strip() if seller_tag else "Not specified"

        # Phone (from data-attributes, if present)
        phone_tag = soup.find('a', class_='phone')
        phone_number = None
        if phone_tag and 'data-phone-number' in phone_tag.attrs:
            phone_str = re.sub(r'\D', '', phone_tag['data-phone-number'])
            phone_number = int(phone_str) if phone_str else None

        # Photo
        img_tag = soup.find('div', class_='photo-620x465')
        img = img_tag.find('img') if img_tag else None
        image_url = img['src'] if img and 'src' in img.attrs else ""

        gallery = soup.find_all('a', class_='photo-220x165')
        images_count = len(gallery) + 1 if img else 0

        # Car number
        car_number_tag = soup.find('span', class_='state-num')
        car_number = car_number_tag.text.strip().split(' ')[0] if car_number_tag else ""

        # VIN
        vin_tag = soup.find('span', class_='label-vin') or soup.find('span', class_='vin-code')
        car_vin = vin_tag.text.strip() if vin_tag else ""

        car_data = {
            "url": url,
            "title": title,
            "price_usd": price_usd,
            "odometer": odometer,
            "username": username,
            "phone_number": phone_number,
            "image_url": image_url,
            "images_count": images_count,
            "car_number": car_number,
            "car_vin": car_vin
        }

        await save_car(car_data)
        print(f"✅ Saved: {title} | {price_usd}$ | {odometer} km")

    except Exception as e:
        print(f"❌ Parsing error {url}: {e}")


async def run_scraper():
    print("Starting scraping process...")
    start_url = os.getenv("SCRAPE_START_URL")
    semaphore = asyncio.Semaphore(CONCURRENCY_LIMIT)

    async with aiohttp.ClientSession() as session:
        page = 0
        while True:
            page_url = f"{start_url}?page={page}"
            html = await fetch_html(page_url, session, semaphore)
            if not html:
                break

            soup = BeautifulSoup(html, 'lxml')

            # AutoRia stores car links in elements with class m-link-ticket or address
            car_links = soup.select('a.m-link-ticket')
            if not car_links:
                car_links = soup.select('a.address')

            if not car_links:
                print("No more cars or page is blocked.")
                break

            tasks = []
            for link in car_links:
                car_url = link.get('href')
                if car_url:
                    tasks.append(process_car(car_url, session, semaphore))

            await asyncio.gather(*tasks)
            page += 1
            break  # TEMPORARY: parsing only the first page for quick testing


async def process_car(url, session, semaphore):
    html = await fetch_html(url, session, semaphore)
    if html:
        await parse_car_page(url, html)