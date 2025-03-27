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
from summarizer import openai_summary_and_reply
import openai
import json
from sentence_transformers import SentenceTransformer
import numpy as np
import faiss
from sklearn.metrics.pairwise import cosine_similarity
from collections import defaultdict


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

# Initialize the embedding model
embedder = SentenceTransformer('all-MiniLM-L6-v2')


def encode_email(email):
    """
    Encodes an email into an embedding vector using its subject, sender, and body.
    """
    text = f"Subject: {email.get('subject', '')}\nSender: {email.get('sender', '')}\nBody: {email.get('body', '')}"
    return embedder.encode(text, convert_to_numpy=True)


def build_vector_index(emails):
    """
    Build a FAISS index from the list of emails and return the index and corresponding email ids.
    """
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
    """
    Retrieves the top_k most relevant emails from the FAISS index based on the query.
    """
    query_embedding = embedder.encode([query], convert_to_numpy=True)
    query_embedding = np.array(query_embedding, dtype=np.float32)
    distances, indices = index.search(query_embedding, top_k)
    retrieved = []
    for idx in indices[0]:
        if idx < len(emails):
            retrieved.append(emails[idx])
    return retrieved


def prepare_context_from_emails(emails):
    """
    Aggregates a list of emails into a single context string.
    """
    context = ""
    for email in emails:
        context += f"Subject: {email.get('subject', '')}\n"
        context += f"From: {email.get('sender', '')}\n"
        context += f"Body: {email.get('body', '')}\n\n"
    return context


def generate_reply_with_context(aggregated_context, user_email, my_name):
    """
    Generates a reply using the aggregated context from multiple emails.
    """
    prompt = (
        f"Below are some emails:\n\n{aggregated_context}\n\n"
        f"Based on these emails, please generate a professional summary and a suggested reply. "
        f"Do not mention that these are aggregated emails. The reply should end with 'Best regards, {my_name}'."
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
    """
    1. Fetch metadata (id, subject, sender, snippet) for emails from the last 24 hours.
    2. Use the classifier to filter and return only the important email IDs.
    3. For each important email, fetch the full email content and extract its plain-text body.
    4. Then, feed the full email to the summarizer to generate a summary and suggested reply.
    5. Return a JSON object with the important emails, including subject, sender, snippet, full_body,
       summary, and suggested_reply.
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
    max_emails = 100


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

    # Process emails_data to extract needed fields and build a list for embedding
    emails_data_for_embedding = []

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
        body = extract_plain_text_body(msg_data.get("payload"))

        emails_data_for_embedding.append({
            "id": msg["id"],
            "subject": subject,
            "sender": sender,
            "snippet": snippet,
            "body": body,
            "full_content": msg_data
        })

    # Build the FAISS vector index from the emails
    index, email_ids = build_vector_index(emails_data_for_embedding)

    # Define a query for retrieval; you can modify this as needed
    query = "Generate a reply based on the recent emails"
    relevant_emails = retrieve_relevant_emails(query, index, emails_data_for_embedding, email_ids, top_k=5)

    # Retrieve the user's display name
    my_name = get_user_profile(access_token, refresh_token)

    # Step 1: Group emails by sender
    sender_groups = defaultdict(list)
    sender_embeddings = defaultdict(list)

    for email in relevant_emails:
        sender = email.get("sender", "")
        sender_groups[sender].append(email)
        sender_embeddings[sender].append(encode_email(email))

    # Step 2: Cluster emails from same sender using cosine similarity
    semantic_groups = []
    for sender, emails in sender_groups.items():
        embeddings = sender_embeddings[sender]
        used = set()

        for i in range(len(emails)):
            if i in used:
                continue
            group = [emails[i]]
            used.add(i)
            for j in range(i + 1, len(emails)):
                if j in used:
                    continue
                sim = cosine_similarity([embeddings[i]], [embeddings[j]])[0][0]
                if sim > 0.75:
                    group.append(emails[j])
                    used.add(j)
            semantic_groups.append(group)

    # Step 3: Process each semantic group
    results = []
    for group_emails in semantic_groups:
        sender = group_emails[0].get("sender", "")
        representative_subject = group_emails[0].get("subject", "")
        aggregated_body = "\n\n".join([email.get("body") or "" for email in group_emails])
        
        aggregated_email_content = {
            "subject": representative_subject,
            "sender": sender,
            "payload": {
                "body": {
                    "data": aggregated_body
                }
            }
        }

        summary_reply = openai_summary_and_reply(aggregated_email_content, user_email)


        try:
            summary_reply_parsed = json.loads(summary_reply)
        except Exception:
            result = {"summary": summary_reply, "suggested_reply": ""}

        result["group"] = {
            "sender": sender,
            "subject": representative_subject,
            "email_ids": [email.get("id") for email in group_emails]
        }
        result["email_id"] = group_emails[0].get("id")

        if not result.get("suggested_reply"):
            summary_text = result.get("summary", "")
            marker = None
            if "Suggested reply:" in summary_text:
                marker = "Suggested reply:"
            elif "Reply suggestion:" in summary_text:
                marker = "Reply suggestion:"
            if marker:
                parts = summary_text.split(marker)
                result["summary"] = parts[0].strip()
                result["suggested_reply"] = parts[1].strip() if len(parts) > 1 else ""

        results.append(result)

    return JSONResponse(content={"emails": results})


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
    Given an email content dictionary with keys "subject", "sender", and a body in email_content['payload']['body']['data'],
    this function uses the LLM to generate a concise summary and a suggested professional reply.
    It returns the LLM's response as a string.
    """
    subject = email_content.get("subject", "")
    sender = email_content.get("sender", "")
    body = email_content.get("payload", {}).get("body", {}).get("data", "")
    if body and len(body) > 500:
        body = body[:500] + "..."
    
    prompt = (
        f"Subject: {subject}\nSender: {sender}\nBody: {plain_text_body}\n\n"
        f"Please summarize the above email for me and suggest a reply {tone} way. "
        f"In summary don't say recipient, instead say you or something from third person perspective. "
        f"Add best regards with {my_name} in the last in the suggested reply. never give [Your Name] in the suggested reply. "

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