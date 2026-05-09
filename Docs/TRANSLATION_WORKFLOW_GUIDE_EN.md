# Prompt, Glossary, Polishing, and Advanced Settings Guide

This guide explains how to improve translation quality in AiNiee-Next. It also explains when to use CLI/TUI, WebUI, profiles, queues, and MCP.

If this is your first time using AiNiee-Next, start with [AiNiee-Next Text Quick Start Guide](README_QUICK_START_EN.md). After you have completed one successful translation, return to this guide.

## 1. Understand the Four Main Inputs

Translation quality usually improves when each type of information is placed in the right place.

- **Prompt**: tells the model how to translate.
- **Glossary**: tells the model how specific terms must be translated.
- **World, character, and style notes**: tell the model what kind of story or text it is handling.
- **Polishing**: improves the final wording after the translation is already mostly correct.

Do not put everything into one giant prompt. Use the correct tool for each kind of information.

## 2. CLI/TUI, WebUI, and MCP

AiNiee-Next has multiple entry points. They serve different users and workflows.

### CLI/TUI for First-Time Users

CLI/TUI is the numbered menu interface shown after launching `Launch.bat` or running `uv run ainiee_cli.py`.

It is recommended for first-time users because:

- the workflow is linear,
- menu items are clear,
- API verification and errors are visible immediately,
- you do not need to understand the WebUI layout first.

The black console window does not mean you need to code. You only choose menu numbers and follow prompts.

### WebUI for Monitoring and Remote Use

WebUI is useful after the basic workflow is clear. It is good for:

- checking task progress,
- viewing RPM, TPM, success rate, and error rate,
- managing queues,
- switching profiles,
- monitoring a task from another device on the same LAN,
- using a phone, tablet, school computer, or office computer to check a task running elsewhere.

WebUI is not the best starting point for complete beginners because it can show many pages before the user understands what must be configured first.

Recommended pattern:

1. Configure API, paths, and prompts in CLI/TUI.
2. Run one small translation.
3. Open WebUI later for monitoring and queue management.

### MCP for LLM Clients

MCP is not required for normal translation. It is for LLM clients that support tool calling through MCP.

Use MCP if you want a client such as Codex, Claude Desktop, Cherry Studio, or another MCP-compatible tool to interact with AiNiee-Next.

MCP is useful for:

- reading task status,
- managing queues,
- checking configuration,
- uploading files through controlled tools,
- building automation workflows.

If you only want to translate files, you can ignore MCP at first.

## 3. How to Write a Good Translation Prompt

A good prompt is clear, stable, and executable. It does not need to be long.

Include these parts:

1. **Role and task**: literary translation, subtitle translation, game script translation, etc.
2. **Language direction**: for example Japanese to Chinese, English to Chinese, or another pair.
3. **Format rules**: preserve line order, numbering, placeholders, variables, tags, and escape characters.
4. **Style rules**: natural, concise, literary, casual, serious, etc.
5. **Do-not rules**: do not summarize, do not explain, do not delete content, do not translate placeholders.

Example:

```text
You are a professional literary translator. Translate the source text into natural and fluent target language.

Translate line by line. Do not merge lines and do not split lines.
Preserve numbering, markers, line breaks, escape characters, code variables, and placeholders.
Content inside {...}, [...], HTML tags, script commands, and game variables should remain unchanged if they are not normal prose.

Accuracy is the first priority. Natural target-language expression is the second priority.
Dialogue should match the speaker's tone. Do not make every character sound the same.
Do not summarize, explain, or add information that is not in the source.

Output only the translation.
```

For novels, add:

```text
Keep narration literary and fluent. Keep dialogue natural and character-specific.
```

For game scripts, add:

```text
Preserve all variables, tags, commands, file paths, and script structure. Translate only player-visible text.
```

For subtitles, add:

```text
Keep the translation concise and suitable for screen reading.
```

Avoid vague prompts such as:

```text
Translate beautifully and perfectly. Make it elegant and faithful.
```

This sounds good but gives the model no concrete priority.

## 4. Do Not Use the Prompt as a Glossary

If a term must always be translated the same way, put it in the glossary instead of writing it repeatedly in the prompt.

Prompt rule:

```text
Follow the glossary strictly. When a source term appears in the glossary, use the glossary translation first.
```

Glossary entries should handle fixed names and terms. The prompt should handle behavior and format rules.

## 5. How to Build a Glossary

Use the glossary for terms that must stay consistent:

- character names,
- nicknames and titles,
- place names,
- organizations,
- schools and companies,
- skills and items,
- system names,
- setting-specific words,
- words the model keeps translating inconsistently.

Do not add every normal word. Common words should be translated by context.

Good glossary entries usually contain:

- **Source**: original term.
- **Target**: fixed translation.
- **Note**: what the term means or when to use it.

Example:

