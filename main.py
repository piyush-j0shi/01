import time
import random
import pandas as pd
import re
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.common.exceptions import TimeoutException
from bs4 import BeautifulSoup
from urllib.parse import urljoin, unquote

INPUT_FILE = 'companies.xlsx'
OUTPUT_FILE = 'companies_updated.xlsx'
SEARCH_ENGINE = "https://www.google.com"

def init_driver():
    options = uc.ChromeOptions()

    # headless chrome
    # options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--disable-software-rasterizer")
    options.add_argument("--disable-extensions")

    options.add_argument("--window-size=1920,1080")
    options.add_argument("--lang=en-GB")

    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

    driver = uc.Chrome(options=options, version_main=142)
    driver.set_page_load_timeout(30)
    return driver

def random_sleep(min_seconds=3, max_seconds=6):
    time.sleep(random.uniform(min_seconds, max_seconds))

def handle_google_consent(driver):
    """Clicks 'Accept All' cookie buttons."""
    try:
        consent_xpaths = [
            "//button[div[contains(text(), 'Accept all')]]",
            "//button[contains(., 'Accept all')]",
            "//button[contains(., 'Reject all')]",
            "//div[@role='button'][contains(., 'Accept all')]",
            "//button[@aria-label='Accept all']"
        ]
        for xpath in consent_xpaths:
            try:
                buttons = driver.find_elements(By.XPATH, xpath)
                for btn in buttons:
                    if btn.is_displayed():
                        btn.click()
                        time.sleep(1)
                        return
            except: continue
    except: pass

def extract_emails_from_html(html_content):
    soup = BeautifulSoup(html_content, 'html.parser')
    found_emails = set()

    for script in soup(['script', 'style', 'noscript']):
        script.decompose()

    for a in soup.find_all('a', href=True):
        href = a['href']
        if href.lower().startswith('mailto:'):
            email = unquote(href.split(':')[1].split('?')[0]).strip()
            if email and '@' in email:
                found_emails.add(email)

    text_content = soup.get_text(separator=' ')

    standard_pattern = r'\b[a-zA-Z0-9][a-zA-Z0-9._%+-]*@[a-zA-Z0-9][a-zA-Z0-9.-]*\.[a-zA-Z]{2,}\b'
    found_emails.update(re.findall(standard_pattern, text_content, re.IGNORECASE))

    dot_pattern = r'\b([a-zA-Z0-9][a-zA-Z0-9._%+-]*)\s*@\s*([a-zA-Z0-9][a-zA-Z0-9.-]*)\s*\.\s*([a-zA-Z]{2,})\b'
    dot_matches = re.findall(dot_pattern, html_content, re.IGNORECASE)
    for match in dot_matches:
        full_email = f"{match[0]}@{match[1]}.{match[2]}"
        found_emails.add(full_email)

    at_pattern = r'\b([a-zA-Z0-9][a-zA-Z0-9._%+-]*)\s*\[\s*at\s*\]\s*([a-zA-Z0-9][a-zA-Z0-9.-]*)\s*\.\s*([a-zA-Z]{2,})\b'
    at_matches = re.findall(at_pattern, html_content, re.IGNORECASE)
    for match in at_matches:
        full_email = f"{match[0]}@{match[1]}.{match[2]}"
        found_emails.add(full_email)

    clean_emails = []
    junk_extensions = ['.png', '.jpg', '.jpeg', '.gif', '.css', '.js', '.svg', '.webp', '.mp4', '.woff', '.woff2', '.ttf', '.eot', '.ico']
    junk_patterns = ['sentry', 'example.com', 'domain.com', 'email.com', 'your-email', 'youremail', 'test@', '@test', 'noreply@example']

    for email in found_emails:
        email = email.lower().strip()
        email = re.sub(r'^[.\-_]+|[.\-_]+$', '', email)
        email = email.rstrip('.,;:')

        if '@' not in email or email.count('@') > 1:
            continue

        if any(email.endswith(ext) for ext in junk_extensions):
            continue

        if any(junk in email for junk in junk_patterns):
            continue

        if len(email) < 6 or len(email) > 254:
            continue

        parts = email.split('@')
        if len(parts) != 2 or not parts[0] or not parts[1]:
            continue

        if '.' not in parts[1]:
            continue

        clean_emails.append(email)

    return list(set(clean_emails))

