"""
Crawls payer websites, finds and downloads PDFs, extracts text
"""
import requests
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
import time
from pathlib import Path
from datetime import datetime
import re
import logging

try:
    import PyPDF2
except ImportError:
    PyPDF2 = None

try:
    import pdfplumber
except ImportError:
    pdfplumber = None

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class PayerPDFCrawler:
    def __init__(self, download_folder="downloads/pdfs"):
        self.download_folder = Path(download_folder)
        self.download_folder.mkdir(parents=True, exist_ok=True)
        
        # Selenium setup
        self.options = Options()
        self.options.add_argument('--headless')
        self.options.add_argument('--no-sandbox')
        self.options.add_argument('--disable-dev-shm-usage')
        self.options.add_argument('--disable-gpu')
        
        prefs = {
            "download.default_directory": str(self.download_folder.absolute()),
            "download.prompt_for_download": False,
            "plugins.always_open_pdf_externally": True
        }
        self.options.add_experimental_option("prefs", prefs)
    
    def scrape_payer(self, payer_name, config):
        """
        Scrape all PDFs for a payer
        
        Args:
            payer_name: "Aetna", "United Healthcare", etc.
            config: {
                "urls": ["url1", "url2"],
                "pdf_keywords": ["manual", "claims"],
                "exclude_keywords": ["dental"]
            }
        
        Returns:
            List of PDF document dicts
        """
        logger.info(f"\n{'='*70}")
        logger.info(f"SCRAPING: {payer_name}")
        logger.info(f"{'='*70}")
        
        try:
            service = Service(ChromeDriverManager().install())
            driver = webdriver.Chrome(service=service, options=self.options)
        except Exception as e:
            logger.error(f"Failed to initialize Chrome driver: {e}")
            return []
        
        pdf_documents = []
        
        try:
            for url in config['urls']:
                logger.info(f"\nVisiting: {url}")
                try:
                    driver.get(url)
                    time.sleep(3)
                    
                    # Find PDF links
                    pdf_links = self.find_pdf_links(driver, url)
                    logger.info(f"  Found {len(pdf_links)} PDF links")
                    
                    # Filter relevant PDFs
                    relevant_pdfs = self.filter_relevant_pdfs(
                        pdf_links,
                        config.get('pdf_keywords', []),
                        config.get('exclude_keywords', [])
                    )
                    logger.info(f"  Filtered to {len(relevant_pdfs)} relevant PDFs")
                    
                    # Download and process (limit to 3 per URL to avoid overload)
                    for pdf_info in relevant_pdfs[:3]:
                        try:
                            pdf_doc = self.download_and_extract_pdf(
                                pdf_info['url'],
                                pdf_info['title'],
                                payer_name
                            )
                            if pdf_doc:
                                pdf_documents.append(pdf_doc)
                                logger.info(f"    ✓ {pdf_info['title'][:60]}")
                        except Exception as e:
                            logger.warning(f"    ✗ {pdf_info['title'][:60]} - {e}")
                
                except Exception as e:
                    logger.error(f"  ✗ Error visiting {url}: {e}")
        
        finally:
            driver.quit()
        
        logger.info(f"\n✓ Scraped {len(pdf_documents)} PDFs for {payer_name}")
        return pdf_documents
    
    def find_pdf_links(self, driver, base_url):
        """Find all PDF links on page"""
        pdf_links = []
        links = driver.find_elements(By.TAG_NAME, 'a')
        
        for link in links:
            try:
                href = link.get_attribute('href')
                text = link.text.strip()
                
                if href and (href.lower().endswith('.pdf') or '/pdf/' in href.lower()):
                    # Make absolute URL
                    if not href.startswith('http'):
                        from urllib.parse import urljoin
                        href = urljoin(base_url, href)
                    
                    pdf_links.append({
                        'url': href,
                        'title': text or 'Untitled Document'
                    })
            except:
                continue
        
        return pdf_links
    
    def filter_relevant_pdfs(self, pdf_links, keywords, exclude_keywords):
        """Filter PDFs by keywords"""
        if not keywords:
            return pdf_links
        
        relevant = []
        for pdf in pdf_links:
            title_lower = pdf['title'].lower()
            url_lower = pdf['url'].lower()
            combined = title_lower + ' ' + url_lower
            
            has_keyword = any(kw.lower() in combined for kw in keywords)
            has_exclude = any(ex.lower() in combined for ex in exclude_keywords)
            
            if has_keyword and not has_exclude:
                relevant.append(pdf)
        
        return relevant
    
    def download_and_extract_pdf(self, pdf_url, title, payer_name):
        """Download PDF and extract text"""
        # Create safe filename
        safe_title = re.sub(r'[^\w\s-]', '', title)[:50]
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"{payer_name.replace(' ', '_')}_{safe_title}_{timestamp}.pdf"
        filepath = self.download_folder / filename
        
        # Download
        try:
            response = requests.get(pdf_url, timeout=30, verify=False)
            response.raise_for_status()
        except Exception as e:
            logger.warning(f"Failed to download {pdf_url}: {e}")
            return None
        
        with open(filepath, 'wb') as f:
            f.write(response.content)
        
        # Extract text
        extracted_text = self.extract_text_from_pdf(filepath)
        
        if not extracted_text or len(extracted_text) < 100:
            logger.warning(f"      ⚠ Minimal text extracted from {filename}")
            return None
        
        # Parse sections
        sections = self.parse_pdf_sections(extracted_text)
        
        return {
            'payer': payer_name,
            'title': title,
            'filename': filename,
            'filepath': str(filepath),
            'url': pdf_url,
            'downloaded_at': datetime.now().isoformat(),
            'full_text': extracted_text,
            'sections': sections,
            'page_count': extracted_text.count('\f') + 1
        }
    
    def extract_text_from_pdf(self, filepath):
        """Extract text from PDF"""
        text = ""
        
        # Try pdfplumber first
        if pdfplumber:
            try:
                with pdfplumber.open(filepath) as pdf:
                    for page in pdf.pages:
                        page_text = page.extract_text()
                        if page_text:
                            text += page_text + "\n\n"
                if text.strip():
                    return text.strip()
            except Exception as e:
                logger.debug(f"pdfplumber failed: {e}")
        
        # Fallback to PyPDF2
        if PyPDF2:
            try:
                with open(filepath, 'rb') as f:
                    pdf_reader = PyPDF2.PdfReader(f)
                    for page in pdf_reader.pages:
                        text += page.extract_text() + "\n\n"
            except Exception as e:
                logger.debug(f"PyPDF2 failed: {e}")
        
        return text.strip()
    
    def parse_pdf_sections(self, full_text):
        """Parse PDF into sections"""
        sections = []
        
        # Section header patterns
        patterns = [
            r'(?i)^(timely filing|claim submission|prior authorization|appeals|reimbursement).*$',
            r'(?i)^chapter \d+[:\s]+(.+)$',
            r'(?i)^section \d+\.?\d*[:\s]+(.+)$',
            r'(?i)^\d+\.\s+([A-Z][^.]{5,})$'
        ]
        
        lines = full_text.split('\n')
        current_section = {'title': 'Introduction', 'content': ''}
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
            
            is_header = False
            for pattern in patterns:
                if re.match(pattern, line):
                    if current_section['content']:
                        sections.append(current_section)
                    current_section = {'title': line, 'content': ''}
                    is_header = True
                    break
            
            if not is_header:
                current_section['content'] += line + ' '
        
        if current_section['content']:
            sections.append(current_section)
        
        return sections


