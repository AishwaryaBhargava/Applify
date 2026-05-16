from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Azure
    AZURE_OPENAI_ENDPOINT: str
    AZURE_OPENAI_API_KEY: str
    AZURE_OPENAI_API_VERSION: str = "2024-12-01-preview"
    AZURE_GPT4O_DEPLOYMENT: str = "gpt-4o"

    # Groq
    GROQ_API_KEY: str

    # Supabase
    SUPABASE_DATABASE_URL: str
    SUPABASE_JWT_SECRET: str

    # CORS
    ALLOWED_ORIGINS: str = "http://localhost:5173"

    class Config:
        env_file = ".env"


settings = Settings()