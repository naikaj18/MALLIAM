import os
import openai
from dotenv import load_dotenv
import json

load_dotenv()

openai.api_key = os.getenv("OPENAI_API_KEY")

def classify_emails(emails_json):
    """
    Sends a list of email JSON objects to OpenAI for classification.
    Returns the classification result.
    """
    # Truncate individual fields to reduce overall token count
    for email in emails_json:
        if 'subject' in email and email['subject']:
            email['subject'] = email['subject'][:100] + "..." if len(email['subject']) > 100 else email['subject']
        if 'sender' in email and email['sender']:
            email['sender'] = email['sender'][:100] + "..." if len(email['sender']) > 100 else email['sender']
        if 'snippet' in email and email['snippet']:
            email['snippet'] = email['snippet'][:200] + "..." if len(email['snippet']) > 200 else email['snippet']
    
    emails_str = f"{emails_json}"
    # Reduce the maximum allowed size from 500000 to 300000 characters
    max_allowed = 300000
    if len(emails_str) > max_allowed:
        allowed_emails = []
        for email in emails_json:
            allowed_emails.append(email)
            if len(f"{allowed_emails}") > max_allowed:
                allowed_emails.pop()
                break
        emails_json = allowed_emails
        
    try:
        response = openai.ChatCompletion.create(
            model="gpt-4o-mini-2024-07-18",
            messages=[
                {
                    "role": "system",
                    "content": "You're an intelligent email filter assistant. You are given a JSON array of emails, where each email includes the fields \"id\", \"subject\", \"sender\", and \"snippet\". Your task is to analyze each email and determine whether it requires the user's direct reply or manual action—such as scheduling interviews, replying to a personal or business inquiry, or acknowledging a critical update. Exclude from your output only those emails that are clearly advertisements, job ads, or sent from talent networks. If an email is ambiguous or does not clearly fall into one of these excluded categories, include it in your output. For each included email, include all the original fields and add a new field \"action_required\", which should be set to true if the email requires a reply, or false otherwise. Additionally, remove any occurrences of the sequence \"\\u200c\" from the JSON output. Please output the classification for every email provided (excluding only those emails that clearly match the excluded categories). Return your output as a JSON array of emails, with each email including: \"id\", \"subject\", \"sender\", \"snippet\", and \"action_required\". If no emails are classified as important, output a JSON object with a field \"message\" stating \"There are no important emails\". Output only the JSON without any extra commentary."
                },
                {
                    "role": "user",
                    "content": f"Here are the emails: {emails_json}"
                }
            ],
            temperature=0.3
        )
        content = response['choices'][0]['message']['content']
        if not content.strip():
            return {"error": "Empty response from OpenAI"}

        # Strip markdown formatting if present
        if content.strip().startswith("```"):
            content = content.strip().strip("`").strip("json").strip()
        parsed = json.loads(content)
        return json.dumps(parsed, indent=4)
    except Exception as e:
        return {"error": str(e)}

def openai_summary_and_reply(email_content):
    subject = email_content.get("subject")
    sender = email_content.get("sender")
    body = email_content.get("body")
    if body and len(body) > 500:
        body = body[:500] + "..."
    
    prompt = (
        f"Please summarize the following email and provide a separate suggested reply. "
        f"Output the result as JSON with two keys: 'summary' and 'suggested_reply', with no additional commentary.\n\n"
        f"Subject: {subject}\nSender: {sender}\nBody: {body}"
    )
    
    response = openai.ChatCompletion.create(
        model="gpt-4o-mini-2024-07-18",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.5
    )
    
    summary_and_reply = response['choices'][0]['message']['content']
    return summary_and_reply