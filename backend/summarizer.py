import os
import openai
from dotenv import load_dotenv
import json

load_dotenv()
openai.api_key = os.getenv("OPENAI_API_KEY")

def openai_summary_and_reply(email_content):
    """
    Given an email content dictionary with keys "subject", "sender", and a body located in email_content['payload']['body']['data'],
    this function uses the LLM to generate a concise summary of the email.
    It will only provide a suggested reply if:
      1. The sender appears to be a personal email (i.e. not a generic or automated company address).
      2. The email asks a question or clearly requires a reply.
    Otherwise, 'suggested_reply' is set to an empty string.
    
    The function returns the LLM's response as a JSON string with exactly two keys: 'summary' and 'suggested_reply'.
    """
    subject = email_content.get("subject", "")
    sender = email_content.get("sender", "")
    body = email_content.get("payload", {}).get("body", {}).get("data", "")
    
    # Truncate the body if it exceeds 500 characters
    if body and len(body) > 500:
        body = body[:500] + "..."
    
    prompt = (
        f"Subject: {subject}\n"
        f"Sender: {sender}\n"
        f"Body: {body}\n\n"
        "Please provide a concise summary of the email. "
        "Only if the sender appears to be a personal email (i.e. not a generic company or automated address) "
        "and if the email asks a question or clearly requires a response, provide a suggested professional reply. "
        "If not, set 'suggested_reply' to an empty string. "
        "Return your result as a valid JSON object with exactly two keys: 'summary' and 'suggested_reply'."
    )
    
    response = openai.ChatCompletion.create(
        model="gpt-3.5-turbo",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.5
    )
    
    return response.choices[0].message['content']