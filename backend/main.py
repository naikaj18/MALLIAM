from fastapi import FastAPI, HTTPException, Request
from starlette.responses import RedirectResponse
from google_auth_oauthlib.flow import Flow
from supabase_client import save_user, get_user_credentials
import os
from dotenv import load_dotenv
import jwt
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

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

    # Decode the ID token if it's a string
    id_token = credentials.id_token
    if isinstance(id_token, str):
        try:
            # Debug decode (no signature verification here!)
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
    user_data = get_user_credentials(user_email)
    if not user_data:
        raise HTTPException(status_code=404, detail="User not found")

    access_token = user_data.get("access_token")
    refresh_token = user_data.get("refresh_token")
    if not access_token:
        raise HTTPException(status_code=400, detail="Access token missing for user")

    # Build the Gmail service
    service = get_gmail_service(access_token, refresh_token)
    
    try:
        results = service.users().messages().list(userId="me", q="newer_than:1d").execute()
        messages = results.get("messages", [])
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch emails: {str(e)}")
    
    emails = []
    for msg in messages[:10]:
        msg_data = service.users().messages().get(userId="me", id=msg["id"]).execute()
        headers = msg_data.get("payload", {}).get("headers", [])
        subject = next((h["value"] for h in headers if h["name"] == "Subject"), "")
        sender = next((h["value"] for h in headers if h["name"] == "From"), "")
        snippet = msg_data.get("snippet", "")
        emails.append({"subject": subject, "sender": sender, "snippet": snippet})
    
    return {"emails": emails}

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