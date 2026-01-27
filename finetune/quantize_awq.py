from llmcompressor import oneshot
from llmcompressor.modifiers.quantization import QuantizationModifier
from transformers import AutoTokenizer


model_path = "adapters/qwen2.5-7b-lydia-merged"
quant_path = "adapters/qwen2.5-7b-lydia-w4a16"

recipe = QuantizationModifier(
    targets="Linear",
    scheme="W4A16",
    ignore=["lm_head"],
)

print("Квантизация W4A16... (10-30 минут)")
oneshot(
    model=model_path,
    dataset="ultrachat_200k",
    recipe=recipe,
    output_dir=quant_path,
    num_calibration_samples=512,
    max_seq_length=1024,
)

tokenizer = AutoTokenizer.from_pretrained(model_path)
tokenizer.save_pretrained(quant_path)
print(f"✅ Готово: {quant_path}")
