from fastapi import FastAPI

app = FastAPI()

@app.get("/")
def read_root():
    return {"message": "Welcome to Mailliam API"}

@app.get("/emails")
def get_emails():
    return {"emails": ["email1", "email2", "email3"]}