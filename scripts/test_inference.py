"""Test Inference with Fine-Tuned SQLWhisperer SLM LoRA Adapter.
Loads 4-bit base model + LoRA adapter onto RTX 4050 and runs live SQL generation.
"""

import sys
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

from pathlib import Path
import torch

# Compatibility polyfill
if not hasattr(torch, "float8_e8m0fnu"):
    setattr(torch, "float8_e8m0fnu", getattr(torch, "float8_e4m3fn", torch.uint8))

from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
from peft import PeftModel

BASE_DIR = Path(__file__).resolve().parent.parent
LORA_PATH = BASE_DIR / "models" / "sqlwhisperer-slm-lora"
BASE_MODEL_CACHE = Path.home() / ".cache" / "modelscope" / "models" / "qwen--Qwen2.5-Coder-1.5B-Instruct" / "snapshots" / "master"

def main():
    print("=" * 65)
    print("[*] Testing SQLWhisperer Fine-Tuned SLM on RTX 4050 GPU")
    print("=" * 65)

    bnb_config = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_compute_dtype=torch.bfloat16,
        bnb_4bit_use_double_quant=True,
    )

    print(f"[*] Loading Tokenizer and Base Model ({BASE_MODEL_CACHE})...")
    tokenizer = AutoTokenizer.from_pretrained(str(BASE_MODEL_CACHE), trust_remote_code=True)
    base_model = AutoModelForCausalLM.from_pretrained(
        str(BASE_MODEL_CACHE),
        quantization_config=bnb_config,
        device_map={"": 0},
        dtype=torch.bfloat16,
        low_cpu_mem_usage=True,
        trust_remote_code=True,
    )

    print(f"[*] Attaching LoRA Adapter from: {LORA_PATH}...")
    model = PeftModel.from_pretrained(base_model, str(LORA_PATH))
    model.eval()

    test_queries = [
        {
            "question": "Find the top 5 customers who have spent the most total money on completed orders.",
            "schema": "CREATE TABLE customers (id INT PRIMARY KEY, name VARCHAR(100), email VARCHAR(100));\nCREATE TABLE orders (id INT PRIMARY KEY, customer_id INT, total_amount DECIMAL(10,2), status VARCHAR(20), order_date TIMESTAMP);"
        },
        {
            "question": "Show all employees in the 'Engineering' department whose salary is above the average salary of their department.",
            "schema": "CREATE TABLE departments (dept_id INT PRIMARY KEY, dept_name VARCHAR(50));\nCREATE TABLE employees (emp_id INT PRIMARY KEY, name VARCHAR(100), dept_id INT, salary NUMERIC(10,2));"
        }
    ]

    system_prompt = (
        "You are SQLWhisperer, an expert enterprise SQL query generator. "
        "Given the database schema DDL and a user question, generate a syntactically correct, "
        "production-grade PostgreSQL query. Return ONLY the raw SQL enclosed in ```sql markdown codeblocks. "
        "Do NOT hallucinate tables or columns."
    )

    for i, item in enumerate(test_queries, 1):
        prompt_text = f"### Database Schema (DDL):\n{item['schema']}\n\n### User Question:\n{item['question']}\n\n### SQL Query:"
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt_text}
        ]

        input_text = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        inputs = tokenizer(input_text, return_tensors="pt").to("cuda:0")

        with torch.no_grad():
            outputs = model.generate(
                **inputs,
                max_new_tokens=256,
                temperature=0.1,
                top_p=0.9,
                repetition_penalty=1.1,
                do_sample=False,
            )

        response = tokenizer.decode(outputs[0][inputs.input_ids.shape[1]:], skip_special_tokens=True).strip()
        print(f"\n--- [Test Query {i}] ---")
        print(f"Question: {item['question']}")
        print(f"Generated SQL:\n{response}")

    print("\n" + "=" * 65)
    print("[+] All Inference Tests Succeeded!")
    print("=" * 65)

if __name__ == "__main__":
    main()
