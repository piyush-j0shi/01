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
OUTPUT_FILE = 'companies_updated.csv'
SEARCH_ENGINE = "https://www.google.com"

def init_driver():
    options = uc.ChromeOptions()
    options.add_argument("--start-maximized")
    options.add_argument("--lang=en-GB")
    
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
    """
    Robust email extraction that handles:
    1. mailto: links
    2. Standard emails
    3. Obfuscated emails with spaces/newlines (e.g. "name @ gmail . com")
    """
    soup = BeautifulSoup(html_content, 'html.parser')
    found_emails = set()

    for a in soup.find_all('a', href=True):
        href = a['href']
        if href.lower().startswith('mailto:'):
            email = unquote(href.split(':')[1].split('?')[0]).strip()
            if email:
                found_emails.add(email)

    text_content = soup.get_text(separator=' ')
    standard_pattern = r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'
    found_emails.update(re.findall(standard_pattern, text_content))

    broken_pattern = r'([a-zA-Z0-9._%+-]+)\s*@\s*([a-zA-Z0-9.-]+)\s*\.\s*([a-zA-Z]{2,})'
    broken_matches = re.findall(broken_pattern, html_content)
    
    for match in broken_matches:
        full_email = f"{match[0]}@{match[1]}.{match[2]}"
        found_emails.add(full_email)

    clean_emails = []
    junk_extensions = ['.png', '.jpg', '.jpeg', '.gif', '.css', '.js', '.svg', '.webp', '.mp4', '.woff']
    
    for email in found_emails:
        email = email.lower().strip()
        email = email.rstrip('.')
        
        if not any(email.endswith(ext) for ext in junk_extensions):
            if "sentry" not in email and "example.com" not in email:
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

def search_company_url(driver, company_name):
    try:
        driver.get(SEARCH_ENGINE)
        handle_google_consent(driver)
        
        if "unusual traffic" in driver.page_source.lower():
            input("   -> [ALERT] CAPTCHA detected! Solve it then press ENTER...")

        try:
            search_box = driver.find_element(By.NAME, "q")
            search_box.clear()
            search_box.send_keys(f"{company_name} London UK")
            search_box.send_keys(Keys.RETURN)
        except:
            driver.refresh()
            time.sleep(3)
            search_box = driver.find_element(By.NAME, "q")
            search_box.send_keys(f"{company_name} London UK")
            search_box.send_keys(Keys.RETURN)
        
        random_sleep(4, 6) 
        handle_google_consent(driver)

        # Official Button
        official_site = get_google_website_button(driver)
        if official_site:
            print(f"   -> [METHOD: BUTTON] Found official link.")
            return official_site

        # Organic Search
        try:
            results_container = driver.find_element(By.ID, "search") 
            links = results_container.find_elements(By.TAG_NAME, "a")
        except:
            links = driver.find_elements(By.XPATH, "//div[@class='g']//a")

        ignored_domains = [
            'google.', 'microsoft.', 'yahoo.', 'bing.', 'facebook.', 'linkedin.', 'instagram.', 'twitter.', 
            'youtube.', 'pinterest.', 'yell.com', 'checkatrade.com', 'trustpilot.com', 'thomsonlocal',
            'company-information.service.gov.uk', 'companieshouse.gov.uk', 
            'thegazette.co.uk', 'endole.co.uk', 'pomanda.com', 'bizify.co.uk', '192.com'
        ]

        valid_links = []
        for link in links:
            href = link.get_attribute('href')
            if not href or 'http' not in href or "google.com" in href: continue
            if any(ignored in href for ignored in ignored_domains): continue
            valid_links.append((href, link.text.lower()))

        # Smart Match
        company_tokens = normalize_name(company_name)
        for href, text in valid_links:
            if any(token in text for token in company_tokens):
                print(f"   -> [METHOD: TITLE MATCH] Found link: {href}")
                return href

        # Fallback
        if valid_links:
            print(f"   -> [METHOD: FALLBACK] Picking first valid result: {valid_links[0][0]}")
            return valid_links[0][0]

        return None
    except Exception as e:
        print(f"Error searching for {company_name}: {e}")
        return None

def find_contact_page(driver, base_url):
    try:
        soup = BeautifulSoup(driver.page_source, 'html.parser')
        keywords = ['contact', 'about', 'get in touch', 'support']
        for link in soup.find_all('a', href=True):
            if any(w in link.get_text().lower() for w in keywords):
                return urljoin(base_url, link['href'])
        return None
    except: return None

def process_workflow():
    print("Starting Browser...")
    driver = init_driver()
    
    try:
        print(f"Reading file: {INPUT_FILE}")
        if INPUT_FILE.endswith('.csv'): df = pd.read_csv(INPUT_FILE)
        else: df = pd.read_excel(INPUT_FILE)
            
        print(f"Loaded {len(df)} companies.")
        if 'Website' not in df.columns: df['Website'] = ""
        if 'Email' not in df.columns: df['Email'] = ""

        for index, row in df.iterrows():
            company = row['Name']
            if pd.isna(company) or str(company).strip() == "": continue
            if pd.notna(row['Website']) and str(row['Website']) not in ["", "nan", "Not Found"]:
                print(f"Skipping {company}, already has data.")
                continue

            print(f"[{index+1}/{len(df)}] Searching: {company}")
            website_url = search_company_url(driver, company)
            
            if not website_url:
                print(f"   -> Could not find website.")
                df.at[index, 'Website'] = "Not Found"
                df.at[index, 'Email'] = "Not Found"
            else:
                print(f"   -> Found Website: {website_url}")
                df.at[index, 'Website'] = website_url
                
                try:
                    try: driver.get(website_url)
                    except TimeoutException: driver.execute_script("window.stop();")
                    except: 
                        time.sleep(2)
                        driver.refresh()
                    
                    random_sleep(3, 5)
                    emails = extract_emails_from_html(driver.page_source)
                    
                    if not emails:
                        print("   -> No emails on home, checking Contact page...")
                        contact_url = find_contact_page(driver, website_url)
                        if contact_url:
                            try:
                                driver.get(contact_url)
                                random_sleep(3, 5)
                                emails = extract_emails_from_html(driver.page_source)
                            except: pass
                    
                    email_string = ", ".join(emails) if emails else "Not Found"
                    print(f"   -> Emails: {email_string}")
                    df.at[index, 'Email'] = email_string
                except Exception as e:
                    print(f"   -> Error visiting website: {e}")
                    df.at[index, 'Email'] = "Error"

            df.to_csv(OUTPUT_FILE, index=False)
    except Exception as e: print(f"Critical Error: {e}")
    finally:
        try: driver.quit()
        except: pass
        print(f"Done. Saved to {OUTPUT_FILE}")

if __name__ == "__main__":
    process_workflow()