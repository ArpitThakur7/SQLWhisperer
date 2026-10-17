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
        import datasets
        import transformers.utils.logging
        datasets.disable_progress_bar()
        transformers.utils.logging.disable_progress_bar()

        from transformers import (
            AutoModelForCausalLM,
            AutoTokenizer,
            BitsAndBytesConfig,
            TrainerCallback,
        )
        from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training
        from trl import SFTTrainer, SFTConfig
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
        bnb_4bit_compute_dtype=torch.bfloat16,
        bnb_4bit_use_double_quant=True,
    )

    print(f"[*] Loading tokenizer: {model_source}...")
    tokenizer = AutoTokenizer.from_pretrained(model_source, trust_remote_code=True)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    print(f"[*] Loading base model in 4-bit NF4 directly into RTX 4050...")
    model = AutoModelForCausalLM.from_pretrained(
        model_source,
        quantization_config=bnb_config,
        device_map={"": 0},
        dtype=torch.bfloat16,
        low_cpu_mem_usage=True,
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

    # 5. Non-Flooding 10-Second Progress Callback
    import datetime
    import time

    class TenSecondProgressCallback(TrainerCallback):
        """Displays progress strictly every 10 seconds to eliminate terminal flooding."""
        def __init__(self, total_steps: int):
            self.total_steps = total_steps
            self.last_print_time = 0.0
            self.start_time = None

        def on_train_begin(self, args, state, control, **kwargs):
            self.start_time = time.time()
            self.last_print_time = self.start_time
            print(f"\n[*] Training launched on RTX 4050: {self.total_steps} total steps.")
            print(f"[*] Showing progress updates every 10 seconds (no flooding)...\n")
            sys.stdout.flush()

        def on_step_end(self, args, state, control, **kwargs):
            current_time = time.time()
            step = state.global_step
            # Trigger every 10 seconds, on step 1, or on the final step
            if (current_time - self.last_print_time >= 10.0) or (step == 1) or (step >= self.total_steps):
                self.last_print_time = current_time
                elapsed = current_time - self.start_time if self.start_time else 0
                pct = (step / self.total_steps) * 100 if self.total_steps else 0.0

                if step > 0:
                    sec_per_step = elapsed / step
                    rem_sec = max(0, (self.total_steps - step) * sec_per_step)
                    eta_str = str(datetime.timedelta(seconds=int(rem_sec)))
                else:
                    eta_str = "--:--"

                elapsed_str = str(datetime.timedelta(seconds=int(elapsed)))

                bar_len = 25
                filled = int(bar_len * (pct / 100))
                bar = "=" * filled + "-" * (bar_len - filled)

                loss_str = "Loss: ----"
                if state.log_history:
                    for entry in reversed(state.log_history):
                        if "loss" in entry:
                            loss_str = f"Loss: {entry['loss']:.4f}"
                            break

                now_str = datetime.datetime.now().strftime("%H:%M:%S")
                print(f"[{now_str}] [{bar}] {pct:5.1f}% | Step {step:>3}/{self.total_steps} | {loss_str} | Elapsed: {elapsed_str} | ETA: {eta_str}")
                sys.stdout.flush()

    # 6. Training Arguments (BF16 native on RTX 4050, 10s non-flooding progress)
    training_args = SFTConfig(
        output_dir=str(OUTPUT_DIR / "checkpoints"),
        dataset_text_field="text",
        max_length=max_seq_length,
        per_device_train_batch_size=1,       # 1 sample per step to save VRAM
        gradient_accumulation_steps=8,       # Effective batch size = 8
        warmup_steps=10,
        max_steps=max_steps,
        learning_rate=2e-4,
        fp16=False,
        bf16=True,                           # Native BF16 on Ada Lovelace RTX 4050 (avoids GradScaler)
        logging_steps=10,
        disable_tqdm=True,                   # Suppresses 1-second high frequency tqdm flooding
        eval_strategy="no",
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
        processing_class=tokenizer,
        train_dataset=dataset,
        eval_dataset=val_dataset,
        args=training_args,
        callbacks=[TenSecondProgressCallback(total_steps=max_steps)],
    )

    print("\n[+] Starting Local Fine-Tuning on RTX 4050...")
    trainer.train()

    print(f"\n[+] Saving fine-tuned LoRA adapter to: {OUTPUT_DIR}...")
    model.save_pretrained(str(OUTPUT_DIR))
    tokenizer.save_pretrained(str(OUTPUT_DIR))
    print("[+] Local Fine-Tuning Complete!")


if __name__ == "__main__":
    main()
