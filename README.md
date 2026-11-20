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
venv\Scripts\python identity.py download
cd ..\app
npm ci
npm run demo
```

`npm run demo` starts the backend on port 8000 and Expo; the app reaches the backend through Expo's port 8081
(`/api/...`, see `app/metro.config.js`). Scan the QR code with Expo Go.
If the phone can't connect, allow port 8081 in the Windows firewall.
`python identity.py download` fetches OpenCV's face models (about 37 MB) for the sign-up selfie check; without them
the selfie is sent to review unchecked.

Reading the phone's real SMS (Inbox tab) needs an Android development build instead of Expo Go:
`npx eas-cli build --profile development --platform android` from `app`, then install the APK on the phone.

Backend only: in `backend`, run `venv\Scripts\python -m uvicorn api:app --port 8000` and open
http://localhost:8000/demo. The demo's date is fixed at 2026-10-20 (change it with the `FINEXA_TODAY` variable).
