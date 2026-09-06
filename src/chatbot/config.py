from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    database_host: str
    database_name: str
    user_name: str
    password: str

    class Config:
        env_file = ".env"