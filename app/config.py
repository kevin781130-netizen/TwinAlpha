from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "TW/US Invest OS"

    finmind_token: str | None = None

    llm_base_url: str = "https://api.openai.com/v1"
    llm_api_key: str | None = None
    llm_model: str = "gpt-4o-mini"

    # 台股費用
    default_tw_fee_rate: float = 0.001425
    default_tw_fee_discount: float = 0.6
    default_tw_min_fee: float = 20.0
    default_tw_tax_rate_sell: float = 0.003

    # 美股費用
    default_us_sec_fee_rate: float = 0.0000278
    default_us_finra_taf_per_share: float = 0.000166
    default_us_commission: float = 0.0


settings = Settings()
