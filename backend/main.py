from fastapi import FastAPI, HTTPException, Request
from starlette.responses import RedirectResponse
from google_auth_oauthlib.flow import Flow
from supabase_client import save_user  # Import Supabase function
import os
from dotenv import load_dotenv

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

# Define redirect_uri in the Flow configuration
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
    # Do NOT pass redirect_uri here since it's set in Flow config
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

    if not credentials.id_token or "email" not in credentials.id_token:
        raise HTTPException(status_code=400, detail="Email not found in Google response")
    
    user_email = credentials.id_token["email"]

    try:
        save_user(
            email=user_email,
            access_token=credentials.token,
            refresh_token=credentials.refresh_token
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save user: {str(e)}")

    return {"message": f"User {user_email} logged in & credentials stored in Supabase"}