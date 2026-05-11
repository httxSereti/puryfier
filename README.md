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
git clone https://github.com/httxSereti/puryfi-chaster-linker.git
cd puryfi-chaster-linker
cp .env.example .env
docker compose up -d
```

## ❓ How to use

1. Copy .env.example as .env and fill it
2. Create a Chaster extension with a public reachable endpoints for webhook (i personally use ngrok)
```
Main page URL: http://localhost:5173/extension/main
Configuration page URL: http://localhost:5173/extension/configuration
Webhook URL: https://<your-public-domain>/api/webhooks/extensions/chaster
```
3. Run using Docker Compose
4. Open Puryfi -> Plugins -> Register new plugin -> WebSocket (default url: ws://localhost:8000)
5. Use the Chaster extension (open main page of the extension as wearer only) to generate a linking token
6. Link Chaster extension in the plugin settings (copy paste the token)
7. Enjoy!

## 🤝 How to Contribute / Contact Us

I've made a discord server to centralize information, suggestions, bugs and more.
You can join it [here](https://discord.gg/vD8zyyMXne)

* 🌍 [Website](https://paa.ge/sereti)
* ✉️ [Email](mailto:httxsereti@gmail.com)
* 💜 [Discord](https://discord.com/users/939288874281222225)