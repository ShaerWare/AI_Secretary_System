# merge_lora.py
import torch
from peft import PeftModel
from transformers import AutoModelForCausalLM, AutoTokenizer


base_model_name = "Qwen/Qwen2.5-7B-Instruct"
lora_path = "adapters/qwen2.5-7b-lydia-lora/final"
output_path = "adapters/qwen2.5-7b-lydia-merged"

print("Загрузка базовой модели...")
model = AutoModelForCausalLM.from_pretrained(
    base_model_name,
    torch_dtype=torch.bfloat16,
    device_map="cpu",  # На CPU для merge
    trust_remote_code=True,
)

print("Загрузка LoRA адаптеров...")
model = PeftModel.from_pretrained(model, lora_path)

print("Объединение весов...")
model = model.merge_and_unload()

print("Сохранение объединённой модели...")
model.save_pretrained(output_path)

tokenizer = AutoTokenizer.from_pretrained(base_model_name)
tokenizer.save_pretrained(output_path)

print(f"✅ Готово! Модель сохранена в {output_path}")
