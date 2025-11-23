import os.path
import sys
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium import webdriver
import utils as u
from errorLogs import logsInsert, logUpdate, errorInsert, LastScrapperTimeUpdate
from datetime import datetime
from database import database
from exchange import Saudia_to_Mexico_rate
from bs4 import BeautifulSoup
from io import BytesIO
import hashlib
import pickle
import xml.etree.ElementTree as ET
import gc
import urllib.parse
import threading
import re
import html
import time
import requests
import glob
import json
import asyncio
import aiohttp
import random
import shutil
from asyncio import Semaphore
from typing import List, Dict, Optional, Tuple

# Try to import lxml for better XML parsing
try:
    from lxml import etree as lxml_etree
    LXML_AVAILABLE = True
    print("✅ lxml available - using optimized XML parsing")
except ImportError:
    LXML_AVAILABLE = False
    print("⚠️ lxml not available - falling back to standard XML parsing")

# Import description fetcher
try:
    from product_description_service import get_product_description
    DESCRIPTION_FETCHER_AVAILABLE = True
    print("✅ Description fetcher available")
except ImportError:
    print("⚠️ Description fetcher module not available")
    DESCRIPTION_FETCHER_AVAILABLE = False

# ===========================================
# CONFIGURATION & CONSTANTS
# ===========================================

BASE_URL = "https://www.nahdionline.com"
CATEGORY_ID = "72666"
CATEGORY_URL = f"{BASE_URL}/en-sa/rx-treatments/cancer-treatments/plp/{CATEGORY_ID}"
API_URL = f"{BASE_URL}/api/analytics/product"
SITEMAP_INDEX_URL = "https://sitemap.nahdionline.com/sitemap_index_en.xml"

# Async configuration
MAX_CONCURRENT_REQUESTS = 5  # Reduced to avoid blocking
API_RATE_LIMIT = 1.2  # Increased delay between requests
MAX_RETRIES = 3
REQUEST_TIMEOUT = 30

# Anti-detection configuration
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/119.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Safari/605.1.15"
]

# Checkpoint configuration
CHECKPOINT_DIR = "checkpoints"
CANCER_PROGRESS_FILE = "cancer_progress.json"
SITEMAP_PROGRESS_FILE = "sitemap_progress.json"
SMALL_BATCH_SIZE = 15  # Optimized batch size

# Sitemap image configuration
SITEMAP_IMAGE_PICKLE_DIR = 'checkpoints/sitemap_image_chunks'
SITEMAP_IMAGE_INDEX_FILE = 'checkpoints/sitemap_image_chunk_index.pkl'
SITEMAP_IMAGE_CHUNK_SIZE = 2000

insert_lock = threading.Lock()

# ===========================================
# INTEGRATED SITEMAP IMAGE HANDLER
# ===========================================

class SitemapImageManager:
    """Integrated sitemap image management"""
    
    def __init__(self):
        self.ensure_pickle_dir()
        
    def ensure_pickle_dir(self):
        """Ensure pickle directory exists"""
        if not os.path.exists(SITEMAP_IMAGE_PICKLE_DIR):
            os.makedirs(SITEMAP_IMAGE_PICKLE_DIR)
    
    def cleanup_old_pickles(self):
        """Clean up old pickle files"""
        try:
            if os.path.exists(SITEMAP_IMAGE_PICKLE_DIR):
                shutil.rmtree(SITEMAP_IMAGE_PICKLE_DIR)
            if os.path.exists(SITEMAP_IMAGE_INDEX_FILE):
                os.remove(SITEMAP_IMAGE_INDEX_FILE)
            print("🧹 Old sitemap image pickles cleaned up")
            self.ensure_pickle_dir()
        except Exception as e:
            print(f"⚠️ Error cleaning up pickles: {e}")
    
    async def extract_images_from_sitemaps_async(self, sitemap_urls: List[str]):
        """Extract images from sitemaps asynchronously"""
        print("📸 Starting sitemap image extraction...")
        self.cleanup_old_pickles()  # Clean old data first
        
        chunk = {}
        chunk_index = {}
        chunk_num = 0
        total = 0
        
        headers = {
            "User-Agent": random.choice(USER_AGENTS),
            "Accept": "application/xml,text/xml,*/*",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
        }
        
        async with aiohttp.ClientSession(headers=headers) as session:
            for sitemap_url in sitemap_urls:
                try:
                    print(f"📄 Processing sitemap images: {sitemap_url.split('/')[-1]}")
                    
                    async with session.get(sitemap_url, timeout=aiohttp.ClientTimeout(total=60)) as response:
                        if response.status != 200:
                            print(f"❌ HTTP {response.status} for {sitemap_url}")
                            continue
                        
                        content = await response.read()
                        print(f"✅ Downloaded sitemap ({len(content)} bytes)")
                    
                    # Parse with lxml if available
                    if LXML_AVAILABLE:
                        xml_data = BytesIO(content)
                        
                        try:
                            context = lxml_etree.iterparse(
                                xml_data, 
                                events=("end",), 
                                tag="{http://www.sitemaps.org/schemas/sitemap/0.9}url", 
                                recover=True
                            )
                            
                            processed_count = 0
                            for event, elem in context:
                                try:
                                    sku = None
                                    
                                    # Extract SKU from URL
                                    loc_elem = elem.find("{http://www.sitemaps.org/schemas/sitemap/0.9}loc")
                                    if loc_elem is not None and loc_elem.text:
                                        url = loc_elem.text
                                        m = re.search(r'/pdp/(\d+)', url)
                                        if m:
                                            sku = m.group(1)
                                    
                                    if not sku:
                                        elem.clear()
                                        continue
                                    
                                    # Extract ALL images
                                    all_images = []
                                    
                                    # Extract cover image from PageMap
                                    pagemap = elem.find('{http://www.google.com/schemas/sitemap-pagemap/1.0}PageMap')
                                    if pagemap is not None:
                                        for attr in pagemap.findall('.//{http://www.google.com/schemas/sitemap-pagemap/1.0}Attribute'):
                                            if attr.get('name') == 'src' and attr.text:
                                                all_images.append(attr.text)
                                                break
                                    
                                    # Extract sitemap images
                                    ns = {'image': 'http://www.google.com/schemas/sitemap-image/1.1'}
                                    image_elements = elem.findall('image:image', ns)
                                    for img_elem in image_elements:
                                        img_loc = img_elem.find('image:loc', ns)
                                        if img_loc is not None and img_loc.text:
                                            if img_loc.text not in all_images:
                                                all_images.append(img_loc.text)
                                    
                                    # Save images for this SKU
                                    if all_images:
                                        chunk[sku] = all_images
                                        chunk_index[sku] = chunk_num
                                        total += 1
                                    
                                    processed_count += 1
                                    
                                    # Save chunk when full
                                    if len(chunk) >= SITEMAP_IMAGE_CHUNK_SIZE:
                                        chunk_file = f"{SITEMAP_IMAGE_PICKLE_DIR}/chunk_{chunk_num}.pkl"
                                        with open(chunk_file, 'wb') as f:
                                            pickle.dump(chunk, f)
                                        print(f"💾 Saved image chunk {chunk_num} with {len(chunk)} items")
                                        chunk = {}
                                        chunk_num += 1
                                    
                                    # Memory cleanup
                                    elem.clear()
                                    
                                except Exception as e:
                                    elem.clear()
                                    continue
                            
                            print(f"✅ Processed {processed_count} items from {sitemap_url.split('/')[-1]}")
                            
                        except Exception as e:
                            print(f"❌ Error parsing sitemap {sitemap_url}: {e}")
                    
                    # Rate limiting
                    await asyncio.sleep(1)
                    
                except Exception as e:
                    print(f"❌ Error downloading sitemap {sitemap_url}: {e}")
                    continue
        
        # Save final chunk
        if chunk:
            chunk_file = f"{SITEMAP_IMAGE_PICKLE_DIR}/chunk_{chunk_num}.pkl"
            with open(chunk_file, 'wb') as f:
                pickle.dump(chunk, f)
            print(f"💾 Saved final image chunk {chunk_num} with {len(chunk)} items")
        
        # Save index
        with open(SITEMAP_IMAGE_INDEX_FILE, 'wb') as f:
            pickle.dump(chunk_index, f)
        
        print(f"✅ Extracted images for {total} products in {chunk_num + 1} chunks")
        return total > 0
    
    def get_product_images_from_sitemap(self, sku: str, api_fallback_image: str = None) -> List[str]:
        """Get all images for SKU from sitemap cache"""
        sitemap_images = []
        
        # Try to load from cache
        if os.path.exists(SITEMAP_IMAGE_INDEX_FILE):
            try:
                with open(SITEMAP_IMAGE_INDEX_FILE, 'rb') as f:
                    chunk_index = pickle.load(f)
                
                chunk_num = chunk_index.get(sku)
                if chunk_num is not None:
                    chunk_file = f"{SITEMAP_IMAGE_PICKLE_DIR}/chunk_{chunk_num}.pkl"
                    if os.path.exists(chunk_file):
                        with open(chunk_file, 'rb') as f:
                            chunk = pickle.load(f)
                        images = chunk.get(sku, [])
                        
                        if images:
                            sitemap_images = [img for img in images if img]
                            
            except Exception as e:
                print(f"[SITEMAP] Error loading images for SKU {sku}: {e}")
        
        # Add API fallback if not already present
        if sitemap_images:
            if api_fallback_image and api_fallback_image not in sitemap_images:
                sitemap_images.append(api_fallback_image)
            print(f"[SITEMAP] ✅ SKU {sku}: Using SITEMAP images ({len(sitemap_images)} images)")
            return sitemap_images
        
        # Fallback to API image
        if api_fallback_image:
            print(f"[SITEMAP] ⚠️ SKU {sku}: Using API FALLBACK (no sitemap images)")
            return [api_fallback_image]
        
        print(f"[SITEMAP] ❌ SKU {sku}: NO IMAGES available")
        return []

