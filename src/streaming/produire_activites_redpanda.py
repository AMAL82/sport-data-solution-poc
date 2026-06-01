"""
Production d'activités sportives vers Redpanda.

Rôle :
- lire une activité sportive depuis DuckDB ;
- transformer l'activité en événement JSON ;
- publier l'événement dans un topic Redpanda.

Exemples :
    python src/streaming/produire_activites_redpanda.py
    python src/streaming/produire_activites_redpanda.py --id-activite 10
"""

from pathlib import Path
import argparse
import json
import os
from datetime import datetime, date

import duckdb
from confluent_kafka import Producer
from dotenv import load_dotenv


RACINE_PROJET = Path(__file__).resolve().parents[2]
CHEMIN_BASE = RACINE_PROJET / "data" / "warehouse.duckdb"


def convertir_valeur_json(valeur):
    """
    Convertit les valeurs Python non sérialisables en JSON.
    """
    if isinstance(valeur, (datetime, date)):
        return valeur.isoformat()
    return valeur


def charger_configuration() -> tuple[str, str]:
    """
    Charge la configuration Redpanda depuis le fichier .env.
    """
    load_dotenv(RACINE_PROJET / ".env")

    bootstrap_servers = os.getenv("REDPANDA_BOOTSTRAP_SERVERS", "localhost:19092")
    topic = os.getenv("REDPANDA_TOPIC_ACTIVITES", "activites_sportives")

    return bootstrap_servers, topic


def recuperer_activite(id_activite: int | None = None) -> dict:
    """
    Récupère une activité sportive depuis DuckDB.

    Si aucun id_activite n'est fourni, récupère la dernière activité disponible.
    """
    if not CHEMIN_BASE.exists():
        raise FileNotFoundError(
            f"Base DuckDB introuvable : {CHEMIN_BASE}\n"
            "Lance d'abord : python src/utils/initialiser_entrepot.py"
        )

    connexion = duckdb.connect(str(CHEMIN_BASE))

    try:
        if id_activite is None:
            requete = """
                SELECT
                    a.id_activite,
                    a.id_salarie,
                    s.prenom,
                    s.nom,
                    a.id_sport,
                    sp.libelle AS sport,
                    a.date_debut,
                    a.date_fin,
                    a.distance_m,
                    a.duree_secondes,
                    a.commentaire,
                    a.source
                FROM bronze.raw_activites_sportives a
                LEFT JOIN bronze.raw_salaries s
                    ON a.id_salarie = s.id_salarie
                LEFT JOIN bronze.raw_sports sp
                    ON a.id_sport = sp.id_sport
                ORDER BY a.id_activite DESC
                LIMIT 1;
            """
            resultat = connexion.execute(requete).fetchdf()
        else:
            requete = """
                SELECT
                    a.id_activite,
                    a.id_salarie,
                    s.prenom,
                    s.nom,
                    a.id_sport,
                    sp.libelle AS sport,
                    a.date_debut,
                    a.date_fin,
                    a.distance_m,
                    a.duree_secondes,
                    a.commentaire,
                    a.source
                FROM bronze.raw_activites_sportives a
                LEFT JOIN bronze.raw_salaries s
                    ON a.id_salarie = s.id_salarie
                LEFT JOIN bronze.raw_sports sp
                    ON a.id_sport = sp.id_sport
                WHERE a.id_activite = ?;
            """
            resultat = connexion.execute(requete, [id_activite]).fetchdf()

        if resultat.empty:
            raise ValueError("Aucune activité trouvée dans DuckDB.")

        ligne = resultat.iloc[0].to_dict()

        return {
            cle: convertir_valeur_json(valeur)
            for cle, valeur in ligne.items()
        }

    finally:
        connexion.close()


def publier_evenement(activite: dict, bootstrap_servers: str, topic: str) -> None:
    """
    Publie l'activité sportive dans Redpanda.
    """
    producer = Producer(
        {
            "bootstrap.servers": bootstrap_servers,
            "client.id": "producer-activites-sportives",
        }
    )

    message = json.dumps(activite, ensure_ascii=False).encode("utf-8")
    cle = str(activite["id_activite"]).encode("utf-8")

    producer.produce(
        topic=topic,
        key=cle,
        value=message,
    )

    producer.flush()

    print("Événement publié dans Redpanda.")
    print(f"Topic : {topic}")
    print(f"Activité : {activite['id_activite']}")
    print(f"Sport : {activite.get('sport')}")
    print(f"Salarié : {activite.get('prenom')} {activite.get('nom')}")


def parser_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Publie une activité sportive dans Redpanda."
    )

    parser.add_argument(
        "--id-activite",
        type=int,
        default=None,
        help="Identifiant de l'activité à publier. Si absent, publie la dernière activité.",
    )

    return parser.parse_args()


if __name__ == "__main__":
    args = parser_arguments()

    activite = recuperer_activite(args.id_activite)
    bootstrap, topic_redpanda = charger_configuration()

    publier_evenement(
        activite=activite,
        bootstrap_servers=bootstrap,
        topic=topic_redpanda,
    )