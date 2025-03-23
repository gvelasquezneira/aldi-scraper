from playwright.sync_api import sync_playwright, Playwright
import csv
import time
from datetime import datetime

def scroll_to_load_all_items(page):
    """Scroll the page to load all dynamically loaded items."""
    last_height = page.evaluate("document.body.scrollHeight")
    while True:
        page.evaluate("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(2)
        new_height = page.evaluate("document.body.scrollHeight")
        if new_height == last_height:
            break
        last_height = new_height

def extract_item_details(deli_item):
    """Extract product name, price, and ounces from a deli item."""
    price = "Not found"
    for price_class in ['div.e-2feaft', 'div.e-s71gfs']:
        price_div = deli_item.locator(price_class).first
        price_span = price_div.locator('span.screen-reader-only').first
        if price_span.count() > 0:
            full_price = price_span.inner_text()
            price = full_price.split('$')[1] if '$' in full_price else full_price
            break

    grocery_div = deli_item.locator('div.e-147kl2c').first
    product_name = grocery_div.inner_text() if grocery_div.count() > 0 else "Not found"

    ozs_div = deli_item.locator('div.e-an4oxa').first
    ounces = ozs_div.inner_text() if ozs_div.count() > 0 else "Not found"

    return {"Product Name": product_name, "Price": f"${price}", "Ounces": ounces}

def scrape_deli_items(page):
    """Scrape all deli items from the page and return with category and date."""
    scroll_to_load_all_items(page)

    category_div = page.locator('h1.e-4jb28s').first
    category = category_div.inner_text() if category_div.count() > 0 else "Unknown Category"
    print(f"Scraping category: {category}")

    deli = page.locator('h3.e-ti75j2')
    deli_count = deli.count()
    print(f"Number of products found: {deli_count}")

    deli_data = []
    current_date = datetime.now().strftime("%Y-%m-%d")
    if deli_count > 0:
        for i in range(deli_count):
            deli_item = deli.nth(i)
            item_details = extract_item_details(deli_item)
            item_details["Category"] = category
            item_details["Date"] = current_date
            deli_data.append(item_details)
    else:
        print("No products found with locator h3.e-ti75j2")
    
    return deli_data

def append_to_csv(data, filename='aldi_products.csv'):
    """Append scraped data to a CSV file."""
    if not data:
        print("No data to append to CSV")
        return

    try:
        with open(filename, 'r', encoding='utf-8') as f:
            has_header = csv.Sniffer().has_header(f.read(1024))
    except FileNotFoundError:
        has_header = False

    with open(filename, mode='a', newline='', encoding='utf-8') as file:
        writer = csv.DictWriter(file, fieldnames=["Date", "Category", "Product Name", "Price", "Ounces"])
        if not has_header:
            writer.writeheader()
        writer.writerows(data)
    print(f"Data appended to {filename}")

def get_subcategory_urls(page, department_url):
    """Extract unique sub-category URLs from a department page."""
    print(f"Navigating to department: {department_url}")
    page.goto(department_url, wait_until="domcontentloaded")
    page.wait_for_timeout(3000)  # Wait for sub-categories to load

    subcat_links = page.locator('a[href*="/store/aldi/collections"]')
    sub_urls = set()  # Use a set to avoid duplicates within this page

    for i in range(subcat_links.count()):
        link = subcat_links.nth(i)
        href = link.get_attribute("href")
        full_url = f"https://shop.aldi.us{href}" if href.startswith("/") else href
        if "/collections/n-" in full_url or "/collections/rc-" in full_url:
            sub_urls.add(full_url)  # Add to set (duplicates are ignored)
            print(f"Found sub-category URL: {full_url}")

    if not sub_urls:
        print(f"No sub-categories found for {department_url}. Treating as a single category.")
        sub_urls.add(department_url)  # Add the department URL if no sub-categories

    return list(sub_urls)  # Convert back to list for consistency

def get_department_urls(page):
    """Extract top-level department URLs and their unique sub-categories from the Aldi storefront page."""
    base_url = "https://shop.aldi.us/store/aldi/storefront"
    print(f"Navigating to {base_url}...")
    page.goto(base_url, wait_until="domcontentloaded")
    print(f"Loaded {page.url}, waiting for content...")
    page.wait_for_timeout(5000)

    continue_button = page.get_by_role("button", name="Confirm")
    if continue_button.count() > 0:
        continue_button.click()
        print("Continue button clicked")
        page.wait_for_timeout(2000)
    else:
        print("Continue button not found")

    ul_locator = page.locator('ul.e-19g896u')
    if ul_locator.count() == 0:
        print("ul.e-19g896u not found. Dumping page content for inspection:")
        print(page.content()[:1000])
        return []

    print("Found ul.e-19g896u")
    department_links = page.locator('ul.e-19g896u > li > a.e-v0wv1')
    dept_urls = set()  # Use a set for unique department URLs

    print(f"Total department links found: {department_links.count()}")
    for i in range(department_links.count()):
        link = department_links.nth(i)
        href = link.get_attribute("href")
        full_url = f"https://shop.aldi.us{href}" if href.startswith("/") else href
        dept_urls.add(full_url)  # Add to set
        print(f"Found department URL: {full_url}")

    # Get sub-categories for each department
    all_sub_urls = set()  # Use a set for unique sub-categories across all departments
    for dept_url in dept_urls:
        sub_urls = get_subcategory_urls(page, dept_url)
        all_sub_urls.update(sub_urls)  # Update set with sub-category URLs

    print(f"Total unique sub-category URLs found: {len(all_sub_urls)}")
    return list(all_sub_urls)  # Convert back to list

def run(playwright: Playwright):
    """Main function to run the scraping process for dynamically fetched URLs."""
    browser = playwright.chromium.launch(headless=True)
    page = browser.new_page()
    
    # Get all unique sub-category URLs
    urls = get_department_urls(page)
    if not urls:
        print("No URLs to scrape. Exiting.")
        browser.close()
        return

    all_deli_data = []
    for i, url in enumerate(urls):
        print(f"\nProcessing URL {i + 1}/{len(urls)}: {url}")
        try:
            page.goto(url, wait_until="domcontentloaded")
            page.wait_for_timeout(2000)
            deli_data = scrape_deli_items(page)
            all_deli_data.extend(deli_data)
            time.sleep(1)  # Avoid rate limiting
        except Exception as e:
            print(f"Error scraping {url}: {e}")

    append_to_csv(all_deli_data)
    browser.close()

if __name__ == "__main__":
    with sync_playwright() as playwright:
        run(playwright)