# ===========================================
# ASYNC API CLIENT WITH ENHANCED ANTI-DETECTION
# ===========================================

class AsyncAPIClient:
    def __init__(self, max_concurrent: int = MAX_CONCURRENT_REQUESTS, rate_limit: float = API_RATE_LIMIT):
        self.semaphore = Semaphore(max_concurrent)
        self.rate_limit = rate_limit
        self.last_request_time = 0
        self.session = None
        self.request_count = 0
        
    async def __aenter__(self):
        connector = aiohttp.TCPConnector(
            limit=MAX_CONCURRENT_REQUESTS,
            limit_per_host=3,  # Conservative limit per host
            ttl_dns_cache=300,
            use_dns_cache=True,
        )
        
        timeout = aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)
        
        self.session = aiohttp.ClientSession(
            connector=connector,
            timeout=timeout,
            headers=self.get_headers()
        )
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()
            
    def get_headers(self) -> Dict[str, str]:
        """Get randomized headers for anti-detection"""
        return {
            "User-Agent": random.choice(USER_AGENTS),
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "en-US,en;q=0.9,ar;q=0.8",
            "Accept-Encoding": "gzip, deflate, br",
            "DNT": "1",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-origin",
            "Cache-Control": "no-cache",
            "Pragma": "no-cache"
        }
    
    async def rate_limited_request(self, method: str, url: str, **kwargs) -> Optional[aiohttp.ClientResponse]:
        """Make rate-limited request with enhanced anti-detection"""
        async with self.semaphore:
            # Enhanced rate limiting
            current_time = time.time()
            time_since_last = current_time - self.last_request_time
            if time_since_last < self.rate_limit:
                sleep_time = self.rate_limit - time_since_last
                # Add random jitter
                sleep_time += random.uniform(0.2, 0.5)
                await asyncio.sleep(sleep_time)
            
            self.last_request_time = time.time()
            self.request_count += 1
            
            # Anti-detection: Longer pause every N requests
            if self.request_count % 15 == 0:
                pause_time = random.uniform(3, 7)
                await asyncio.sleep(pause_time)
                print(f"    🛡️ Anti-detection pause ({pause_time:.1f}s) after {self.request_count} requests")
            
            # Retry logic with exponential backoff
            for attempt in range(MAX_RETRIES):
                try:
                    # Use your original working proxy method
                    async with self.session.request(method, url, **kwargs) as response:
                        if response.status == 200:
                            return response
                        elif response.status == 429:  # Rate limited
                            wait_time = (2 ** attempt) + random.uniform(2, 5)
                            print(f"    ⚠️ Rate limited (429), waiting {wait_time:.1f}s")
                            await asyncio.sleep(wait_time)
                        elif response.status == 403:  # Forbidden
                            wait_time = (2 ** attempt) + random.uniform(5, 10)
                            print(f"    🚫 Forbidden (403), waiting {wait_time:.1f}s")
                            await asyncio.sleep(wait_time)
                        else:
                            print(f"    ❌ HTTP {response.status} on attempt {attempt + 1}")
                            
                except asyncio.TimeoutError:
                    wait_time = (2 ** attempt) + random.uniform(1, 3)
                    print(f"    ⏰ Timeout on attempt {attempt + 1}, waiting {wait_time:.1f}s")
                    await asyncio.sleep(wait_time)
                except Exception as e:
                    wait_time = (2 ** attempt) + random.uniform(1, 3)
                    print(f"    ❌ Request error on attempt {attempt + 1}: {e}")
                    await asyncio.sleep(wait_time)
            
            return None

# ===========================================
# HELPER FUNCTIONS
# ===========================================

def clean_url(url):
    """Remove 'hlprd.' from URLs and fix double slashes"""
    if url and 'hlprd.' in url:
        url = url.replace('hlprd.', '')
    
    # Fix any double slashes except in the protocol (http://)
    if url and '://' in url:
        protocol, rest = url.split('://', 1)
        rest = rest.replace('//', '/')
        url = protocol + '://' + rest
    
    return url

def get_chrome_options():
    """Get optimized Chrome options"""
    options = Options()
    options.add_argument("--headless")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option('useAutomationExtension', False)
    
    # Anti-detection
    options.add_argument(f"--user-agent={random.choice(USER_AGENTS)}")
    options.add_argument("--disable-background-timer-throttling")
    options.add_argument("--disable-renderer-backgrounding")
    options.add_argument("--disable-backgrounding-occluded-windows")
    options.add_argument("--disable-background-networking")
    options.add_argument("--disable-background-mode")
    options.add_argument("--disable-extensions")
    options.add_argument("--disable-plugins")
    options.add_argument("--disable-images")
    options.add_argument("--disable-javascript")
    
    # Memory optimization
    options.add_argument("--max-heap-size=2048")
    options.add_argument("--js-flags=--max-old-space-size=2048")
    
    return options

def handle_modals(driver):
    """Handle modals efficiently"""
    try:
        modal_selectors = [
            "//button[contains(@class, 'close')]",
            "//button[contains(@aria-label, 'close')]",
            "//button[contains(@aria-label, 'Close')]",
            "//button[@title='Close']",
            "//button[text()='×']",
            "//button[text()='✕']",
            "//button[contains(text(), 'Close')]",
            "//button[contains(text(), 'Cancel')]",
            "//button[contains(text(), 'No')]",
            "//button[contains(text(), 'Later')]",
            "//button[contains(text(), 'Skip')]"
        ]

        for selector in modal_selectors[:3]:  # Try only first 3 for speed
            try:
                elements = driver.find_elements(By.XPATH, selector)
                for element in elements:
                    if element.is_displayed() and element.is_enabled():
                        try:
                            driver.execute_script("arguments[0].click();", element)
                            time.sleep(0.5)
                            return True
                        except:
                            continue
            except:
                continue

        # ESC key fallback
        try:
            driver.find_element(By.TAG_NAME, "body").send_keys(Keys.ESCAPE)
            time.sleep(0.5)
        except:
            pass

        return False
    except:
        return False

def extract_sku_from_pdp_url(url):
    """Extract SKU from PDP URL"""
    match = re.search(r'/pdp/(\d+)', url)
    if match:
        return match.group(1)
    return None

def cleanup_all_checkpoints():
    """Clean up all checkpoint files after successful completion"""
    try:
        import shutil
        
        # List of checkpoint files to clean
        checkpoint_files = [
            os.path.join(CHECKPOINT_DIR, CANCER_PROGRESS_FILE),
            os.path.join(CHECKPOINT_DIR, SITEMAP_PROGRESS_FILE),
            os.path.join(CHECKPOINT_DIR, "progress.json"),
            SITEMAP_IMAGE_INDEX_FILE
        ]
        
        # Remove individual files
        for file_path in checkpoint_files:
            if os.path.exists(file_path):
                os.remove(file_path)
                print(f"🗑️ Removed {file_path}")
        
        # Remove image chunks directory
        if os.path.exists(SITEMAP_IMAGE_PICKLE_DIR):
            shutil.rmtree(SITEMAP_IMAGE_PICKLE_DIR)
            print(f"🗑️ Removed {SITEMAP_IMAGE_PICKLE_DIR}")
        
        # Remove checkpoint directory if empty
        if os.path.exists(CHECKPOINT_DIR) and not os.listdir(CHECKPOINT_DIR):
            os.rmdir(CHECKPOINT_DIR)
            print("🗑️ Removed empty checkpoint directory")
            
        print("✅ All checkpoints cleaned - next run will start fresh")
        
    except Exception as e:
        print(f"⚠️ Error during checkpoint cleanup: {e}")


# ===========================================
# CHECKPOINT FUNCTIONS
# ===========================================

def create_checkpoint_dir():
    """Create checkpoint directory if it doesn't exist"""
    if not os.path.exists(CHECKPOINT_DIR):
        os.makedirs(CHECKPOINT_DIR)
    return CHECKPOINT_DIR

