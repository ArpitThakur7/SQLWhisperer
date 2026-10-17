"""Google Colab / Local 1-Click Free Fine-Tuning Script using Unsloth.

Trains a 4-bit LoRA adapter on Qwen 2.5 Coder 7B (or 3B) using the harvested
SQLWhisperer datasets for $0.00 on a free Google Colab T4 GPU (16GB VRAM) or local GPU.

Steps:
1. Upload this script and `data/training_datasets/train_chatml.jsonl` to Google Colab.
2. Run: python train_lora_colab.py
3. Download the exported `sqlwhisperer-coder-7b-q4.gguf` to run in local Ollama!
"""

import os
import torch

try:
    from unsloth import FastLanguageModel
    from datasets import load_dataset
    from trl import SFTTrainer
    from transformers import TrainingArguments
except ImportError:
    print("Installing Unsloth and dependencies for Google Colab...")
    os.system("pip install --no-deps 'unsloth[colab-new] @ git+https://github.com/unslothai/unsloth.git'")
    os.system("pip install --no-deps trl peft accelerate bitsandbytes")
    from unsloth import FastLanguageModel
    from datasets import load_dataset
    from trl import SFTTrainer
    from transformers import TrainingArguments


def main():
    print("=" * 60)
    print("🔮 SQLWhisperer Free LoRA Fine-Tuning Pipeline (Unsloth)")
    print("=" * 60)

    # 1. Configuration
    max_seq_length = 2048
    model_name = "unsloth/Qwen2.5-Coder-7B-Instruct-bnb-4bit"
    dataset_path = "train_chatml.jsonl" if os.path.isfile("train_chatml.jsonl") else "data/training_datasets/train_chatml.jsonl"
    output_model_dir = "sqlwhisperer-coder-7b-q4"

    print(f"Loading Base Model: {model_name} in 4-bit...")
    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=model_name,
        max_seq_length=max_seq_length,
        dtype=None,              # Auto detect (float16 for T4, bfloat16 for Ampere)
        load_in_4bit=True,
    )

    # 2. Add LoRA Adapters
    print("Configuring LoRA adapters (Rank=16, Alpha=16)...")
    model = FastLanguageModel.get_peft_model(
        model,
        r=16,
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"],
        lora_alpha=16,
        lora_dropout=0,          # Optimized for Unsloth 0 dropout
        bias="none",
        use_gradient_checkpointing="unsloth",
        random_state=42,
    )

    # 3. Load Harvested Dataset
    print(f"Loading training data from: {dataset_path}...")
    dataset = load_dataset("json", data_files=dataset_path, split="train")
    print(f"Dataset loaded: {len(dataset)} instruction pairs.")

    # Format ChatML messages into prompt string
    def formatting_prompts_func(examples):
        convos = examples["messages"]
        texts = [tokenizer.apply_chat_template(convo, tokenize=False, add_generation_prompt=False) for convo in convos]
        return {"text": texts}

    dataset = dataset.map(formatting_prompts_func, batched=True)

    # 4. Training Arguments
    training_args = TrainingArguments(
        per_device_train_batch_size=2,
        gradient_accumulation_steps=4,
        warmup_steps=10,
        max_steps=120,           # ~15-20 minutes on Colab Free T4 GPU
        learning_rate=2e-4,
        fp16=not torch.cuda.is_bf16_supported(),
        bf16=torch.cuda.is_bf16_supported(),
        logging_steps=10,
        optim="adamw_8bit",
        weight_decay=0.01,
        lr_scheduler_type="cosine",
        seed=42,
        output_dir="outputs",
    )

    print("🚀 Starting Fine-Tuning on Free GPU...")
    trainer = SFTTrainer(
        model=model,
        tokenizer=tokenizer,
        train_dataset=dataset,
        dataset_text_field="text",
        max_seq_length=max_seq_length,
        dataset_num_proc=2,
        args=training_args,
    )

    trainer.train()
    print("✅ Training complete!")

    # 5. Export to GGUF format for Ollama
    print(f"📦 Exporting model to GGUF format for Ollama ({output_model_dir})...")
    model.save_pretrained_gguf(output_model_dir, tokenizer, quantization_method="q4_k_m")

    print("\n" + "=" * 60)
    print("🎉 ALL DONE! MODEL EXPORTED SUCCESSFULLY!")
    print("=" * 60)
    print("Next Steps to run locally in Ollama:")
    print("1. Download the generated `.gguf` file to your PC.")
    print("2. Create a file named `Modelfile` containing:")
    print(f'   FROM ./{output_model_dir}-unsloth.Q4_K_M.gguf')
    print('   SYSTEM "You are a deterministic Text-to-SQL compiler. Generate valid SQL only."')
    print("3. Run in terminal: ollama create sqlwhisperer -f Modelfile")
    print("4. Set in your SQLWhisperer `.env`:")
    print("   LLM_PROVIDER=ollama")
    print("   OLLAMA_MODEL=sqlwhisperer")
    print("=" * 60)


if __name__ == "__main__":
    main()
