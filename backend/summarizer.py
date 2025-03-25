import os
import openai
from dotenv import load_dotenv

load_dotenv()

openai.api_key = os.getenv("OPENAI_API_KEY")

def openai_summary_and_reply(email_content):
    """
    Given an email content dictionary with keys "subject", "sender", and a body (located in email_content['payload']['body']['data']),
    this function uses the LLM to generate a concise summary and a suggested professional reply.
    If the email body is longer than 500 characters, it is truncated.
    The function returns the LLM's JSON response with keys "summary" and "suggested_reply".
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
        "Please provide a concise summary of the email and suggest a professional reply. "
        "Return your result as a valid JSON object with two keys: 'summary' and 'suggested_reply'."
    )

    response = openai.ChatCompletion.create(
        model="gpt-3.5-turbo",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.5
    )
    
    return response.choices[0].message['content']