def save_cancer_progress(progress_data):
    """Save cancer treatment progress"""
    try:
        create_checkpoint_dir()
        progress_path = os.path.join(CHECKPOINT_DIR, CANCER_PROGRESS_FILE)
        with open(progress_path, 'w') as f:
            json.dump(progress_data, f, indent=2)
    except Exception as e:
        print(f"⚠️ Failed to save cancer progress: {e}")

def load_cancer_progress():
    """Load cancer treatment progress"""
    try:
        progress_path = os.path.join(CHECKPOINT_DIR, CANCER_PROGRESS_FILE)
        if os.path.exists(progress_path):
            with open(progress_path, 'r') as f:
                progress = json.load(f)
            print(f"📂 Cancer progress loaded")
            return progress
    except Exception as e:
        print(f"⚠️ Failed to load cancer progress: {e}")
    return None

def save_sitemap_progress(progress_data):
    """Save sitemap progress"""
    try:
        create_checkpoint_dir()
        progress_path = os.path.join(CHECKPOINT_DIR, SITEMAP_PROGRESS_FILE)
        with open(progress_path, 'w') as f:
            json.dump(progress_data, f, indent=2)
    except Exception as e:
        print(f"⚠️ Failed to save sitemap progress: {e}")

def load_sitemap_progress():
    """Load sitemap progress"""
    try:
        progress_path = os.path.join(CHECKPOINT_DIR, SITEMAP_PROGRESS_FILE)
        if os.path.exists(progress_path):
            with open(progress_path, 'r') as f:
                progress = json.load(f)
            print(f"📂 Sitemap progress loaded")
            return progress
    except Exception as e:
        print(f"⚠️ Failed to load sitemap progress: {e}")
    return None

def is_processing_complete(mode):
    """Check if processing mode is complete"""
    if mode == "cancer":
        progress = load_cancer_progress()
        return progress and progress.get('completed', False)
    elif mode == "sitemap":
        progress = load_sitemap_progress()
        return progress and progress.get('completed', False)
    return False

# ===========================================
# ASYNC API FUNCTIONS
# ===========================================

async def get_single_product_api_data_async(client: AsyncAPIClient, sku: str, category_id: str, pharmacyname: str) -> Optional[Dict]:
    """Async single product API call - using requests for now to maintain compatibility"""
    try:
        api_url = f"{API_URL}?skus={sku}&language=en&region=SA&category_id={category_id}"
        
        # Use your original working requests method instead of aiohttp for API calls
        response = requests.get(api_url, headers={
            "User-Agent": random.choice(USER_AGENTS),
            "Accept": "application/json",
        }, proxies=u.web_share_proxy(), timeout=15)
        
        response.raise_for_status()
        data = response.json()
        
        if data and isinstance(data, list) and len(data) > 0:
            return data[0]
        elif data and isinstance(data, dict):
            return data
        else:
            return None
            
    except Exception as e:
        print(f"    ❌ API Error for SKU {sku}: {e}")
        #errorInsert(f"API_SINGLE_PRODUCT_{sku}", type(e).__name__, str(e), 0, pharmacyname)
        return None

async def get_multiple_products_async(client: AsyncAPIClient, skus: List[str], pharmacyname: str) -> List[Dict]:
    """Get multiple products using your original working method with rate limiting"""
    if not skus:
        return []
        
    print(f"🚀 Fetching {len(skus)} products with rate limiting...")
    
    products = []
    failed_count = 0
    
    for i, sku in enumerate(skus):
        try:
            # Add rate limiting between requests
            if i > 0:
                await asyncio.sleep(API_RATE_LIMIT + random.uniform(0.1, 0.3))
            
            # Use the working method
            product = await get_single_product_api_data_async(client, sku, "", pharmacyname)
            
            if product:
                products.append(product)
            else:
                failed_count += 1
                
            # Progress indicator
            if (i + 1) % 10 == 0:
                print(f"    📊 Progress: {i + 1}/{len(skus)} products")
                
        except Exception as e:
            failed_count += 1
            print(f"    ❌ SKU {sku} failed: {e}")
    
    success_rate = (len(products) / len(skus)) * 100 if skus else 0
    print(f"✅ API Success: {len(products)}/{len(skus)} products ({success_rate:.1f}%)")
    
    if failed_count > 0:
        print(f"⚠️ {failed_count} API calls failed")
    
    return products

# ===========================================
# OPTIMIZED SITEMAP FUNCTIONS
# ===========================================

async def fetch_sitemap_index_async():
    """Fetch sitemap index asynchronously"""
    try:
        print(f"🌐 Fetching sitemap index: {SITEMAP_INDEX_URL}")
        
        headers = {
            "User-Agent": random.choice(USER_AGENTS),
            "Accept": "application/xml,text/xml,*/*",
            "Accept-Language": "en-US,en;q=0.9",
        }
        
        async with aiohttp.ClientSession(headers=headers) as session:
            async with session.get(SITEMAP_INDEX_URL, timeout=aiohttp.ClientTimeout(total=20)) as response:
                if response.status != 200:
                    print(f"❌ HTTP {response.status}")
                    return []
                
                content = await response.read()
                print("✅ Sitemap index fetched successfully")
        
        sitemap_urls = []
        
        # Try lxml first
        if LXML_AVAILABLE:
            try:
                xml_data = BytesIO(content)
                for event, elem in lxml_etree.iterparse(xml_data, events=("end",), tag="{http://www.sitemaps.org/schemas/sitemap/0.9}loc", recover=True):
                    if elem.text and 'sitemap' in elem.text.lower():
                        sitemap_urls.append(elem.text)
                    elem.clear()
                    while elem.getprevious() is not None:
                        del elem.getparent()[0]
                
                if sitemap_urls:
                    print(f"✅ lxml found {len(sitemap_urls)} sitemap URLs")
                    return sitemap_urls
            except Exception as e:
                print(f"❌ lxml parsing failed: {e}")
        
        # Fallback to regex
        try:
            content_text = content.decode('utf-8')
            patterns = [
                r'<loc[^>]*>(https?://[^<]*sitemap[^<]*\.xml)</loc>',
                r'<loc>(https?://[^<]*sitemap[^<]*\.xml)</loc>',
            ]
            
            all_matches = set()
            for pattern in patterns:
                matches = re.findall(pattern, content_text, re.IGNORECASE)
                for match in matches:
                    if 'xml' in match.lower():
                        all_matches.add(match)
            
            sitemap_urls = list(all_matches)
            print(f"✅ Regex found {len(sitemap_urls)} sitemap URLs")
            return sitemap_urls
            
        except Exception as e:
            print(f"❌ Regex parsing failed: {e}")
            return []
    
    except Exception as e:
        print(f"❌ Failed to fetch sitemap index: {e}")
        return []

async def parse_sitemap_urls_async(session: aiohttp.ClientSession, sitemap_url: str) -> List[str]:
    """Parse sitemap URLs asynchronously - PDP URLs only"""
    try:
        print(f"📄 Parsing sitemap: {sitemap_url.split('/')[-1]}")
        
        async with session.get(sitemap_url, timeout=aiohttp.ClientTimeout(total=45)) as response:
            if response.status != 200:
                print(f"❌ HTTP {response.status} for {sitemap_url}")
                return []
            
            content = await response.read()
            content_length = len(content)
            print(f"📊 Size: {content_length / (1024*1024):.1f} MB")
        
        urls = []
        
        # Use lxml for better performance
        if LXML_AVAILABLE and content_length > 512 * 1024:  # 512KB+
            try:
                xml_data = BytesIO(content)
                url_count = 0
                
                for event, elem in lxml_etree.iterparse(xml_data, events=("end",), recover=True):
                    if elem.tag and 'loc' in elem.tag and elem.text:
                        url = elem.text.strip()
                        if url and url.startswith('http') and '/pdp/' in url:  # Filter PDP only
                            urls.append(url)
                            url_count += 1
                            
                            if url_count % 5000 == 0:
                                print(f"  📊 Processed {url_count} PDP URLs...")
                    
                    elem.clear()
                    while elem.getprevious() is not None:
                        del elem.getparent()[0]
                
                print(f"✅ lxml found {len(urls)} PDP URLs")
                return urls
                
            except Exception as e:
                print(f"❌ lxml parsing failed: {e}")
        
        # Fallback to standard parsing
        try:
            root = ET.fromstring(content)
            for url_elem in root.findall('.//{http://www.sitemaps.org/schemas/sitemap/0.9}loc'):
                if url_elem.text and '/pdp/' in url_elem.text:  # Filter PDP only
                    urls.append(url_elem.text.strip())
            
            # Try without namespace
            if not urls:
                for url_elem in root.findall('.//loc'):
                    if url_elem.text and '/pdp/' in url_elem.text:  # Filter PDP only
                        urls.append(url_elem.text.strip())
            
            print(f"✅ Standard parsing found {len(urls)} PDP URLs")
            return urls
            
        except ET.ParseError:
            # Regex fallback
            content_text = content.decode('utf-8')
            url_pattern = r'<loc[^>]*>(https?://[^<]+/pdp/[^<]+)</loc>'  # PDP only regex
            matches = re.findall(url_pattern, content_text, re.IGNORECASE)
            urls = [url.strip() for url in matches if url.strip()]
            print(f"✅ Regex found {len(urls)} PDP URLs")
            return urls
    
    except Exception as e:
        print(f"❌ Error parsing {sitemap_url}: {e}")
        return []

