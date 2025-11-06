1. Prerequisites

Azure Account (Free tier OK)
Azure CLI
Terraform


2. Clone & Enter Project
git clone https://github.com/JamiuEjiwumi/vllm-talking-avatar.git
cd vllm-talking-avatar



3. 🚀 Local Run (Docker Compose)
1️⃣ Create a .env file
FAL_API_KEY=sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxx
D_ID_API_KEY=xxxxxxxxxxxxxxxxxxxxxxxxxxxx
PORT=8501

2️⃣ Build and run the container
docker-compose up --build

3️⃣ Open the app
http://localhost:8501

4️⃣ Test the health endpoint
curl http://localhost:8501/_stcore/health

5️⃣ Stop the containers
docker-compose down


✅ Notes

Make sure your .env file is in the same directory as your docker-compose.yml.

If you change model files or app code, rebuild with --build.

Health endpoint returns 200 OK when Streamlit is up.


To Create and deploy on AZURE, Deploy with ONE terraform script.
1. cd terraform
2. terraform init
3. terraform apply -auto-approve
4. pick the url outputted after the resources finished creating.


🧠 Using the Web UI

1. Once the app is running (either locally or on Azure), open it in your browser:
👉 http://localhost:8501

You’ll see the Speech VLLM – Realistic Talking Avatar interface:

2. 🎛️ Settings Panel (left side)

- Movement style – choose how much facial motion and blinking the avatar shows (e.g., Subtle (D-ID)).

- Local TTS Provider – Leave at default.

3. Video Provider – select did (D-ID) or sadtalker depending on which model you want to drive video generation.

4. Output FPS / Size – Leave at default.

5. D-ID Voice & Realism – Leave at default.

7. 🖼️ Generate a Talking Avatar (main area)

- Upload a face image (.jpg or .png, ≤200 MB).
- The image should show a clear, front-facing head.
- Enter text in the message box — this is what the avatar will say.
    Example:

    Hello! I'm alive with real head movement and eye blinks.
- Click Speak to start generation and wait.

The system will:
- Render the final video.


runpod key: rpa_LJ27J375BAGQKLQ3TX20PWGTL5J7HNRX75HG065K1arlcf