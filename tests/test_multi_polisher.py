"""
测试：agents/multi_polisher.py — 多模型润色模块。

覆盖：
- MultiModelPolisher 创建和基本调用
- 并发润色（mock LLMClient）
- 单模型失败不影响其他模型
- 文件润色流程
- 配置加载

不依赖 pytest-asyncio：用 asyncio.new_event_loop() 驱动。
"""
from __future__ import annotations

import asyncio
from pathlib import Path

import pytest


def _run(coro):
    """用独立 event loop 运行 async 协程。"""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# ── Mock 类 ─────────────────────────────────────────────────────

class FakeLLMClient:
    """Mock LLMClient：记录每次 chat 调用，返回预定义响应。"""

    def __init__(self, responses: dict[str, str] | None = None):
        self.calls: list[dict] = []  # 记录所有调用参数
        self.responses = responses or {}
        self._default_response = "（润色后的文本）"

    async def chat(self, *, messages, model, temperature, max_tokens, system):
        self.calls.append({
            "messages": messages,
            "model": model,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "system": system,
        })
        return self.responses.get(model, self._default_response)

    async def aclose(self):
        pass


class FailingLLMClient:
    """Mock LLMClient：指定模型调用时抛出异常。"""

    def __init__(self, failing_models: set[str]):
        self.failing_models = failing_models
        self.calls: list[dict] = []

    async def chat(self, *, messages, model, temperature, max_tokens, system):
        self.calls.append({"model": model})
        if model in self.failing_models:
            raise RuntimeError(f"模型 {model} 模拟调用失败")
        return f"[{model}] 润色结果"

    async def aclose(self):
        pass


# ── 测试：创建与基本调用 ─────────────────────────────────────────

class TestMultiModelPolisherCreation:
    def test_create_with_defaults(self):
        from agents.multi_polisher import MultiModelPolisher

        client = FakeLLMClient()
        polisher = MultiModelPolisher(
            client=client,
            models=["model-a", "model-b"],
        )
        assert polisher.models == ["model-a", "model-b"]
        assert polisher.max_concurrent == 3
        assert polisher.default_temperature == 0.8
        assert polisher.default_max_tokens == 12000

    def test_create_requires_models(self):
        from agents.multi_polisher import MultiModelPolisher

        client = FakeLLMClient()
        with pytest.raises(ValueError, match="models 不能为空"):
            MultiModelPolisher(client=client, models=[])

    def test_create_requires_valid_prompt_file(self):
        from agents.multi_polisher import MultiModelPolisher

        client = FakeLLMClient()
        with pytest.raises(FileNotFoundError, match="不存在"):
            MultiModelPolisher(
                client=client,
                models=["model-a"],
                polish_prompt_path="nonexistent_file.txt",
            )

    def test_factory_function(self):
        from agents.multi_polisher import create_multi_polisher, MultiModelPolisher

        client = FakeLLMClient()
        polisher = create_multi_polisher(
            client=client,
            models=["model-a", "model-b"],
            max_concurrent=2,
            default_temperature=0.6,
        )
        assert isinstance(polisher, MultiModelPolisher)
        assert polisher.max_concurrent == 2
        assert polisher.default_temperature == 0.6


# ── 测试：润色流程 ──────────────────────────────────────────────

class TestPolishFlow:
    def test_single_model_polish(self, tmp_path: Path):
        """单模型润色基本流程。"""
        from agents.multi_polisher import MultiModelPolisher

        client = FakeLLMClient({"model-a": "润色后的文字，AI感显著降低。"})
        polisher = MultiModelPolisher(
            client=client,
            models=["model-a"],
            max_concurrent=1,
        )

        text = "这是一段有AI感的文字。"
        report = _run(polisher.polish(text))

        assert len(report.results) == 1
        assert report.results[0].model_name == "model-a"
        assert report.results[0].success is True
        assert "润色后的文字" in report.results[0].polished_text
        assert report.success_count == 1
        assert report.fail_count == 0
        assert report.best_model == "model-a"

    def test_multi_model_concurrent_polish(self, tmp_path: Path):
        """多模型并发润色：每个模型收到独立调用。"""
        from agents.multi_polisher import MultiModelPolisher

        responses = {
            "model-a": "模型A的润色结果。",
            "model-b": "模型B的润色结果，更自然。",
            "model-c": "模型C的润色结果，保留了更多细节。",
        }
        client = FakeLLMClient(responses)
        polisher = MultiModelPolisher(
            client=client,
            models=["model-a", "model-b", "model-c"],
            max_concurrent=3,
        )

        text = "需要润色的原文。"
        report = _run(polisher.polish(text))

        # 所有模型都成功了
        assert report.success_count == 3
        assert report.fail_count == 0
        assert len(report.results) == 3

        # 检查每个模型都被调用了
        called_models = {c["model"] for c in client.calls}
        assert called_models == {"model-a", "model-b", "model-c"}

        # 检查每个调用都传了正确的参数
        for call in client.calls:
            assert call["messages"][0]["content"] == text
            assert call["temperature"] == 0.8
            assert call["max_tokens"] == 12000
            assert "system" in call  # polish prompt template

    def test_results_sorted_by_score(self, tmp_path: Path):
        """结果按 deai_score 降序排列。"""
        from agents.multi_polisher import MultiModelPolisher

        # 不同评分的响应（给不同文本以产生不同评分）
        client = FakeLLMClient()
        polisher = MultiModelPolisher(
            client=client,
            models=["model-a", "model-b"],
            max_concurrent=2,
        )

        text = "原文内容。"
        report = _run(polisher.polish(text))

        ranked = report.ranked_results
        for i in range(len(ranked) - 1):
            assert ranked[i].deai_score >= ranked[i + 1].deai_score


