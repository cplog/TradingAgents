"""Entrypoint: python -m api"""
import os

import uvicorn

if __name__ == "__main__":
    port = int(os.environ.get("BACKEND_PORT", os.environ.get("TRADINGAGENTS_API_PORT", "8808")))
    uvicorn.run("api.main:app", host="0.0.0.0", port=port, reload=False)
