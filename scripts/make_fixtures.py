"""Extrait les enregistrements témoins des extractions complètes."""
import json
from pathlib import Path

WITNESSES = [
    "b10bbbfc-cf9e-42e0-be17-e2c3e1d2600d",  # The Beatles
    "9d953ee6-4ea6-4b0e-aea6-7268d380bef1",  # homonyme
    "8d3431db-bc83-4dc2-93b8-0e46e31d09f7",  # homonyme
    "9a58fda3-f4ed-4080-a3a5-f457aac9fcdd",  # Joy Division
    "f1106b17-dcbb-45f6-b938-199ccfab50cc",  # New Order
    "a3cb23fc-acd3-4ce0-8f36-1e5aa6a18432",  # U2
    "8f6bd1e4-fbe1-4f50-aa9b-94c450ec0f11",  # Portishead
    "97c86b2c-2765-46a2-aef8-76a7e24c430f",  # XTC
    "e598d30e-4ce1-402e-94a7-6f44779da6b7",  # Orange Juice
    "6959c3d5-3e7f-41bb-aba3-50e38225d23d",  # homonyme
    "a9424175-8b06-44ad-a1f4-319e92a50879",  # Disincarnate
    "125948ec-7f91-4d1a-8b83-accbf50fae3d",  # 3OH!3
    "d25be955-6fed-4303-bffb-8c440c191edb",  # Lethal Shöck
    "53fc0417-7585-490c-b2ea-5f9737e14c0f",  # Blackdeath
    "1434b0d0-d647-421e-b345-1b9847045a52",  # Cleef
    "6dfa03fb-8b02-4055-b7cc-e48f426b13f8",  # Unheilig
    "d770374d-05e9-4ed3-a068-3fbd4e6e4dd6",  # Wiener Philharmoniker
    "0ab49580-c84f-44d4-875f-d83760ea2cfe",  # Maroon 5
    "703c4c92-43f7-4268-9f85-0ca6f0cd1a22",  # Polska Radio One
    "f7338f2a-136b-4d5e-b099-5504cf997f58",  # Cardiacs
    "bd13909f-1c29-4c27-a874-d4aaf27c5b1a",  # Fleetwood Mac
    "3cb86073-22d7-43d5-8f22-422b1e54988e",  # ROD
    "212faddb-cd09-4fbc-9336-3ed7cadfba68",  # Flesh Field
    "8a1f012c-acc1-4dda-878f-43ac02f2366f",  # Demented Are Go!
    "62f7a211-0056-45fe-934a-37a388a7356f",  # The Belle Stars
    "35ddcb29-4c16-4af6-b6f8-32143ee24a6c",  # Handel and Haydn Society
    "d36b0fad-abd7-44e4-88fa-f638bbf8c9a6",  # Thunder Jolt
    "03c2e506-e8bb-4bd6-9693-5aa97c8eea1c",  # Inspiral Carpets
]

if __name__ == "__main__":
    work = Path("data/work")
    out = Path("pipeline/tests/fixtures")
    out.mkdir(parents=True, exist_ok=True)
    wanted = set(WITNESSES)

    kept = []
    with open(out / "artists.jsonl", "w", encoding="utf-8") as fh:
        for line in open(work / "artists.jsonl", encoding="utf-8"):
            rec = json.loads(line)
            if rec["mbid"] in wanted:
                fh.write(line)
                kept.append(rec["mbid"])

    with open(out / "release_groups.jsonl", "w", encoding="utf-8") as fh:
        for line in open(work / "release_groups.jsonl", encoding="utf-8"):
            rec = json.loads(line)
            if wanted & set(rec["artists"]):
                fh.write(line)

    print("témoins trouvés :", len(kept))
    missing = wanted - set(kept)
    print("manquants :", missing or "aucun")
