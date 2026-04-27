from __future__ import annotations

import os
import sys
import time
from dataclasses import dataclass, field

from openai import APIError
from resmgr import vllm_client


@dataclass
class LLMUsage:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    calls: int = 0

    def add(self, pt: int, ct: int) -> None:
        self.prompt_tokens += pt
        self.completion_tokens += ct
        self.calls += 1

    def total(self) -> int:
        return self.prompt_tokens + self.completion_tokens


@dataclass
class LLMClient:
    model: str = os.environ.get("EVO_MODEL", "Qwen/Qwen2.5-32B-Instruct")
    timeout: float = 120.0
    vllm_kwargs: dict | None = None
    usage: LLMUsage = field(default_factory=LLMUsage)

    def __post_init__(self) -> None:
        kwargs = dict(self.vllm_kwargs or {})
        kwargs.setdefault("max_model_len", 16384)
        self._client = vllm_client(self.model, **kwargs)
        self._client.timeout = self.timeout

    @property
    def base_url(self) -> str:
        return str(self._client.base_url)

    def chat(
        self,
        system: str,
        user: str,
        temperature: float = 0.2,
        max_tokens: int = 1024,
        response_format: dict | None = None,
        retries: int = 3,
        stop: list[str] | None = None,
    ) -> tuple[str, int, int]:
        msgs = [{"role": "system", "content": system}, {"role": "user", "content": user}]
        last_err: Exception | None = None
        for attempt in range(retries):
            try:
                kwargs: dict = dict(
                    model=self.model,
                    messages=msgs,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
                if response_format is not None:
                    kwargs["response_format"] = response_format
                if stop is not None:
                    kwargs["stop"] = stop
                resp = self._client.chat.completions.create(**kwargs)
                text = resp.choices[0].message.content or ""
                pt = resp.usage.prompt_tokens if resp.usage else 0
                ct = resp.usage.completion_tokens if resp.usage else 0
                self.usage.add(pt, ct)
                return text, pt, ct
            except APIError as e:
                last_err = e
                time.sleep(1.5 * (attempt + 1))
        raise RuntimeError(f"LLM call failed after {retries} retries: {last_err}")


def _smoke() -> int:
    c = LLMClient()
    print(f"model={c.model} base_url={c.base_url}")
    t0 = time.time()
    text, pt, ct = c.chat(
        system="You are a helpful assistant.",
        user="Reply with exactly: 'pong'.",
        temperature=0.0,
        max_tokens=16,
    )
    dt = time.time() - t0
    print(f"[{dt:.2f}s] pt={pt} ct={ct} reply={text!r}")
    return 0 if "pong" in text.lower() else 1


if __name__ == "__main__":
    if len(sys.argv) >= 2 and sys.argv[1] == "--smoke":
        sys.exit(_smoke())
    print("usage: python -m src.llm --smoke")
    sys.exit(2)
