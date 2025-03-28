import os
import openai
import json
from dotenv import load_dotenv

load_dotenv()
openai.api_key = os.getenv("OPENAI_API_KEY")

def group_emails_by_llm(emails):
    """
    Takes a list of emails, each with 'subject', 'sender', 'summary', 'time', and 'suggested_reply',
    and returns a single string that groups similar emails together in a human-readable format.
    
    Expected format for each email item:
    {
      "subject": "Subject of Email",
      "sender": "sender@example.com",
      "summary": "A concise summary",
      "time": "2025-04-01 10:30 AM",
      "suggested_reply": "A short suggested reply or empty string"
    }
    
    The output should have a heading for each group (e.g., based on topic or relevance) with symbols, and then list the emails in numbered order using the following format:
    
    **Heading for Group (with an emoji)**
    
    1. **Subject:** [subject]
       **Sender:** [sender]
       **Time:** [time]
       **Summary:** [summary]
       **Suggested Reply:** [suggested_reply]
    
    Ensure extra blank lines between emails for readability, and do not include any introductory commentary.
    Return only the final grouped summary text as Markdown.
    """
    # Convert emails to JSON for the LLM
    emails_json = json.dumps(emails, indent=2)
    
    prompt = (
        "You are an intelligent email-organizing assistant. "
        "You are given a JSON array of emails, where each email has the keys 'subject', 'sender', 'summary', 'time', and 'suggested_reply'. "
        "Your task is to group these emails by similarity of topic or relevance and output a final result in Markdown format. "
        "For each group, provide a heading with an appropriate emoji (for example, '📦', '💼', or '🎟️') that describes the theme. "
        "Then, for each email in that group, list the details in numbered order as follows:\n\n"
        "1. **Subject:** [subject]\n"
        "   **Sender:** [sender]\n"
        "   **Time:** [time]\n"
        "   **Summary:** [summary]\n"
        "   **Suggested Reply:** [suggested_reply]\n\n"
        "Ensure there is an extra blank line between each email for readability. "
        "Return only the final grouped summary text in Markdown with no introductory commentary or extra text."
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