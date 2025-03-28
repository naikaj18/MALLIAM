import os
import openai
from dotenv import load_dotenv
import json
import re

load_dotenv()
openai.api_key = os.getenv("OPENAI_API_KEY")

def openai_summary_and_reply(email_content):
    """
    Given an email content dictionary with keys "subject", "sender", and a body located in email_content['payload']['body']['data'],
    this function uses the LLM to generate a concise summary of the email in less than 120 words.
    It will only provide a suggested reply if the email clearly demands a reply (for example, if it asks a question or requests a response).
    Otherwise, it returns an empty string for 'suggested_reply'.
    
    The function returns the LLM's response as a JSON string with exactly two keys: 'summary' and 'suggested_reply'.
    If the model embeds the suggested reply within the summary (after "Suggested reply:"), this function extracts that part 
    using regex and assigns it to the 'suggested_reply' field, cleaning up the summary.
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
        "Generate a concise summary of the email in less than 120 words. "
        "Return your result as a valid JSON object with exactly two keys: 'summary' and 'suggested_reply'."
    )
    
    response = openai.ChatCompletion.create(
        model="gpt-3.5-turbo",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.5
    )
    
    raw_output = response.choices[0].message['content']
    
    try:
        result = json.loads(raw_output)
    except Exception:
        # If output isn't valid JSON, return it as is
        return raw_output
    
    # Use regex to extract suggested reply if it's embedded in summary.
    # Look for "Suggested reply:" (case-insensitive)
    summary_text = result.get("summary", "")
    if not result.get("suggested_reply"):
        match = re.search(r"Suggested reply:\s*(.+)", summary_text, re.IGNORECASE | re.DOTALL)
        if match:
            reply = match.group(1).strip()
            # Remove the suggested reply part from summary
            summary_clean = re.sub(r"Suggested reply:\s*.+", "", summary_text, flags=re.IGNORECASE | re.DOTALL).strip()
            result["summary"] = summary_clean
            result["suggested_reply"] = reply

    return json.dumps(result)