# import ssl

# ssl._create_default_https_context = ssl._create_unverified_context
# from pinecone import Pinecone

# pc = Pinecone(api_key="pcsk_6vNZC9_BSAwXcKEzWvsT4LnvANDHxaUcpD7ENiUUQjX6PRPZDqYroAomH9poByvykEm4tP")


# index = pc.Index(host="https://uapalaw-pe84aca.svc.aped-4627-b74a.pinecone.io")
# results = index.search(
#     namespace="income_tax_act_1961", 
#     query={
#         "inputs": {"text": "My CTC is ₹12,00,000 per year. I have HRA of ₹2,40,000, rent paid is ₹20,000/month in Mumbai, and I invest ₹1.5 lakh in Section 80C. Should I choose the old or new tax regime for FY 2024-25?"}, 
#         "top_k": 4
#     },
# )
# print(results)

import requests
import os

# Configuration variables (replace with your actual values)
INDEX_HOST = os.getenv("INDEX_HOST", "uapalaw-pe84aca.svc.aped-4627-b74a.pinecone.io")  # From your error
NAMESPACE = os.getenv("NAMESPACE", "income_tax_act_1961")  # From your error
# PINECONE_API_KEY = os.getenv("PINECONE_API_KEY", "YOUR_API_KEY")  # Replace with your actual API key

# Construct the URL
url = f"https://{INDEX_HOST}/records/namespaces/{NAMESPACE}/search"

# Define headers
headers = {
    "Accept": "application/json",
    "Content-Type": "application/json",
    "Api-Key": "pcsk_6vNZC9_BSAwXcKEzWvsT4LnvANDHxaUcpD7ENiUUQjX6PRPZDqYroAomH9poByvykEm4tP" ,
    "X-Pinecone-API-Version": "unstable"
}

# Define the JSON payload
payload = {
    "query": {
        "inputs": {"text": "My CTC is ₹12,00,000 per year. I have HRA of ₹2,40,000, rent paid is ₹20,000/month in Mumbai, and I invest ₹1.5 lakh in Section 80C. Should I choose the old or new tax regime for FY 2024-25?"},
        "top_k": 4
    },
}

# Make the POST request
try:
    response = requests.post(url, json=payload, headers=headers)
    response.raise_for_status()  # Raise an error for bad status codes
    print(response.json())  # Print the response
except requests.exceptions.SSLError as ssl_err:
    print(f"SSL Error: {ssl_err}")
    # Fallback: Retry with SSL verification disabled (for testing only)
    response = requests.post(url, json=payload, headers=headers, verify=False)
    print(response.json())
except requests.exceptions.RequestException as e:
    print(f"Request failed: {e}")