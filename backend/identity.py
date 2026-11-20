import base64
import binascii
import hashlib
import os
import sys
import urllib.request
from contextlib import closing
from datetime import date, datetime
from pathlib import Path

import users
from config import TODAY

BACKEND = Path(__file__).parent
DOCS_DIR = Path(os.environ.get("FINEXA_DOCS", BACKEND / "identity_docs"))
MODEL_DIR = BACKEND / "models" / "face"
ZOO = "https://github.com/opencv/opencv_zoo/raw/main/models/"
MODELS = {
    "detector": ("face_detection_yunet_2023mar.onnx", ZOO + "face_detection_yunet/face_detection_yunet_2023mar.onnx"),
    "recognizer": ("face_recognition_sface_2021dec.onnx",
                   ZOO + "face_recognition_sface/face_recognition_sface_2021dec.onnx"),
}
MATCH_SCORE = 0.363
MAX_IMAGE_BYTES = 5 * 1024 * 1024
IMAGE_TYPES = {b"\xff\xd8\xff": "jpg", b"\x89PNG": "png", b"RIFF": "webp"}
KINDS = {
    "id_front": "National ID, front",
    "id_back": "National ID, back",
    "selfie": "Selfie",
    "income_proof": "Proof of income (HR letter, payslip or salary statement)",
    "remote_proof": "Proof of remote work",
}
MIN_AGE = 18

GOVERNORATES = {
    "01": "Cairo", "02": "Alexandria", "03": "Port Said", "04": "Suez", "11": "Damietta", "12": "Dakahlia",
    "13": "Sharqia", "14": "Qalyubia", "15": "Kafr El Sheikh", "16": "Gharbia", "17": "Monufia", "18": "Beheira",
    "19": "Ismailia", "21": "Giza", "22": "Beni Suef", "23": "Fayoum", "24": "Minya", "25": "Asyut", "26": "Sohag",
    "27": "Qena", "28": "Aswan", "29": "Luxor", "31": "Red Sea", "32": "New Valley", "33": "Matrouh",
    "34": "North Sinai", "35": "South Sinai", "88": "Born abroad",
}
ARABIC_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")

SCHEMA = """
CREATE TABLE IF NOT EXISTS identity (
    user_id INTEGER PRIMARY KEY,
    id_hash TEXT UNIQUE,
    id_last4 TEXT, birth_date TEXT, governorate TEXT, gender TEXT,
    face_status TEXT, face_score REAL,
    status TEXT NOT NULL DEFAULT 'incomplete',
    updated TEXT
);
CREATE TABLE IF NOT EXISTS documents (
    user_id INTEGER NOT NULL,
    kind TEXT NOT NULL,
    file TEXT NOT NULL,
    uploaded TEXT NOT NULL,
    PRIMARY KEY (user_id, kind)
);
"""


class AlreadyUsed(ValueError):
    pass


def connect():
    con = users.connect()
    con.executescript(SCHEMA)
    return con


def stamp():
    return datetime.now().isoformat(timespec="seconds")


def check_national_id(number, today=TODAY):
    digits = str(number).translate(ARABIC_DIGITS).replace(" ", "")
    fail = lambda reason: {"ok": False, "reason": reason, "birth_date": None, "governorate": None, "gender": None}
    if len(digits) != 14 or not digits.isdigit():
        return fail("A national ID number has 14 digits.")
    century = {"2": 1900, "3": 2000}.get(digits[0])
    if century is None:
        return fail("The first digit must be 2 (born 1900-1999) or 3 (born 2000 or later).")
    try:
        born = date(century + int(digits[1:3]), int(digits[3:5]), int(digits[5:7]))
    except ValueError:
        return fail("Digits 2 to 7 are not a real birth date.")
    if born > today:
        return fail("The birth date in the number is in the future.")
    if digits[7:9] not in GOVERNORATES:
        return fail("Digits 8 and 9 are not a known governorate code.")
    age = today.year - born.year - ((today.month, today.day) < (born.month, born.day))
    if age < MIN_AGE:
        return fail(f"Finexa is for adults: the number says you are {age}.")
    return {"ok": True, "reason": None, "birth_date": born.isoformat(), "governorate": GOVERNORATES[digits[7:9]],
            "gender": "male" if int(digits[12]) % 2 else "female", "digits": digits}


