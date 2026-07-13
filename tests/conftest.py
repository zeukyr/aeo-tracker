import os
import sys

# tab2_scorecard instantiates the OpenAI client at import time; tests never
# call it, but the constructor requires *a* key to exist.
os.environ.setdefault("OPENAI_API_KEY", "test-key-never-called")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