# ── 测试：错误处理 ──────────────────────────────────────────────

class TestErrorHandling:
    def test_one_model_fails_others_succeed(self, tmp_path: Path):
        """单个模型失败不影响其他模型的润色。"""
        from agents.multi_polisher import MultiModelPolisher

        client = FailingLLMClient(failing_models={"bad-model"})
        polisher = MultiModelPolisher(
            client=client,
            models=["good-model", "bad-model", "another-good"],
            max_concurrent=3,
        )

        text = "需要润色的原文。"
        report = _run(polisher.polish(text))

        # 总共 3 个结果
        assert len(report.results) == 3

        # 成功的 2 个
        assert report.success_count == 2

        # 失败的 1 个
        assert report.fail_count == 1
        failed = [r for r in report.results if not r.success]
        assert len(failed) == 1
        assert failed[0].model_name == "bad-model"
        assert failed[0].error is not None
        assert "模拟调用失败" in failed[0].error

        # 成功的模型结果是正确的
        succeeded = [r for r in report.results if r.success]
        for r in succeeded:
            assert r.model_name in ["good-model", "another-good"]
            assert r.polished_text != ""

    def test_polish_result_grade(self):
        """PolishResult.grade 返回正确的评级。"""
        from agents.multi_polisher import PolishResult

        r = PolishResult(model_name="test", deai_score=50)
        assert "优秀" in r.grade

        r.deai_score = 40
        assert "良好" in r.grade

        r.deai_score = 30
        assert "一般" in r.grade

        r.deai_score = 10
        assert "需改进" in r.grade

    def test_error_sentinel_handling(self, tmp_path: Path):
        """LLM 返回错误哨兵时正确处理为失败。"""
        from agents.multi_polisher import MultiModelPolisher
        from agents.llm_client import LLM_ERROR_PREFIX

        error_response = f"{LLM_ERROR_PREFIX}: 服务暂时不可用]"
        client = FakeLLMClient({"model-a": error_response})
        polisher = MultiModelPolisher(
            client=client,
            models=["model-a"],
            max_concurrent=1,
        )

        text = "原文。"
        report = _run(polisher.polish(text))

        assert report.success_count == 0
        assert report.fail_count == 1
        assert report.results[0].error == error_response

    def test_empty_text_skipped(self, tmp_path: Path):
        """空文本直接跳过。"""
        from agents.multi_polisher import MultiModelPolisher

        client = FakeLLMClient()
        polisher = MultiModelPolisher(
            client=client,
            models=["model-a"],
            max_concurrent=1,
        )

        report = _run(polisher.polish(""))
        assert "空文本" in report.summary

        report = _run(polisher.polish("   \n  "))
        assert "空文本" in report.summary


# ── 测试：文件操作 ──────────────────────────────────────────────