def save_national_id(user_id, number):
    check = check_national_id(number)
    if not check["ok"]:
        raise ValueError(check["reason"])
    id_hash = hashlib.sha256(check["digits"].encode()).hexdigest()
    with closing(connect()) as con, con:
        other = con.execute("SELECT user_id FROM identity WHERE id_hash = ? AND user_id != ?",
                            (id_hash, user_id)).fetchone()
        if other:
            raise AlreadyUsed("This national ID already has a Finexa account.")
        con.execute("INSERT INTO identity (user_id) VALUES (?) ON CONFLICT(user_id) DO NOTHING", (user_id,))
        con.execute("UPDATE identity SET id_hash = ?, id_last4 = ?, birth_date = ?, governorate = ?, gender = ?, "
                    "updated = ? WHERE user_id = ?",
                    (id_hash, check["digits"][-4:], check["birth_date"], check["governorate"], check["gender"],
                     stamp(), user_id))
    return refresh(user_id)


def decode_image(image_b64):
    try:
        data = base64.b64decode(image_b64, validate=True)
    except binascii.Error:
        raise ValueError("The photo could not be read.")
    if len(data) > MAX_IMAGE_BYTES:
        raise ValueError("The photo is larger than 5 MB.")
    ext = next((e for magic, e in IMAGE_TYPES.items() if data.startswith(magic)), None)
    if ext is None:
        raise ValueError("The photo must be a JPEG, PNG or WebP image.")
    return data, ext


def save_document(user_id, kind, image_b64):
    if kind not in KINDS:
        raise ValueError(f"Unknown document: {kind}")
    data, ext = decode_image(image_b64)
    folder = DOCS_DIR / str(user_id)
    folder.mkdir(parents=True, exist_ok=True)
    for old in folder.glob(f"{kind}.*"):
        old.unlink()
    (folder / f"{kind}.{ext}").write_bytes(data)
    with closing(connect()) as con, con:
        con.execute("INSERT INTO identity (user_id) VALUES (?) ON CONFLICT(user_id) DO NOTHING", (user_id,))
        con.execute("INSERT OR REPLACE INTO documents (user_id, kind, file, uploaded) VALUES (?, ?, ?, ?)",
                    (user_id, kind, f"{kind}.{ext}", stamp()))
    documents_changed(user_id)
    if kind in ("id_front", "selfie"):
        run_face_check(user_id)
    return refresh(user_id)


def document_path(user_id, kind):
    with closing(connect()) as con:
        row = con.execute("SELECT file FROM documents WHERE user_id = ? AND kind = ?", (user_id, kind)).fetchone()
    return row and DOCS_DIR / str(user_id) / row["file"]



def download_models():
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    for name, url in MODELS.values():
        target = MODEL_DIR / name
        if not target.exists():
            print("downloading", name)
            urllib.request.urlretrieve(url, target)
    return [MODEL_DIR / name for name, _ in MODELS.values()]


def models_ready():
    return all((MODEL_DIR / name).exists() for name, _ in MODELS.values())


def largest_face(image, detector):
    import cv2
    h, w = image.shape[:2]
    scale = min(1.0, 1280 / max(h, w))
    if scale < 1:
        image = cv2.resize(image, (int(w * scale), int(h * scale)))
    detector.setInputSize((image.shape[1], image.shape[0]))
    _, faces = detector.detect(image)
    if faces is None or not len(faces):
        return None, image
    return max(faces, key=lambda f: f[2] * f[3]), image


