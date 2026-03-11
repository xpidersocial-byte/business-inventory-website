"""
XPIDER Website Health & Security Scanner
---------------------------------------
A modular crawler designed to identify broken links, server errors, 
missing security headers, and publicly exposed sensitive files.
"""

import requests
import re
from urllib.parse import urljoin, urlparse

class WebsiteScanner:
    """
    Main scanner class for diagnostic crawling and security auditing.
    """
    
    def __init__(self, base_url, cookies=None):
        """
        Initializes the scanner with a base URL and optional authentication.
        
        Args:
            base_url (str): The starting point of the crawl.
            cookies (dict, optional): Session cookies to bypass login screens.
        """
        self.base_url = base_url
        self.visited = set()
        self.to_visit = [base_url]
        self.broken_links = []
        self.server_errors = []
        self.vulnerabilities = []
        self.cookies = cookies or {}
        self.scan_log = []

    def log(self, message):
        """Internal logging utility for scan progress."""
        self.scan_log.append(message)
        print(f"[SCANNER] {message}")

    def is_internal(self, url):
        """Determines if a URL belongs to the target website's domain."""
        return urlparse(url).netloc == urlparse(self.base_url).netloc

    def scan_page(self, url):
        """
        Analyzes a single page for broken links, errors, and security issues.
        
        Args:
            url (str): The specific URL to analyze.
        """
        if url in self.visited:
            return
        self.visited.add(url)
        
        self.log(f"Scanning: {url}")
        try:
            # Perform a GET request to analyze the page
            response = requests.get(url, cookies=self.cookies, timeout=10)
            
            # --- 1. Basic Status Code Checks ---
            if response.status_code == 404:
                self.broken_links.append({"url": url, "status": 404})
                self.log(f"Broken Link Found: {url}")
            elif response.status_code >= 500:
                self.server_errors.append({"url": url, "status": response.status_code})
                self.log(f"Server Error Found: {url} ({response.status_code})")

            # --- 2. Security Header Analysis ---
            headers = response.headers
            missing_headers = []
            if 'Content-Security-Policy' not in headers: missing_headers.append('CSP')
            if 'X-Frame-Options' not in headers: missing_headers.append('X-Frame-Options')
            if 'X-Content-Type-Options' not in headers: missing_headers.append('X-Content-Type-Options')
            
            if missing_headers:
                self.vulnerabilities.append({
                    "url": url,
                    "type": "Missing Security Headers",
                    "details": f"Missing: {', '.join(missing_headers)}"
                })

            # --- 3. Sensitive File Probing ---
            # Attempt to access files that should never be public
            sensitive_paths = ['.env', '.git', 'config.py', 'initial_data.py']
            for path in sensitive_paths:
                check_url = urljoin(self.base_url, path)
                if check_url not in self.visited:
                    s_res = requests.get(check_url, cookies=self.cookies, timeout=5)
                    if s_res.status_code == 200:
                        self.vulnerabilities.append({
                            "url": check_url,
                            "type": "Exposed Sensitive File",
                            "details": f"File {path} is publicly accessible!"
                        })
                    self.visited.add(check_url)

            # --- 4. Link Extraction ---
            # Find and queue internal links for the crawler
            if "text/html" in response.headers.get("Content-Type", ""):
                links = re.findall(r'href=["\'](.[^"\']+)["\']', response.text)
                for link in links:
                    full_url = urljoin(url, link)
                    # Strip fragments (#anchor) to avoid duplicate scans
                    full_url = full_url.split('#')[0]
                    if self.is_internal(full_url) and full_url not in self.visited:
                        if full_url not in self.to_visit:
                            self.to_visit.append(full_url)

        except Exception as e:
            self.log(f"Error scanning {url}: {str(e)}")

    def run_scan(self):
        """
        Starts the iterative crawl process.
        
        Returns:
            dict: Detailed report containing findings and scan logs.
        """
        self.log("Starting full website health & security scan...")
        # Iteratively pop URLs from the queue until empty or limit reached
        while self.to_visit and len(self.visited) < 50: # Safeguard limit
            current_url = self.to_visit.pop(0)
            self.scan_page(current_url)
        
        self.log(f"Scan complete. Visited {len(self.visited)} pages.")
        return {
            "visited_count": len(self.visited),
            "broken_links": self.broken_links,
            "server_errors": self.server_errors,
            "vulnerabilities": self.vulnerabilities,
            "scan_log": self.scan_log
        }
