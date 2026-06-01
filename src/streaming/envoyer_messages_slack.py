"""
Envoi des messages Slack pour les activités sportives.

Rôle :
- récupérer les activités sportives NON encore notifiées depuis DuckDB ;
- construire un message Slack anonymisé ;
- envoyer le message via webhook Slack (ou simuler en mode dry_run) ;
- enregistrer le statut d'envoi dans gold.messages_slack (idempotence).

Garde-fous production :
- IDEMPOTENCE : une activité déjà notifiée (statut ENVOYE) n'est jamais renvoyée.
- RATE LIMIT : --limite borne le nombre de messages par exécution.
- DRY RUN : SLACK_MODE=dry_run dans .env permet de tester sans rien envoyer.

Exemples :
    python src/streaming/envoyer_messages_slack.py
    python src/streaming/envoyer_messages_slack.py --limite 10
    python src/streaming/envoyer_messages_slack.py --id-activite 10
"""

from pathlib import Path
import argparse
import os
from datetime import datetime
import random

import duckdb
import requests
from dotenv import load_dotenv


RACINE_PROJET = Path(__file__).resolve().parents[2]
CHEMIN_BASE = RACINE_PROJET / "data" / "warehouse.duckdb"


TEMPLATES = {
    "Course à pied": [
        "Bravo {prenom} {initiale}. ! Tu viens de courir {distance_km} km en {duree_min} min ! 🔥",
        "Super sortie {prenom} {initiale}. : {distance_km} km de course réalisés ! 🏃",
    ],
    "Vélo": [
        "Magnifique {prenom} {initiale}. ! {distance_km} km à vélo, belle énergie ! 🚴",
        "Belle sortie vélo {prenom} {initiale}. : {distance_km} km parcourus !",
    ],
    "Randonnée": [
        "Bravo {prenom} {initiale}. ! Une randonnée de {distance_km} km terminée 🌄",
        "Super randonnée {prenom} {initiale}. : {distance_km} km au compteur !",
    ],
    "Marche": [
        "Bravo {prenom} {initiale}. ! {distance_km} km de marche réalisés 🚶",
        "Belle marche {prenom} {initiale}. : {distance_km} km parcourus !",
    ],
    "Yoga": [
        "Zen {prenom} {initiale}. ! {duree_min} min de yoga pour recharger les batteries 🧘",
    ],
    "Natation": [
        "Bravo {prenom} {initiale}. ! {distance_km} km de natation réalisés 🏊",
    ],
    "Tennis": [
        "Belle séance de tennis {prenom} {initiale}. pendant {duree_min} min 🎾",
    ],
    "Escalade": [
        "Bravo {prenom} {initiale}. ! Belle séance d'escalade de {duree_min} min 🧗",
    ],
    "Fitness": [
        "Super séance fitness {prenom} {initiale}. pendant {duree_min} min 💪",
    ],
}


def charger_configuration() -> str:
    """
    Charge l'URL du webhook Slack depuis le fichier .env.
    """
    load_dotenv(RACINE_PROJET / ".env")

    webhook_url = os.getenv("SLACK_WEBHOOK_URL")

    if not webhook_url:
        raise ValueError(
            "SLACK_WEBHOOK_URL manquant dans le fichier .env. "
            "Ajoute ton webhook Slack dans .env."
        )

    return webhook_url


def recuperer_activites_a_notifier(
    limite: int = 5,
    id_activite: int | None = None,
) -> list[dict]:
    """
    Récupère les activités NON encore notifiées sur Slack (anti-spam).

    - Si id_activite est fourni : cible cette activité précise (pour debug/démo).
    - Sinon : toutes les activités dont l'id n'est pas déjà ENVOYE,
      des plus anciennes aux plus récentes, bornées par `limite`.
    """
    if not CHEMIN_BASE.exists():
        raise FileNotFoundError(
            f"Base DuckDB introuvable : {CHEMIN_BASE}\n"
            "Lance d'abord : python src/utils/initialiser_entrepot.py"
        )

    connexion = duckdb.connect(str(CHEMIN_BASE))

    try:
        base_select = """
            SELECT
                a.id_activite,
                a.id_salarie,
                s.prenom,
                s.nom,
                sp.libelle AS sport,
                a.distance_m,
                a.duree_secondes,
                a.commentaire
            FROM bronze.raw_activites_sportives a
            LEFT JOIN bronze.raw_salaries s
                ON a.id_salarie = s.id_salarie
            LEFT JOIN bronze.raw_sports sp
                ON a.id_sport = sp.id_sport
        """

        if id_activite is not None:
            requete = base_select + " WHERE a.id_activite = ?;"
            resultat = connexion.execute(requete, [id_activite]).fetchdf()
        else:
            requete = base_select + """
                WHERE a.id_activite NOT IN (
                    SELECT id_activite
                    FROM gold.messages_slack
                    WHERE statut_envoi = 'ENVOYE'
                )
                ORDER BY a.id_activite ASC
                LIMIT ?;
            """
            resultat = connexion.execute(requete, [limite]).fetchdf()

        return resultat.to_dict("records")

    finally:
        connexion.close()


