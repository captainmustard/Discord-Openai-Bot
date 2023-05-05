import os
import openai
from dotenv import load_dotenv

# Load the environment variables from the config.env file
load_dotenv("config.env")

# Set up the OpenAI API client
openai.api_key = os.environ["OPENAI_API_KEY"]

response = openai.ChatCompletion.create(
    model="gpt-3.5-turbo",
    messages=[
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "What is the capital of France?"},
    ],
    max_tokens=3500,
    n=1,
    stop=None,
    temperature=0.5,
)
print(response)
