from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # App URLs
    FRONTEND_URL: str = "http://localhost:3000"
    BACKEND_URL: str = "http://localhost:8000"

    # GitHub OAuth App credentials (NEVER expose client_secret to frontend)
    GITHUB_CLIENT_ID: str
    GITHUB_CLIENT_SECRET: str

    # Must exactly match the redirect_uri your GitHub OAuth App is configured with.
    # Frontend uses: `${window.location.origin}/auth/callback`
    GITHUB_REDIRECT_URI: str = "http://localhost:3000/auth/callback"
    GITHUB_OAUTH_TOKEN_URL: str = "https://github.com/login/oauth/access_token"
    GITHUB_API_BASE: str = "https://api.github.com"

    # Database
    POSTGRES_USER: str = "conductor"
    POSTGRES_PASSWORD: str = "conductor_dev"
    POSTGRES_DB: str = "conductor"
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432

    @property
    def POSTGRES_URL(self) -> str:
        return (
            "postgresql+asyncpg://"
            f"{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    # Redis
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379

    @property
    def REDIS_URL(self) -> str:
        return f"redis://{self.REDIS_HOST}:{self.REDIS_PORT}"

    # Qdrant
    QDRANT_HOST: str = "localhost"
    QDRANT_PORT: int = 6333
    QDRANT_COLLECTION: str = "conductor-memory"

    @property
    def QDRANT_URL(self) -> str:
        return f"http://{self.QDRANT_HOST}:{self.QDRANT_PORT}"

    # Ollama
    OLLAMA_HOST: str = "localhost"
    OLLAMA_PORT: int = 11434

    @property
    def OLLAMA_BASE_URL(self) -> str:
        return f"http://{self.OLLAMA_HOST}:{self.OLLAMA_PORT}"

    # Celery
    CELERY_BROKER_URL: str = "redis://localhost:6379/0"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/0"

    # LLM / agent credentials
    ANTHROPIC_API_KEY: str = ""
    GITHUB_TOKEN: str = ""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