def face_match(id_photo, selfie):
    if not models_ready():
        return {"status": "not_checked", "score": None,
                "reason": "The face model is not installed on the server (python identity.py download)."}
    import cv2
    import numpy as np
    cv2.utils.logging.setLogLevel(cv2.utils.logging.LOG_LEVEL_ERROR)
    detector = cv2.FaceDetectorYN.create(str(MODEL_DIR / MODELS["detector"][0]), "", (320, 320), 0.7, 0.3, 5000)
    recognizer = cv2.FaceRecognizerSF.create(str(MODEL_DIR / MODELS["recognizer"][0]), "")
    features = []
    for data, missing in ((id_photo, "no_face_id"), (selfie, "no_face_selfie")):
        image = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
        face, image = largest_face(image, detector) if image is not None else (None, None)
        if face is None:
            where = "the ID photo" if missing == "no_face_id" else "the selfie"
            return {"status": missing, "score": None, "reason": f"No face was found in {where}. Take it again in good light."}
        features.append(recognizer.feature(recognizer.alignCrop(image, face)))
    score = round(float(recognizer.match(features[0], features[1], cv2.FaceRecognizerSF_FR_COSINE)), 3)
    if score >= MATCH_SCORE:
        return {"status": "match", "score": score, "reason": "The selfie looks like the photo on the ID."}
    return {"status": "no_match", "score": score, "reason": "The selfie does not look like the photo on the ID."}


def run_face_check(user_id):
    front, selfie = document_path(user_id, "id_front"), document_path(user_id, "selfie")
    if not (front and selfie):
        return None
    result = face_match(front.read_bytes(), selfie.read_bytes())
    with closing(connect()) as con, con:
        con.execute("UPDATE identity SET face_status = ?, face_score = ?, updated = ? WHERE user_id = ?",
                    (result["status"], result["score"], stamp(), user_id))
    return result



FACE_REASON = {
    "match": "The selfie looks like the photo on the ID.",
    "no_match": "The selfie does not look like the photo on the ID.",
    "no_face_id": "No face was found in the ID photo.",
    "no_face_selfie": "No face was found in the selfie.",
    "not_checked": "The face was not checked automatically.",
}


def required_steps(remote):
    steps = ["national_id", "id_front", "id_back", "selfie", "work", "income_proof"]
    return steps + ["remote_proof"] if remote else steps


def progress(user_id):
    with closing(connect()) as con:
        row = con.execute("SELECT * FROM identity WHERE user_id = ?", (user_id,)).fetchone()
        docs = {r["kind"] for r in con.execute("SELECT kind FROM documents WHERE user_id = ?", (user_id,))}
    work = users.workplace(user_id)
    remote = bool(work and work["remote"])
    done = {"national_id": bool(row and row["id_hash"]), "work": bool(work), **{k: k in docs for k in KINDS}}
    steps = required_steps(remote)
    missing = [s for s in steps if not done[s]]
    face = row and row["face_status"]
    notes = []
    if face:
        notes.append(FACE_REASON[face] + (f" (score {row['face_score']:.2f}, match from {MATCH_SCORE})"
                                          if row["face_score"] is not None else ""))
    if remote:
        notes.append("Remote worker: the work-location check is off; the proof of remote work is reviewed instead.")
    return {
        "status": row["status"] if row else "incomplete",
        "steps": {s: done[s] for s in steps},
        "missing": missing,
        "remote": remote,
        "national_id": row and row["id_hash"] and {
            "last4": row["id_last4"], "birth_date": row["birth_date"], "governorate": row["governorate"],
            "gender": row["gender"]},
        "face": face and {"status": face, "score": row["face_score"], "reason": FACE_REASON[face]},
        "notes": notes,
    }


def refresh(user_id):
    p = progress(user_id)
    status = "incomplete" if p["missing"] else ("verified" if p["status"] == "verified" else "needs_review")
    if status != p["status"]:
        with closing(connect()) as con, con:
            con.execute("INSERT INTO identity (user_id) VALUES (?) ON CONFLICT(user_id) DO NOTHING", (user_id,))
            con.execute("UPDATE identity SET status = ?, updated = ? WHERE user_id = ?", (status, stamp(), user_id))
        p["status"] = status
    return p


def verify(user_id):
    p = refresh(user_id)
    if p["missing"]:
        raise ValueError("Not every sign-up step is done yet.")
    with closing(connect()) as con, con:
        con.execute("UPDATE identity SET status = 'verified', updated = ? WHERE user_id = ?", (stamp(), user_id))
    return progress(user_id)


def documents_changed(user_id):
    with closing(connect()) as con, con:
        con.execute("UPDATE identity SET status = 'needs_review' WHERE user_id = ? AND status = 'verified'", (user_id,))


if __name__ == "__main__":
    if sys.argv[1:] == ["download"]:
        print("saved", *download_models())
    else:
        print("usage: python identity.py download    (fetches the face models, about 37 MB)")
