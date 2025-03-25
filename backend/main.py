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
import openai
import json

load_dotenv()

app = FastAPI()
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
        if "duplicate key value violates unique constraint" in str(e):
            # User already exists; that's okay—continue to homepage
            pass
        else:
            raise HTTPException(status_code=500, detail=f"Failed to save user: {str(e)}")

    return RedirectResponse(url=f"http://localhost:3000/home?email={user_email}")

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

    service = get_gmail_service(access_token, refresh_token)
    
    messages = []
    page_token = None

    try:
        while True:
            response = service.users().messages().list(
                userId="me",
                q="newer_than:1d",
                maxResults=50,
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
            "id": msg["id"],
            "subject": subject,
            "sender": sender,
            "snippet": snippet
        })

    return classify_emails(emails_data)

@app.get("/emails/actions")
def email_actions(user_email: str):
    """
    Classifies important emails, fetches their full content,
    and returns results in a readable JSON format.
    """
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
                format="full"
            ).execute()
        except Exception as e:
            continue

        headers = msg_data.get("payload", {}).get("headers", [])
        subject = next((h["value"] for h in headers if h["name"] == "Subject"), "")
        sender = next((h["value"] for h in headers if h["name"] == "From"), "")
        snippet = msg_data.get("snippet", "")

        emails_data.append({
            "id": msg["id"],
            "subject": subject,
            "sender": sender,
            "snippet": snippet,
            "full_content": msg_data
        })

    classification_result = classify_emails(emails_data)
    if isinstance(classification_result, dict):
        # If there's an error, raise an HTTPException with the error message
        raise HTTPException(status_code=500, detail=classification_result.get("error", "Unknown classification error"))
    
    classified_emails = json.loads(classification_result)

    # Create a mapping from email id to full_content from the original emails_data
    full_content_map = { email['id']: email['full_content'] for email in emails_data }

    emails_to_summarize = []
    for email in classified_emails:
        # If the email is a string, attempt to parse it into a dictionary
        if isinstance(email, str):
            try:
                email = json.loads(email)
            except Exception as e:
                continue
        full_content = full_content_map.get(email.get('id'))
        if not full_content:
            continue
        headers = full_content.get("payload", {}).get("headers", [])
        subject = next((h["value"] for h in headers if h["name"].lower() == "subject"), "")
        sender = next((h["value"] for h in headers if h["name"].lower() == "from"), "")

        plain_text_body = extract_plain_text_body(full_content.get('payload'))
        if plain_text_body and len(plain_text_body) > 500:
            plain_text_body = plain_text_body[:500] + "..."

        emails_to_summarize.append({
            "id": email.get('id'),
            "subject": subject,
            "sender": sender,
            "body": plain_text_body
        })
    if not emails_to_summarize:
        return {"emails": []}

    results = []
    for email in emails_to_summarize:
        # Prepare an email_content dictionary for openai_summary_and_reply
        email_content = {
            "subject": email["subject"],
            "sender": email["sender"],
            "payload": {
                "body": {
                    "data": email["body"]
                }
            }
        }
        summary_reply = openai_summary_and_reply(email_content,user_email)
        
        try:
            parsed_output = json.loads(summary_reply)
            # If the output is a list, use the first element; otherwise, use it directly
            if isinstance(parsed_output, list):
                result = parsed_output[0]
            else:
                result = parsed_output
        except Exception as e:
            result = {"summary": summary_reply, "suggested_reply": ""}
        
        # Ensure email_id is included in the result
        result["email_id"] = email["id"]
        
        # If suggested_reply is empty but summary contains a reply suggestion marker, split them
        if not result.get("suggested_reply"):
            marker = None
            summary_text = result.get("summary", "")
            if "Suggested reply:" in summary_text:
                marker = "Suggested reply:"
            elif "Reply suggestion:" in summary_text:
                marker = "Reply suggestion:"
            
            if marker:
                parts = summary_text.split(marker)
                result["summary"] = parts[0].strip()
                result["suggested_reply"] = parts[1].strip() if len(parts) > 1 else ""
        
        results.append(result)
    
    return json.dumps({"emails": results}, indent=4)

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

def openai_summary_and_reply(email_content,user_email):
    user_data = get_user_credentials(user_email)
    access_token = user_data.get("access_token")
    refresh_token = user_data.get("refresh_token")
    my_name=get_user_profile(access_token, refresh_token)

    subject = email_content.get("subject")
    sender = email_content.get("sender")
    tone="professional"
    
    # plain_text_body = extract_plain_text_body(email_content.get("payload"))
    plain_text_body=email_content['payload']['body']['data']
    prompt = f"Subject: {subject}\nSender: {sender}\nBody: {plain_text_body}\n\nPlease summarize the above email for me and suggest a reply {tone} way .In summary dont say recipient instead just say you or something from third person perspective.Add best regards with {my_name}"
   
    response = openai.ChatCompletion.create(
        model="gpt-3.5-turbo",
        messages=[{"role": "user", "content": prompt}]
    )
    
    return response.choices[0].message['content']
def get_user_profile(access_token: str, refresh_token: str):
    """
    Retrieves the user's profile using the Google People API.
    Returns the display name if available.
    """
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build

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