# ===========================================
# OPTIMIZED BULK SAVE FUNCTION
# ===========================================

def save_bulk_operations_optimized(bulk_operations, collection, pharmacyname, country, processed_urls):
    """Optimized bulk operations save"""
    if not bulk_operations:
        return 0

    try:
        print(f"💾 Saving {len(bulk_operations)} operations...")
        
        # Quick duplicate check
        unique_urls = set()
        duplicate_count = 0
        
        for operation in bulk_operations:
            if hasattr(operation, '_filter') and 'URL' in operation._filter:
                url = operation._filter['URL']
                if url in unique_urls:
                    duplicate_count += 1
                else:
                    unique_urls.add(url)
        
        if duplicate_count > 0:
            print(f"⚠️ {duplicate_count} duplicate URLs in batch")
        
        # Database operation
        with insert_lock:
            result = collection.bulk_write(bulk_operations, ordered=False)
            saved_count = result.modified_count + result.upserted_count
            
            print(f"✅ Database operation completed!")
            print(f"  📊 Operations sent: {len(bulk_operations)}")
            print(f"  📊 Items saved: {saved_count}")
            print(f"  📊 Modified: {result.modified_count}")
            print(f"  📊 Upserted: {result.upserted_count}")
            
            if len(bulk_operations) != saved_count:
                discrepancy = len(bulk_operations) - saved_count
                print(f"⚠️ Discrepancy: {discrepancy} operations not saved (likely duplicates)")
            
            # Track URLs
            for url in unique_urls:
                processed_urls.add(url)
            
            # Update counters
            for _ in range(result.modified_count):
                u.itemCount(pharmacyname, country, "update")
            for _ in range(result.upserted_count):
                u.itemCount(pharmacyname, country, "insert")
            
            return saved_count

    except Exception as e:
        print(f"❌ Database save error: {e}")
        #errorInsert("BULK_SAVE_ERROR", type(e).__name__, str(e), 0, pharmacyname)
        return 0

# ===========================================
# OPTIMIZED PROCESSING FUNCTIONS
# ===========================================

async def process_sitemap_pdp_urls_async(pdp_urls: List[str], pharmacyname: str, conversionRate: float, 
                                       countries: List[str], pharmacyStoreId: str, originalPriceCurrency: str,
                                       processed_urls: set, progress_data: dict, image_manager: SitemapImageManager,
                                       fetch_descriptions: bool = True):
    """Async processing of PDP URLs from sitemap"""
    
    db = database()
    collection = db['pharmacies']
    country = "Saudi Arabia"
    
    bulk_operations = []
    processed_count = 0
    total_saved_to_db = 0
    processed_skus = set()
    
    # Resume from checkpoint
    start_index = progress_data.get('pdp_processed', 0)
    print(f"📂 Resuming from index {start_index}")
    
    # Process URLs in batches for async API calls
    batch_size = 30  # Optimized batch size for async processing
    
    async with AsyncAPIClient() as api_client:
        for batch_start in range(start_index, len(pdp_urls), batch_size):
            batch_end = min(batch_start + batch_size, len(pdp_urls))
            batch_urls = pdp_urls[batch_start:batch_end]
            
            print(f"\n🔄 Processing batch {batch_start//batch_size + 1}: URLs {batch_start+1}-{batch_end}")
            
            # Extract SKUs and filter duplicates
            batch_skus = []
            batch_url_sku_map = {}
            
            for url in batch_urls:
                if url in processed_urls:
                    continue
                    
                sku = extract_sku_from_pdp_url(url)
                if not sku or sku in processed_skus:
                    continue
                
                batch_skus.append(sku)
                batch_url_sku_map[sku] = url
                processed_skus.add(sku)
            
            if not batch_skus:
                print("  ⚠️ No new SKUs in batch, skipping")
                continue
            
            print(f"  🚀 Fetching {len(batch_skus)} products asynchronously...")
            
            # Get all products for this batch asynchronously
            products = await get_multiple_products_async(api_client, batch_skus, pharmacyname)
            
            # Process each product
            for product in products:
                try:
                    if not product:
                        continue
                    
                    # Find URL for this product by matching item_link or SKU
                    url = None
                    sku = None
                    
                    # Method 1: Use item_link from product
                    item_link = product.get('item_link', '')
                    if item_link:
                        # Ensure item_link starts with single slash
                        if not item_link.startswith('/'):
                            item_link = '/' + item_link
                        elif item_link.startswith('//'):
                            item_link = item_link[1:]  # Remove one slash from double slash
                        
                        url = BASE_URL + item_link
                        #Ensure '/en-sa/' is in the URL for sitemap products
                        if '/en-sa/' not in url:
                            url = url.replace(BASE_URL, BASE_URL + '/en-sa/')
                        # Clean any double slashes
                        url = clean_url(url)
                        sku = extract_sku_from_pdp_url(url)
                    
                    # Method 2: Find by matching product data with our batch
                    if not url or not sku:
                        # Try to match by any identifiable data
                        product_name = product.get('item_name', '').lower()
                        for batch_sku, batch_url in batch_url_sku_map.items():
                            if batch_sku in str(product) or any(batch_sku in str(v) for v in product.values() if isinstance(v, str)):
                                sku = batch_sku
                                url = batch_url
                                #Ensure '/en-sa/' is in the URL for sitemap products
                                if '/en-sa/' not in url:
                                    url = url.replace(BASE_URL, BASE_URL + '/en-sa/')
                                # Clean any double slashes
                                url = clean_url(url)
                                break
                    
                    if not url or not sku:
                        continue
                    
                    # Skip if already processed
                    if url in processed_urls:
                        continue
                    
                    # Extract product data
                    name = product.get('item_name', '')
                    brand = html.unescape(product.get('item_brand', ''))
                    
                    # Get images from sitemap manager
                    api_image = product.get('item_image_link', '')
                    images = image_manager.get_product_images_from_sitemap(sku, api_image)
                    
                    # Category mapping
                    category_fields = [
                        product.get('item_category', ''),
                        product.get('item_category2', ''),
                        product.get('item_category3', ''),
                        product.get('item_category4', ''),
                        product.get('item_category5', '')
                    ]
                    category_mapped = ', '.join([cat for cat in category_fields if cat])
                    
                    # Speciality mapping
                    speciality = []
                    if product.get('imf_class'):
                        speciality.append(product.get('imf_class'))
                    if product.get('query_category', {}).get('name'):
                        speciality.append(product.get('query_category', {}).get('name'))
                    if product.get('imf_department'):
                        speciality.append(product.get('imf_department'))
                    if not speciality:
                        speciality = ["Sitemap Product"]
                    
                    # Price calculation
                    originalPrice = float(product.get('price', 0))
                    shelf_price = float(product.get('shelf_price', 0))
                    price = str("{:.2f}".format(originalPrice * conversionRate))
                    
                    cutPrice = None
                    if shelf_price > 0:
                        cutPrice = str("{:.2f}".format(shelf_price * conversionRate))
                    
                    # Ingredients
                    ingredients = []
                    if product.get('item_ingredients'):
                        ingredients = [product.get('item_ingredients')]
                    
                    # Description (conditional)
                    description = ""
                    if fetch_descriptions and DESCRIPTION_FETCHER_AVAILABLE:
                        try:
                            description = get_product_description(url, pharmacyname)
                        except Exception as e:
                            print(f"    ⚠️ Description fetch failed for {sku}: {e}")
                    
                    print(f"    ✅ {name[:40]}... - {originalPrice} SAR - SKU: {sku}")
                    
                    # Create bulk operation
                    u.nahdionlineBulkInsert(bulk_operations,
                                 _pharmacyname=pharmacyname,
                                 _url=clean_url(url),
                                 _pharmacyStoreId=pharmacyStoreId,
                                 _category=category_mapped,
                                 _product=name,
                                 _price=price,
                                 _img=images,  # Use all images from sitemap
                                 _ingrads=ingredients,
                                 _cutPrice=cutPrice,
                                 _description=description,
                                 _presentation="",
                                 _marca=brand,
                                 _originalPrice=originalPrice,
                                 _originalPriceCurrency=originalPriceCurrency,
                                 _country=countries,
                                 _speciality=speciality,
                                 _conversionRate=conversionRate)
                    
                    processed_count += 1
                    processed_urls.add(url)
                    
                    # Save batch if needed
                    if len(bulk_operations) >= SMALL_BATCH_SIZE:
                        saved_count = save_bulk_operations_optimized(
                            bulk_operations, collection, pharmacyname, country, processed_urls)
                        total_saved_to_db += saved_count
                        bulk_operations = []
                        print(f"    💾 Batch saved: {saved_count} items")
                    
                except Exception as e:
                    print(f"    ❌ Error processing product: {e}")
                    continue
            
            # Update progress every batch
            progress_data['pdp_processed'] = batch_end
            progress_data['total_processed'] = processed_count
            save_sitemap_progress(progress_data)
            
            # Memory cleanup
            if batch_start % 5 == 0:
                gc.collect()
    
    # Save remaining operations
    if bulk_operations:
        saved_count = save_bulk_operations_optimized(
            bulk_operations, collection, pharmacyname, country, processed_urls)
        total_saved_to_db += saved_count
        print(f"💾 Final batch saved: {saved_count} items")
    
    # Update final progress
    progress_data['pdp_processed'] = len(pdp_urls)
    progress_data['pdp_completed'] = True
    progress_data['total_processed'] = processed_count
    save_sitemap_progress(progress_data)
    
    print(f"✅ Async PDP processing completed: {processed_count} products processed")
    print(f"💾 Total saved to database: {total_saved_to_db}")
    return processed_count

