import time
import json
import urllib.request
import subprocess
import re
import os

def main():
    print("🚀 Starting ngrok container...")
    subprocess.run(["docker", "compose", "up", "-d", "ngrok"])

    print("⏳ Waiting for ngrok to establish tunnels (5 seconds)...")
    time.sleep(5)

    print("📡 Fetching ngrok tunnels...")
    try:
        req = urllib.request.Request("http://localhost:4040/api/tunnels")
        with urllib.request.urlopen(req) as response:
            data = json.loads(response.read().decode())
            tunnels = data.get("tunnels", [])
            
            backend_url = ""
            front_url = ""
            
            for t in tunnels:
                if t["name"] == "backend":
                    backend_url = t["public_url"]
                elif t["name"] == "frontend":
                    front_url = t["public_url"]
            
            if not backend_url or not front_url:
                print("❌ Could not find both frontend and backend tunnels. Is ngrok running properly?")
                return

            print(f"✅ Backend URL: {backend_url}")
            print(f"✅ Frontend URL: {front_url}")
            
            # update .env
            env_path = ".env"
            if not os.path.exists(env_path):
                print(f"⚠️ {env_path} does not exist. Creating it...")
                with open(env_path, "w") as f:
                    f.write("")

            with open(env_path, "r") as f:
                content = f.read()
                
            # Replace existing or append
            if re.search(r"^BACKEND_URL=.*", content, flags=re.MULTILINE):
                content = re.sub(r"^BACKEND_URL=.*", f"BACKEND_URL={backend_url}", content, flags=re.MULTILINE)
            else:
                content += f"\nBACKEND_URL={backend_url}"

            if re.search(r"^FRONT_URL=.*", content, flags=re.MULTILINE):
                content = re.sub(r"^FRONT_URL=.*", f"FRONT_URL={front_url}", content, flags=re.MULTILINE)
            else:
                content += f"\nFRONT_URL={front_url}"
                
            with open(env_path, "w") as f:
                f.write(content.strip() + "\n")
                
            print("📝 Updated .env file.")
            
            print("🐳 Starting other services and rebuilding front...")
            subprocess.run(["docker", "compose", "up", "-d", "--build", "front", "server", "mongo"])
            print("🎉 All services started successfully!")

    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    main()
