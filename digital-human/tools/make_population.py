"""Generate N distinct character configs (data only) for the 100-agent extension.
python tools/make_population.py 100 pipeline/characters/population
Each config is consumed unchanged by pipeline/build_all.sh."""
import json
import os
import random
import sys

N = int(sys.argv[1]) if len(sys.argv) > 1 else 100
OUT = sys.argv[2] if len(sys.argv) > 2 else "pipeline/characters/population"
base = json.load(open(os.path.join(os.path.dirname(__file__), "..", "pipeline", "characters", "minjun.json")))
rng = random.Random(42)
os.makedirs(OUT, exist_ok=True)
FIRST = ["Seo-yeon", "Ji-ho", "Ha-eun", "Do-yun", "Min-seo", "Ye-jun", "Alex", "Maria", "David", "Aisha", "Kenji", "Lucas", "Sofia", "Omar", "Mei"]
for i in range(N):
    male = rng.random() < 0.5
    age = rng.choice([rng.uniform(18, 35), rng.uniform(35, 60), rng.uniform(60, 80)])
    eth = [rng.random() ** 2 for _ in range(3)]
    s = sum(eth)
    h = rng.gauss(175 if male else 162, 7)
    c = json.loads(json.dumps(base))
    c["id"] = f"p{i:03d}"
    c["name"] = rng.choice(FIRST) + f" #{i}"
    c["macro"].update({"gender": 1.0 if male else 0.0, "age_years": round(age, 1), "height_cm": round(h, 1),
                       "muscle": round(rng.uniform(0.3, 0.75), 2), "weight": round(rng.uniform(0.3, 0.8), 2),
                       "proportions": round(rng.uniform(0.4, 0.8), 2),
                       "african": round(eth[0] / s, 3), "asian": round(eth[1] / s, 3), "caucasian": round(eth[2] / s, 3)})
    c["modifiers"] = {k: round(rng.uniform(-0.35, 0.35), 3) for k in base["modifiers"]}
    c["asymmetry"] = {k: round(rng.uniform(0, 0.4), 3) for k in base["asymmetry"]}
    c["look"].update({"seed": rng.randrange(1 << 30), "melanin": round(0.15 + 0.8 * eth[0] / s + rng.uniform(-0.05, 0.1), 3),
                      "beard_shadow": round(rng.uniform(0.2, 0.8), 2) if male else 0.0,
                      "freckle_density": round(rng.uniform(0, 0.3), 2), "hair_melanin": round(rng.uniform(0.3, 0.98), 2)})
    c["personality"] = {k: round(rng.uniform(0.15, 0.9), 2) for k in base["personality"]}
    c["voice"] = {"ko": {"provider": "typecast", "voice_id": None}, "en": {"provider": "typecast", "voice_id": None}}
    json.dump(c, open(os.path.join(OUT, f"{c['id']}.json"), "w"), indent=1, ensure_ascii=False)
print(f"wrote {N} configs to {OUT}")
