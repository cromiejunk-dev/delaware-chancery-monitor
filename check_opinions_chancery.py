import os
import json
import time
from datetime import datetime
from pathlib import Path
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
import requests

# Configuration
EMAIL_FROM = os.getenv("EMAIL_FROM", "your-email@gmail.com")
EMAIL_TO = os.getenv("EMAIL_TO", "your-email@gmail.com")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD", "your-app-password")
SMTP_SERVER = os.getenv("SMTP_SERVER", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))

SEEN_OPINIONS_FILE = "seen_opinions.json"

def load_seen_opinions():
    """Load previously seen opinions"""
    if Path(SEEN_OPINIONS_FILE).exists():
        with open(SEEN_OPINIONS_FILE, "r") as f:
            return json.load(f)
    return []

def save_seen_opinions(opinions):
    """Save seen opinions"""
    with open(SEEN_OPINIONS_FILE, "w") as f:
        json.dump(opinions, f, indent=2)

def setup_driver():
    """Set up Chrome driver"""
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.binary_location = "/snap/bin/chromium"
    
    driver = webdriver.Chrome(options=chrome_options)
    return driver

def scrape_chancery_opinions():
    """Scrape Court of Chancery opinions"""
    driver = setup_driver()
    opinions = []
    
    try:
        url = "https://courts.delaware.gov/opinions/index.aspx?ag=court%20of%20chancery"
        print(f"Loading page: {url}")
        driver.get(url)
        
        time.sleep(5)
        
        print("Searching for PDF links...")
        pdf_links = driver.find_elements(By.XPATH, "//a[contains(@href, '.pdf')]")
        print(f"Found {len(pdf_links)} PDF links")
        
        for link in pdf_links:
            try:
                href = link.get_attribute("href")
                text = link.text.strip()
                
                if href and text and "chancery" in href.lower():
                    opinions.append({
                        "title": text,
                        "url": href,
                        "date_found": datetime.now().isoformat()
                    })
                    print(f"Found opinion: {text}")
            except:
                continue
        
        if len(opinions) == 0:
            print("No chancery PDFs found, trying broader search...")
            all_links = driver.find_elements(By.TAG_NAME, "a")
            print(f"Checking {len(all_links)} total links...")
            
            for link in all_links:
                try:
                    href = link.get_attribute("href")
                    text = link.text.strip()
                    
                    if href and ".pdf" in href.lower() and text:
                        opinions.append({
                            "title": text,
                            "url": href,
                            "date_found": datetime.now().isoformat()
                        })
                        print(f"Found PDF: {text}")
                except:
                    continue
        
    except Exception as e:
        print(f"Error scraping: {e}")
    finally:
        driver.quit()
    
    return opinions

def download_pdf(url, filename):
    """Download PDF file"""
    try:
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        
        filepath = Path("downloads") / filename
        filepath.parent.mkdir(exist_ok=True)
        
        with open(filepath, "wb") as f:
            f.write(response.content)
        
        print(f"Downloaded: {filename}")
        return filepath
    except Exception as e:
        print(f"Error downloading {url}: {e}")
        return None

def send_email(new_opinions, pdf_paths):
    """Send email with PDFs"""
    try:
        msg = MIMEMultipart()
        msg["From"] = EMAIL_FROM
        msg["To"] = EMAIL_TO
        msg["Subject"] = f"New Delaware Court of Chancery Opinions - {datetime.now().strftime('%Y-%m-%d')}"
        
        body = f"Found {len(new_opinions)} new opinion(s):\n\n"
        for opinion in new_opinions:
            body += f"- {opinion['title']}\n  {opinion['url']}\n\n"
        
        msg.attach(MIMEText(body, "plain"))
        
        for pdf_path in pdf_paths:
            if pdf_path and pdf_path.exists():
                with open(pdf_path, "rb") as f:
                    pdf = MIMEApplication(f.read(), _subtype="pdf")
                    pdf.add_header("Content-Disposition", "attachment", 
                                 filename=pdf_path.name)
                    msg.attach(pdf)
        
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()
            server.login(EMAIL_FROM, EMAIL_PASSWORD)
            server.send_message(msg)
        
        print(f"Email sent successfully with {len(pdf_paths)} attachments")
        return True
    
    except Exception as e:
        print(f"Error sending email: {e}")
        return False

def main():
    """Main function"""
    print(f"Starting Court of Chancery opinion check at {datetime.now()}")
    
    seen_opinions = load_seen_opinions()
    seen_urls = {op["url"] for op in seen_opinions}
    print(f"Previously seen {len(seen_urls)} opinions")
    
    current_opinions = scrape_chancery_opinions()
    print(f"Found {len(current_opinions)} total opinions on the page")
    
    new_opinions = [op for op in current_opinions if op["url"] not in seen_urls]
    
    if new_opinions:
        print(f"Found {len(new_opinions)} new opinion(s)!")
        
        pdf_paths = []
        for opinion in new_opinions:
            filename = opinion["url"].split("/")[-1]
            pdf_path = download_pdf(opinion["url"], filename)
            if pdf_path:
                pdf_paths.append(pdf_path)
        
        if send_email(new_opinions, pdf_paths):
            seen_opinions.extend(new_opinions)
            save_seen_opinions(seen_opinions)
            print("Successfully processed new opinions")
        else:
            print("Failed to send email")
    else:
        print("No new opinions found")

if __name__ == "__main__":
    main()
