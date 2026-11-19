import json
from pathlib import Path

from comfy_api.latest import ComfyExtension, io
from typing_extensions import override

ASSET_DIR = Path(__file__).parent
PAN2_SYSTEM_PROMPT = (ASSET_DIR / "pan2_system_prompt.md").read_text(encoding="utf-8").strip()
NEGATIVE_TEMPLATE = (ASSET_DIR / "generic_negative.txt").read_text(encoding="utf-8").strip()

CAPTION_KEYS = {"video_style", "lighting", "perspective_view", "subjects_lifecycle",
                "init_frame_visual_description", "events", "quality"}

REFERENCE_IMAGE_NOTE = ("Reference image: the attached image is the exact first visible frame "
                        "for this image-to-video rewrite.")


def format_duration(duration):
    return "%g" % round(float(duration), 1)


def unwrap_positive(text):
    decoder = json.JSONDecoder()
    pos = 0
    while True:
        start = text.find("{", pos)
        if start < 0:
            break
        try:
            value, pos = decoder.raw_decode(text, start)
        except json.JSONDecodeError:
            pos = start + 1
            continue
        if isinstance(value, dict) and isinstance(value.get("refined_prompt"), str):
            return value["refined_prompt"]
        if isinstance(value, dict) and set(value) == CAPTION_KEYS:
            return json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    raise ValueError("PAN2 Prompt Writer: no refined_prompt or caption JSON in rewriter reply: " + text.strip()[:200])


class PAN2PromptWriter(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="PAN2PromptWriter",
            display_name="PAN2 Prompt Writer",
            category="text/pan2",
            inputs=[
                io.Clip.Input("clip", tooltip="Rewriter LLM loaded as a text encoder, same as Generate Text. A vision model is required for image-to-video."),
                io.String.Input("prompt", multiline=True, dynamic_prompts=True, default=""),
                io.Image.Input("image", optional=True, tooltip="First frame. Connect for image-to-video; leave unconnected for text-to-video."),
                io.Float.Input("duration", default=13.0, min=0.1, max=60.0, step=0.1, tooltip="Target video duration in seconds; written into the caption request and the fixed negative."),
                io.Int.Input("max_length", default=3072, min=256, max=32768, tooltip="Maximum rewriter output tokens. The caption JSON is long; 512 will cut it off."),
                io.Float.Input("temperature", default=0.7, min=0.0, max=2.0, step=0.01),
                io.Float.Input("top_p", default=0.95, min=0.0, max=1.0, step=0.01),
                io.Int.Input("seed", default=0, min=0, max=0xffffffffffffffff),
                io.String.Input("negative_prompt", multiline=True, default="", optional=True, tooltip="Overrides the fixed PAN2 negative when nonempty."),
            ],
            outputs=[
                io.String.Output(display_name="positive_prompt"),
                io.String.Output(display_name="negative_prompt"),
            ],
        )

    @classmethod
    def execute(cls, clip, prompt, duration, max_length, temperature, top_p, seed, image=None, negative_prompt=""):
        duration_str = format_duration(duration)
        request = '{"original_prompt": %s, "duration_sec": %s}' % (json.dumps(prompt, ensure_ascii=False), duration_str)
        user_text = "Input text:\n" + request
        if image is not None:
            if image.shape[0] > 1:
                image = image[:1]
            user_text = REFERENCE_IMAGE_NOTE + "\n\n" + user_text

        tokens = clip.tokenize(user_text, image=image, skip_template=False, min_length=1, thinking=False, system_prompt=PAN2_SYSTEM_PROMPT)
        do_sample = temperature > 0.0
        generated = clip.generate(tokens, do_sample=do_sample, max_length=max_length,
                                  temperature=temperature, top_p=top_p, seed=seed)
        reply = clip.decode(generated)

        head, sep, tail = reply.partition("</think>")
        if sep:
            reply = tail

        positive = unwrap_positive(reply)
        negative = negative_prompt.strip() or NEGATIVE_TEMPLATE.replace("0 to {duration_sec}", "0 to " + duration_str)
        return io.NodeOutput(positive, negative)


class PAN2PromptWriterExtension(ComfyExtension):
    @override
    async def get_node_list(self) -> list[type[io.ComfyNode]]:
        return [PAN2PromptWriter]


async def comfy_entrypoint() -> PAN2PromptWriterExtension:
    return PAN2PromptWriterExtension()
