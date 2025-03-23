from fastapi import FastAPI, HTTPException, Request
from starlette.responses import RedirectResponse
from google_auth_oauthlib.flow import Flow
from supabase_client import save_user, get_user_credentials
import os
from dotenv import load_dotenv
import jwt
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
import base64
from classifier import classify_emails
load_dotenv()

app = FastAPI()

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
    """Redirects user to Google OAuth Login"""
    auth_url, _ = flow.authorization_url(prompt="consent")
    return RedirectResponse(auth_url)

@app.get("/auth/callback")
def auth_callback(request: Request):
    """Handles OAuth Callback and stores credentials in Supabase"""
    code = request.query_params.get("code")
    if not code:
        raise HTTPException(status_code=400, detail="Authorization code not found")
    try:
        flow.fetch_token(code=code)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Token exchange failed: {str(e)}")
    
    credentials = flow.credentials

    # Decode the ID token if it's a string
    id_token = credentials.id_token
    if isinstance(id_token, str):
        try:
            # Decode without verifying signature for debugging purposes
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
        raise HTTPException(status_code=500, detail=f"Failed to save user: {str(e)}")

    return {"message": f"User {user_email} logged in & credentials stored in Supabase"}

@app.get("/emails")
def fetch_emails(user_email: str):
    """
    Fetches all emails from the last 24 hours for the given user,
    retrieving only key parts: Subject, From, and Snippet.
    """
    user_data = get_user_credentials(user_email)
    if not user_data:
        raise HTTPException(status_code=404, detail="User not found")

    access_token = user_data.get("access_token")
    refresh_token = user_data.get("refresh_token")
    if not access_token:
        raise HTTPException(status_code=400, detail="Access token missing for user")

    # Build the Gmail service with refresh token support
    service = get_gmail_service(access_token, refresh_token)
    
    messages = []
    page_token = None

    # Pagination: gather all messages from the last 24 hours
    try:
        while True:
            response = service.users().messages().list(
                userId="me",
                q="newer_than:1d",
                pageToken=page_token
            ).execute()

            msgs = response.get("messages", [])
            messages.extend(msgs)

            page_token = response.get("nextPageToken")
            if not page_token:
                break
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list emails: {str(e)}")

    emails_data = []

    # Retrieve metadata and snippet for each message
    for msg in messages:
        try:
            msg_data = service.users().messages().get(
                userId="me",
                id=msg["id"],
                format="metadata",
                metadataHeaders=["Subject", "From"]
            ).execute()
        except Exception as e:
            continue

        headers = msg_data.get("payload", {}).get("headers", [])
        subject = next((h["value"] for h in headers if h["name"] == "Subject"), "")
        sender = next((h["value"] for h in headers if h["name"] == "From"), "")
        snippet = msg_data.get("snippet", "")

        emails_data.append({
            "subject": subject,
            "sender": sender,
            "snippet": snippet
        })

    return classify_emails(emails_data)

    # return {"emails": emails_data}

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
    """
    Recursively look for a text/plain part and decode it.
    """
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
    """Base64-url decode the given string."""
    if not data:
        return ""
    decoded_bytes = base64.urlsafe_b64decode(data)
    return decoded_bytes.decode("utf-8", errors="replace")