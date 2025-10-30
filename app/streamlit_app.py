import ssl
ssl._create_default_https_context = ssl._create_unverified_context

import os
import streamlit as st
from vllm.core.pipelines.speak_pipeline import SpeakPipeline
from vllm.core.providers.tts.piper_tts import PiperTTS
from vllm.core.providers.tts.pyttsx_tts import PyttsxTTS
from vllm.core.providers.video.wav2lip_provider import Wav2LipProvider

st.set_page_config(page_title="VLLM – Local Avatar Talker", page_icon="🗣️", layout="centered")

st.sidebar.header("Settings")
tts_choice = st.sidebar.selectbox("TTS Provider", ["piper", "pyttsx3"], index=0)
video_choice = st.sidebar.selectbox("Video Provider", ["wav2lip"], index=0)
fps = st.sidebar.number_input("Output FPS", min_value=15, max_value=60, value=25, step=1)
size = st.sidebar.number_input("Output size (px)", min_value=192, max_value=512, value=512, step=32)

st.title("🗣️ VLLM – Local Avatar Talker")
st.caption("Upload a face image, type text, and get a talking-head video. Runs locally.")

img_file = st.file_uploader("Upload a face image (.jpg/.png)", type=["jpg","jpeg","png"])
text = st.text_area("Type what the avatar should say", "Hello there! This runs on my machine.", height=120)

if st.button("🧵 Speak", type="primary"):
    if not img_file or not text.strip():
        st.error("Please upload an image and enter some text.")
        st.stop()

    # Choose providers
    tts = PiperTTS() if tts_choice == "piper" else PyttsxTTS()
    if video_choice == "wav2lip":
        video = Wav2LipProvider()
    else:
        st.error("Only wav2lip is wired right now.")
        st.stop()

    pipe = SpeakPipeline(tts=tts, video=video)

    with st.spinner("Generating..."):
        try:
            result = pipe.invoke({
                "image_file": img_file,
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