"""Load the pinned, packaged model without contacting Hugging Face at runtime."""

import asyncio

import uvicorn
from strands_decider.server import create_app

app = create_app(
    "/opt/models/decider",
    device="cpu",
    model_name="strands-decider-2B-hobson-v19",
    strict_window=True,
    max_batch=8,
)
lock = asyncio.Lock()


@app.middleware("http")
async def serialize_inference(request, call_next):
    # Also serialize here so an API timeout cannot overlap two model evaluations.
    if request.url.path == "/v1/systemone":
        async with lock:
            return await call_next(request)
    return await call_next(request)


if __name__ == "__main__":
    # The API sidecar shares the task network namespace. No model port is published.
    uvicorn.run(app, host="127.0.0.1", port=8099, workers=1, access_log=False)