def get_google_website_button(driver):
    try:
        xpaths = [
            "//a[@aria-label='Website']",
            "//a[.//div[text()='Website']]",
            "//a[.//span[text()='Website']]",
            "//div[@role='heading']//following::a[contains(@href, 'http')][text()='Website']",
            "//a[contains(@class, 'ab_button')]"
        ]
        for xpath in xpaths:
            buttons = driver.find_elements(By.XPATH, xpath)
            for btn in buttons:
                href = btn.get_attribute('href')
                if href and "http" in href and "google" not in href:
                    return href
        return None
    except: return None

def normalize_name(name):
    """Cleans company name for matching logic."""
    if not isinstance(name, str): return []
    remove_words = ['ltd', 'limited', 'uk', 'services', 'london', 'co', 'company', '&', 'and', 'sons', 'bros']
    clean = re.sub(r'[^a-z0-9\s]', '', name.lower())
    tokens = clean.split()
    return [t for t in tokens if t not in remove_words and len(t) > 2]

def search_company_url(driver, company_name, location="London UK", log_callback=None):
    try:
        driver.get(SEARCH_ENGINE)
        handle_google_consent(driver)

        if "unusual traffic" in driver.page_source.lower():
            print("   -> [ALERT] CAPTCHA detected! This may cause failures in automated mode.")
            if log_callback:
                log_callback("CAPTCHA detected - request may fail")

        try:
            search_box = driver.find_element(By.NAME, "q")
            search_box.clear()
            search_box.send_keys(f"{company_name} {location}")
            search_box.send_keys(Keys.RETURN)
        except:
            driver.refresh()
            time.sleep(3)
            search_box = driver.find_element(By.NAME, "q")
            search_box.send_keys(f"{company_name} {location}")
            search_box.send_keys(Keys.RETURN)

        random_sleep(4, 6)
        handle_google_consent(driver)

        official_site = get_google_website_button(driver)
        if official_site:
            print(f"   -> [METHOD: BUTTON] Found official link: {official_site}")
            return official_site

        try:
            results_container = driver.find_element(By.ID, "search")
            links = results_container.find_elements(By.TAG_NAME, "a")
        except:
            links = driver.find_elements(By.XPATH, "//div[@class='g']//a")

        ignored_domains = [
            'google.', 'microsoft.', 'yahoo.', 'bing.', 'facebook.', 'linkedin.', 'instagram.', 'twitter.',
            'youtube.', 'pinterest.', 'yell.com', 'checkatrade.com', 'trustpilot.com', 'thomsonlocal',
            'company-information.service.gov.uk', 'companieshouse.gov.uk',
            'thegazette.co.uk', 'endole.co.uk', 'pomanda.com', 'bizify.co.uk', '192.com',
            'wikipedia.org', 'wiki', '.gov.qa', 'gov.qa', 'moci.gov.qa', 'portal.www.gov.qa',
            'hukoomi.gov.qa', 'gsdp.gov.qa', 'yellowpages', 'whitepages', 'yelp.com',
            'bbb.org', 'dnb.com', 'bloomberg.com', 'reuters.com', 'crunchbase.com',
            'zoominfo.com', 'kompass.com', 'europages.', 'alibaba.com', 'indiamart.com',
            'justdial.com', 'sulekha.com', 'foursquare.com', 'manta.com', 'bizapedia.com',
            'corporationwiki.com', 'spoke.com', 'vault.com', 'glassdoor.com', 'indeed.com',
            'naviqatar.com', 'waze.com', 'wanderlog.com'
        ]

        valid_links = []
        for link in links:
            href = link.get_attribute('href')
            if not href or 'http' not in href or "google.com" in href: continue
            if any(ignored in href for ignored in ignored_domains): continue
            valid_links.append((href, link.text.lower()))

        company_tokens = normalize_name(company_name)
        for href, text in valid_links:
            if any(token in text for token in company_tokens):
                print(f"   -> [METHOD: TITLE MATCH] Found link: {href}")
                return href

        if valid_links:
            print(f"   -> [METHOD: FALLBACK] Picking first valid result: {valid_links[0][0]}")
            return valid_links[0][0]

        print(f"   -> No valid website found for {company_name}")
        return None
    except Exception as e:
        print(f"   -> Error searching for {company_name}: {e}")
        return None

