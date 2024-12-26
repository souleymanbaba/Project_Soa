import base64
import requests
import os
import qrcode
from io import BytesIO
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
import re
from urllib.parse import urlparse
from fastapi.responses import FileResponse
import shutil

load_dotenv()

app = FastAPI()

origins = [
    "https://mounamahfd.github.io/QR-Frontend/",
]

app.add_middleware(
    CORSMiddleware,  
    allow_origins=origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

# GitHub API Configuration
GITHUB_TOKEN = os.getenv("MY_GITHUB_TOKEN")
REPO_OWNER = os.getenv("REPO_OWNER") 
REPO_NAME = "QR-Backend"  
BRANCH_NAME = "main" 
COMMITTER_NAME = "GitHub Actions"
COMMITTER_EMAIL = "github-actions@github.com"

# GitHub API URL to commit files to repository
GITHUB_API_URL = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/contents"

print(f"REPO_OWNER: {REPO_OWNER}")
print(f"GITHUB_TOKEN: {GITHUB_TOKEN}")


class QRRequest(BaseModel):
    url: str

def is_valid_url(url: str) -> bool:
    parsed_url = urlparse(url)
    return bool(parsed_url.netloc) and bool(parsed_url.scheme) and re.match(r'^[a-zA-Z0-9.-]+$', parsed_url.netloc)

def sanitize_url(url: str) -> str:
    sanitized_url = url.split('//')[-1]
    sanitized_url = re.sub(r'[^a-zA-Z0-9.-]', '_', sanitized_url)
    sanitized_url = sanitized_url.rstrip('/')
    return sanitized_url

def check_if_file_exists(file_name):
    url = f"{GITHUB_API_URL}/{file_name}"
    headers = {"Authorization": f"token {GITHUB_TOKEN}"}
    response = requests.get(url, headers=headers)
    return response.status_code == 200

def upload_to_github(file_name, image_data):
    url = f"{GITHUB_API_URL}/{file_name}"
    headers = {"Authorization": f"token {GITHUB_TOKEN}"}

    commit_data = {
        "message": f"Add QR code for {file_name}",
        "content": image_data,
        "branch": BRANCH_NAME,
    }

    print(f"Uploading file to: {url}") 
    response = requests.put(url, headers=headers, json=commit_data)

    print(f"GitHub API response: {response.status_code} - {response.text}")

    if response.status_code != 200 and response.status_code != 201:
        raise Exception(f"Error uploading file to GitHub: {response.text}")

    return f"https://{REPO_OWNER}.github.io/{REPO_NAME}/{file_name}"

@app.post("/generate-qr/")
async def generate_qr(request: QRRequest):
    print(f"Received URL: {request.url}")

    try:
        if not is_valid_url(request.url):
            raise HTTPException(status_code=400, detail="Invalid URL")

        sanitized_url = sanitize_url(request.url)
        file_name = f"qr_codes/{sanitized_url}.png"
        print(f"Generated file name: {file_name}")

        # Check if the file already exists in the GitHub repository
        if check_if_file_exists(file_name):
            return {"message": "QR code for this URL already exists.", "qr_code_url": f"https://{REPO_OWNER}.github.io/{REPO_NAME}/{file_name}"}

        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=10,
            border=4,
        )
        qr.add_data(request.url)
        qr.make(fit=True)

        img = qr.make_image(fill_color="black", back_color="white")

        img_byte_arr = BytesIO()
        img.save(img_byte_arr, format='PNG')
        img_byte_arr.seek(0)

        # Optionally, save the QR code temporarily to serve it faster (e.g., in a 'static' folder)
        temp_file_path = f"static/{file_name}"
        os.makedirs(os.path.dirname(temp_file_path), exist_ok=True)
        
        with open(temp_file_path, 'wb') as f:
            f.write(img_byte_arr.read())

        # Upload to GitHub asynchronously
        img_base64 = base64.b64encode(img_byte_arr.getvalue()).decode('utf-8')
        github_url = upload_to_github(file_name, img_base64)

        # Serve the file immediately from the local server
        return {"qr_code_url": f"http://localhost:8000/static/{file_name}"}

    except HTTPException as e:
        print(f"HTTP Exception: {e.detail}")
        raise e
    except Exception as e:
        print(f"Unexpected error: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error")

# Serve static files for quicker access (e.g., QR code images)
@app.get("/static/{file_path:path}")
async def serve_static_file(file_path: str):
    file_path = os.path.join("static", file_path)
    if os.path.exists(file_path):
        return FileResponse(file_path)
    raise HTTPException(status_code=404, detail="File not found")
