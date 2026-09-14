# 工作流运行参数

运行参数允许同一个工作流在执行时更换接口、模型、并发和质量设置。接口的 Key、Base URL 与模型列表继续在原接口管理中配置，同一接口下更换模型无需复制 Profile。

## 使用入口

- Web 任务页：展开“运行参数覆盖”，设置公共参数，或调整翻译/润色步骤参数。参数在页面切换时保留，本次修改不写回 Profile。
- Web 队列编辑：保留原有模型、并发等字段，新增质量和参考参数面板及步骤参数。
- TUI 自动化：创建监控/定时规则时设置公共运行参数；自定义工作流中选择 `E` 编辑步骤启停和覆盖参数。
- CLI：使用 `--runtime-overrides`、`--step-overrides`；`--workflow-file` 可加载已有工作流 JSON。
- MCP：通过工具目录中的任务接口传递 `runtime_overrides`、`step_overrides`。参数元数据位于 `/api/task/runtime-parameters`，通过 MCP 的 `call_web_api` 获取。
- Skills：`translate.run` 和 `queue.add` 支持相同字段；`system` 的 `runtime_parameters` action 返回参数目录。

查看全部字段、类型、范围和依赖：

```bash
python ainiee_cli.py --runtime-parameters
python Tools/Skills/cli.py run system '{"action":"runtime_parameters"}'
```

## 公共参数示例

```bash
python ainiee_cli.py translate input.txt --profile default --yes \
  --runtime-overrides '{"model":"your-model-id","user_thread_counts":12,"pre_line_counts":0,"think_switch":false,"retry_count":0}'
```

JSON 中的模型 ID 必须是所选接口支持的实际模型。Windows PowerShell/CMD 的引号规则与 Bash 不同，复杂配置可保存为工作流文件：

```json
{
  "profile": "default",
  "runtime_overrides": {
    "model": "your-model-id",
    "user_thread_counts": 12,
    "prompt_dictionary_switch": true,
    "translation_memory_switch": false,
    "think_switch": false
  },
  "workflow_steps": [
    {"id": "translate", "type": "translate"},
    {
      "id": "polish",
      "type": "polish",
      "enabled": true,
      "runtime_overrides": {
        "user_thread_counts": 4,
        "pre_line_counts": 5
      }
    }
  ]
}
```

```bash
python ainiee_cli.py all_in_one input.txt --workflow-file workflow.json --yes
```

创建新工作流时建议显式指定稳定的步骤 `id`。旧步骤缺省 ID 会在归一化时补全；移动已保存步骤不改变 ID。`all_in_one` 兼容步骤会展开成 `<id>.translate` 和 `<id>.polish`，可以分别覆盖。

## 步骤覆盖与继承

```json
{
  "runtime_overrides": {"user_thread_counts": 20, "think_switch": false},
  "step_overrides": {
    "polish": {
      "enabled": true,
      "runtime_overrides": {"user_thread_counts": 4, "think_switch": true}
    }
  }
}
```

内置 `translate`、`polish`、`all_in_one` 命令的步骤 ID 分别使用 `translate`、`polish`。自定义文件使用其中保存的步骤 ID。

从低到高逐字段合并：原 Profile → 工作流公共参数 → 本次公共参数 → 工作流步骤参数 → 本次步骤参数。步骤明确指定的值优先于公共参数。重复提供旧参数和新参数且值冲突时返回错误。

- 字段缺省或 `null`：该层继承。
- `false`：明确关闭，不恢复成 Profile 中的开启值。
- `0`：保留参数自身语义；前文 0 表示不携带该类前文，请求重试 0 表示只尝试一次，并发 0 表示自动并发。
- 切换接口未指定模型：使用新接口默认模型。仅指定模型：复用当前有效接口。
- 步骤 `enabled: false`：跳过该步骤。需要后续润色时仍须具备相应输入或已有译文。

## 参数分类