def find_contact_and_about_pages(driver, base_url):
    try:
        soup = BeautifulSoup(driver.page_source, 'html.parser')
        pages = {
            'contact-us': None,
            'contact': None,
            'about-us': None,
            'about': None,
            'reach-us': None,
            'get-in-touch': None
        }

        for link in soup.find_all('a', href=True):
            href = link.get('href', '')
            text = link.get_text().lower().strip()
            full_url = urljoin(base_url, href)

            if full_url.startswith(base_url) or href.startswith('/'):
                href_lower = href.lower()

                if ('contact-us' in href_lower or 'contactus' in href_lower or
                    'contact_us' in href_lower or text == 'contact us'):
                    if not pages['contact-us']:
                        pages['contact-us'] = full_url

                elif ('contact' in href_lower or text == 'contact' or
                      'get-in-touch' in href_lower or 'reach-us' in href_lower):
                    if not pages['contact'] and not pages['contact-us']:
                        pages['contact'] = full_url

                elif ('about-us' in href_lower or 'aboutus' in href_lower or
                      'about_us' in href_lower or text == 'about us'):
                    if not pages['about-us']:
                        pages['about-us'] = full_url

                elif 'about' in href_lower or text == 'about':
                    if not pages['about'] and not pages['about-us']:
                        pages['about'] = full_url

        result = []
        priority_order = ['contact-us', 'contact', 'about-us', 'about']
        for key in priority_order:
            if pages[key]:
                result.append(pages[key])

        return result if result else []
    except:
        return []

def has_valid_data(value):
    """Check if a cell has valid data (not empty, not 'Not Found', not 'Error')"""
    if pd.isna(value):
        return False
    value_str = str(value).strip().lower()
    if value_str in ["", "nan", "not found", "error", "none"]:
        return False
    return True

