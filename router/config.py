from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    litellm_url: str = "http://localhost:4000"
    router_api_key: str = ""
    litellm_api_key: str = ""
    session_ttl_seconds: int = 3600
    session_max_size: int = 10000
    log_level: str = "INFO"
    rules_path: str = "config/rules.yaml"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
