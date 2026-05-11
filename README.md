<p align="center">
  <img src="front/public/puryfier_main.png" width="600px" alt="Puryfier" />
  <br><b>🌙 Puryfier</b>
</p>

**Puryfier** is a Chaster extension that link [Pury.fi](https://pury.fi/) with [Chaster.app](https://chaster.app/) to provide more fun to your chastity locks and self lock.

## ✨ Key Features

- ❄️ Lock & Enable Puryfi when your lock is frozen.
- 🔓 Unlock & Disable Puryfi when your lock is unfrozed.
- 📸 Add time when a media is censored by Puryfi.

## 🚀 Goals

Censorship is fun, even more when involving other things such as Chastity, Denial and more.. Puryfier is something made to help you to have fun with these.

## 📖 Requirements

- Puryfi 0.8.6.0 or higher
- Docker & Docker Compose
- Chaster Extension (+ public exposed endpoints for webhook)
- Public endpoint (can use ngrok, cloudflared, etc.)

## 🌟 Run

**⚠ Fill the `.env` file before running using docker compose.**

```bash
git clone https://github.com/httxSereti/puryfier.git
cd puryfier
cp .env.example .env
# Edit .env and provide your NGROK_AUTHTOKEN
docker compose up -d
```

## ❓ How to use

1. Copy .env.example as .env and fill it. Make sure to get your `NGROK_AUTHTOKEN` from [ngrok dashboard](https://dashboard.ngrok.com/get-started/your-authtoken) and add it to the file.
2. Run using Docker Compose: `docker compose up -d`
3. After starting, go to `http://localhost:4040` to see your Ngrok dashboard. There you will find the 2 public URLs provided by Ngrok (one for the `frontend`, one for the `backend`).
4. Create a Chaster extension with these URLs .
```
Main page URL: <frontend-ngrok-url>/extension/main
Configuration page URL: <frontend-ngrok-url>/extension/configuration
Webhook URL: <backend-ngrok-url>/api/webhooks/extensions/chaster
```
5. Open Puryfi -> Plugins -> Register new plugin -> WebSocket (url: ws://<backend-ngrok-domain> without https://)
6. Use the Chaster extension (open main page of the extension as wearer only) to generate a linking token
7. Link Chaster extension in the plugin settings (copy paste the token)
8. Enjoy!

## 🤝 How to Contribute / Contact Us

I've made a discord server to centralize information, suggestions, bugs and more.
You can join it [here](https://discord.gg/vD8zyyMXne)

* 🌍 [Website](https://paa.ge/sereti)
* ✉️ [Email](mailto:httxsereti@gmail.com)
* 💜 [Discord](https://discord.com/users/939288874281222225)