class TestPolishFile:
    def test_polish_file_saves_results(self, tmp_path: Path):
        """polish_file 保存各模型结果和报告。"""
        from agents.multi_polisher import MultiModelPolisher

        # 创建输入文件
        input_file = tmp_path / "test_chapter.md"
        input_file.write_text("需要润色的原文内容。", encoding="utf-8")

        output_dir = tmp_path / "output"
        output_dir.mkdir()

        responses = {
            "model-a": "模型A的润色版本。",
            "model-b": "模型B的润色版本，文字更自然。",
        }
        client = FakeLLMClient(responses)
        polisher = MultiModelPolisher(
            client=client,
            models=["model-a", "model-b"],
            max_concurrent=2,
        )

        report = _run(polisher.polish_file(
            input_path=str(input_file),
            output_dir=str(output_dir),
        ))

        # 模型结果文件存在
        for model, content in responses.items():
            safe_name = model.replace("/", "_").replace("\\", "_")
            out_file = output_dir / f"test_chapter_{safe_name}.md"
            assert out_file.exists()
            assert out_file.read_text(encoding="utf-8") == content

        # 对比报告存在
        report_file = output_dir / "test_chapter_report.md"
        assert report_file.exists()
        report_content = report_file.read_text(encoding="utf-8")
        assert "model-a" in report_content
        assert "model-b" in report_content

    def test_polish_file_nonexistent_input(self):
        """不存在的输入文件抛 FileNotFoundError。"""
        from agents.multi_polisher import MultiModelPolisher

        client = FakeLLMClient()
        polisher = MultiModelPolisher(
            client=client,
            models=["model-a"],
            max_concurrent=1,
        )

        with pytest.raises(FileNotFoundError, match="不存在"):
            _run(polisher.polish_file(input_path="/nonexistent/path.md"))


# ── 测试：配置加载 ──────────────────────────────────────────────

class TestConfigLoading:
    def test_multi_polish_config_default(self):
        """默认配置：multi_polish 字段正常创建。"""
        from config import StudioConfig, MultiPolishConfig

        cfg = StudioConfig()
        assert isinstance(cfg.multi_polish, MultiPolishConfig)
        assert cfg.multi_polish.enabled is True
        assert cfg.multi_polish.models == []
        assert cfg.multi_polish.max_concurrent == 3

    def test_multi_polish_model_config_defaults(self):
        """MultiPolishModelConfig 默认值正确。"""
        from config import MultiPolishModelConfig

        mc = MultiPolishModelConfig()
        assert mc.name == ""
        assert mc.temperature == 0.8
        assert mc.max_tokens == 12000
        assert mc.prompt_version == "v4"

    def test_multi_polish_config_from_dict(self):
        """配置可以从 YAML 数据正确加载。"""
        from config import MultiPolishConfig, MultiPolishModelConfig

        data = {
            "enabled": True,
            "models": [
                {"name": "DeepSeek-V4-Pro", "temperature": 0.9},
                {"name": "qwen-plus", "temperature": 0.7, "prompt_version": "v3"},
            ],
            "max_concurrent": 2,
        }

        mp_models = []
        for m in data["models"]:
            mp_models.append(MultiPolishModelConfig(
                name=m.get("name", ""),
                temperature=m.get("temperature", 0.8),
                max_tokens=m.get("max_tokens", 12000),
                prompt_version=m.get("prompt_version", "v4"),
            ))
        cfg = MultiPolishConfig(
            enabled=data.get("enabled", True),
            models=mp_models,
            max_concurrent=data.get("max_concurrent", 3),
        )

        assert cfg.enabled is True
        assert len(cfg.models) == 2
        assert cfg.models[0].name == "DeepSeek-V4-Pro"
        assert cfg.models[0].temperature == 0.9
        assert cfg.models[0].prompt_version == "v4"
        assert cfg.models[1].name == "qwen-plus"
        assert cfg.models[1].temperature == 0.7
        assert cfg.models[1].prompt_version == "v3"
        assert cfg.max_concurrent == 2


# ── 测试：MultiModelPolishReport ─────────────────────────────────

class TestReport:
    def test_ranked_results(self):
        """ranked_results 按 deai_score 降序。"""
        from agents.multi_polisher import MultiModelPolishReport, PolishResult

        report = MultiModelPolishReport(results=[
            PolishResult(model_name="low", deai_score=20),
            PolishResult(model_name="high", deai_score=45),
            PolishResult(model_name="mid", deai_score=35),
        ])

        ranked = report.ranked_results
        assert ranked[0].model_name == "high"
        assert ranked[1].model_name == "mid"
        assert ranked[2].model_name == "low"

    def test_success_and_fail_counts(self):
        """success_count 和 fail_count 正确统计。"""
        from agents.multi_polisher import MultiModelPolishReport, PolishResult

        report = MultiModelPolishReport(results=[
            PolishResult(model_name="a", success=True),
            PolishResult(model_name="b", success=False, error="fail"),
            PolishResult(model_name="c", success=True),
        ])

        assert report.success_count == 2
        assert report.fail_count == 1
