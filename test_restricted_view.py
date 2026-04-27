import requests
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv(override=True)

# URL of the app
BASE_URL = "http://localhost:5000"

# User credentials
CASHIER_EMAIL = "lyka@xpider.social"
CASHIER_PASSWORD = "password123"

session = requests.Session()

# 1. Login
login_payload = {
    "email": CASHIER_EMAIL,
    "password": CASHIER_PASSWORD
}
response = session.post(f"{BASE_URL}/login", data=login_payload)
print(f"Login Status: {response.status_code}")
print(f"Final URL after login: {response.url}")

# 2. Check /select-branch content
response = session.get(f"{BASE_URL}/select-branch")
html = response.text

print(f"\nVerifying HTML content at /select-branch for {CASHIER_EMAIL}:")

# Count how many forms (branches) are present
branch_count = html.count('form action="/select-branch/set_branch"') 
# Wait, the action URL is {{ url_for('branches.set_branch') }} which is /set-branch
branch_count = html.count('action="/set-branch"')
print(f"Total Branches found in HTML: {branch_count}")

# Check for "Restricted Access"
restricted_count = html.count('Restricted Access')
print(f"Restricted Branches found: {restricted_count}")

# Check for "Deploy Terminal"
deploy_count = html.count('Deploy Terminal')
print(f"Accessible Branches found (Deploy Terminal): {deploy_count}")

if branch_count > 1 and deploy_count == 1:
    print("\nSUCCESS: Global view enabled, but only one branch is accessible.")
else:
    print("\nFAILURE: Logic not correctly reflected in HTML.")