async def process_sitemap_products_async(pharmacyname: str, conversionRate: float, countries: List[str], 
                                       pharmacyStoreId: str, originalPriceCurrency: str, collection,
                                       processed_urls: set, fetch_descriptions: bool = True):
    """Async sitemap processing with integrated image management"""
    
    # Load progress
    progress = load_sitemap_progress() or {
        'sitemap_urls_fetched': False,
        'images_extracted': False,
        'pdp_urls': [],
        'pdp_completed': False,
        'total_processed': 0
    }
    
    total_processed = 0
    image_manager = SitemapImageManager()
    
    # Step 1: Get sitemap URLs and extract images
    if not progress.get('sitemap_urls_fetched', False):
        print("📋 Fetching sitemap URLs...")
        sitemap_urls = await fetch_sitemap_index_async()
        if not sitemap_urls:
            print("❌ No sitemap URLs found")
            return 0
        
        print(f"✅ Found {len(sitemap_urls)} sitemap files")
        
        # Extract images from sitemaps first
        print("📸 Extracting images from sitemaps...")
        images_extracted = await image_manager.extract_images_from_sitemaps_async(sitemap_urls)
        
        if not images_extracted:
            print("⚠️ Image extraction failed, continuing without sitemap images")
        
        # Get PDP URLs
        print("📄 Extracting PDP URLs from sitemaps...")
        pdp_urls = []
        
        headers = {
            "User-Agent": random.choice(USER_AGENTS),
            "Accept": "application/xml,text/xml,*/*",
        }
        
        async with aiohttp.ClientSession(headers=headers) as session:
            # Process sitemaps concurrently but with rate limiting
            semaphore = asyncio.Semaphore(3)  # Max 3 concurrent sitemap downloads
            
            async def process_sitemap_with_limit(sitemap_url):
                async with semaphore:
                    urls = await parse_sitemap_urls_async(session, sitemap_url)
                    await asyncio.sleep(1)  # Rate limiting
                    return urls
            
            tasks = [process_sitemap_with_limit(url) for url in sitemap_urls]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            for result in results:
                if isinstance(result, list):
                    pdp_urls.extend(result)
                elif isinstance(result, Exception):
                    print(f"❌ Sitemap processing error: {result}")
        
        # Deduplicate by SKU
        unique_pdp_urls = []
        seen_skus = set()
        
        for url in pdp_urls:
            sku = extract_sku_from_pdp_url(url)
            if sku and sku not in seen_skus:
                seen_skus.add(sku)
                unique_pdp_urls.append(url)
        
        print(f"📊 Found {len(unique_pdp_urls)} unique PDP URLs (removed {len(pdp_urls) - len(unique_pdp_urls)} duplicates)")
        
        # Save progress
        progress.update({
            'sitemap_urls_fetched': True,
            'images_extracted': images_extracted,
            'pdp_urls': unique_pdp_urls
        })
        save_sitemap_progress(progress)
    else:
        unique_pdp_urls = progress.get('pdp_urls', [])
        print(f"📂 Loaded {len(unique_pdp_urls)} PDP URLs from cache")
    
    # Step 2: Process PDP URLs asynchronously
    if not progress.get('pdp_completed', False) and unique_pdp_urls:
        print(f"📦 Processing {len(unique_pdp_urls)} PDP URLs asynchronously...")
        total_processed = await process_sitemap_pdp_urls_async(
            unique_pdp_urls, pharmacyname, conversionRate, countries,
            pharmacyStoreId, originalPriceCurrency, processed_urls, progress,
            image_manager, fetch_descriptions
        )
    
    return total_processed

# ===========================================
# CANCER TREATMENT FUNCTIONS (OPTIMIZED)
# ===========================================

def get_ingredients(pharmacyname):
    """Get cancer treatment ingredients (optimized version)"""
    driver = None
    try:
        options = get_chrome_options()
        driver = webdriver.Chrome(options=options)
        driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")

        ingredients = []

        print(f"🌐 Loading cancer treatment page: {CATEGORY_URL}")
        driver.get(CATEGORY_URL)
        WebDriverWait(driver, 20).until(EC.presence_of_element_located((By.TAG_NAME, "body")))
        time.sleep(5)

        handle_modals(driver)

        # Click ingredients filter button
        print("🔍 Looking for Ingredients filter...")
        ingredients_expanded = False
        button_selectors = [
            "//button[.//span[text()='Ingredients']]",
            "//button[contains(@class, 'flex') and .//span[contains(text(), 'Ingredients')]]",
            "//div[contains(@class, 'filter')]//button[.//span[text()='Ingredients']]",
            "//span[text()='Ingredients']/parent::button",
        ]

        for i, selector in enumerate(button_selectors, 1):
            try:
                handle_modals(driver)
                button = WebDriverWait(driver, 5).until(EC.element_to_be_clickable((By.XPATH, selector)))
                driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", button)
                time.sleep(1)
                
                try:
                    button.click()
                    print(f"  ✅ Ingredients button clicked (selector {i})")
                except:
                    driver.execute_script("arguments[0].click();", button)
                    print(f"  ✅ Ingredients button clicked with JS (selector {i})")
                
                time.sleep(3)
                handle_modals(driver)
                ingredients_expanded = True
                break
            except Exception as e:
                print(f"  ❌ Selector {i} failed: {e}")
                continue

        # Look for "Show All" button
        show_all_selectors = [
            "//button[contains(text(), 'Show All')]",
            "//button[.//span[contains(text(), 'Show All')]]",
            "//button[contains(text(), 'View More')]",
        ]

        for selector in show_all_selectors:
            try:
                handle_modals(driver)
                show_all_btn = WebDriverWait(driver, 3).until(EC.element_to_be_clickable((By.XPATH, selector)))
                driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", show_all_btn)
                time.sleep(1)
                
                try:
                    show_all_btn.click()
                    print(f"  ✅ Show All button clicked")
                except:
                    driver.execute_script("arguments[0].click();", show_all_btn)
                    print(f"  ✅ Show All button clicked with JS")
                
                time.sleep(3)
                handle_modals(driver)
                break
            except:
                continue

        # Scroll to load ingredients (simplified)
        try:
            print("🔄 Loading all ingredients...")
            container_selectors = [
                "div.max-h-\\[22em\\].overflow-y-auto",
                "div[class*='overflow-y-auto']",
                "div[class*='max-h-']",
            ]

            scrollable_container = None
            for selector in container_selectors:
                try:
                    scrollable_container = driver.find_element(By.CSS_SELECTOR, selector)
                    print(f"✅ Found scrollable container: {selector}")
                    break
                except:
                    continue

            if scrollable_container:
                # Simplified scrolling - just scroll to bottom a few times
                for _ in range(10):
                    driver.execute_script("arguments[0].scrollTop = arguments[0].scrollHeight;", scrollable_container)
                    time.sleep(1)
                
                driver.execute_script("arguments[0].scrollTop = 0;", scrollable_container)
                time.sleep(2)

        except Exception as e:
            print(f"❌ Scrolling error: {e}")

        handle_modals(driver)

        # Extract ingredients
        print("🔍 Extracting ingredients...")
        labels = driver.find_elements(By.XPATH, "//label[starts-with(@for, 'Ingredients')]")
        print(f"  Found {len(labels)} ingredient labels")

        for i, label in enumerate(labels, 1):
            try:
                ingredient_name = ""
                count = "0"

                # Extract name
                spans = label.find_elements(By.TAG_NAME, "span")
                for span in spans:
                    text = span.text.strip()
                    if text and not re.match(r'^\(\d+\)$', text) and len(text) > 2:
                        ingredient_name = text
                        break

                # Extract count
                try:
                    count_span = label.find_element(By.XPATH, ".//span[contains(@class, 'text-custom-sm')]")
                    count_text = count_span.text.strip()
                    count_match = re.search(r'\((\d+)\)', count_text)
                    if count_match:
                        count = count_match.group(1)
                except:
                    pass

                if ingredient_name:
                    filter_url = f"{CATEGORY_URL}?refinementList%5Bingredient%5D%5B0%5D={ingredient_name.replace(' ', '%20')}"
                    if not any(ing['name'] == ingredient_name for ing in ingredients):
                        ingredients.append({
                            'name': ingredient_name,
                            'count': count,
                            'filter_url': filter_url
                        })
                        print(f"  {len(ingredients)}. {ingredient_name} ({count})")

            except Exception as e:
                print(f"  ❌ Error processing label {i}: {e}")
                continue

        # Add fallback ingredients if not enough found
        if len(ingredients) < 25:
            print(f"⚠️ Found {len(ingredients)}/28 ingredients, adding fallbacks...")
            fallback_ingredients = [
                "Imatinib Mesilate", "Lenalidomide", "Palbociclib", "Ruxolitinib", "Ramucirumab",
                "crizotinib", "nilotinib", "zoledronic acid", "Acalabrutinib Maleate", "Anastrazole",
                "Goserelin", "Granisetron", "Letrozole", "Oseltamivir", "Pembrolizumab",
                "Ribociclib", "Sorafenib", "abemaciclib", "abiraterone acetate", "canakinumab",
                "enzalutamide", "exemestano", "ibrutinib", "olaparib", "osimertinib",
                "pazopanib", "sunitinib", "trastuzumab"
            ]

            existing_names = [ing['name'].lower() for ing in ingredients]
            for ingredient in fallback_ingredients:
                if ingredient.lower() not in existing_names and len(ingredients) < 28:
                    filter_url = f"{CATEGORY_URL}?refinementList%5Bingredient%5D%5B0%5D={ingredient.replace(' ', '%20')}"
                    ingredients.append({'name': ingredient, 'count': '0', 'filter_url': filter_url})
                    print(f"  Added fallback: {ingredient}")

    except Exception as e:
        exception_type, exception_object, exception_traceback = sys.exc_info()
        line_number = exception_traceback.tb_lineno
        print(f"❌ Error in get_ingredients: {e}")
        #errorInsert(CATEGORY_URL, exception_type, exception_object, line_number, pharmacyname)

    finally:
        if driver:
            try:
                driver.quit()
            except:
                pass
        gc.collect()

    print(f"✅ Found {len(ingredients)} cancer treatment ingredients")
    return ingredients

