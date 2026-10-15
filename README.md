# Finexa

Finexa is an Earned Wage Access app for salaried people in Egypt: withdraw part of the salary you have already earned
this month, before payday, with no employer integration. It reads your bank and wallet SMS to confirm your salary,
and explains every decision in plain language (Explainable AI).

## Run it (Windows)

You need Python 3.14, Node.js 24, and the Expo Go app on an Android phone on the same Wi-Fi.

```
cd backend
python -m venv venv
venv\Scripts\python -m pip install -r requirements.txt
cd ..\app
npm ci
npm run demo
```

`npm run demo` starts the backend on port 8000, a Cloudflare tunnel to it and Expo; scan the QR code with Expo Go.
If the phone can't connect, allow port 8081 in the Windows firewall.

Backend only: in `backend`, run `venv\Scripts\python -m uvicorn api:app --port 8000` and open
http://localhost:8000/demo. The demo's date is fixed at 2026-10-20 (change it with the `FINEXA_TODAY` variable).
