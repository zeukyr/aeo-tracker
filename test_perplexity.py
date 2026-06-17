import os
from dotenv import load_dotenv
from perplexity import Perplexity

load_dotenv()

client = Perplexity(api_key=os.getenv("PERPLEXITY_API_KEY"))

completion = client.chat.completions.create(
    model="sonar",
    messages=[{"role": "user", "content": "is QC Career School accredited"}]
)

print(completion)