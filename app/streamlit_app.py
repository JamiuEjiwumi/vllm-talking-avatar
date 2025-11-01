# app/streamlit_app.py
import os
import tempfile
import streamlit as st
from vllm.core.pipelines.speak_pipeline import SpeakPipeline
from vllm.core.providers.tts.piper_tts import PiperTTS
from vllm.core.providers.tts.pyttsx_tts import PyttsxTTS
from vllm.core.providers.video import VIDEO_PROVIDERS

st.set_page_config(page_title="VLLM – Talking Avatar", page_icon="Speech", layout="centered")

# === SIDEBAR ===
st.sidebar.header("Settings")
tts_choice = st.sidebar.selectbox("TTS Provider", ["piper", "pyttsx3"], index=0)
video_choice = st.sidebar.selectbox(
    "Video Provider",
    ["wav2lip", "sadtalker", "did", "fal_infinitalk", "veo3", "fal_veo3"],
    index=1  # default: sadtalker
)
fps = st.sidebar.number_input("Output FPS", min_value=15, max_value=60, value=25, step=1)
size = st.sidebar.number_input("Output size (px)", min_value=192, max_value=512, value=512, step=32)

# === MAIN UI ===
st.title("Speech VLLM – Realistic Talking Avatar")
st.caption("Upload face → type text → realistic head movement, eye blinks, lip sync")

img_file = st.file_uploader("Upload face image (.jpg/.png)", type=["jpg", "jpeg", "png"])
text = st.text_area("What should the avatar say?",
                    "Hello! I'm alive with real head movement and eye blinks.",
                    height=120)

if st.button("Speak", type="primary"):
    # === VALIDATION ===
    if video_choice in ("wav2lip", "sadtalker", "did") and not img_file:
        st.error("Please upload a face image for this provider.")
        st.stop()
    if not text.strip():
        st.error("Please enter some text.")
        st.stop()

    # === PROVIDERS ===
    tts = PiperTTS() if tts_choice == "piper" else PyttsxTTS()
    VideoCls = VIDEO_PROVIDERS[video_choice]
    video = VideoCls()

    # === TEMP FILES ===
    face_path = None
    audio_path = None
    out_path = None

    try:
        with st.spinner(f"Generating with **{video_choice}**..."):
            # Save image (if provided)
            if img_file:
                temp_dir = tempfile.mkdtemp(prefix="avatar_", dir="/tmp")
                face_path = os.path.join(temp_dir, "face.png")
                with open(face_path, "wb") as f:
                    f.write(img_file.getvalue())
                os.chmod(face_path, 0o644)

            # Output path
            out_fd, out_path = tempfile.mkstemp(suffix=".mp4", dir="/tmp")
            os.close(out_fd)

            if video_choice == "did":
                # D-ID handles speech itself; pass text via env for the provider
                os.environ["DID_TEXT"] = text
                result_path = video.generate(
                    face_image_path=face_path,
                    audio_wav_path=None,
                    out_mp4_path=out_path,
                    fps=fps,
                    size=size,
                )
            elif video_choice == "sadtalker":
                # Local TTS then SadTalker
                audio_fd, audio_path = tempfile.mkstemp(suffix=".wav", dir="/tmp")
                os.close(audio_fd)
                tts.synthesize(text, audio_path)
                result_path = video.generate(
                    face_image_path=face_path,
                    audio_wav_path=audio_path,
                    out_mp4_path=out_path,
                    fps=fps,
                    size=size,
                )
            else:
                # wav2lip / fal_* / veo3 via your SpeakPipeline
                audio_fd, audio_path = tempfile.mkstemp(suffix=".wav", dir="/tmp")
                os.close(audio_fd)
                tts.synthesize(text, audio_path)
                pipe = SpeakPipeline(tts=tts, video=video)
                result = pipe.invoke({
                    "image_file": img_file,
                    "text": text,
                    "fps": fps,
                    "size": size,
                })
                result_path = result.get("video_path") or out_path

            # Read result & display
            with open(result_path, "rb") as f:
                video_bytes = f.read()

        st.success("Video ready!")
        st.video(video_bytes)
        st.download_button("Download MP4", data=video_bytes,
                           file_name=f"avatar_{video_choice}.mp4", mime="video/mp4")
        if audio_path and os.path.exists(audio_path):
            st.audio(audio_path)

    except Exception as e:
        st.error("Generation failed:")
        st.exception(e)
    finally:
        # Cleanup
        for path in [audio_path, out_path]:
            if path and os.path.exists(path):
                try:
                    os.unlink(path)
                except:
                    pass
        if face_path:
            try:
                os.unlink(face_path)
            except:
                pass
            try:
                os.rmdir(os.path.dirname(face_path))
            except:
                pass
