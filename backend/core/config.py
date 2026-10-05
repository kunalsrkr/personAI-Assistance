from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=(".env", "../.env"), extra="ignore")

    app_name: str = "Asteria Enterprise AI Command Center"
    app_env: str = "local"
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    cors_origins: str = "http://localhost:5173"

    database_url: str = "postgresql+asyncpg://asteria:asteria@localhost:5432/asteria"
    redis_url: str = "redis://localhost:6379/0"
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.2"
    gmail_mcp_url: str = "https://gmailmcp.googleapis.com/mcp/v1"
    gmail_oauth_keys_path: str = ""
    gmail_token_path: str = ""
    linkedin_oauth_keys_path: str = ""
    linkedin_token_path: str = ""
    linkedin_redirect_uri: str = "http://localhost:8000/api/v1/linkedin/callback"
    public_app_url: str = "http://localhost:5173"
    papers_root: str = ""
    workspace_root: str = ""
    file_search_roots: str = ""
    library_root: str = ""
    funnel_root: str = ""
    sessions_root: str = ""
    host_home: str = "/host-home"
    browser_history_root: str = "/browser-history"
    history_utc_offset: str = "+05:30"
    whisper_root: str = ""

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


settings = Settings()
