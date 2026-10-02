import os

# Force test settings before app imports.
os.environ["GOOGLE_API_KEY"] = "test-key"
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///./test_vma.db"
os.environ["DEFAULT_PRACTICE_ID"] = "1"
os.environ["ENVIRONMENT"] = "test"