def get_products_for_ingredient(ingredient_data, pharmacyname):
    """Get products for ingredient (simplified version)"""
    driver = None
    product_links = []

    try:
        options = get_chrome_options()
        driver = webdriver.Chrome(options=options)

        ingredient_name = ingredient_data['name']
        filter_url = ingredient_data['filter_url']

        print(f"🔍 Getting products for: {ingredient_name}")

        # Try the filter URL
        handle_modals(driver)
        driver.get(filter_url)

        try:
            WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.TAG_NAME, "body")))
            time.sleep(3)
        except:
            return []

        handle_modals(driver)

        # Get products from multiple pages (simplified)
        for page in range(1, 4):  # Max 3 pages
            if page > 1:
                page_url = f"{filter_url}&page={page}"
                driver.get(page_url)
                time.sleep(2)
                handle_modals(driver)

            soup = BeautifulSoup(driver.page_source, 'html.parser')
            
            # Find product links
            products = soup.find_all("div", class_="js-plp-product")
            if not products:
                products = soup.select('a[href*="/pdp/"]')

            page_links = []
            for product in products:
                try:
                    if hasattr(product, 'find'):
                        a_tag = product.find("a", href=True)
                    else:
                        a_tag = product

                    if a_tag:
                        href = a_tag.get('href') if hasattr(a_tag, 'get') else a_tag['href']
                        if href:
                            full_link = BASE_URL + href if not href.startswith('http') else href
                            # Ensure /en-sa/ is in the URL for cancer treatment products
                            if '/en-sa/' not in full_link:
                                full_link = full_link.replace(BASE_URL, BASE_URL + '/en-sa/')
                            # Clean any double slashes
                            full_link = clean_url(full_link)
                            page_links.append(full_link)
                except:
                    continue

            if not page_links:
                break

            product_links.extend(page_links)
            print(f"  ✅ Found {len(page_links)} products on page {page}")

    except Exception as e:
        print(f"❌ Error getting products for {ingredient_name}: {e}")

    finally:
        if driver:
            try:
                driver.execute_script("window.localStorage.clear();")
                driver.execute_script("window.sessionStorage.clear();")
                driver.delete_all_cookies()
                driver.quit()
            except:
                pass
        gc.collect()
        time.sleep(1)

    # Remove duplicates
    product_links = list(set(product_links))
    print(f"✅ Total products for {ingredient_name}: {len(product_links)}")
    return product_links

# ===========================================
# UTILITY FUNCTIONS FOR STANDALONE USAGE
# ===========================================

def refresh_sitemap_images():
    """Refresh sitemap image cache (standalone function)"""
    print("🔄 Refreshing sitemap image cache...")
    
    async def refresh_async():
        try:
            # Fetch sitemap URLs
            sitemap_urls = await fetch_sitemap_index_async()
            if not sitemap_urls:
                print("❌ No sitemap URLs found")
                return False
            
            # Extract images
            image_manager = SitemapImageManager()
            success = await image_manager.extract_images_from_sitemaps_async(sitemap_urls)
            
            if success:
                print("✅ Sitemap image cache refreshed successfully")
                return True
            else:
                print("❌ Failed to refresh sitemap image cache")
                return False
                
        except Exception as e:
            print(f"❌ Error refreshing sitemap images: {e}")
            return False
    
    return asyncio.run(refresh_async())

def test_api_connectivity():
    """Test API connectivity and rate limiting"""
    print("🔬 Testing API connectivity...")
    
    async def test_async():
        try:
            async with AsyncAPIClient() as client:
                # Test with a known SKU
                test_sku = "123456789"  # Replace with actual SKU if known
                
                start_time = time.time()
                result = await get_single_product_api_data_async(client, test_sku, "", "test")
                end_time = time.time()
                
                print(f"✅ API call completed in {end_time - start_time:.2f} seconds")
                print(f"📊 Rate limiting: {API_RATE_LIMIT}s between requests")
                print(f"🔄 Max concurrent: {MAX_CONCURRENT_REQUESTS}")
                
                if result:
                    print("✅ API response received")
                else:
                    print("⚠️ No data returned (expected for test SKU)")
                
                return True
                
        except Exception as e:
            print(f"❌ API test failed: {e}")
            return False
    
    return asyncio.run(test_async())

def get_sitemap_stats():
    """Get statistics about cached sitemap data"""
    try:
        image_manager = SitemapImageManager()
        
        if not os.path.exists(SITEMAP_IMAGE_INDEX_FILE):
            print("❌ No sitemap image cache found")
            return None
        
        with open(SITEMAP_IMAGE_INDEX_FILE, 'rb') as f:
            chunk_index = pickle.load(f)
        
        total_products = len(chunk_index)
        chunk_files = glob.glob(f"{SITEMAP_IMAGE_PICKLE_DIR}/chunk_*.pkl")
        
        print(f"📊 Sitemap Image Cache Statistics:")
        print(f"   📦 Total products with images: {total_products}")
        print(f"   📁 Cache files: {len(chunk_files)}")
        print(f"   💾 Average products per chunk: {total_products // len(chunk_files) if chunk_files else 0}")
        
        # Sample a few products to show image counts
        sample_skus = list(chunk_index.keys())[:5]
        for sku in sample_skus:
            images = image_manager.get_product_images_from_sitemap(sku)
            print(f"   🖼️ SKU {sku}: {len(images)} images")
        
        return {
            'total_products': total_products,
            'chunk_files': len(chunk_files),
            'sample_skus': sample_skus
        }
        
    except Exception as e:
        print(f"❌ Error getting sitemap stats: {e}")
        return None

# ===========================================
# MAIN OPTIMIZED FUNCTION
# ===========================================

