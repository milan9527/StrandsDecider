"""Load the pinned, packaged model without contacting Hugging Face at runtime."""

import asyncio
import os

import uvicorn
from strands_decider.schema import SystemOneRequest
from strands_decider.server import create_app, get_engine

device = os.getenv("DECIDER_DEVICE", "cpu")

app = create_app(
    "/opt/models/decider",
    device=device,
    model_name="strands-decider-2B-hobson-v19",
    strict_window=True,
    max_batch=8,
)
if device == "cuda":
    # Compile CUDA kernels before advertising health to ECS and accepting paid requests.
    get_engine().evaluate(
        SystemOneRequest(
            state="A confirmed payment matches its order.",
            questions={"matches": {"type": "noul", "instructions": "Does the payment match?"}},
        )
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
    uvicorn.run(
        app, host=os.getenv("MODEL_HOST", "127.0.0.1"), port=8099, workers=1, access_log=False
    )
