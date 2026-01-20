import os
from dotenv import load_dotenv
from supabase import create_client

load_dotenv()  # 🔥 THIS LINE IS CRITICAL

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise RuntimeError("Supabase env vars not loaded")

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
