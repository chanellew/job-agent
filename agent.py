import csv
import json
from datetime import date
from pathlib import Path
from dotenv import load_dotenv
import anthropic

load_dotenv()
client = anthropic.Anthropic()
MODEL = "claude-sonnet-5-5"

# ---------- 1. Les tools : de simples fonctions Python ----------
def lire_fichier(nom: str) -> str:
    return Path(nom).read_text()

def sauvegarder_candidature(poste, entreprise, localisation, score, verdict, resume) -> str:
    fichier = Path("tracker.csv")
    nouveau = not fichier.exists()
    with fichier.open("a", newline="") as f:
        w = csv.writer(f)
        if nouveau:
            w.writerow(["date", "poste", "entreprise", "localisation", "score", "verdict", "resume", "statut"])
        w.writerow([date.today().isoformat(), poste, entreprise, localisation, score, verdict, resume, "à postuler"])
    return f"Candidature {entreprise} ajoutée au tracker."

TOOLS_PY = {"lire_fichier": lire_fichier, "sauvegarder_candidature": sauvegarder_candidature}

# ---------- 2. La description des tools, pour que Claude sache s'en servir ----------
TOOLS = [
    {
        "name": "lire_fichier",
        "description": "Lit un fichier texte local (ex : cv.md, offre.txt) et renvoie son contenu.",
        "input_schema": {
            "type": "object",
            "properties": {"nom": {"type": "string", "description": "Nom du fichier"}},
            "required": ["nom"],
        },
    },
    {
        "name": "sauvegarder_candidature",
        "description": "Ajoute une offre analysée au tracker CSV. À appeler une fois l'analyse terminée.",
        "input_schema": {
            "type": "object",
            "properties": {
                "poste": {"type": "string"},
                "entreprise": {"type": "string"},
                "localisation": {"type": "string"},
                "score": {"type": "integer", "description": "Adéquation CV/offre, de 0 à 100"},
                "verdict": {"type": "string", "enum": ["postuler", "postuler avec réserves", "passer"]},
                "resume": {"type": "string", "description": "2 phrases max"},
            },
            "required": ["poste", "entreprise", "localisation", "score", "verdict", "resume"],
        },
    },
]

# ---------- 3. Le contexte : c'est ce qui rend l'agent pertinent ----------
SYSTEM = """Tu es l'assistant de recherche d'emploi d'une Product Manager.
Utilise tes outils : lis le CV et l'offre, analyse honnêtement l'adéquation,
sauvegarde le résultat dans le tracker, puis donne un résumé court (5 lignes max).

Contexte de la candidate (à prendre en compte dans l'analyse) :
- Poste actuel en VIE, contrat à durée fixe qui se termine fin décembre 2026 : ce n'est PAS un départ anticipé
- Disponible début janvier 2027
- Cherche idéalement à l'étranger, de préférence dans un pays anglophone
- Ne veut pas de full remote
"""

# ---------- 4. La boucle d'agent ----------
def run_agent(demande: str):
    messages = [{"role": "user", "content": demande}]

    while True:
        response = client.messages.create(
            model=MODEL, max_tokens=2000, system=SYSTEM, tools=TOOLS, messages=messages
        )
        messages.append({"role": "assistant", "content": response.content})

        # Claude a fini : il ne demande plus d'outil
        if response.stop_reason != "tool_use":
            for block in response.content:
                if block.type == "text":
                    print("\n" + block.text)
            return

        # Claude veut utiliser des outils : on les exécute et on lui renvoie les résultats
        resultats = []
        for block in response.content:
            if block.type == "tool_use":
                print(f"🔧 {block.name}({json.dumps(block.input, ensure_ascii=False)[:80]})")
                resultat = TOOLS_PY[block.name](**block.input)
                resultats.append({"type": "tool_result", "tool_use_id": block.id, "content": resultat})
        messages.append({"role": "user", "content": resultats})


run_agent("Analyse l'offre dans offre.txt par rapport à mon CV (cv.md) et ajoute-la à mon tracker.")