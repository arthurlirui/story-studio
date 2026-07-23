"""
🎨 Local Inference Client — 本地 Qwen + LoRA 推理引擎

加载 Qwen3.5-9B 基础模型 + 训练好的 LoRA adapter，
通过 transformers 直接推理，支持风格化润色。
"""
from __future__ import annotations

import logging
import threading
from typing import Any

# torch / transformers / peft 是重量级可选依赖，仅在真正使用本地推理时才需要。
# 延迟导入避免未安装时整个 agents 包无法 import（影响测试与 API 启动）。
try:
    import torch
    from transformers import (
        AutoTokenizer,
        AutoModelForCausalLM,
        GenerationConfig,
    )
    from peft import PeftModel
    _LOCAL_INFERENCE_AVAILABLE = True
except ImportError:
    torch = None  # type: ignore
    AutoTokenizer = None  # type: ignore
    AutoModelForCausalLM = None  # type: ignore
    GenerationConfig = None  # type: ignore
    PeftModel = None  # type: ignore
    _LOCAL_INFERENCE_AVAILABLE = False

logger = logging.getLogger(__name__)


class LocalInferenceClient:
    """本地 Qwen + LoRA 推理客户端.

    与 OllamaClient / VolcengineClient 接口兼容，
    可直接替换到 Agent 基类中使用。

    Usage:
        # 方式1: 直接指定路径
        client = LocalInferenceClient(
            base_model_path="/data/.../Qwen3.5-9B",
            lora_path="/data/.../moyan-style-lora-9b",
        )

        # 方式2: 通过风格名自动查找路径
        client = LocalInferenceClient.from_style("moyan")
    """

    # 单例缓存：避免重复加载大模型
    _instances: dict[str, "LocalInferenceClient"] = {}
    _lock = threading.Lock()

    @classmethod
    def from_style(cls, style: str, **kwargs) -> "LocalInferenceClient":
        """从风格名称创建客户端（自动查找路径）.

        Args:
            style: 风格名，如 "moyan"
        Returns:
            LocalInferenceClient 实例
        """
        from agents.style_polisher import STYLE_REGISTRY

        config = STYLE_REGISTRY.get(style)
        if not config:
            raise ValueError(
                f"未知风格 '{style}'，已注册: {list(STYLE_REGISTRY.keys())}"
            )
        return cls(
            base_model_path=config["base_model"],
            lora_path=config["lora_path"],
            **kwargs,
        )

    def __new__(
        cls,
        base_model_path: str | None = None,
        lora_path: str | None = None,
        *args,
        **kwargs,
    ):
        # 支持从风格名构造
        if base_model_path is None and "style" in kwargs:
            instance = cls.from_style(kwargs.pop("style"), **kwargs)
            return instance

        if base_model_path is None or lora_path is None:
            raise ValueError("必须提供 base_model_path + lora_path，或 style 参数")

        cache_key = f"{base_model_path}::{lora_path}"
        with cls._lock:
            if cache_key not in cls._instances:
                instance = super().__new__(cls)
                cls._instances[cache_key] = instance
            return cls._instances[cache_key]

    def __init__(
        self,
        base_model_path: str,
        lora_path: str,
        device: str = "cuda:0",
        dtype: Any = None,
        max_new_tokens: int = 4096,
        temperature: float = 0.7,
        top_p: float = 0.9,
        repetition_penalty: float = 1.1,
    ):
        # __init__ 可能被多次调用（单例模式），跳过已初始化的
        if hasattr(self, "_loaded") and self._loaded:
            return

        if not _LOCAL_INFERENCE_AVAILABLE:
            raise RuntimeError(
                "本地推理依赖未安装。请安装 torch/transformers/peft 后再使用 "
                "LocalInferenceClient，或改用 LLMClient / OllamaClient。"
            )

        # dtype 默认值延迟求值（torch 可能在该环境未安装）
        if dtype is None:
            dtype = torch.float16 if torch is not None else None

        self.base_model_path = base_model_path
        self.lora_path = lora_path
        self.device = device
        self.dtype = dtype
        self.max_new_tokens = max_new_tokens
        self.temperature = temperature
        self.top_p = top_p
        self.repetition_penalty = repetition_penalty
        self.default_model = f"local::{base_model_path}+{lora_path}"

        self.model = None
        self.tokenizer = None
        self._loaded = False

        self._load()

    def _load(self):
        """加载基础模型和 LoRA adapter."""
        # 检测 CUDA 是否可用
        use_cuda = torch.cuda.is_available()
        if not use_cuda:
            logger.warning(
                "CUDA 不可用，回退到 CPU 推理。"
            )
            self.device = "cpu"
            self.dtype = torch.float32
        else:
            self.device = "cuda:0"
            self.dtype = torch.float16

        logger.info("Loading base model from %s on %s ...", self.base_model_path, self.device)

        self.tokenizer = AutoTokenizer.from_pretrained(
            self.base_model_path,
            trust_remote_code=True,
            padding_side="left",
        )
        if self.tokenizer.pad_token is None:
            self.tokenizer.pad_token = self.tokenizer.eos_token

        if use_cuda:
            # FP16 单卡加载（9B ~18GB，V100 32GB 足够）
            self.model = AutoModelForCausalLM.from_pretrained(
                self.base_model_path,
                device_map={"": 0},
                torch_dtype=torch.float16,
                trust_remote_code=True,
            )
        else:
            self.model = AutoModelForCausalLM.from_pretrained(
                self.base_model_path,
                device_map=None,
                torch_dtype=self.dtype,
                trust_remote_code=True,
                low_cpu_mem_usage=True,
            )
            self.model = self.model.to("cpu")

        logger.info("Loading LoRA adapter from %s ...", self.lora_path)
        self.model = PeftModel.from_pretrained(self.model, self.lora_path)
        self.model = self.model.merge_and_unload()
        self.model.eval()

        # 生成配置
        self.gen_config = GenerationConfig(
            max_new_tokens=self.max_new_tokens,
            temperature=self.temperature,
            top_p=self.top_p,
            repetition_penalty=self.repetition_penalty,
            do_sample=True,
            pad_token_id=self.tokenizer.pad_token_id,
            eos_token_id=self.tokenizer.eos_token_id,
        )

        self._loaded = True
        logger.info("✅ Local inference client ready on %s", self.device)

    async def chat(
        self,
        messages: list[dict[str, str]],
        model: str | None = None,  # 忽略，使用本地模型
        temperature: float | None = None,
        max_tokens: int | None = None,
        stream: bool = False,
        system: str | None = None,
    ) -> str:
        """与 OllamaClient 兼容的 chat 接口."""
        # 组装消息
        payload_messages = []
        if system:
            payload_messages.append({"role": "system", "content": system})
        payload_messages.extend(messages)

        # 应用 chat template
        text = self.tokenizer.apply_chat_template(
            payload_messages,
            tokenize=False,
            add_generation_prompt=True,
        )

        # 生成
        gen_kwargs = {"generation_config": self.gen_config}
        if temperature is not None:
            gen_kwargs["generation_config"] = GenerationConfig(
                **{**self.gen_config.to_dict(),
                   "temperature": temperature,
                   "max_new_tokens": max_tokens or self.max_new_tokens,
                   "do_sample": True,
            })
        elif max_tokens is not None:
            gen_kwargs["generation_config"] = GenerationConfig(
                **{**self.gen_config.to_dict(),
                   "max_new_tokens": max_tokens,
                   "do_sample": True,
            })

        inputs = self.tokenizer(text, return_tensors="pt")
        # 多 GPU 时放到第一个设备
        device = self.model.device if hasattr(self.model, 'device') else (self.device if self.device != "cpu" else "cpu")
        if isinstance(device, str) and device != "cpu":
            inputs = inputs.to(device)
        elif not isinstance(device, str):
            # device_map="auto" 返回 dict-like，取第一个
            try:
                first_device = next(iter(self.model.hf_device_map.values()))
                inputs = inputs.to(first_device)
            except (AttributeError, StopIteration):
                inputs = inputs.to("cuda:0")

        with torch.no_grad():
            output_ids = self.model.generate(**inputs, **gen_kwargs)

        # 只取新生成的部分
        input_len = inputs["input_ids"].shape[1]
        generated_ids = output_ids[0][input_len:]
        response = self.tokenizer.decode(generated_ids, skip_special_tokens=True)

        return response

    async def generate(
        self,
        prompt: str,
        system: str | None = None,
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> str:
        """简化接口."""
        messages = [{"role": "user", "content": prompt}]
        return await self.chat(
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            system=system,
        )

    async def check_health(self) -> bool:
        return self._loaded

    async def list_models(self) -> list[dict]:
        return [{"name": self.default_model, "size": "local", "modified": ""}]

    def reload_lora(self, lora_path: str):
        """重新加载不同的 LoRA adapter."""
        logger.info("Reloading LoRA from %s ...", lora_path)
        del self.model
        if self.device != "cpu":
            torch.cuda.empty_cache()

        use_cuda = self.device != "cpu"
        if use_cuda:
            self.model = AutoModelForCausalLM.from_pretrained(
                self.base_model_path,
                device_map={"": 0},
                torch_dtype=torch.float16,
                trust_remote_code=True,
            )
        else:
            self.model = AutoModelForCausalLM.from_pretrained(
                self.base_model_path,
                device_map=None,
                torch_dtype=self.dtype,
                trust_remote_code=True,
                low_cpu_mem_usage=True,
            )
            self.model = self.model.to("cpu")

        self.model = PeftModel.from_pretrained(self.model, lora_path)
        self.model = self.model.merge_and_unload()
        self.model.eval()
        self.lora_path = lora_path
        logger.info("✅ LoRA reloaded from %s", lora_path)
