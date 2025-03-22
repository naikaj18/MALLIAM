import os
from supabase import create_client
from dotenv import load_dotenv

# Load environment variables from the .env file
load_dotenv()

# Retrieve Supabase credentials from environment variables
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

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