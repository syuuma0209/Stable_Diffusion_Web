import modal

stub = modal.Stub("syuuma_stable_diffusion_web")

device = "cuda"
cache_path = "/vol/cache"


def download_models():
    import diffusers
    import torch

    # "andite/anything-v4.0",
    # Downloads all other models.
    pipe = diffusers.StableDiffusionPipeline.from_pretrained(
        "andite/anything-v4.0",
        torch_dtype=torch.float16,
        low_cpu_mem_usage=False,
        custom_pipeline="lpw_stable_diffusion",  # プロンプトの長さを制限なしに
    )
    pipe.save_pretrained(cache_path, safe_serialization=True)


image = (
    modal.Image.debian_slim(python_version="3.10")
    .pip_install(
        "accelerate",
        "diffusers",
        "ftfy",
        "torch",
        "torchvision",
        "transformers",
        "triton",
        "safetensors",
        "huggingface_hub",
        "deep-translator",
    )
    .pip_install("xformers", pre=True)
    .run_function(
        download_models,
    )
)
stub.image = image


@stub.function(gpu="A10G")
async def run_stable_diffusion(prompt: str):
    import torch
    from diffusers import StableDiffusionPipeline
    from torch import autocast

    # パイプライン読み込み
    pipe = StableDiffusionPipeline.from_pretrained(
        cache_path,
        custom_pipeline="lpw_stable_diffusion",  # プロンプトの長さを制限なしに
    ).to(device)
    pipe.enable_xformers_memory_efficient_attention()

    # NSWFフィルターを削除(黒塗り回避) (これによりエロ、グロ画像が生成可能になります) (閲覧注意)
    pipe.safety_checker = lambda images, **kwargs: (images, False)

    # ランダムなシードを生成
    input_seed = torch.Generator(device=device).seed()
    generator = torch.Generator(device=device).manual_seed(int(input_seed))

    negative_prompt = ""
    # 画質
    negative_prompt += "flat color, flat shading, blender, retro style, poor quality, worst quality, low quality, normal quality, error, lowere, jpeg artifacts, extra digit, fewer digits, chromatic aberration, "
    # テキストを消す
    negative_prompt += "signature, watermark, username, artist name, tittle, signature, watermark, "
    # 色
    negative_prompt += "grayscale, monochrome, "
    # 構図
    negative_prompt += "cropped, panel layout"
    # キャラ
    negative_prompt += "eye shadow, asymmetrical bangs, expressionless, blank stare, {{{fat}}}, "
    # 指や体の変形を軽減
    negative_prompt += "bad fingers, bad anatomy, missing fingers, bad feet, bad hands, long body, "
    # エロ軽減
    negative_prompt += "{{{{{{{{{{NSWF}}}}}}}}}}, "

    print("--------------------------------------------------------------------------------------------")
    print(f"prompt = {prompt}")
    print("--------------------------------------------------------------------------------------------")
    print(f"seed = {input_seed}")
    print("--------------------------------------------------------------------------------------------")

    with autocast(device):
        image = pipe(
            prompt,
            negative_prompt=negative_prompt,
            guidance_scale=7.5,
            num_inference_steps=100,
            generator=generator,
            height=512,
            width=512,
            max_embeddings_multiples=10,
        )[0][0]

    return image


def pil_to_base64(img):
    import base64
    from io import BytesIO

    buffer = BytesIO()
    img.save(buffer, "png")
    img_str = base64.b64encode(buffer.getvalue()).decode("ascii")

    return img_str


@stub.webhook
def main(prompt: str):
    from deep_translator import GoogleTranslator

    prompt = GoogleTranslator(
        source='auto', target='en').translate(prompt)

    image = run_stable_diffusion.call(prompt)
    base64 = pil_to_base64(image)
    return {"image": base64}
