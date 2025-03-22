import os
from supabase import create_client

# Supabase Credentials
SUPABASE_URL = "https://yomrpvvyipdvqskwtkzh.supabase.co/"
SUPABASE_SERVICE_ROLE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InlvbXJwdnZ5aXBkdnFza3d0a3poIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc0MjU5MzIzNSwiZXhwIjoyMDU4MTY5MjM1fQ.mAWemZJaR8JoOZeBwcK25psvOjkFhMIt9Kxqx7aIV64"

# Create Supabase Client
supabase = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)

def save_user(email, access_token, refresh_token, summary_time="08:00"):
    """Save user credentials in Supabase."""
    data = {
        "email": email,
        "access_token": access_token,
        "refresh_token": refresh_token,
        "summary_time": summary_time
    }
    response = supabase.table("users").insert(data).execute()
    return response