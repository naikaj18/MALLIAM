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
      - Exclude emails that appear to be job alerts, subscription newsletters, daily digests,
        or that contain keywords such as "sale", "offer", "discount", "promotion", "newsletter", or "digest".
      - Return only the IDs of emails that are genuine personal or work-related communications 
        requiring direct attention or action.
    
    Aggregates and returns all important email IDs as a JSON array string.
    """
    important_ids = []
    
    # Process emails in batches
    for i in range(0, len(emails_json), batch_size):
        batch = emails_json[i:i+batch_size]
        
        # Optional pre-filter: discard emails whose subject or snippet contain common advertisement keywords
        prefiltered = []
        ad_keywords = ["sale", "offer", "discount", "promotion", "newsletter", "digest"]
        for email in batch:
            subject = email.get("subject", "").lower()
            snippet = email.get("snippet", "").lower()
            if any(keyword in subject or keyword in snippet for keyword in ad_keywords):
                continue
            prefiltered.append(email)
        batch = prefiltered

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
                            "You are a no-nonsense email filter assistant. You are provided with a JSON array of emails, "
                            "where each email includes the fields 'id', 'subject', 'sender', and 'snippet'. "
                            "Your task is to return only the IDs of emails that are genuinely important – that is, "
                            "those that represent personal or work-related communications requiring direct attention or action. "
                            "Exclude any emails that are automated, promotional, or marketing in nature. This includes emails that are job alerts, "
                            "subscription newsletters, daily digests, or any messages containing keywords like 'sale', 'offer', 'discount', "
                            "'promotion', 'newsletter', or 'digest'. "
                            "Return only a valid JSON array of email IDs with no extra commentary."
                        )
                    },
                    {
                        "role": "user",
                        "content": f"Here are the emails: {batch_json_str}"
                    }
                ],
                temperature=0.4
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