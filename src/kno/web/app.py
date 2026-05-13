from fastapi import FastAPI

from kno.config import Settings

app = FastAPI()


@app.get("/api/health")
def health() -> dict[str, str]:
    settings = Settings()
    return {
        provider: "ok" if configured else "not_configured"
        for provider, configured in settings.providers_status.items()
    }
