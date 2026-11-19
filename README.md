# ComfyUI-PAN2-PromptWriter

Rewrite a rough, one-line scene idea into the **structured JSON prompt pair that the PAN2 video model expects** — using a local LLM loaded through ComfyUI's native text-encoder ("Generate Text") path. No API keys, no cloud calls.

The PAN 2 video model ([ifm-ai/PAN2](https://github.com/ifm-ai/PAN2)) does not work well with plain prose prompts. It expects a caption JSON with a fixed schema, a duration-aware negative prompt, and it rewards one continuous shot with explicitly scheduled camera motion and events. This node runs PAN2's official prompt-rewriter policy (bundled unmodified) on the LLM of your choice and hands you ready-to-encode positive/negative text.

## Requirements

- A recent ComfyUI build with the native **Generate Text** nodes and V3 custom-node loading (v0.45+, late-2025 or newer).
- A rewriter LLM loaded as a **CLIP text encoder**. The simplest choice: the PAN2 text encoder itself (**Qwen3.5-9B**, CLIP Loader type `pan2`) — it is vision-capable, so the same clip serves both text-to-video and image-to-video rewriting. Any other instruct model that works with Generate Text also works (vision model required for I2V).
- No extra Python dependencies.

## Installation

**ComfyUI Manager:** Custom Nodes Manager → search "PAN2 PromptWriter", or install via git URL `https://github.com/benjiyaya/ComfyUI-PAN2-PromptWriter`.

**Manual:**

```bash
cd ComfyUI/custom_nodes
git clone https://github.com/benjiyaya/ComfyUI-PAN2-PromptWriter.git
```

Restart ComfyUI. The node appears as **PAN2 Prompt Writer** under `text/pan2`.

## Quick start

1. **CLIP Loader** — load your rewriter LLM as a text encoder (type `pan2` for Qwen3.5-9B).
2. **PAN2 Prompt Writer** — connect the `clip`, type your idea, set `duration`. For image-to-video, also connect the first-frame `image`.
3. **CLIP Loader** (type `pan2`, the PAN2 text encoder) → two **CLIP Text Encode** nodes for the writer's `positive_prompt` / `negative_prompt` outputs.
4. Wire the conditioning into your PAN2 sampler as usual.

```
CLIP Loader (pan2 / Qwen3.5-9B) ──► PAN2 Prompt Writer ──► positive ──► CLIP Text Encode ─► KSampler/...
LoadImage (optional, first frame) ──┘        ▲              negative ──► CLIP Text Encode ─┘
                                     your prompt text
```

## Node reference: PAN2 Prompt Writer

| Input | Type | Default | Description |
| --- | --- | --- | --- |
| `clip` | CLIP | — | Rewriter LLM as a text encoder (same input as Generate Text) |
| `prompt` | STRING | — | Your raw scene idea, any language; the policy always writes the caption in English |
| `image` | IMAGE | — | **First frame.** Connect for image-to-video; leave unconnected for text-to-video |
| `duration` | FLOAT | 13.0 | Target video length in seconds; drives event time ranges and the negative prompt |
| `max_length` | INT | 3072 | Max rewriter output tokens — the caption JSON is long, don't set this low |
| `temperature` | FLOAT | 0.7 | Sampling temperature (0 = greedy) |
| `top_p` | FLOAT | 0.95 | Nucleus sampling |
| `seed` | INT | 0 | Sampling seed; reroll to get a different rewrite |
| `negative_prompt` | STRING | — | Optional override of the fixed PAN2 negative |

| Output | Description |
| --- | --- |
| `positive_prompt` | The caption as compact JSON (the `refined_prompt` value) — connect to CLIP Text Encode |
| `negative_prompt` | PAN2's fixed generic negative with your duration stamped in — connect to CLIP Text Encode |

## What the output looks like

The positive is a compact single-line JSON object; pretty-printed here for readability:

```json
{
  "video_style": "Realistic documentary cinematography in one uninterrupted continuous shot.",
  "lighting": "Warm late-afternoon sunlight from the window left of frame, soft shadows.",
  "perspective_view": "Medium shot from counter height, slightly angled.",
  "subjects_lifecycle": [
    { "subject_id": "<|Subject1|>", "display_name": "barista",
      "subject_attribute": "Woman in her 30s, dark canvas apron, brown hair tied back" }
  ],
  "init_frame_visual_description": "A café counter with a chrome espresso machine...",
  "events": [
    { "event_index": 0, "time_range_sec": "0 to 2.5",
      "event_description": "The barista tamps coffee grounds into a portafilter with steady presses...",
      "camera_motion": [ { "time_range_sec": "0 to 2.5", "camera_motion": ["static"] } ],
      "contained_actions": [ { "time_range_sec": "0 to 2.5",
        "action": "<|Subject1|> tamps coffee grounds into a portafilter" } ] },
    { "event_index": 1, "time_range_sec": "2.5 to 5",
      "event_description": "...", "camera_motion": [], "contained_actions": [] }
  ],
  "quality": { "video_quality": "sharp natural detail, stable motion",
               "text_logos_overlays": null, "artifacts": null }
}
```

Key rules the rewriter enforces: events tile the full duration contiguously (`0 to 2.5`, `2.5 to 5`, …), every event carries camera tags from a fixed list, action strings start with a registered `<|SubjectN|>` performer, and the whole caption stays under the encoder budget (1,480 tokens soft / 1,536 hard).

## How it works

- The full official rewriter system prompt (`pan2_system_prompt.md`, verbatim from [inference/pan-prompt-rewriter](https://github.com/ifm-ai/PAN2/tree/main/inference/pan-prompt-rewriter)) is sent as the LLM's system turn; your idea is sent as `{"original_prompt": "...", "duration_sec": N}`. Thinking mode is disabled, matching upstream's `enable_thinking=False`.
- For I2V the image goes to the vision LLM with the upstream grounding note ("the attached image is the exact first visible frame"), and the caption's `init_frame_visual_description` is written from the actual image.
- The reply is unwrapped robustly: markdown fences, preamble, echoed requests, repeated envelopes and directly-returned captions are all handled — the node takes the first valid `refined_prompt` envelope or caption-schema object it finds.
- The negative is the fixed upstream template (`generic_negative.txt`) with your duration substituted into all three time ranges — byte-identical to upstream's own assembly.

## Troubleshooting

| Symptom | Fix |
| --- | --- |
| `no refined_prompt or caption JSON in rewriter reply: …` | The error shows the first 200 chars of the reply. Usually a weak model — raise `max_length`, reroll `seed`, lower `temperature`, or use a stronger instruct model |
| Positive JSON looks cut off mid-string | `max_length` too low; raise it (3072 fits a full caption) |
| I2V ignores the image | The rewriter `clip` must be a vision model (Qwen3.5-9B with type `pan2` works) |
| Rewrites feel repetitive or off-schema | Reroll `seed`, or try a larger rewriter model — small LLMs follow the long policy noticeably worse |

## Credits & license

- Prompt rewriter policy, negative template, and caption schema: [ifm-ai/PAN2](https://github.com/ifm-ai/PAN2) by MBZUAI — **Apache-2.0**. `pan2_system_prompt.md` and `generic_negative.txt` are verbatim copies from that repository.
- This pack: Apache-2.0.
