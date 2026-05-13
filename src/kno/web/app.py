from fastapi import FastAPI
from fastapi.responses import HTMLResponse

from kno.config import Settings

app = FastAPI()


@app.get("/api/health")
def health() -> dict[str, str]:
    settings = Settings()
    return {
        provider: "ok" if configured else "not_configured"
        for provider, configured in settings.providers_status.items()
    }


@app.get("/ui/", response_class=HTMLResponse)
def ui_root() -> str:
    return "<!doctype html><title>Kno</title><p>Kno is running; setup not yet completed.</p>"
