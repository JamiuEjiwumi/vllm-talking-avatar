from fastapi import FastAPI, UploadFile, File, Form, Header, HTTPException
from fastapi.responses import FileResponse
import os, tempfile, subprocess, uuid, shutil

API_KEY = os.getenv("INFINITALK_API_KEY")
APP = FastAPI()

@APP.get("/health")
def health():
    return {"status": "ok"}

@APP.post("/generate")
async def generate(
    image: UploadFile = File(...),
    audio: UploadFile | None = File(default=None),
    fps: int = Form(25),
    size: int = Form(512),
    x_api_key: str | None = Header(default=None),
):
    if API_KEY and x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Unauthorized")

    work = tempfile.mkdtemp(prefix="inftalk_")
    try:
        img_path = os.path.join(work, image.filename or "face.png")
        with open(img_path, "wb") as f: f.write(await image.read())

        audio_path = None
        if audio is not None:
            audio_path = os.path.join(work, audio.filename or "voice.wav")
            with open(audio_path, "wb") as f: f.write(await audio.read())

        out_path = os.path.join(work, f"result_{uuid.uuid4().hex}.mp4")

        # TODO: swap this command to the actual InfiniteTalk entrypoint/flags.
        # Run from upstream/ so relative paths work.
        cmd = [
            "python", "tools/infer.py",
            "--image", img_path,
            "--audio", audio_path or "",
            "--size", str(size),
            "--fps", str(fps),
            "--out", out_path
        ]
        subprocess.run(cmd, cwd="/app/upstream", check=True)

        if not os.path.exists(out_path):
            raise HTTPException(status_code=500, detail="No output produced.")

        return FileResponse(out_path, media_type="video/mp4", filename="result.mp4")
    finally:
        shutil.rmtree(work, ignore_errors=True)
