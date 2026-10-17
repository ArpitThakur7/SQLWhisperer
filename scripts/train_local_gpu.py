"""SQLWhisperer Local GPU Fine-Tuning Pipeline.

Optimized for NVIDIA GeForce RTX 4050 (6GB VRAM) and consumer laptop GPUs.
Uses HuggingFace PEFT + bitsandbytes 4-bit QLoRA to fine-tune Qwen 2.5 Coder 1.5B/3B
on the curated SQLWhisperer dataset directly on Windows without Linux/WSL dependencies.

Memory Budget (6GB VRAM):
- 4-bit Base Model: ~1.1 GB VRAM
- LoRA Adapters (r=16): ~30 MB VRAM
- Activations (Seq Len 1024, Batch Size 1, Grad Accum 8): ~1.8 GB VRAM
- Total Peak VRAM: ~3.0 GB (fits comfortably in 6GB)
"""

from __future__ import annotations

import os
import sys
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from pathlib import Path
import torch

# Compatibility polyfill: PyTorch 2.6.0 with Transformers 5.x
if not hasattr(torch, "float8_e8m0fnu"):
    setattr(torch, "float8_e8m0fnu", getattr(torch, "float8_e4m3fn", torch.uint8))

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_PATH = BASE_DIR / "data" / "training_datasets" / "slm_prepared" / "train_slm_curated.jsonl"
VAL_PATH = BASE_DIR / "data" / "training_datasets" / "slm_prepared" / "val_slm_curated.jsonl"
OUTPUT_DIR = BASE_DIR / "models" / "sqlwhisperer-slm-lora"


def check_gpu():
    if not torch.cuda.is_available():
        print("\n[!] CUDA is not detected by PyTorch!")
        print("    Your machine HAS an NVIDIA RTX 4050 GPU, but you currently have the CPU-only build of PyTorch.")
        print("    Run this command in terminal to enable GPU:")
        print("    pip install torch --index-url https://download.pytorch.org/whl/cu124\n")
        sys.exit(1)

    device_name = torch.cuda.get_device_name(0)
    total_vram = torch.cuda.get_device_properties(0).total_memory / (1024 ** 3)
    print(f"[*] Detected GPU: {device_name} ({total_vram:.2f} GB VRAM)")


def main():
    check_gpu()

    try:
        from datasets import load_dataset
        from transformers import (
            AutoModelForCausalLM,
            AutoTokenizer,
            BitsAndBytesConfig,
            TrainingArguments,
        )
        from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training
        from trl import SFTTrainer
    except ImportError as e:
        print(f"\n[!] Missing fine-tuning packages: {e}")
        print("    Install them with:")
        print("    pip install peft trl accelerate bitsandbytes datasets\n")
        sys.exit(1)

    # 1. Configuration
    model_id = os.getenv("LOCAL_BASE_MODEL", "qwen/Qwen2.5-Coder-1.5B-Instruct")
    max_seq_length = 1024  # Tailored for 6GB VRAM
    max_steps = int(os.getenv("TRAIN_STEPS", "150"))  # ~15 min on RTX 4050

    print("=" * 65)
    print(f"[*] SQLWhisperer Local GPU Training on {torch.cuda.get_device_name(0)}")
    print(f"   Base Model:     {model_id}")
    print(f"   Dataset:        {DATA_PATH}")
    print(f"   Max Seq Length: {max_seq_length}")
    print(f"   Train Steps:    {max_steps}")
    print("=" * 65)

    if not DATA_PATH.is_file():
        print(f"[!] Dataset not found at {DATA_PATH}. Run scripts/prepare_slm_data.py first.")
        sys.exit(1)

    # Resolve model directory via ModelScope (fast, unblocked, avoids HF network resets)
    try:
        from modelscope import snapshot_download
        print(f"[*] Checking local model cache for '{model_id}' via ModelScope...")
        model_source = snapshot_download(model_id)
        print(f"[*] Base model ready at: {model_source}")
    except Exception as e:
        print(f"[!] ModelScope note ({e}), using direct model ID: {model_id}")
        model_source = model_id

    # 2. 4-bit Quantization Config (bitsandbytes QLoRA)
    bnb_config = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_compute_dtype=torch.float16,
        bnb_4bit_use_double_quant=True,
    )

    print(f"[*] Loading tokenizer: {model_source}...")
    tokenizer = AutoTokenizer.from_pretrained(model_source, trust_remote_code=True)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    print(f"[*] Loading base model in 4-bit NF4...")
    model = AutoModelForCausalLM.from_pretrained(
        model_source,
        quantization_config=bnb_config,
        device_map="auto",
        trust_remote_code=True,
    )

    model = prepare_model_for_kbit_training(model)
    model.gradient_checkpointing_enable()

    # 3. LoRA Configuration
    peft_config = LoraConfig(
        r=16,
        lora_alpha=16,
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"],
        lora_dropout=0.05,
        bias="none",
        task_type="CAUSAL_LM",
    )

    model = get_peft_model(model, peft_config)
    model.print_trainable_parameters()

    # 4. Load Dataset
    print(f"[*] Loading dataset: {DATA_PATH}...")
    dataset = load_dataset("json", data_files=str(DATA_PATH), split="train")

    def format_chatml(example):
        texts = [tokenizer.apply_chat_template(convo, tokenize=False, add_generation_prompt=False) for convo in example["messages"]]
        return {"text": texts}

    dataset = dataset.map(format_chatml, batched=True)

    val_dataset = None
    if VAL_PATH.is_file():
        val_dataset = load_dataset("json", data_files=str(VAL_PATH), split="train")
        val_dataset = val_dataset.map(format_chatml, batched=True)

    # 5. Training Arguments (optimized for 6GB VRAM)
    training_args = TrainingArguments(
        output_dir=str(OUTPUT_DIR / "checkpoints"),
        per_device_train_batch_size=1,       # 1 sample per step to save VRAM
        gradient_accumulation_steps=8,       # Effective batch size = 8
        warmup_steps=10,
        max_steps=max_steps,
        learning_rate=2e-4,
        fp16=True,
        bf16=False,
        logging_steps=10,
        eval_strategy="steps" if val_dataset else "no",
        eval_steps=40 if val_dataset else None,
        optim="paged_adamw_8bit",            # Paged 8-bit optimizer uses minimal VRAM
        lr_scheduler_type="cosine",
        save_strategy="steps",
        save_steps=100,
        save_total_limit=1,
        report_to="none",
        seed=42,
    )

    trainer = SFTTrainer(
        model=model,
        tokenizer=tokenizer,
        train_dataset=dataset,
        eval_dataset=val_dataset,
        dataset_text_field="text",
        max_seq_length=max_seq_length,
        args=training_args,
    )

    print("\n[+] Starting Local Fine-Tuning on RTX 4050...")
    trainer.train()

    print(f"\n[+] Saving fine-tuned LoRA adapter to: {OUTPUT_DIR}...")
    model.save_pretrained(str(OUTPUT_DIR))
    tokenizer.save_pretrained(str(OUTPUT_DIR))
    print("[+] Local Fine-Tuning Complete!")


if __name__ == "__main__":
    main()
