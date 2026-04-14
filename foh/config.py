from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_env: str = "development"    # development | sandbox | production
    data_mode: str = "live"         # live | batch  (mock servers only)
    standalone: bool = False        # True = dashboard generates data in-process (no HTTP servers needed)

    # Toast credentials
    toast_client_id: str = "mock-client-id"
    toast_client_secret: str = "mock-client-secret"
    toast_restaurant_guid: str = "mock-restaurant-guid"

    # OpenTable credentials
    opentable_client_id: str = "mock-client-id"
    opentable_client_secret: str = "mock-client-secret"
    opentable_restaurant_id: str = "mock-restaurant-id"

    # Mock server ports
    toast_mock_port: int = 8001
    opentable_mock_port: int = 8002

    @property
    def toast_base_url(self) -> str:
        return {
            "development": f"http://localhost:{self.toast_mock_port}",
            "sandbox":     "https://ws-sandbox.toasttab.com",
            "production":  "https://ws-api.toasttab.com",
        }[self.app_env]

    @property
    def opentable_base_url(self) -> str:
        # /v2 is included so provider routes append directly (e.g. /oauth/token)
        return {
            "development": f"http://localhost:{self.opentable_mock_port}/v2",
            "sandbox":     "https://sandbox.opentable.com/v2",
            "production":  "https://platform.otrestaurant.com/v2",
        }[self.app_env]

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
