# augment_dataset.py
import json

from tqdm import tqdm


INPUT_JSONL = "lydia_dataset.jsonl"
OUTPUT_JSONL = "lydia_augmented.jsonl"


def is_contradictory(example):
    # Простая проверка на противоречие промпту: длина ответа >2 предложений или отсутствие «ё» где должно быть
    assistant_msgs = [m["value"] for m in example["messages"] if m["from"] == "assistant"]
    for msg in assistant_msgs:
        sentences = msg.split(". ")  # грубая проверка
        if len(sentences) > 2 or (
            "е" in msg.lower() and "ё" not in msg.lower()
        ):  # пример: отсутствие «ё»
            return True
    return False


# Загружаем и аугментируем
examples = []
with open(INPUT_JSONL, encoding="utf-8") as f:
    for line in tqdm(f):
        ex = json.loads(line)
        examples.append(ex)
        if is_contradictory(ex):
            examples.append(ex)  # дублируем 1 раз (можно 2-3 для усиления)

with open(OUTPUT_JSONL, "w", encoding="utf-8") as f:
    for ex in examples:
        f.write(json.dumps(ex, ensure_ascii=False) + "\n")

print(f"Аугментировано: {len(examples)} примеров")