| 类别 | 常用参数 |
| --- | --- |
| 接口 | `platform`、`model` |
| 并发/限流 | `user_thread_counts`、`enable_async_mode`、`enable_rate_limit`、`custom_rpm_limit`、`custom_tpm_limit`、`request_timeout` |
| 分块 | `tokens_limit_switch`、`lines_limit`、`tokens_limit`、`chunk_soft_limit_extra_lines`、`line_split_optimization_mode` |
| 上下文 | `pre_line_counts`、`polishing_pre_line_counts`、`enable_context_enhancement`、`character_recall_switch`、`translation_consistency_enhancement` |
| 参考 | `prompt_dictionary_switch`、`dynamic_glossary_switch`、`translation_memory_switch`、`rag_enabled`、`rag_top_k` |
| 提示词 | `translation_prompt_id`、`polishing_prompt_id`、`characterization_switch`、`world_building_switch`、`writing_style_switch`、`translation_example_switch`、`few_shot_and_example_switch` |
| 生成 | `think_switch`、`think_depth`、`thinking_budget`、`temperature`、`top_p`、`max_output_tokens`、`enable_prompt_caching` |
| 检查/重试 | `reply_format_check`、`newline_character_count_check`、`return_to_original_text_check`、`residual_original_text_check`、`retry_count`、`round_limit`、`enable_smart_round_limit`、`smart_round_max_limit`、`untranslated_retry_limit`、`enable_retry_backoff`、`enable_api_failover` |
| 校对 | `enable_auto_proofread`、`proofread_batch_size`、`proofread_context_lines`、`proofread_confidence_threshold` |
| 文本处理 | `pre_translation_switch`、`post_translation_switch`、`exclusion_list_switch`、`auto_process_text_code_segment`、`language_filter_minority_ratio_threshold` |

`translation_prompt_id`、`polishing_prompt_id` 接受对应提示词目录中的文件名或已有内置 ID，不接受任意路径。具体参数与类型以元数据目录为准。

`structured_output_mode` 为 OpenAI-compatible 请求提供 `0`（不额外要求）、`1`（JSON object）与 `2`（使用接口扩展参数已配置的 JSON Schema）。JSON Schema 模式需要已有 `response_format.json_schema`。是否接受生成参数最终取决于模型和接口；错误会通过现有任务错误路径返回。

## 执行语义

- 分块的 `tokens_limit` 只控制正文分批，完整请求还包含提示词、术语和上下文。`max_output_tokens` 单独控制每次生成上限。
- 并发表示请求数，不是同时运行的工作流数量。一致性增强依赖前序结果，会采用并发 1 并关闭异步翻译。
- 智能轮数可追加处理轮次，`smart_round_max_limit` 控制追加上限（默认 10）；达到上限后保留未完成条目供恢复。
- 请求器沿用旧重试计数约定：正数表示该请求路径的最大尝试次数，0 为一次尝试。该值不关闭任务轮次、缺行补全、润色或校对。
- RAG 在任务内启停；不修改全局插件持久设置。翻译记忆提供已有译法参考，不保证跳过调用。
- 自动校对在翻译完成后生成报告。自定义 `proofread` 步骤可明确指定顺序；存在显式校对步骤时不再额外执行自动校对。校对不自动接受建议或改写译文。
- 术语提取和使用术语表分别控制。分析行数优先于百分比；当前分析范围从输入开头选取，跳过分析使用步骤开关。

## 队列和恢复

包含运行覆盖的队列/自动化任务记录配置快照，保留关键有效值、接口参数、规则内容和已解析提示词。已有队列不会因为之后修改 Profile 而改变这些设置。凭证仍从当前接口读取，快照不保存原始 Key。接口 `extra_body` 可能包含敏感信息，因此继续从接口配置读取。

修改参数后继续只影响之后执行的部分，已有译文不会自动全量重译。新参数不写回共享 Profile，任务结束后恢复调用方原配置。

本功能面向文本翻译工作流。接口能力、内容质量与缓存命中仍以实际运行结果为准。