def process_workflow(input_file=None, city=None, country=None, log_callback=None, stop_check=None):
    if not city or not country:
        raise ValueError("City and Country are required parameters")

    city = city.strip()
    country = country.strip()
    location = f"{city} {country}"

    msg = f"Starting Browser for location: {location}..."
    print(msg)
    if log_callback:
        log_callback(msg)

    driver = init_driver()

    try:
        file_to_process = input_file or INPUT_FILE
        print(f"Reading file: {file_to_process}")

        if file_to_process.endswith('.csv'): df = pd.read_csv(file_to_process)
        else: df = pd.read_excel(file_to_process)

        print(f"Loaded {len(df)} companies.")

        if 'Website' not in df.columns: df['Website'] = ""
        if 'Email' not in df.columns: df['Email'] = ""

        msg = "Processing all companies with fresh search..."
        print(msg)
        if log_callback:
            log_callback(msg)

        companies_to_process = 0
        for idx, row in df.iterrows():
            if pd.isna(row['Name']) or str(row['Name']).strip() == "":
                continue
            companies_to_process += 1

        msg = f"Total companies to process: {companies_to_process}"
        print(msg)
        if log_callback:
            log_callback(msg)

        processed_count = 0
        for index, row in df.iterrows():
            if stop_check and stop_check():
                msg = "Stop signal received. Saving progress..."
                print(msg)
                if log_callback:
                    log_callback(msg)
                break

            company = row['Name']
            if pd.isna(company) or str(company).strip() == "": continue

            processed_count += 1

            msg = f"[{processed_count}/{companies_to_process}] Processing {company} - searching for website and email"
            print(msg)
            if log_callback:
                log_callback(msg)

            website_url = search_company_url(driver, company, location, log_callback)
            if not website_url:
                print("   -> Could not find website.")
                df.at[index, 'Website'] = "Not Found"
                df.at[index, 'Email'] = "Not Found"
                website_url = None
            else:
                print(f"   -> Found Website: {website_url}")
                df.at[index, 'Website'] = website_url

            if website_url:
                try:
                    try: driver.get(website_url)
                    except TimeoutException: driver.execute_script("window.stop();")
                    except:
                        time.sleep(2)
                        driver.refresh()

                    random_sleep(2, 4)
                    print("   -> Searching for emails on homepage...")
                    emails = extract_emails_from_html(driver.page_source)

                    if emails:
                        print(f"   -> Found {len(emails)} email(s) on homepage")
                    else:
                        print("   -> No emails on homepage, checking contact/about pages...")
                        contact_pages = find_contact_and_about_pages(driver, website_url)

                        if contact_pages:
                            print(f"   -> Found {len(contact_pages)} potential page(s) to check")
                            for page_url in contact_pages:
                                if emails:
                                    break
                                try:
                                    print(f"   -> Checking: {page_url}")
                                    driver.get(page_url)
                                    random_sleep(2, 3)
                                    emails = extract_emails_from_html(driver.page_source)
                                    if emails:
                                        print(f"   -> Found {len(emails)} email(s) on this page")
                                        break
                                except Exception as e:
                                    print(f"   -> Error loading page: {e}")
                                    continue
                        else:
                            print("   -> No contact/about pages found")

                        if not emails:
                            print("   -> No emails found on existing website, searching Google for alternative website...")
                            new_website_url = search_company_url(driver, company, location, log_callback)

                            if new_website_url and new_website_url != website_url:
                                print(f"   -> Found alternative website: {new_website_url}")
                                try:
                                    driver.get(new_website_url)
                                    random_sleep(2, 4)
                                    print("   -> Searching for emails on alternative homepage...")
                                    emails = extract_emails_from_html(driver.page_source)

                                    if emails:
                                        print(f"   -> Found {len(emails)} email(s) on alternative homepage")
                                        df.at[index, 'Website'] = new_website_url
                                        print(f"   -> Updated website to: {new_website_url}")
                                    else:
                                        print("   -> No emails on alternative homepage, checking its contact/about pages...")
                                        contact_pages = find_contact_and_about_pages(driver, new_website_url)

                                        if contact_pages:
                                            print(f"   -> Found {len(contact_pages)} potential page(s) on alternative site")
                                            for page_url in contact_pages:
                                                if emails:
                                                    break
                                                try:
                                                    print(f"   -> Checking: {page_url}")
                                                    driver.get(page_url)
                                                    random_sleep(2, 3)
                                                    emails = extract_emails_from_html(driver.page_source)
                                                    if emails:
                                                        print(f"   -> Found {len(emails)} email(s) on this page")
                                                        df.at[index, 'Website'] = new_website_url
                                                        print(f"   -> Updated website to: {new_website_url}")
                                                        break
                                                except Exception as e:
                                                    print(f"   -> Error loading page: {e}")
                                                    continue
                                except Exception as e:
                                    print(f"   -> Error visiting alternative website: {e}")
                            else:
                                print("   -> No alternative website found or same as existing")

                    email_string = ", ".join(emails) if emails else "Not Found"
                    print(f"   -> Final result: {email_string}")
                    df.at[index, 'Email'] = email_string
                except Exception as e:
                    print(f"   -> Error visiting website: {e}")
                    df.at[index, 'Email'] = "Error"
            else:
                print("   -> Cannot search for email without a website")
                df.at[index, 'Email'] = "Not Found"

            update_msg = "Updated: website and email"
            if log_callback:
                log_callback(update_msg)

            df.to_excel(OUTPUT_FILE, index=False)

        msg = f"Processing complete! Processed {processed_count} companies. Saved to {OUTPUT_FILE}"
        print(msg)
        if log_callback:
            log_callback(msg)

    except Exception as e:
        msg = f"Critical Error: {e}"
        print(msg)
        if log_callback:
            log_callback(msg)
    finally:
        try:
            driver.quit()
        except:
            pass

    return OUTPUT_FILE

if __name__ == "__main__":
    process_workflow(city="London", country="UK")
