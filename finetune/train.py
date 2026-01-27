# train.py — дообучение Qwen2.5-7B-Instruct на датасете lydia_dataset_v2.jsonl

import os


os.environ["CUDA_VISIBLE_DEVICES"] = "1"  # RTX 3060 ДО импорта torch
os.environ["CUDA_DEVICE_ORDER"] = "PCI_BUS_ID"
os.environ["PYTORCH_CUDA_ALLOC_CONF"] = "expandable_segments:True"  # против фрагментации

import torch
from datasets import load_dataset
from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training
from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig, TrainingArguments
from trl import SFTTrainer


print("Используемое устройство:", torch.cuda.current_device(), torch.cuda.get_device_name(0))

# ==================== НАСТРОЙКИ ====================
model_name = "Qwen/Qwen2.5-7B-Instruct"
dataset_path = "datasets/lydia_dataset_v3.jsonl"  # полный датасет (из result.json)
# dataset_path = "datasets/lydia_dataset_v2.jsonl" # старый датасет

output_dir = "adapters/qwen2.5-7b-lydia-lora"

max_seq_length = 768  # Уменьшено для экономии памяти (было 2048)
load_in_4bit = True
lora_rank = 8  # Уменьшено с 32 для меньшего потребления VRAM
batch_size = 1
gradient_accumulation_steps = 64  # Увеличено с 16 для реже обновлений градиентов
learning_rate = 2e-4
num_epochs = 1  # для первого прогона 1 эпоха
# ====================================================


# Мониторинг памяти
def print_gpu_memory():
    print(f"GPU memory allocated: {torch.cuda.memory_allocated() / 1024**3:.2f} GiB")
    print(f"GPU memory reserved: {torch.cuda.memory_reserved() / 1024**3:.2f} GiB")


quant_config = BitsAndBytesConfig(
    load_in_4bit=load_in_4bit,
    bnb_4bit_quant_type="nf4",
    bnb_4bit_compute_dtype=torch.bfloat16,
    bnb_4bit_use_double_quant=True,  # Включено для дополнительной экономии памяти
)

tokenizer = AutoTokenizer.from_pretrained(model_name)
tokenizer.pad_token = tokenizer.eos_token

model = AutoModelForCausalLM.from_pretrained(
    model_name,
    quantization_config=quant_config,
    device_map="cuda:0",  # cuda:0 = RTX 3060 после переменной выше
    torch_dtype=torch.bfloat16,
    trust_remote_code=True,
)

print("После загрузки модели:")
print_gpu_memory()

model = prepare_model_for_kbit_training(model)

lora_config = LoraConfig(
    r=lora_rank,
    lora_alpha=16,
    target_modules=["q_proj", "k_proj", "v_proj"],
    lora_dropout=0.05,
    bias="none",
    task_type="CAUSAL_LM",
)

model = get_peft_model(model, lora_config)

dataset = load_dataset("json", data_files=dataset_path, split="train")


def formatting_prompts_func(examples):
    texts = []
    for messages in examples["messages"]:
        chat = []
        for msg in messages:
            role = "user" if msg["from"] == "user" else "assistant"
            content = msg["value"]
            if isinstance(content, dict) and "text" in content:
                content = content["text"]
            chat.append({"role": role, "content": content})

        formatted = tokenizer.apply_chat_template(chat, tokenize=False, add_generation_prompt=False)
        texts.append(formatted)
    return {"text": texts}


dataset = dataset.map(formatting_prompts_func, batched=True, remove_columns=dataset.column_names)

training_args = TrainingArguments(
    output_dir=output_dir,
    num_train_epochs=num_epochs,
    per_device_train_batch_size=batch_size,
    gradient_accumulation_steps=gradient_accumulation_steps,
    learning_rate=learning_rate,
    bf16=True,
    logging_steps=10,
    save_steps=200,
    optim="paged_adamw_8bit",  # Оптимизатор с пейджингом для лучшей памяти
    report_to="none",
    gradient_checkpointing=True,
    max_grad_norm=0.3,
    warmup_ratio=0.03,
)

trainer = SFTTrainer(
    model=model,
    tokenizer=tokenizer,
    train_dataset=dataset,
    dataset_text_field="text",
    max_seq_length=max_seq_length,
    args=training_args,
    packing=False,
)

# Очистка кэша перед обучением
torch.cuda.empty_cache()
print("Перед обучением после очистки:")
print_gpu_memory()

trainer.train()
trainer.save_model(output_dir + "/final")
tokenizer.save_pretrained(output_dir + "/final")