# PAYER CONFIGURATIONS - SPECIFIC WEBSITES TO SCRAPE
PAYER_CONFIGS = {
    'Aetna': {
        'urls': [
            'https://www.aetna.com/health-care-professionals/provider-education-manuals.html',
            'https://www.aetna.com/health-care-professionals/claims-payment-reimbursement.html',
        ],
        'pdf_keywords': [
            'provider manual', 'claims', 'timely filing', 'reimbursement',
            'prior authorization', 'appeals', 'billing', 'guidelines', 'manual'
        ],
        'exclude_keywords': ['dental', 'vision', 'pharmacy', 'behavioral']
    },
    'United Healthcare': {
        'urls': [
            'https://www.uhcprovider.com/en/resource-library/manual-policies.html',
            'https://www.uhcprovider.com/en/claims-payments.html',
        ],
        'pdf_keywords': [
            'provider', 'manual', 'claims', 'timely filing', 'authorization',
            'reimbursement', 'appeals', 'billing'
        ],
        'exclude_keywords': ['dental', 'vision', 'pharmacy']
    },
    'Anthem': {
        'urls': [
            'https://www.anthem.com/provider/manual',
            'https://www.anthem.com/provider/claims',
        ],
        'pdf_keywords': [
            'provider manual', 'claims', 'billing', 'authorization',
            'appeals', 'timely filing'
        ],
        'exclude_keywords': ['dental', 'vision']
    }
}
