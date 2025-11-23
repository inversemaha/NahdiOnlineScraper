"""
Simplified Nahdi Online Product Description Fetcher

Only includes the update_all_descriptions functionality and its dependencies.

Usage:
    # Update descriptions for all products in database
    update_all_descriptions()

    # Get description for a URL (used internally)
    description = get_product_description(
        "https://www.nahdionline.com/product/...", "nahdi")
"""

import os
import sys
import time
import gc
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup
from database import database
from pymongo import UpdateOne
from typing import Optional, Dict
import utils as u


def get_chrome_options():
    """Get optimized Chrome options for description fetching"""
    options = Options()
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option('useAutomationExtension', False)
    options.add_argument(
        "--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36")
    options.add_argument("--headless=new")
    # ...existing code...
    return options


def handle_modals(driver):
    """Comprehensive modal detection and handling"""
    try:
        modal_closed = False

        # Common modal selectors
        modal_selectors = [
            "//button[contains(@class, 'close')]",
            "//button[contains(@aria-label, 'close')]",
            "//button[contains(@aria-label, 'Close')]",
            "//button[@title='Close']",
            "//span[contains(@class, 'close')]",
            "//div[contains(@class, 'close')]",
            "//div[contains(@class, 'modal')]//button",
            "//div[contains(@class, 'popup')]//button",
            "//div[contains(@class, 'overlay')]//button",
            "//div[contains(@class, 'dialog')]//button",
            "//button[text()='×']",
            "//button[text()='✕']",
            "//span[text()='×']",
            "//span[text()='✕']",
            "//button[contains(text(), 'Close')]",
            "//button[contains(text(), 'close')]",
            "//button[contains(text(), 'Cancel')]",
            "//button[contains(text(), 'cancel')]",
            "//button[contains(text(), 'No')]",
            "//button[contains(text(), 'Later')]",
            "//button[contains(text(), 'Skip')]",
            "//div[contains(@class, 'backdrop')]",
            "//div[contains(@class, 'overlay')]"
        ]

        for selector in modal_selectors:
            try:
                modal_elements = driver.find_elements(By.XPATH, selector)

                for element in modal_elements:
                    if element.is_displayed() and element.is_enabled():
                        try:
                            driver.execute_script(
                                "arguments[0].click();", element)
                            modal_closed = True
                            time.sleep(0.5)
                            break
                        except:
                            continue

                if modal_closed:
                    break

            except Exception as e:
                continue

        # Additional check for Esc key
        if not modal_closed:
            try:
                driver.find_element(By.TAG_NAME, "body").send_keys(Keys.ESCAPE)
            except:
                pass

    except Exception as e:
        pass


def get_product_description(url: str, pharmacyname: str) -> str:
    """
    Fetch product description from a given URL

    Args:
        url: Product URL to fetch description from
        pharmacyname: Pharmacy name for error logging

    Returns:
        Product description text or empty string if failed
    """
    driver = None

    try:
        options = get_chrome_options()
        driver = webdriver.Chrome(options=options)

        driver.set_page_load_timeout(20)
        driver.get(url)
        time.sleep(5)

        try:
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.TAG_NAME, "body")))
        except:
            return ""

        # Handle modals on product page
        handle_modals(driver)

        soup = BeautifulSoup(driver.page_source, 'html.parser')

        # Try to find description in about section
        about_section = soup.find('div', class_='pdp-about-section')
        if about_section:
            paragraphs = about_section.find_all('p')
            if paragraphs:
                description = "\n".join(p.get_text(
                    separator="\n", strip=True) for p in paragraphs)
                return description
            html_div = about_section.find(
                'div', attrs={'data-content-type': 'html'})
            if html_div:
                description = html_div.get_text(separator="\n", strip=True)
                return description
            # fallback to all text
            description = about_section.get_text(separator="\n", strip=True)
            return description

        # Fallback to container base
        container = soup.find('div', class_='container-base')
        if container:
            description = container.get_text(separator="\n", strip=True)
            return description

        return ""

    except Exception as e:
        exception_type, exception_object, exception_traceback = sys.exc_info()
        line_number = exception_traceback.tb_lineno
        print(f"❌ Error fetching description for {url}")
        print(f"Exception type: {exception_type}")
        print(f"Exception object: {exception_object}")
        print(f"Line number: {line_number}")
        # Uncomment if you want error logging to database
        # errorInsert(url, exception_type, exception_object, line_number, pharmacyname)
        return ""

    finally:
        if driver:
            try:
                driver.quit()
            except:
                pass
        gc.collect()


