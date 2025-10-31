# app/streamlit_app.py  (or app/streamlit_aa.py if that's what you run)
import os
import streamlit as st
from vllm.core.pipelines.speak_pipeline import SpeakPipeline
from vllm.core.providers.tts.piper_tts import PiperTTS
from vllm.core.providers.tts.pyttsx_tts import PyttsxTTS
from vllm.core.providers.video import VIDEO_PROVIDERS

st.set_page_config(page_title="VLLM – Local Avatar Talker", page_icon="🗣️", layout="centered")

st.sidebar.header("Settings")
tts_choice = st.sidebar.selectbox("TTS Provider", ["piper", "pyttsx3"], index=0)
video_choice = st.sidebar.selectbox("Video Provider", ["wav2lip", "infinitetalk", "fal_infinitalk", "veo3", "fal_veo3"], index=0)
fps = st.sidebar.number_input("Output FPS", min_value=15, max_value=60, value=25, step=1)
size = st.sidebar.number_input("Output size (px)", min_value=192, max_value=512, value=512, step=32)

st.title("🗣️ VLLM – Local Avatar Talker")
st.caption("Upload a face image, type text, and get a talking-head video. Local + optional cloud backends.")

# Image optional only for Veo (text-to-video). Required for lip-sync providers.
img_file = st.file_uploader("Upload a face image (.jpg/.png) — optional for Veo", type=["jpg","jpeg","png"])
text = st.text_area("Type what the avatar should say (or a prompt for Veo)", "Hello there!", height=120)

if st.button("🧵 Speak", type="primary"):
    if video_choice in ("wav2lip", "infinitetalk") and not img_file:
        st.error("Please upload an image for lip-sync providers.")
        st.stop()
    if not text.strip():
        st.error("Please enter some text.")
        st.stop()

    # Choose providers
    tts = PiperTTS() if tts_choice == "piper" else PyttsxTTS()
    VideoCls = VIDEO_PROVIDERS[video_choice]
    video = VideoCls()
    pipe = SpeakPipeline(tts=tts, video=video)

    with st.spinner(f"Generating via {video_choice}…"):
        try:
            result = pipe.invoke({
                "image_file": img_file,   # may be None for Veo
                "text": text,
                "fps": int(fps),
                "size": int(size),
            })
        except Exception as e:
            st.exception(e)
            st.stop()

    st.success("Done!")
    st.video(result["video_bytes"])
    st.download_button(
        "Download MP4",
        data=result["video_bytes"],
        file_name=result.get("video_name", "result.mp4"),
        mime="video/mp4"
    )
    st.audio(result["audio_bytes"])