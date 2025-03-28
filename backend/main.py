from fastapi import FastAPI, HTTPException, Request
from starlette.responses import RedirectResponse, JSONResponse, PlainTextResponse
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
from summarizer import openai_summary_and_reply  # Use summarizer from summarizer.py
from group_emails import group_emails_by_llm
import openai
import numpy as np
import faiss
from sentence_transformers import SentenceTransformer
from collections import defaultdict
from fastapi.middleware.cors import CORSMiddleware
from datetime import datetime

load_dotenv()

app = FastAPI()

# Enable CORS for your frontend
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

# Initialize the embedding model
embedder = SentenceTransformer('all-MiniLM-L6-v2')

def encode_email(email):
    text = f"Subject: {email.get('subject', '')}\nSender: {email.get('sender', '')}\nBody: {email.get('body', '')}"
    return embedder.encode(text, convert_to_numpy=True)

def build_vector_index(emails):
    embeddings = []
    email_ids = []
    for email in emails:
        emb = encode_email(email)
        embeddings.append(emb)
        email_ids.append(email['id'])
    embeddings = np.stack(embeddings)
    dimension = embeddings.shape[1]
    index = faiss.IndexFlatL2(dimension)
    index.add(np.array(embeddings, dtype=np.float32))
    return index, email_ids

def retrieve_relevant_emails(query, index, emails, email_ids, top_k=5):
    query_embedding = embedder.encode([query], convert_to_numpy=True)
    query_embedding = np.array(query_embedding, dtype=np.float32)
    distances, indices = index.search(query_embedding, top_k)
    retrieved = []
    for idx in indices[0]:
        if idx < len(emails):
            retrieved.append(emails[idx])
    return retrieved

def prepare_context_from_emails(emails):
    context = ""
    for email in emails:
        context += f"Subject: {email.get('subject', '')}\n"
        context += f"From: {email.get('sender', '')}\n"
        context += f"Body: {email.get('body', '')}\n\n"
    return context

def generate_reply_with_context(aggregated_context):
    prompt = (
        f"Below are some emails:\n\n{aggregated_context}\n\n"
        "Based on these emails, please generate a professional summary and a suggested reply. "
        "Do not mention that these are aggregated emails. The reply should end with 'Best regards, <Your Name>'."
    )
    response = openai.ChatCompletion.create(
        model="gpt-3.5-turbo",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.5
    )
    return response.choices[0].message['content']

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
        if "duplicate key value violates unique constraint" in str(e):
            pass
        else:
            raise HTTPException(status_code=500, detail=f"Failed to save user: {str(e)}")
    return RedirectResponse(url=f"http://localhost:3000/home?email={user_email}")

@app.get("/emails/important_full")
def fetch_important_full_emails(user_email: str):
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
    max_emails = 100

    try:
        while True:
            response = service.users().messages().list(
                userId="me",
                q="newer_than:1d",  # fetch all emails from the last 24 hours
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
    gmail_important_ids = set()

    for msg in messages:
        try:
            # Retrieve the full email instead of metadata so we get internalDate
            msg_data = service.users().messages().get(
                userId="me",
                id=msg["id"],
                format="full"
            ).execute()
        except Exception:
            continue
        headers = msg_data.get("payload", {}).get("headers", [])
        subject = next((h["value"] for h in headers if h["name"].lower() == "subject"), "")
        sender = next((h["value"] for h in headers if h["name"].lower() == "from"), "")
        snippet = msg_data.get("snippet", "")
        label_ids = msg_data.get("labelIds", [])
        if "IMPORTANT" in label_ids:
            gmail_important_ids.add(msg["id"])
        body_preview = extract_plain_text_body(msg_data.get("payload", {}))
        # Extract internalDate and convert it
        internal_date = msg_data.get("internalDate")
        if internal_date:
            time_str = datetime.fromtimestamp(int(internal_date) / 1000).strftime("%Y-%m-%d %H:%M:%S")
        else:
            time_str = "Unknown"
            
        emails_data.append({
            "id": msg["id"],
            "subject": subject,
            "sender": sender,
            "snippet": snippet,
            "body": body_preview,
            "time": time_str
        })

    classifier_result = classify_emails(emails_data)
    try:
        classifier_ids = set(json.loads(classifier_result))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to parse classification result: {str(e)}")
    
    important_ids = list(gmail_important_ids.union(classifier_ids))
    important_emails = []
    for email_id in important_ids:
        meta = next((x for x in emails_data if x["id"] == email_id), None)
        if not meta:
            continue
        try:
            full_msg = service.users().messages().get(
                userId="me",
                id=email_id,
                format="full"
            ).execute()
        except Exception:
            continue
        headers = full_msg.get("payload", {}).get("headers", [])
        subject = next((h["value"] for h in headers if h["name"].lower() == "subject"), meta.get("subject"))
        sender = next((h["value"] for h in headers if h["name"].lower() == "from"), meta.get("sender"))
        full_body = extract_plain_text_body(full_msg.get("payload", {}))
        if full_body and len(full_body) > 500:
            full_body = full_body[:500] + "..."
        
        summarizer_input = {
            "subject": subject,
            "sender": sender,
            "payload": {"body": {"data": full_body}}
        }
        summary_reply = openai_summary_and_reply(summarizer_input)
        try:
            summary_reply_parsed = json.loads(summary_reply)
        except Exception:
            summary_reply_parsed = {"summary": summary_reply, "suggested_reply": ""}
        
        important_emails.append({
            "id": email_id,
            "subject": subject,
            "sender": sender,
            "snippet": meta.get("snippet"),
            "full_body": full_body,
            "summary_info": summary_reply_parsed,
            "time": meta.get("time", "Unknown")
        })
    
    return JSONResponse(content={"important_emails": important_emails})

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

@app.get("/emails/grouped_summary")
def get_grouped_summary(user_email: str):
    """
    1. Retrieve the important emails using fetch_important_full_emails.
    2. Convert them into the format required by group_emails_by_llm:
       each item must have 'subject', 'sender', 'summary', 'time', and 'suggested_reply'.
    3. Call group_emails_by_llm and return the result as plain text.
    """
    response = fetch_important_full_emails(user_email)
    try:
        data_dict = json.loads(response.body.decode("utf-8"))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to parse JSONResponse body: {str(e)}")
    
    if "important_emails" not in data_dict:
        raise HTTPException(status_code=500, detail="No important emails found.")
    
    raw_emails = data_dict["important_emails"]
    important_emails_data = []
    for item in raw_emails:
        summary_info = item.get("summary_info", {})
        important_emails_data.append({
            "subject": item.get("subject", ""),
            "sender": item.get("sender", ""),
            "summary": summary_info.get("summary", ""),
            "time": item.get("time", "Unknown"),
            "suggested_reply": summary_info.get("suggested_reply", "")
        })
    
    grouped_output = group_emails_by_llm(important_emails_data)
    return PlainTextResponse(content=grouped_output)