def update_all_descriptions(pharmacyname: str = "Nahdionline", collection_name: str = "pharmacies",
                            batch_size: int = 15, filter_criteria: Optional[Dict] = None) -> Dict[str, int]:
    """
    Update descriptions for all products in the database

    Args:
        pharmacyname: Pharmacy name
        collection_name: MongoDB collection name
        batch_size: Number of products to process in each batch
        filter_criteria: Optional MongoDB filter to limit which products to update

    Returns:
        Dictionary with update statistics
    """
    stats = {
        "total_found": 0,
        "successful_updates": 0,
        "failed_updates": 0,
        "skipped_no_url": 0,
        "skipped_has_description": 0
    }

    try:
        db = database()
        collection = db[collection_name]

        # Default filter - only products without descriptions or with empty descriptions
        # Also filter by pharmacy name to only update Nahdi products
        if filter_criteria is None:
            filter_criteria = {
                "Pharmacyname": pharmacyname,
                "$or": [
                    {"ExtraInfo.description": {"$exists": False}},
                    {"ExtraInfo.description": ""},
                    {"ExtraInfo.description": None}
                ]
            }

        # Get total count
        total_products = collection.count_documents(filter_criteria)
        stats["total_found"] = total_products

        if total_products == 0:
            return stats

        # Process in batches
        processed = 0
        batch_operations = []

        cursor = collection.find(
            filter_criteria, {"URL": 1, "ExtraInfo.description": 1, "Product": 1})

        for product in cursor:
            processed += 1
            url = product.get("URL")
            product_name = product.get("Product", "Unknown")
            # Skip if no url
            if not url:
                stats["skipped_no_url"] += 1
                continue
            # Skip if already has description (optional check)
            existing_desc = product.get("ExtraInfo", {}).get("description", "")
            if existing_desc and len(existing_desc.strip()) > 10:
                stats["skipped_has_description"] += 1
                continue
            print(f"🔄 Requesting: {url} | Product: {product_name}")
            # Fetch description
            description = get_product_description(url, pharmacyname)
            if description and len(description.strip()) > 0:
                # Add to batch operations
                batch_operations.append(
                    UpdateOne(
                        {"_id": product["_id"]},
                        {"$set": {"ExtraInfo.description": description}}
                    )
                )
                stats["successful_updates"] += 1
                print(f"✅ SUCCESS: {product_name}")
            else:
                stats["failed_updates"] += 1
                print(f"❌ FAILED: {product_name}")
            # Execute batch when it reaches batch_size
            if len(batch_operations) >= batch_size:
                try:
                    result = collection.bulk_write(batch_operations)
                    batch_operations = []
                except Exception as e:
                    batch_operations = []

        # Execute remaining batch operations
        if batch_operations:
            try:
                result = collection.bulk_write(batch_operations)
                print(
                    f"💾 Saved final batch of {len(batch_operations)} updates")
            except Exception as e:
                print(f"❌ Error saving final batch: {e}")

    except Exception as e:
        print(f"❌ Error in update_all_descriptions: {e}")
        exception_type, exception_object, exception_traceback = sys.exc_info()
        line_number = exception_traceback.tb_lineno
        # Uncomment if you want error logging to database
        # errorInsert("update_all_descriptions", exception_type, exception_object, line_number, pharmacyname)

    return stats


if __name__ == "__main__":
    """
    Command line interface for description fetcher
    Usage:
        python product_description_service.py
    """
    print("🚀 Starting description update for all products...")
    stats = update_all_descriptions()
    print("✅ Description update completed!")
