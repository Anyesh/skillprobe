import httpx


class HttpLLMClient:
    def __init__(
        self,
        anthropic_base_url: str = "https://api.anthropic.com",
        openai_base_url: str = "https://api.openai.com",
        anthropic_api_key: str = "",
        openai_api_key: str = "",
    ):
        self._anthropic_url = anthropic_base_url
        self._openai_url = openai_base_url
        self._anthropic_key = anthropic_api_key
        self._openai_key = openai_api_key
        self._client = httpx.AsyncClient(timeout=120.0)

    async def call(self, system: str, message: str, model: str, provider: str) -> str:
        if provider == "openai":
            return await self._call_openai(system, message, model)
        return await self._call_anthropic(system, message, model)

    async def _call_anthropic(self, system: str, message: str, model: str) -> str:
        resp = await self._client.post(
            f"{self._anthropic_url}/v1/messages",
            json={
                "model": model,
                "max_tokens": 4096,
                "system": system,
                "messages": [{"role": "user", "content": message}],
            },
            headers={
                "x-api-key": self._anthropic_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
        )
        resp.raise_for_status()
        data = resp.json()
        return "\n".join(
            block["text"] for block in data.get("content", [])
            if block.get("type") == "text"
        )

    async def _call_openai(self, system: str, message: str, model: str) -> str:
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": message})
        resp = await self._client.post(
            f"{self._openai_url}/v1/chat/completions",
            json={"model": model, "messages": messages},
            headers={
                "authorization": f"Bearer {self._openai_key}",
                "content-type": "application/json",
            },
        )
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"]

    async def close(self):
        await self._client.aclose()