def anonymiser_nom(nom: str) -> str:
    """
    Retourne uniquement l'initiale du nom.
    """
    if not nom or str(nom).lower() == "nan":
        return "X"

    return str(nom).strip()[0].upper()


def construire_message(activite: dict) -> str:
    """
    Construit un message Slack anonymisé à partir d'une activité.
    """
    sport = activite.get("sport") or "Activité sportive"
    prenom = str(activite.get("prenom") or "Salarié").strip()
    initiale = anonymiser_nom(activite.get("nom"))

    distance_m = activite.get("distance_m")
    duree_secondes = activite.get("duree_secondes") or 0
    commentaire = activite.get("commentaire")

    distance_km = ""
    if distance_m is not None:
        try:
            distance_km = round(float(distance_m) / 1000, 1)
        except Exception:
            distance_km = ""

    duree_min = round(float(duree_secondes) / 60)

    templates_sport = TEMPLATES.get(
        sport,
        ["Bravo {prenom} {initiale}. ! Belle activité sportive réalisée !"],
    )

    template = random.choice(templates_sport)

    message = template.format(
        prenom=prenom,
        initiale=initiale,
        distance_km=distance_km,
        duree_min=duree_min,
    )

    if commentaire and str(commentaire).strip() and str(commentaire).lower() != "nan":
        message += f' ("{str(commentaire).strip()}")'

    return message


def envoyer_message_slack(webhook_url: str, message: str) -> str:
    """
    Envoie le message à Slack via webhook.

    Respecte SLACK_MODE : si 'dry_run', n'envoie rien et retourne DRY_RUN.
    """
    mode = os.getenv("SLACK_MODE", "production").strip().lower()

    if mode == "dry_run":
        print(f"[DRY RUN] Message non envoyé : {message}")
        return "DRY_RUN"

    reponse = requests.post(
        webhook_url,
        json={"text": message},
        timeout=10,
    )

    if reponse.status_code == 200:
        return "ENVOYE"

    return f"ECHEC_{reponse.status_code}"


def enregistrer_message(
    id_activite: int,
    contenu_message: str,
    statut_envoi: str,
) -> None:
    """
    Enregistre le message Slack dans gold.messages_slack.
    """
    connexion = duckdb.connect(str(CHEMIN_BASE))

    try:
        prochain_id = connexion.execute(
            "SELECT COALESCE(MAX(id_message), 0) + 1 FROM gold.messages_slack;"
        ).fetchone()[0]

        connexion.execute(
            """
            INSERT INTO gold.messages_slack (
                id_message,
                id_activite,
                date_envoi,
                contenu_message,
                statut_envoi
            )
            VALUES (?, ?, ?, ?, ?);
            """,
            [
                prochain_id,
                int(id_activite),
                datetime.now(),
                contenu_message,
                statut_envoi,
            ],
        )

    finally:
        connexion.close()


def traiter_messages_slack(
    limite: int = 5,
    id_activite: int | None = None,
) -> None:
    """
    Pipeline complet d'envoi Slack avec anti-spam.

    Ne notifie que les activités non encore envoyées (idempotence),
    dans la limite fixée. Si rien à notifier : sortie propre, sans erreur.
    """
    webhook_url = charger_configuration()
    activites = recuperer_activites_a_notifier(limite=limite, id_activite=id_activite)

    if not activites:
        print("Aucune nouvelle activité à notifier. Rien à envoyer.")
        return

    print(f"{len(activites)} activité(s) à notifier.")

    for activite in activites:
        message = construire_message(activite)
        statut = envoyer_message_slack(webhook_url, message)

        enregistrer_message(
            id_activite=int(activite["id_activite"]),
            contenu_message=message,
            statut_envoi=statut,
        )

        print(f"  Activité {activite['id_activite']} → {statut} : {message}")

    print("Traitement Slack terminé.")


def parser_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Envoie des messages Slack pour les activités non notifiées."
    )

    parser.add_argument(
        "--limite",
        type=int,
        default=5,
        help="Nombre max de messages par exécution (anti-flood). Défaut : 5.",
    )

    parser.add_argument(
        "--id-activite",
        type=int,
        default=None,
        help="Cible une activité précise (debug/démo). Ignore le filtre anti-spam.",
    )

    return parser.parse_args()


if __name__ == "__main__":
    args = parser_arguments()
    traiter_messages_slack(limite=args.limite, id_activite=args.id_activite)