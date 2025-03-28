import os
import openai
import json
from dotenv import load_dotenv

load_dotenv()
openai.api_key = os.getenv("OPENAI_API_KEY")

def group_emails_by_llm(emails):
    """
    Takes a list of emails, each with 'subject', 'sender', 'summary', 'time', and 'suggested_reply',
    and returns a single string that groups similar emails together in a human-readable Markdown format.
    
    Expected format for each email item:
    {
      "subject": "Subject of Email",
      "sender": "sender@example.com",
      "summary": "A concise summary",
      "time": "2025-04-01 10:30:00",
      "suggested_reply": "A short suggested reply or empty string"
    }
    
    The output will have a heading for each group that includes an appropriate emoji and a descriptive category name
    (e.g., "📦 Job Applications & Opportunities"). Then, for each email in that group, list the details in numbered order using:
    
    1. **Subject:** [subject]  
       **Sender:** [sender]  
       **Time:** [time]  
       **Summary:** [summary]  
       **Suggested Reply:** 💬 [suggested_reply]
       
    Ensure there is an extra blank line between each email for readability.
    Return only the final grouped summary text as plain Markdown with no introductory commentary.
    """
    # Convert emails to JSON for the LLM
    emails_json = json.dumps(emails, indent=2)
    
    prompt = (
        "You are an intelligent email-organizing assistant. "
        "You are given a JSON array of emails, where each email has the keys 'subject', 'sender', 'summary', 'time', and 'suggested_reply'. "
        "Your task is to group these emails by similarity of topic or relevance and output a final result in Markdown format. "
        "For each group, provide a heading that includes an appropriate emoji and a descriptive category name (for example, '📦 Job Applications & Opportunities'). "
        "Then list the emails in numbered order using the following format:\n\n"
        "1. **Subject:** [subject]  \n"
        "   **Sender:** [sender]  \n"
        "   **Time:** [time]  \n"
        "   **Summary:** [summary]  \n"
        "   **Suggested Reply:** 💬 [suggested_reply]  \n\n"
        "Ensure there is an extra blank line between each email for readability. "
        "Return only the final grouped summary text in plain Markdown with no introductory commentary or extra text."
    )
    
    user_message = f"Here are the important emails in JSON:\n{emails_json}\n\nGroup them as instructed."
    
    response = openai.ChatCompletion.create(
        model="gpt-3.5-turbo",
        messages=[
            {"role": "system", "content": prompt},
            {"role": "user", "content": user_message}
        ],
        temperature=0.5
    )
    
    return response.choices[0].message["content"]