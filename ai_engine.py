import os
import requests
import json
# import google.generativeai as genai # Disabled
from dotenv import load_dotenv

load_dotenv()

# Configuration
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

# AI is disabled as per user request
DISABLED_MESSAGE = "AI functionality is currently disabled."

def get_ai_response(prompt, context_data=None):
    """
    Returns a disabled message. Original functionality removed to avoid API usage.
    """
    return DISABLED_MESSAGE

def get_quick_insight(item_name, stock, sold):
    """Returns a static disabled message."""
    return "AI insights are disabled."

def run_full_site_scan(base_url="http://127.0.0.1:5000", cookies=None):
    """
    Simulates a crawl WITHOUT AI analysis.
    """
    try:
        from scanner import WebsiteScanner
        scanner = WebsiteScanner(base_url, cookies=cookies)
        scanner.run_scan()
        return {
            "total_pages": len(scanner.visited),
            "broken_links": scanner.broken_links,
            "scan_log": scanner.scan_log,
            "ai_analysis": "AI analysis skipped (Disabled)."
        }
    except Exception as e:
        return {"error": str(e)}
