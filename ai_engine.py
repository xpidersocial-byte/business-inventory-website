"""
XPIDER AI Engine Module
-----------------------
This module handles integration with Large Language Models (LLMs) via OpenRouter and Google Gemini.
Note: Currently in 'Disabled' mode as per system requirements to prevent unnecessary API costs.
"""

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

def get_ai_response(prompt, context_data=None):
    """
    Main entry point for generating AI text responses.
    Currently returns a static 'Disabled' message.
    """
    return "AI functionality is currently disabled."

def get_quick_insight(item_name, stock, sold):
    """
    Generates a quick business insight for an item.
    Currently returns a static 'Disabled' message.
    """
    return "AI insights are disabled."

def run_full_site_scan(base_url="http://127.0.0.1:5000", cookies=None):
    """
    Orchestrates a full website crawl and diagnostic scan.
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