| Source | Target | Note |
| --- | --- | --- |
| Tsukuyomi | Tsukuyomi | Main virtual space. Keep as a proper noun. |
| Hagoromo Protocol | Hagoromo Protocol | Synchronization protocol that gives virtual bodies real feedback. |
| Kaguya | Kaguya | Main heroine. Innocent, proud, princess-like tone. |
| Moon Envoy | Moon Envoy | System cleanup agent, not a normal mythological messenger. |

Keep notes short and useful. A note should explain meaning, not express anxiety.

Good note:

```text
Main heroine. Innocent, proud, princess-like tone.
```

Bad note:

```text
Very important character. Must be translated perfectly. Do not make mistakes.
```

The second note has emotion but little useful information.

## 6. Glossary Maintenance

Start small.

Recommended order:

1. Add main character names.
2. Add major places, organizations, abilities, and system terms.
3. Translate a small sample.
4. Add terms that the model translated inconsistently.
5. Test again.

Avoid glossary conflicts. If the same source term has two different target translations, the model may become unstable.

If a term has different meanings in different contexts, explain the condition:

```text
Source: Master
Target: Master
Note: Use as a character address. If it refers to a rank, title, or skill level, translate by context.
```

## 7. World, Character, and Style Notes

For long works, prompts and glossaries are not enough. The model also needs context.

World notes should explain:

- time period,
- setting,
- social structure,
- magic or technology system,
- special meanings of terms.

Character notes should explain:

- original name and translated name,
- age and role,
- personality,
- speaking style,
- relationships.

Style notes should explain:

- narration style,
- dialogue style,
- level of formality,
- whether jokes, slang, profanity, honorifics, or archaic style should be preserved.

Example:

```text
This is a near-future sci-fi romance. The real world is quiet and lonely, while the virtual world is bright and crowded.
Narration should be smooth and light-novel-like.
Kaguya speaks innocently and proudly, sometimes with a princess-like attitude.
Yachiyo speaks calmly, elegantly, and with emotional distance.
```

Write these notes like translator references, not like emotional commands.

## 8. When to Use Polishing

Polishing is optional. Use it when:

- the translation is correct but stiff,
- Chinese or target-language phrasing feels unnatural,
- long-form style needs to be unified,
- character voices need light adjustment,
- the source is already in the target language and only needs rewriting.

Do not use polishing to fix severe mistranslations. If the meaning is wrong, names are wrong, or variables are broken, fix the prompt, glossary, or settings and translate again.

## 9. Polishing Modes

There are two common polishing scenarios:

- **Polish translated text**: translate first, then improve the translated result. This is the most common workflow.
- **Polish source text**: use this when the source is already in the target language and only needs rewriting.

Recommended workflow:

1. Finish translation.
2. Check term consistency and format safety.
3. Run polishing if the wording is stiff.
4. Export or manually inspect important sections.

Example polishing prompt:

```text
You are a target-language literary editor. Polish the translated text without changing the meaning or adding new information.

Make the wording more natural and fluent.
Preserve character voice.
Preserve numbering, placeholders, tags, variables, and line structure.
Do not summarize or explain. Output only the polished text.
```

For light polishing:

```text
Only fix stiff or unnatural expressions. Do not rewrite sentences heavily.
```

For stronger polishing:

```text
You may reorganize sentence order if the meaning remains unchanged and the result reads more naturally.
```

Do not ask for both "do not change anything" and "rewrite freely" at the same time.

## 10. Reasonable Basic Settings

Start stable. Speed comes later.

Recommended first settings:

| Setting | Suggested value | Reason |
| --- | --- | --- |
| Source language | `auto` or exact language | Use exact language if known. |
| Target language | your target language | For Chinese output, use `Chinese`. |
| Lines per request | `10` to `30` | Start around `20` for novels. |
| Previous context lines | `2` to `5` | `3` is usually enough. |
| Request timeout | `60` to `120` seconds | Increase if network or model is slow. |
| Thread count | `5` to `10` first | Raise only after stable tests. |
| Thinking mode | off at first | Test later if needed. |
| Token mode | off at first | Line mode is easier for beginners. |

For fast providers such as DeepSeek, you can later try higher thread counts such as `20`, `30`, or `50`, but only if the success rate stays high.

If you see many `429`, timeout, or connection errors, lower the thread count.

## 11. Lines, Context, and Tokens

**Lines per request** controls how many lines are sent in one API request.

Too few lines:

- weaker context,
- more requests,
- possibly higher overhead.

Too many lines:

- higher chance of missing lines,
- higher chance of format mistakes,
- more costly failures,
- possible context length issues.

For novels, start around `20`. For short subtitles or short dialogue lines, you may increase it. For complex scripts with variables and tags, lower it.

**Previous context lines** give the model a small amount of preceding text. `3` is a good starting point. Too much context can increase cost and distract the model.

**Token mode** is useful for advanced users who understand model context limits. Beginners should start with line mode.

## 12. Thinking Mode

Thinking mode can help with complex reasoning, long sentences, dense settings, or difficult literary passages. It can also increase time and cost.

Advice:

