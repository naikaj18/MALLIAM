import os
import openai
from dotenv import load_dotenv
import json

load_dotenv()
openai.api_key = os.getenv("OPENAI_API_KEY")

def classify_emails(emails_json, batch_size=10):
    """
    Processes the list of emails in batches to avoid exceeding the model's context length.
    For each batch, it sends a JSON array of emails to OpenAI with a strict prompt.
    
    The prompt instructs the LLM to:
      - Exclude any emails that are automated, promotional, or marketing in nature.
      - Exclude job alerts (e.g., from LinkedIn Job Alerts, ZipRecruiter, etc.), career notifications, 
        subscription newsletters, daily digests, and any emails offering discounts, deals, or offers.
      - Return only the IDs of emails that are genuine personal or work-related communications requiring direct attention or action.
    
    Aggregates and returns all important email IDs as a JSON array string.
    """
    important_ids = []
    
    # Process emails in batches
    for i in range(0, len(emails_json), batch_size):
        batch = emails_json[i:i+batch_size]
        
        # Truncate fields to reduce token usage
        for email in batch:
            if 'subject' in email and email['subject']:
                email['subject'] = email['subject'][:50] + "..." if len(email['subject']) > 50 else email['subject']
            if 'sender' in email and email['sender']:
                email['sender'] = email['sender'][:50] + "..." if len(email['sender']) > 50 else email['sender']
            if 'snippet' in email and email['snippet']:
                email['snippet'] = email['snippet'][:100] + "..." if len(email['snippet']) > 100 else email['snippet']
        
        batch_json_str = json.dumps(batch)
        
        try:
            response = openai.ChatCompletion.create(
                model="gpt-3.5-turbo",  # Change model as needed
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are a no-nonsense email filter assistant. You are given a JSON array of emails, "
                            "where each email includes the fields 'id', 'subject', 'sender', and 'snippet'. "
                            "Your task is to output only a valid JSON array of the IDs of emails that are truly important. "
                            "Important emails are those that represent genuine personal or work-related communications requiring direct attention or action. "
                            "Strictly exclude any emails that are automated, promotional, or marketing in nature. "
                            "This includes, but is not limited to, emails that are job alerts (e.g. from LinkedIn, ZipRecruiter, or similar), "
                            "career notifications, subscription newsletters, daily digests, and emails offering discounts, deals, or offers. "
                            "Return only a valid JSON array of email IDs with no extra commentary."
                        )
                    },
                    {
                        "role": "user",
                        "content": f"Here are the emails: {batch_json_str}"
                    }
                ],
                temperature=0.3
            )
            content = response['choices'][0]['message']['content']
            if not content.strip():
                continue
            # Remove markdown code fences if present
            if content.strip().startswith("```"):
                content = content.strip().strip("`").strip("json").strip()
            batch_ids = json.loads(content)
            if isinstance(batch_ids, list):
                important_ids.extend(batch_ids)
        except Exception as e:
            print(f"Batch starting at index {i} error: {e}")
            continue

    return json.dumps(important_ids, indent=4)