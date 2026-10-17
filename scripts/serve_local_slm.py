"""Local OpenAI-Compatible Server for SQLWhisperer Fine-Tuned SLM.

Serves the RTX 4050 fine-tuned LoRA model on an OpenAI-compatible API endpoint:
    http://localhost:8001/v1/chat/completions

Allows SQLWhisperer UI and API to generate SQL queries completely locally & offline
without needing Ollama, Docker, or external cloud keys.

Usage:
    python scripts/serve_local_slm.py
"""

from __future__ import annotations

import os
import sys
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

import torch

# PyTorch 2.6.0 polyfill for Transformers 5.x
if not hasattr(torch, "float8_e8m0fnu"):
    setattr(torch, "float8_e8m0fnu", getattr(torch, "float8_e4m3fn", torch.uint8))

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
import uvicorn
from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
from peft import PeftModel

BASE_DIR = Path(__file__).resolve().parent.parent
LORA_PATH = BASE_DIR / "models" / "sqlwhisperer-slm-lora"
BASE_MODEL_CACHE = (
    Path.home()
    / ".cache"
    / "modelscope"
    / "models"
    / "qwen--Qwen2.5-Coder-1.5B-Instruct"
    / "snapshots"
    / "master"
)

app = FastAPI(title="SQLWhisperer Local SLM Server", version="1.0.0")

model = None
tokenizer = None


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatCompletionRequest(BaseModel):
    model: str = "sqlwhisperer-slm"
    messages: List[ChatMessage]
    temperature: Optional[float] = 0.05
    top_p: Optional[float] = 0.95
    max_tokens: Optional[int] = 512
    stream: Optional[bool] = False


def load_model():
    global model, tokenizer
    if model is not None:
        return

    # Dynamically detect base model from adapter_config.json
    base_source = str(BASE_MODEL_CACHE)
    adapter_cfg_file = LORA_PATH / "adapter_config.json"
    if adapter_cfg_file.is_file():
        try:
            with open(adapter_cfg_file, "r", encoding="utf-8") as f:
                cfg_data = json.load(f)
                b_path = cfg_data.get("base_model_name_or_path")
                if b_path and (Path(b_path).exists() or not b_path.startswith("C:")):
                    base_source = b_path
        except Exception:
            pass

    print("=" * 65)
    print("[*] Initializing SQLWhisperer Local SLM Engine on RTX 4050...")
    print(f"    Base Model: {base_source}")
    print(f"    LoRA Path:  {LORA_PATH}")
    print("=" * 65)

    bnb_config = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_compute_dtype=torch.bfloat16,
        bnb_4bit_use_double_quant=True,
    )

    tokenizer = AutoTokenizer.from_pretrained(base_source, trust_remote_code=True)
    base = AutoModelForCausalLM.from_pretrained(
        base_source,
        quantization_config=bnb_config,
        device_map={"": 0},
        dtype=torch.bfloat16,
        low_cpu_mem_usage=True,
        trust_remote_code=True,
    )

    if LORA_PATH.is_dir():
        print(f"[*] Attaching fine-tuned LoRA adapter from {LORA_PATH}...")
        model = PeftModel.from_pretrained(base, str(LORA_PATH))
    else:
        print("[!] LoRA adapter not found, using base model directly.")
        model = base

    model.eval()
    print("[+] Model loaded successfully and ready for inference on cuda:0!\n")


@app.on_event("startup")
def startup_event():
    load_model()


@app.get("/health")
@app.get("/v1/health")
def health():
    return {"status": "ok", "device": torch.cuda.get_device_name(0), "model": "sqlwhisperer-slm"}


@app.get("/v1/models")
def list_models():
    return {
        "object": "list",
        "data": [
            {
                "id": "sqlwhisperer-slm",
                "object": "model",
                "created": int(time.time()),
                "owned_by": "sqlwhisperer-local",
            }
        ],
    }


@app.post("/v1/chat/completions")
def chat_completions(request: ChatCompletionRequest):
    global model, tokenizer
    if model is None or tokenizer is None:
        raise HTTPException(status_code=503, detail="Model is still initializing")

    # Format messages using Qwen ChatML template
    convo = [{"role": m.role, "content": m.content} for m in request.messages]
    input_text = tokenizer.apply_chat_template(convo, tokenize=False, add_generation_prompt=True)
    inputs = tokenizer(input_text, return_tensors="pt").to("cuda:0")

    with torch.no_grad():
        outputs = model.generate(
            **inputs,
            max_new_tokens=min(request.max_tokens or 192, 256),
            do_sample=False,
            repetition_penalty=1.1,
            pad_token_id=tokenizer.eos_token_id,
        )

    # Decode assistant response
    generated_ids = outputs[0][inputs.input_ids.shape[1]:]
    response_content = tokenizer.decode(generated_ids, skip_special_tokens=True).strip()

    req_id = f"chatcmpl-{uuid.uuid4().hex[:12]}"
    return {
        "id": req_id,
        "object": "chat.completion",
        "created": int(time.time()),
        "model": request.model,
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": response_content,
                },
                "finish_reason": "stop",
            }
        ],
        "usage": {
            "prompt_tokens": len(inputs.input_ids[0]),
            "completion_tokens": len(generated_ids),
            "total_tokens": len(inputs.input_ids[0]) + len(generated_ids),
        },
    }


if __name__ == "__main__":
    port = int(os.getenv("SLM_PORT", "8001"))
    print(f"[*] Starting SQLWhisperer Local SLM Server on http://0.0.0.0:{port}...")
    uvicorn.run(app, host="0.0.0.0", port=port)
