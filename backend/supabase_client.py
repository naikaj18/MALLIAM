import os
from supabase import create_client
from dotenv import load_dotenv

# Load environment variables from the .env file
load_dotenv()


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

def get_user_credentials(email: str):
    """Fetch user credentials from Supabase by email."""
    response = supabase.table("users").select("*").eq("email", email).execute()
    # Assuming response.data contains the results.
    if response.data:
        return response.data[0]
    return None