import requests
import re
from urllib.parse import urljoin, urlparse

class WebsiteScanner:
    def __init__(self, base_url, cookies=None):
        self.base_url = base_url
        self.visited = set()
        self.to_visit = [base_url]
        self.broken_links = []
        self.server_errors = []
        self.vulnerabilities = []
        self.cookies = cookies or {}
        self.scan_log = []

    def log(self, message):
        self.scan_log.append(message)
        print(f"[SCANNER] {message}")

    def is_internal(self, url):
        return urlparse(url).netloc == urlparse(self.base_url).netloc

    def scan_page(self, url):
        if url in self.visited:
            return
        self.visited.add(url)
        
        self.log(f"Scanning: {url}")
        try:
            response = requests.get(url, cookies=self.cookies, timeout=10)
            
            # Check Status
            if response.status_code == 404:
                self.broken_links.append({"url": url, "status": 404})
                self.log(f"Broken Link Found: {url}")
            elif response.status_code >= 500:
                self.server_errors.append({"url": url, "status": response.status_code})
                self.log(f"Server Error Found: {url} ({response.status_code})")

            # Check Security Headers
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

            # Check for exposed sensitive files
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

            # Extract Internal Links
            if "text/html" in response.headers.get("Content-Type", ""):
                links = re.findall(r'href=["\'](.[^"\']+)["\']', response.text)
                for link in links:
                    full_url = urljoin(url, link)
                    # Strip fragments
                    full_url = full_url.split('#')[0]
                    if self.is_internal(full_url) and full_url not in self.visited:
                        if full_url not in self.to_visit:
                            self.to_visit.append(full_url)

        except Exception as e:
            self.log(f"Error scanning {url}: {str(e)}")

    def run_scan(self):
        self.log("Starting full website health & security scan...")
        while self.to_visit and len(self.visited) < 50: # Limit to 50 pages for safety
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
