"""
AlphaForge Web — FastAPI backend serving the browser demo.

Run:
    export CMC_API_KEY=your_key_here
    python web/server.py
"""
import hashlib
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from alphaforge import generate_strategy
from alphaforge.visualizer import plot_results

CMC_API_KEY = os.getenv("CMC_API_KEY")

STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
CHARTS_DIR = os.path.join(STATIC_DIR, "charts")
os.makedirs(CHARTS_DIR, exist_ok=True)

app = FastAPI(title="AlphaForge API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class GenerateRequest(BaseModel):
    input: str


@app.get("/")
def index():
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))


@app.post("/api/generate")
def generate(req: GenerateRequest):
    if not CMC_API_KEY:
        raise HTTPException(500, "Server is missing CMC_API_KEY. Set the environment variable and restart.")
    user_input = req.input.strip()
    if not user_input:
        raise HTTPException(400, "Strategy intent text is required.")

    try:
        result = generate_strategy(user_input, CMC_API_KEY)
    except Exception as exc:
        raise HTTPException(502, f"Strategy generation failed: {exc}") from exc

    ohlcv = result.pop("_ohlcv", [])

    chart_url = None
    download_name = None
    try:
        chart_name = f"{hashlib.sha1(user_input.encode()).hexdigest()[:10]}_{int(time.time())}.png"
        chart_path = os.path.join(CHARTS_DIR, chart_name)
        plot_results(result, ohlcv, output_path=chart_path)
        chart_url = f"/static/charts/{chart_name}"
        asset = result["intent"]["asset"]
        timeframe = result["intent"]["timeframe"]
        regime = result["regime"]["primary"]
        download_name = f"AlphaForge_{asset}_{timeframe}_{regime}.png"
    except Exception:
        chart_url = None

    result["chart_url"] = chart_url
    result["chart_download_name"] = download_name
    return result


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


if __name__ == "__main__":
    import uvicorn

    if not CMC_API_KEY:
        sys.exit("Error: set the CMC_API_KEY environment variable before running the web server.")
    port = int(os.getenv("PORT", 8800))
    uvicorn.run(app, host="0.0.0.0", port=port)