- Normal novels and game dialogue: keep it off first.
- Dense settings or complex long sentences: test it on a small sample.
- Large batch jobs: compare a small sample before enabling it globally.
- If cost rises but quality does not improve, turn it off.

If the API returns parameter errors, disable thinking mode and try again. Not all providers or middle layers support the same thinking parameters.

## 13. Profiles

Profiles separate settings for different works and workflows.

Recommended profile types:

| Profile | Use |
| --- | --- |
| `Default` | Temporary testing. |
| `Novel-Title` | One long novel with its own glossary and style. |
| `Game-Title` | One game script project with format protection rules. |
| `Subtitle-General` | Subtitle workflow. |
| `Polish-Title` | Polishing and review workflow for one work. |

Use separate profiles for different works. Otherwise, glossary terms and character notes from one work may affect another.

## 14. Task Queue

Use the task queue after a single task has been tested successfully.

Good queue use cases:

- multiple volumes of one novel,
- many files from one game project,
- multiple subtitle files with the same settings,
- overnight batch processing.

Do not use the queue before API, prompt, glossary, paths, and output format are verified.

Recommended queue workflow:

1. Translate one small file.
2. Check output.
3. Fix glossary or prompt.
4. Add similar files to the queue.

## 15. WebUI Usage

WebUI is best for monitoring and management.

Use it when:

- the task is already running,
- you want to view progress from another device,
- the main machine is in another room, home, dorm, office, or server,
- you want to manage queues visually,
- you want browser-based profile or plugin management.

Do not expose WebUI to the public internet unless you fully understand the security implications. For normal users, LAN-only use is recommended.

## 16. MCP Usage

MCP is for LLM clients, not for normal manual operation.

Simple distinction:

- CLI/TUI: human uses keyboard.
- WebUI: human uses browser.
- MCP: LLM client uses tools.

MCP connection styles:

| Transport | Best for |
| --- | --- |
| `stdio` | Local LLM clients that start the MCP process automatically. |
| `streamable-http` | Clients that connect to a fixed local or LAN URL. |

After connecting MCP, ask the client to read:

```text
get_mcp_usage_manual
get_mcp_security_policy
get_mcp_tool_catalog
get_mcp_validation_checklist
```

Security rules:

- LLM clients should use MCP tools only.
- Do not bypass MCP and call WebUI or localhost HTTP APIs directly.
- Secret fields such as API keys are redacted.
- Redacted placeholders are not real keys and must not be saved back as real values.

If you only want to translate files, ignore MCP until later.

## 17. Different Project Types

### Novels

Focus on tone, glossary, and context.

Suggested:

- Lines per request: `15` to `25`
- Previous context lines: `3`
- Glossary: on
- Character notes: recommended
- World notes: recommended for complex settings
- Polishing: optional after translation

Prompt emphasis:

```text
Keep narration fluent and literary. Keep dialogue character-specific.
Preserve line order, placeholders, and formatting.
Do not summarize or explain.
```

### Game Scripts

Focus on format safety.

Suggested:

- Lines per request: `10` to `20`
- Previous context lines: `2` to `3`
- Glossary: on
- Polishing: use carefully

Prompt emphasis:

```text
Translate only player-visible text.
Preserve variables, tags, commands, file paths, keys, and script structure.
```

### Subtitles

Focus on brevity and readability.

Suggested:

- Lines per request: `20` to `40`
- Previous context lines: `2`
- Keep translations short

Prompt emphasis:

```text
Keep the translation concise and suitable for screen reading.
Preserve subtitle structure and timing.
```

### Manga

Focus on short, natural dialogue.

Suggested:

- Glossary: on
- Character voice: recommended
- Polishing: useful, but avoid expanding dialogue too much
- WebUI: useful for status checking and later manual refinement

Prompt emphasis:

```text
Keep dialogue short and natural.
Make it suitable for speech bubbles.
Do not over-expand short lines.
```

## 18. Common Mistakes

**Mistake: Starting with WebUI because it looks easier.**

WebUI is visual, but not always more linear. Use CLI/TUI first.

**Mistake: Raising concurrency too high immediately.**

High concurrency can cause rate limits and timeouts. Stable throughput matters more than a large thread number.

**Mistake: Writing an extremely long prompt.**

Put fixed terms in the glossary. Put background in world notes. Put character voice in character notes. Keep the prompt focused.

**Mistake: Using polishing to fix bad translation.**

Fix mistranslation at the translation stage. Use polishing only after the meaning is mostly correct.

**Mistake: Configuring MCP before basic translation works.**

MCP is advanced. It is unnecessary for normal first-time translation.

## 19. Recommended Learning Path

1. Run one small translation in CLI/TUI.
2. Add a small glossary.
3. Add character and world notes if needed.
4. Improve the prompt with one change at a time.
5. Translate a larger sample.
6. Increase concurrency only after stable results.
7. Use the queue for batch tasks.
8. Use WebUI for monitoring and remote management.
9. Use MCP only when you need LLM-client automation.

The core rule is: stabilize first, speed up later; test small samples before batch processing.
