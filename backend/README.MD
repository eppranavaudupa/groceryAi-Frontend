main.py code
python3.10 -m venv env
source ./env/bin/activate
save requirements.txt
pip install -r require,ments.txt 6. python main.py
Start backend: python app.py — ensure it prints that it's running on 0.0.0.0:5000.

Start frontend: npm run dev (Next.js). Open http://localhost:3000.

Mobile access: open the frontend on your phone using http://<your-pc-ip>:3000. Then the frontend will call http://<your-pc-ip>:5000/ai automatically. If you see CORS errors, add the phone's origin (e.g. http://192.168.x.y:3000) to the CORS(..., origins=[...]) list in app.py.

Session cookies: we use credentials: "include" on the client; keep that so session persists server-side. If cookies are not being set, check the browser devtools network tab and verify the Set-Cookie header from Flask.

Cart language: to add items by voice, speak phrases like "add 2 kg banana", "I want 1 apple", "add milk" — the backend tries to parse common patterns and falls back to looking for item names in grocery_prices.json