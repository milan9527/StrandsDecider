"""SageMaker HTTP contract around the unchanged, serialized Decider server."""

import httpx
import uvicorn
from fastapi import FastAPI, Request, Response


def create_gateway(model_app):
    gateway = FastAPI()

    async def forward(path, payload=None):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=model_app), base_url="http://model", timeout=55
        ) as client:
            response = (
                await client.get(path) if payload is None else await client.post(path, json=payload)
            )
        return Response(
            content=response.content,
            status_code=response.status_code,
            media_type="application/json",
        )

    @gateway.api_route("/ping", methods=["GET", "POST"])
    async def ping():
        return await forward("/health")

    @gateway.post("/invocations")
    async def invoke(request: Request):
        try:
            payload = await request.json()
        except ValueError:
            return Response('{"detail":"Invalid JSON"}', status_code=422)
        if payload == {"operation": "health"}:
            return await forward("/health")
        return await forward("/v1/systemone", payload)

    return gateway


if __name__ == "__main__":
    from model_server import app

    uvicorn.run(create_gateway(app), host="0.0.0.0", port=8080, workers=1, access_log=False)
