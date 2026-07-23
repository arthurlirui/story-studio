#!/usr/bin/env python3
"""
🔧 合并 LoRA adapter 到基座模型并保存到磁盘

用法:
    python3 merge_lora.py
"""
from __future__ import annotations

import gc
import logging
import shutil
from pathlib import Path

import torch
from transformers import AutoTokenizer, AutoModelForCausalLM
from peft import PeftModel

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("merge-lora")

# ── 配置 ────────────────────────────────────────────────────────
BASE_MODEL = "/data/openclaw/workspace/model/Qwen3.5-9B"
LORA_PATH = "/data/openclaw/workspace/lora-style-transfer/output/adapters/moyan-style-lora-9b"
OUTPUT_DIR = "/data/openclaw/workspace/model/Qwen3.5-9B-moyan-merged"

# 保存精度: fp16 (推荐，Ollama 转 GGUF 时用 fp16)
SAVE_DTYPE = torch.float16


def main():
    print(f"\n{'='*60}")
    print(f"🔧 LoRA 模型合并工具")
    print(f"{'='*60}")
    print(f"  基座模型: {BASE_MODEL}")
    print(f"  LoRA:     {LORA_PATH}")
    print(f"  输出目录: {OUTPUT_DIR}")
    print(f"  保存精度: fp16")
    print(f"{'='*60}\n")

    # 1. 加载 tokenizer
    logger.info("加载 tokenizer...")
    tokenizer = AutoTokenizer.from_pretrained(BASE_MODEL, trust_remote_code=True)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    # 2. 加载基座模型 (fp16, 单卡)
    logger.info("加载基座模型 (fp16)...")
    model = AutoModelForCausalLM.from_pretrained(
        BASE_MODEL,
        device_map={"": 0},
        torch_dtype=torch.float16,
        trust_remote_code=True,
    )
    logger.info(f"基座模型加载完成，显存: {torch.cuda.memory_allocated(0)/1024**3:.1f} GB")

    # 3. 加载 LoRA adapter
    logger.info("加载 LoRA adapter...")
    model = PeftModel.from_pretrained(model, LORA_PATH)
    logger.info("LoRA adapter 加载完成")

    # 4. 合并 LoRA 权重
    logger.info("合并 LoRA 权重到基座模型...")
    model = model.merge_and_unload()
    logger.info("合并完成")

    # 5. 保存合并后的模型
    logger.info(f"保存合并模型到 {OUTPUT_DIR} ...")
    Path(OUTPUT_DIR).mkdir(parents=True, exist_ok=True)

    model.save_pretrained(
        OUTPUT_DIR,
        safe_serialization=True,  # safetensors 格式
        max_shard_size="5GB",     # 每个分片最大 5GB
    )
    tokenizer.save_pretrained(OUTPUT_DIR)

    # 复制 chat_template
    chat_template_src = Path(BASE_MODEL) / "chat_template.jinja"
    if chat_template_src.exists():
        shutil.copy(chat_template_src, Path(OUTPUT_DIR) / "chat_template.jinja")

    logger.info("✅ 合并模型保存完成!")

    # 6. 验证
    logger.info("验证合并模型...")
    del model
    gc.collect()
    torch.cuda.empty_cache()

    test_model = AutoModelForCausalLM.from_pretrained(
        OUTPUT_DIR,
        device_map={"": 0},
        torch_dtype=torch.float16,
        trust_remote_code=True,
    )
    test_tokenizer = AutoTokenizer.from_pretrained(OUTPUT_DIR, trust_remote_code=True)

    # 简单推理测试
    prompt = "用莫言的笔触，描写一个在火车站卖粽子的老妇人："
    messages = [{"role": "user", "content": prompt}]
    text = test_tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    inputs = test_tokenizer(text, return_tensors="pt").to("cuda:0")

    with torch.no_grad():
        outputs = test_model.generate(
            **inputs,
            max_new_tokens=200,
            temperature=0.8,
            top_p=0.9,
            do_sample=True,
        )

    response = test_tokenizer.decode(outputs[0][inputs["input_ids"].shape[1]:], skip_special_tokens=True)
    logger.info(f"测试输出:\n{response[:500]}")

    # 清理
    del test_model
    gc.collect()
    torch.cuda.empty_cache()

    print(f"\n{'='*60}")
    print(f"✅ 全部完成!")
    print(f"  合并模型: {OUTPUT_DIR}")
    print(f"  文件列表:")
    for f in sorted(Path(OUTPUT_DIR).iterdir()):
        size = f.stat().st_size
        print(f"    {f.name:40s} {size/1024**2:8.1f} MB")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