def nahdionline(fetch_descriptions=False):
    """Fully optimized async Nahdi scraper"""
    pharmacyname = 'Nahdionline'
    current_time = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    
    print(f"🚀 Starting Optimized Async Nahdi Scraper")
    print(f"📅 Time: {current_time} UTC")
    print(f"🏥 Pharmacy: {pharmacyname}")
    print(f"📝 Description Fetching: {'Enabled' if fetch_descriptions else 'Disabled'}")
    print(f"🔄 Async Processing: Enabled with {MAX_CONCURRENT_REQUESTS} concurrent requests")
    print("="*60)

    try:
        # Setup
        conversionRate = round(float(Saudia_to_Mexico_rate()), 2)
        countries = ['Saudi Arabia']
        db = database()
        
        # Collections
        store_collection = db['pharmacystores']
        data_collection = db['pharmacies']
        country = "Saudi Arabia"
        originalPriceCurrency = "SAR"

        print(f"💱 Conversion Rate: 1 SAR = {conversionRate} MXN")

        # Get/create pharmacy store
        try:
            pharmacyStoreId = store_collection.find_one({u.name: pharmacyname})['_id']
            print(f"📍 Found pharmacy store ID: {pharmacyStoreId}")
        except:
            pharmacyStoreId = store_collection.insert_one({
                u.name: pharmacyname, 
                u.isActive: False, 
                u.country: country, 
                u.scrapperUrl: 'https://scrapper.vooyfarma.com/nahdionline'
            }).inserted_id
            print(f"📍 Created pharmacy store ID: {pharmacyStoreId}")

        # Logging
        log = logsInsert(pharmacyname)
        u.updateScrapperFalse(pharmacyname)

        # Tracking
        total_products_processed = 0
        processed_urls = set()

        # ===========================================
        # FLOW 1: CANCER TREATMENT PROCESSING
        # ===========================================
        cancer_processed = 0
        if not is_processing_complete("cancer"):
            print("\n" + "="*60)
            print("🎯 CANCER TREATMENT PROCESSING")
            print("="*60)
            
            # Load progress
            cancer_progress = load_cancer_progress() or {
                'processed_ingredients': [],
                'processed_urls': [],
                'total_processed': 0,
                'current_ingredient_index': 0,
                'ingredients_extracted': False,
                'cached_ingredients': []
            }
            
            processed_cancer_urls = set(cancer_progress.get('processed_urls', []))
            processed_ingredients = set(cancer_progress.get('processed_ingredients', []))
            cancer_total = cancer_progress.get('total_processed', 0)
            
            if cancer_total > 0:
                print(f"📂 Resuming: {cancer_total} products already processed")
            
            # Get ingredients
            print("📋 Getting cancer treatment ingredients...")
            #Check if ingredients are cached
            if cancer_progress.get('ingredients_extracted', False) and cancer_progress.get('cached_ingredients'):
                ingredients = cancer_progress['cached_ingredients']
                print(f"📂 Using cached ingredients: {len(ingredients)} found")
            else:
                print("🔄 Extracting ingredients from website (first time)...")
                ingredients = get_ingredients(pharmacyname)

                # Cache ingredients for future runs
                cancer_progress['ingredients_extracted'] = True
                cancer_progress['cached_ingredients'] = ingredients
                save_cancer_progress(cancer_progress)
                print(f"💾 Cached {len(ingredients)} ingredients for future runs")
            
            if ingredients:
                print(f"✅ Found {len(ingredients)} cancer treatment ingredients")
                
                # Process ingredients with async API calls
                bulk_operations = []
                
                for i, ingredient_data in enumerate(ingredients, 1):
                    ingredient_name = ingredient_data['name']
                    
                    if ingredient_name in processed_ingredients:
                        print(f"⏭️ Skipping processed ingredient: {ingredient_name}")
                        continue
                    #Restart Chorme every 5 ingredients to prevent memory buildup
                    if i % 5 == 0:
                        print(f"\n🔄 Restarting Chrome to free memory...")
                        time.sleep(1)
                    
                    print(f"\n🔄 Processing ingredient {i}/{len(ingredients)}: {ingredient_name}")
                    
                    # Get product links for this ingredient
                    product_links = get_products_for_ingredient(ingredient_data, pharmacyname)
                    if not product_links:
                        processed_ingredients.add(ingredient_name)
                        print(f"  ❌ No products found for {ingredient_name}")
                        continue
                    
                    # Extract SKUs
                    skus = []
                    sku_url_map = {}
                    for link in product_links:
                        if link in processed_urls or link in processed_cancer_urls:
                            continue
                        sku_match = re.search(r'/pdp/(\d+)', link)
                        if sku_match:
                            sku = sku_match.group(1)
                            skus.append(sku)
                            sku_url_map[sku] = link
                    
                    if not skus:
                        processed_ingredients.add(ingredient_name)
                        continue
                    
                    print(f"  📦 Processing {len(skus)} products for {ingredient_name}")
                    
                    # Process products asynchronously
                    async def process_cancer_products():
                        async with AsyncAPIClient() as api_client:
                            products = await get_multiple_products_async(api_client, skus, pharmacyname)
                            return products
                    
                    # Run async processing
                    products = asyncio.run(process_cancer_products())
                    
                    # Process each product
                    for product in products:
                        try:
                            if not product:
                                continue
                            
                            # Find URL for this product
                            item_link = product.get('item_link', '')
                            if item_link:
                                url = BASE_URL + item_link
                                #Ensure /en-sa/ is in the URL for cancer treatment products
                                if '/en-sa/' not in url:
                                    url = url.replace(BASE_URL, BASE_URL + '/en-sa/')
                                # Clean any double slashes
                                url = clean_url(url)
                            else:
                                # Find by SKU matching
                                found_url = None
                                for sku, product_url in sku_url_map.items():
                                    if sku in str(product):
                                        found_url = product_url
                                        break
                                if not found_url:
                                    continue
                                url = found_url
                                #Ensure /en-sa/ is in the URL for cancer treatment products
                                if '/en-sa/' not in url:
                                    url = url.replace(BASE_URL, BASE_URL + '/en-sa/')
                                # Clean any double slashes
                                url = clean_url(url)
                            
                            # Skip if already processed
                            if url in processed_urls or url in processed_cancer_urls:
                                continue
                            
                            # Extract product data
                            name = product.get('item_name', '')
                            brand = html.unescape(product.get('item_brand', ''))
                            sku = extract_sku_from_pdp_url(url) or "unknown"
                            
                            # Use integrated image manager
                            image_manager = SitemapImageManager()
                            api_image = product.get('item_image_link', '')
                            images = image_manager.get_product_images_from_sitemap(sku, api_image)
                            
                            category = product.get('imf_category', 'Cancer Treatments')
                            
                            # Speciality for cancer treatments
                            speciality = ["Cancer Treatments"]
                            if product.get('query_category', {}).get("name"):
                                speciality.append(product.get('query_category', {}).get("name"))
                            if product.get('imf_class'):
                                speciality.append(product.get('imf_class'))
                            
                            # Price calculation
                            originalPrice = float(product.get('price', 0))
                            shelf_price = float(product.get('shelf_price', 0))
                            price = str("{:.2f}".format(originalPrice * conversionRate))
                            
                            cutPrice = None
                            if shelf_price > 0:
                                cutPrice = str("{:.2f}".format(shelf_price * conversionRate))
                            
                            # Ingredients - include the cancer ingredient
                            _ingrads = [ingredient_name]
                            if product.get('item_ingredients'):
                                _ingrads.append(product.get('item_ingredients'))
                            
                            # Description (conditional)
                            description = ""
                            if fetch_descriptions and DESCRIPTION_FETCHER_AVAILABLE:
                                try:
                                    description = get_product_description(url, pharmacyname)
                                except Exception as e:
                                    print(f"    ⚠️ Description fetch failed: {e}")
                            
                            print(f"    ✅ {name[:40]}... - {originalPrice} SAR")
                            
                            # Create bulk operation
                            u.nahdionlineBulkInsert(bulk_operations,
                                         _pharmacyname=pharmacyname,
                                         _url=clean_url(url),
                                         _pharmacyStoreId=pharmacyStoreId,
                                         _category=category,
                                         _product=name,
                                         _price=price,
                                         _img=images,
                                         _ingrads=_ingrads,
                                         _cutPrice=cutPrice,
                                         _description=description,
                                         _presentation="",
                                         _marca=brand,
                                         _originalPrice=originalPrice,
                                         _originalPriceCurrency=originalPriceCurrency,
                                         _country=countries,
                                         _speciality=speciality,
                                         _conversionRate=conversionRate)
                            
                            cancer_total += 1
                            processed_cancer_urls.add(url)
                            processed_urls.add(url)
                            
                            # Save batch if needed
                            if len(bulk_operations) >= SMALL_BATCH_SIZE:
                                saved_count = save_bulk_operations_optimized(
                                    bulk_operations, data_collection, pharmacyname, country, processed_urls)
                                bulk_operations = []
                                print(f"    💾 Cancer batch saved: {saved_count} items")
                        
                        except Exception as e:
                            print(f"    ❌ Error processing cancer product: {e}")
                            continue
                    
                    # Mark ingredient as processed
                    processed_ingredients.add(ingredient_name)
                    
                    # Save progress after each ingredient
                    cancer_progress.update({
                        'processed_ingredients': list(processed_ingredients),
                        'processed_urls': list(processed_cancer_urls),
                        'total_processed': cancer_total,
                        'current_ingredient_index': i
                    })
                    save_cancer_progress(cancer_progress)
                    
                    print(f"  ✅ Completed {ingredient_name}")
                
                # Save remaining cancer operations
                if bulk_operations:
                    saved_count = save_bulk_operations_optimized(
                        bulk_operations, data_collection, pharmacyname, country, processed_urls)
                    print(f"💾 Final cancer batch saved: {saved_count} items")
                
                # Mark cancer processing complete
                cancer_progress.update({
                    'completed': True,
                    'completed_at': datetime.now().isoformat(),
                    'total_processed': cancer_total
                })
                save_cancer_progress(cancer_progress)
                
                cancer_processed = cancer_total
                total_products_processed += cancer_processed
                
                print(f"✅ Cancer treatment processing completed: {cancer_processed} products")
            else:
                print("❌ No cancer treatment ingredients found")
        else:
            print("✅ Cancer treatment processing already completed")

        # ===========================================
        # FLOW 2: ASYNC SITEMAP PROCESSING
        # ===========================================
        sitemap_processed = 0
        if not is_processing_complete("sitemap"):
            print("\n" + "="*60)
            print("🗺️ ASYNC SITEMAP PROCESSING")
            print("="*60)
            
            # Run async sitemap processing
            async def run_sitemap_processing():
                return await process_sitemap_products_async(
                    pharmacyname, conversionRate, countries, pharmacyStoreId,
                    originalPriceCurrency, data_collection, processed_urls, fetch_descriptions
                )
            
            sitemap_processed = asyncio.run(run_sitemap_processing())
            total_products_processed += sitemap_processed
            
            # Mark sitemap processing complete
            sitemap_progress = load_sitemap_progress() or {}
            sitemap_progress.update({
                'completed': True,
                'completed_at': datetime.now().isoformat(),
                'total_processed': sitemap_processed
            })
            save_sitemap_progress(sitemap_progress)
            
            print(f"✅ Sitemap processing completed: {sitemap_processed} products")
        else:
            print("✅ Sitemap processing already completed")

        # ===========================================
        # FINALIZATION & CLEANUP
        # ===========================================
        u.updateIsDeletedTrue(pharmacyname)
        
        print(f"\n🎉 OPTIMIZED ASYNC SCRAPING COMPLETED!")
        print(f"📊 FINAL SUMMARY:")
        print(f"   🎯 Cancer treatment products: {cancer_processed}")
        print(f"   🗺️ Sitemap products: {sitemap_processed}")
        print(f"   📦 Total products processed: {total_products_processed}")
        print(f"   🔍 Total unique URLs tracked: {len(processed_urls)}")
        print(f"   ⚡ Async API calls: Enabled")
        print(f"   🛡️ Anti-detection: Enabled")
        print(f"   📸 Sitemap images: Integrated")

        # Update logs
        if log:
            logUpdate(log, total_products_processed)
        
        if total_products_processed > 0 and pharmacyStoreId:
            LastScrapperTimeUpdate(pharmacyStoreId, store_collection, countries)

        # AUTOMATIC CLEANUP after successful completion
        try:
            print("\n🧹 Cleaning up all checkpoint files...")
            cleanup_all_checkpoints()
        except Exception as e:
            print(f"⚠️ Cleanup warning: {e}")

        return f"Optimized Async Completed - {total_products_processed} products saved (Cancer: {cancer_processed}, Sitemap: {sitemap_processed})"

    except Exception as e:
        exception_type, exception_object, exception_traceback = sys.exc_info()
        line_number = exception_traceback.tb_lineno
        print(f"❌ MAIN SCRAPER ERROR: {e}")
        print(f"Exception type: {exception_type}")
        print(f"Line number: {line_number}")
        #errorInsert("OPTIMIZED_ASYNC_MAIN_SCRAPER_ERROR", exception_type, exception_object, line_number, pharmacyname)
        return f"Optimized async scraper failed: {e}"

