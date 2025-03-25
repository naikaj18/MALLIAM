from fastapi import FastAPI, HTTPException, Request
from starlette.responses import RedirectResponse, JSONResponse
from google_auth_oauthlib.flow import Flow
from supabase_client import save_user, get_user_credentials
import os
from dotenv import load_dotenv
import jwt
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
import base64
import json
from classifier import classify_emails
import openai

load_dotenv()

app = FastAPI()

# Enable CORS for your frontend
from fastapi.middleware.cors import CORSMiddleware
origins = [
    "http://localhost:3000",
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")
REDIRECT_URI = os.getenv("REDIRECT_URI")
SCOPES = [
    "openid",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/userinfo.profile",
    "https://www.googleapis.com/auth/gmail.readonly"
]

flow = Flow.from_client_config(
    {
        "web": {
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "redirect_uris": [REDIRECT_URI],
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
        }
    },
    scopes=SCOPES,
    redirect_uri=REDIRECT_URI
)

@app.get("/")
def read_root():
    return {"message": "Welcome to Mailliam!"}

@app.get("/auth/login")
def login():
    auth_url, _ = flow.authorization_url(prompt="consent")
    return RedirectResponse(auth_url)

@app.get("/auth/callback")
def auth_callback(request: Request):
    code = request.query_params.get("code")
    if not code:
        raise HTTPException(status_code=400, detail="Authorization code not found")
    try:
        flow.fetch_token(code=code)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Token exchange failed: {str(e)}")
    
    credentials = flow.credentials
    id_token = credentials.id_token
    if isinstance(id_token, str):
        try:
            id_token = jwt.decode(id_token, options={"verify_signature": False})
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to decode ID token: {str(e)}")
    if "email" not in id_token:
        raise HTTPException(status_code=400, detail="Email not found in Google response")
    user_email = id_token["email"]
    try:
        save_user(
            email=user_email,
            access_token=credentials.token,
            refresh_token=credentials.refresh_token
        )
    except Exception as e:
        # If it's a duplicate entry error, we ignore it
        if "duplicate key value violates unique constraint" in str(e):
            pass
        else:
            raise HTTPException(status_code=500, detail=f"Failed to save user: {str(e)}")
    return RedirectResponse(url=f"http://localhost:3000/home?email={user_email}")

@app.get("/emails/important_full")
def fetch_important_full_emails(user_email: str):
    """
    1. Fetch metadata (id, subject, sender, snippet) for emails from the last 24 hours.
    2. Use the classifier to filter and return only the important email IDs.
    3. Fetch the full email content for each important email and extract its plain-text body.
    4. Return a JSON object with the important emails, including their subject, sender, snippet, and full_body.
    """
    # Get user credentials from Supabase
    user_data = get_user_credentials(user_email)
    if not user_data:
        raise HTTPException(status_code=404, detail="User not found")
    access_token = user_data.get("access_token")
    refresh_token = user_data.get("refresh_token")
    if not access_token:
        raise HTTPException(status_code=400, detail="Access token missing for user")
    
    service = get_gmail_service(access_token, refresh_token)
    
    messages = []
    page_token = None
    max_emails = 50
    try:
        while True:
            response = service.users().messages().list(
                userId="me",
                q="newer_than:1d",
                pageToken=page_token
            ).execute()
            msgs = response.get("messages", [])
            messages.extend(msgs)
            if len(messages) >= max_emails:
                messages = messages[:max_emails]
                break
            page_token = response.get("nextPageToken")
            if not page_token:
                break
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list emails: {str(e)}")
    
    emails_data = []
    for msg in messages:
        try:
            msg_data = service.users().messages().get(
                userId="me",
                id=msg["id"],
                format="metadata",
                metadataHeaders=["Subject", "From"]
            ).execute()
        except Exception:
            continue
        headers = msg_data.get("payload", {}).get("headers", [])
        subject = next((h["value"] for h in headers if h["name"].lower() == "subject"), "")
        sender = next((h["value"] for h in headers if h["name"].lower() == "from"), "")
        snippet = msg_data.get("snippet", "")
        emails_data.append({
            "id": msg["id"],
            "subject": subject,
            "sender": sender,
            "snippet": snippet
        })
    
    # Use batch processing for classification if needed
    emails_json_str = json.dumps(emails_data)
    classification_result = classify_emails(emails_data)
    if isinstance(classification_result, dict) and "error" in classification_result:
        raise HTTPException(status_code=500, detail=f"Classifier error: {classification_result['error']}")
    try:
        important_ids = json.loads(classification_result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to parse classification result: {str(e)}")
    
    # Map full content for each email by ID
    full_content_map = {}
    for msg in messages:
        try:
            full_msg = service.users().messages().get(
                userId="me",
                id=msg["id"],
                format="full"
            ).execute()
            full_content_map[msg["id"]] = full_msg
        except Exception:
            continue
    
    important_full_emails = []
    for email_id in important_ids:
        meta = next((x for x in emails_data if x["id"] == email_id), None)
        if not meta:
            continue
        full_msg = full_content_map.get(email_id)
        if not full_msg:
            continue
        headers = full_msg.get("payload", {}).get("headers", [])
        subject = next((h["value"] for h in headers if h["name"].lower() == "subject"), "")
        sender = next((h["value"] for h in headers if h["name"].lower() == "from"), "")
        plain_text_body = extract_plain_text_body(full_msg.get("payload", {}))
        # Optionally truncate long body content
        if plain_text_body and len(plain_text_body) > 500:
            plain_text_body = plain_text_body[:500] + "..."
        important_full_emails.append({
            "id": email_id,
            "subject": subject,
            "sender": sender,
            "snippet": meta.get("snippet"),
            "full_body": plain_text_body
        })
    
    return JSONResponse(content={"important_emails": important_full_emails})

def get_gmail_service(access_token: str, refresh_token: str):
    creds = Credentials(
        token=access_token,
        refresh_token=refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=CLIENT_ID,
        client_secret=CLIENT_SECRET,
        scopes=SCOPES
    )
    return build("gmail", "v1", credentials=creds)

def extract_plain_text_body(payload):
    parts = payload.get("parts")
    if parts:
        for part in parts:
            mime_type = part.get("mimeType", "")
            if mime_type == "text/plain":
                body_data = part["body"].get("data", "")
                return decode_base64(body_data)
            else:
                nested = extract_plain_text_body(part)
                if nested:
                    return nested
    if payload.get("mimeType") == "text/plain":
        body_data = payload.get("body", {}).get("data", "")
        return decode_base64(body_data)
    return None

def decode_base64(data):
    if not data:
        return ""
    decoded_bytes = base64.urlsafe_b64decode(data)
    return decoded_bytes.decode("utf-8", errors="replace")

def openai_summary_and_reply(email_content):
    """
    Given an email content dictionary with keys "subject", "sender", and a body (in email_content['payload']['body']['data']),
    this function uses the LLM to generate a summary and a suggested reply.
    The function returns the LLM's JSON response with keys "summary" and "suggested_reply".
    """
    subject = email_content.get("subject", "")
    sender = email_content.get("sender", "")
    body = email_content.get("payload", {}).get("body", {}).get("data", "")
    if body and len(body) > 500:
        body = body[:500] + "..."
    
    # You can adjust the tone and details of the prompt as needed
    prompt = (
        f"Subject: {subject}\nSender: {sender}\nBody: {body}\n\n"
        "Please provide a concise summary of this email and suggest a professional reply. "
        "Return your result as a valid JSON object with two keys: 'summary' and 'suggested_reply'."
    )

    response = openai.ChatCompletion.create(
        model="gpt-3.5-turbo",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.5
    )
    
    return response.choices[0].message['content']

def get_user_profile(access_token: str, refresh_token: str):
    creds = Credentials(
        token=access_token,
        refresh_token=refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=CLIENT_ID,
        client_secret=CLIENT_SECRET,
        scopes=["https://www.googleapis.com/auth/userinfo.profile"]
    )
    people_service = build("people", "v1", credentials=creds)
    profile = people_service.people().get(
        resourceName="people/me",
        personFields="names,emailAddresses"
    ).execute()
    display_name = None
    if "names" in profile and profile["names"]:
        display_name = profile["names"][0].get("displayName")
    return display_name