# ===========================================
# UTILITY FUNCTIONS FOR STANDALONE USAGE
# ===========================================

def refresh_sitemap_images():
    """Refresh sitemap image cache (standalone function)"""
    print("🔄 Refreshing sitemap image cache...")
    
    async def refresh_async():
        try:
            # Fetch sitemap URLs
            sitemap_urls = await fetch_sitemap_index_async()
            if not sitemap_urls:
                print("❌ No sitemap URLs found")
                return False
            
            # Extract images
            image_manager = SitemapImageManager()
            success = await image_manager.extract_images_from_sitemaps_async(sitemap_urls)
            
            if success:
                print("✅ Sitemap image cache refreshed successfully")
                return True
            else:
                print("❌ Failed to refresh sitemap image cache")
                return False
                
        except Exception as e:
            print(f"❌ Error refreshing sitemap images: {e}")
            return False
    
    return asyncio.run(refresh_async())

def test_api_connectivity():
    """Test API connectivity and rate limiting"""
    print("🔬 Testing API connectivity...")
    
    async def test_async():
        try:
            async with AsyncAPIClient() as client:
                # Test with a known SKU
                test_sku = "123456789"  # Replace with actual SKU if known
                
                start_time = time.time()
                result = await get_single_product_api_data_async(client, test_sku, "", "test")
                end_time = time.time()
                
                print(f"✅ API call completed in {end_time - start_time:.2f} seconds")
                print(f"📊 Rate limiting: {API_RATE_LIMIT}s between requests")
                print(f"🔄 Max concurrent: {MAX_CONCURRENT_REQUESTS}")
                
                if result:
                    print("✅ API response received")
                else:
                    print("⚠️ No data returned (expected for test SKU)")
                
                return True
                
        except Exception as e:
            print(f"❌ API test failed: {e}")
            return False
    
    return asyncio.run(test_async())

def get_sitemap_stats():
    """Get statistics about cached sitemap data"""
    try:
        image_manager = SitemapImageManager()
        
        if not os.path.exists(SITEMAP_IMAGE_INDEX_FILE):
            print("❌ No sitemap image cache found")
            return None
        
        with open(SITEMAP_IMAGE_INDEX_FILE, 'rb') as f:
            chunk_index = pickle.load(f)
        
        total_products = len(chunk_index)
        chunk_files = glob.glob(f"{SITEMAP_IMAGE_PICKLE_DIR}/chunk_*.pkl")
        
        print(f"📊 Sitemap Image Cache Statistics:")
        print(f"   📦 Total products with images: {total_products}")
        print(f"   📁 Cache files: {len(chunk_files)}")
        print(f"   💾 Average products per chunk: {total_products // len(chunk_files) if chunk_files else 0}")
        
        # Sample a few products to show image counts
        sample_skus = list(chunk_index.keys())[:5]
        for sku in sample_skus:
            images = image_manager.get_product_images_from_sitemap(sku)
            print(f"   🖼️ SKU {sku}: {len(images)} images")
        
        return {
            'total_products': total_products,
            'chunk_files': len(chunk_files),
            'sample_skus': sample_skus
        }
        
    except Exception as e:
        print(f"❌ Error getting sitemap stats: {e}")
        return None

# ===========================================
# MAIN EXECUTION
# ===========================================

if __name__ == "__main__":
    """
    Command line interface for the optimized scraper
    """
    import argparse
    
    parser = argparse.ArgumentParser(description="Optimized Async Nahdionline Scraper")
    parser.add_argument("--descriptions", action="store_true", help="Enable description fetching during scraping")
    parser.add_argument("--refresh-images", action="store_true", help="Refresh sitemap image cache only")
    parser.add_argument("--test-api", action="store_true", help="Test API connectivity")
    parser.add_argument("--stats", action="store_true", help="Show sitemap cache statistics")
    parser.add_argument("--cancer-only", action="store_true", help="Process cancer treatments only")
    parser.add_argument("--sitemap-only", action="store_true", help="Process sitemap products only")
    
    args = parser.parse_args()
    
    if args.refresh_images:
        print("🔄 Refreshing sitemap image cache...")
        success = refresh_sitemap_images()
        if success:
            print("✅ Sitemap image cache refreshed successfully")
        else:
            print("❌ Failed to refresh sitemap image cache")
    
    elif args.test_api:
        print("🔬 Testing API connectivity...")
        success = test_api_connectivity()
        if success:
            print("✅ API test completed")
        else:
            print("❌ API test failed")
    
    elif args.stats:
        print("📊 Getting sitemap cache statistics...")
        get_sitemap_stats()
    
    elif args.cancer_only:
        print("🎯 Processing cancer treatments only...")
        # Set completion flags to skip sitemap processing
        sitemap_progress = {'completed': True, 'completed_at': datetime.now().isoformat()}
        save_sitemap_progress(sitemap_progress)
        result = nahdionline(fetch_descriptions=args.descriptions)
        print(f"Result: {result}")
    
    elif args.sitemap_only:
        print("🗺️ Processing sitemap products only...")
        # Set completion flags to skip cancer processing  
        cancer_progress = {'completed': True, 'completed_at': datetime.now().isoformat()}
        save_cancer_progress(cancer_progress)
        result = nahdionline(fetch_descriptions=args.descriptions)
        print(f"Result: {result}")
    
    else:
        print("🚀 Starting full optimized async scraping...")
        result = nahdionline(fetch_descriptions=args.descriptions)
        print(f"Result: {result}")
        
        # Show final statistics
        print("\n📊 Final Statistics:")
        get_sitemap_stats()