"""
Génération d'activités sportives simulées.

Rôle :
- lire les salariés chargés dans bronze.raw_salaries ;
- créer un référentiel de sports ;
- générer plusieurs milliers d'activités sportives sur 12 mois ;
- charger les données dans bronze.raw_sports, bronze.raw_pratiques_sportives
  et bronze.raw_activites_sportives.

Exemple :
    python src/generation/generer_activites_sportives.py
    python src/generation/generer_activites_sportives.py --nb-activites 5000
"""

from pathlib import Path
import argparse
import random
from datetime import datetime, timedelta

import duckdb


RACINE_PROJET = Path(__file__).resolve().parents[2]
CHEMIN_BASE = RACINE_PROJET / "data" / "warehouse.duckdb"


SPORTS = [
    (1, "Course à pied", "outdoor"),
    (2, "Vélo", "outdoor"),
    (3, "Randonnée", "outdoor"),
    (4, "Marche", "outdoor"),
    (5, "Yoga", "indoor"),
    (6, "Natation", "indoor"),
    (7, "Tennis", "collectif"),
    (8, "Escalade", "indoor"),
    (9, "Fitness", "indoor"),
]


PROFILS = {
    "inactif": (0, 3),
    "debutant": (4, 14),
    "regulier": (15, 45),
    "sportif": (46, 95),
}


def verifier_base() -> None:
    if not CHEMIN_BASE.exists():
        raise FileNotFoundError(
            f"Base DuckDB introuvable : {CHEMIN_BASE}\n"
            "Lance d'abord : python src/utils/initialiser_entrepot.py"
        )


def charger_salaries(connexion: duckdb.DuckDBPyConnection):
    salaries = connexion.execute(
        """
        SELECT id_salarie, date_embauche
        FROM bronze.raw_salaries
        WHERE id_salarie IS NOT NULL
        """
    ).fetchall()

    if not salaries:
        raise ValueError(
            "Aucun salarié trouvé dans bronze.raw_salaries. "
            "Lance d'abord l'ingestion RH."
        )

    return salaries


def choisir_profil() -> str:
    return random.choices(
        population=["inactif", "debutant", "regulier", "sportif"],
        weights=[20, 30, 30, 20],
        k=1,
    )[0]


def choisir_sport() -> tuple[int, str]:
    sport = random.choices(
        population=SPORTS,
        weights=[25, 20, 15, 15, 8, 6, 4, 3, 4],
        k=1,
    )[0]
    return sport[0], sport[1]


def generer_distance_et_duree(sport: str) -> tuple[int | None, int]:
    if sport == "Course à pied":
        distance = random.randint(3000, 22000)
        vitesse_kmh = random.uniform(7, 13)
    elif sport == "Vélo":
        distance = random.randint(8000, 80000)
        vitesse_kmh = random.uniform(14, 28)
    elif sport == "Randonnée":
        distance = random.randint(4000, 25000)
        vitesse_kmh = random.uniform(3, 6)
    elif sport == "Marche":
        distance = random.randint(1000, 12000)
        vitesse_kmh = random.uniform(3, 6)
    elif sport == "Natation":
        distance = random.randint(500, 3000)
        vitesse_kmh = random.uniform(2, 4)
    elif sport == "Tennis":
        distance = None
        return distance, random.randint(3600, 7200)
    elif sport == "Escalade":
        distance = None
        return distance, random.randint(3600, 10800)
    elif sport == "Yoga":
        distance = None
        return distance, random.randint(1800, 5400)
    else:
        distance = None
        return distance, random.randint(1800, 7200)

    duree_heures = (distance / 1000) / vitesse_kmh
    duree_secondes = int(duree_heures * 3600)

    return distance, max(duree_secondes, 60)


def generer_date_activite(date_embauche) -> datetime:
    maintenant = datetime.now()
    debut_periode = maintenant - timedelta(days=365)

    if date_embauche:
        date_embauche_dt = datetime.combine(date_embauche, datetime.min.time())
        debut_periode = max(debut_periode, date_embauche_dt)

    delta_jours = max((maintenant - debut_periode).days, 1)
    jour_aleatoire = random.randint(0, delta_jours)

    date_debut = debut_periode + timedelta(days=jour_aleatoire)

    # Activités plus fréquentes en soirée ou le week-end
    heure = random.choices([7, 12, 18, 19, 20], weights=[15, 10, 35, 25, 15], k=1)[0]
    minute = random.choice([0, 10, 15, 20, 30, 45])

    return date_debut.replace(hour=heure, minute=minute, second=0, microsecond=0)


def generer_commentaire(sport: str) -> str:
    commentaires = [
        "",
        "Bonne séance",
        "Sortie après le travail",
        "Reprise du sport",
        "Séance tranquille",
        "Très bonne énergie",
        "Activité du week-end",
        f"{sport} avec de bonnes sensations",
    ]
    return random.choice(commentaires)


def vider_tables(connexion: duckdb.DuckDBPyConnection) -> None:
    connexion.execute("DELETE FROM bronze.raw_activites_sportives;")
    connexion.execute("DELETE FROM bronze.raw_pratiques_sportives;")
    connexion.execute("DELETE FROM bronze.raw_sports;")


def inserer_sports(connexion: duckdb.DuckDBPyConnection) -> None:
    connexion.executemany(
        """
        INSERT INTO bronze.raw_sports (
            id_sport,
            libelle,
            categorie
        )
        VALUES (?, ?, ?);
        """,
        SPORTS,
    )


def generer_activites(nb_activites_cible: int) -> None:
    verifier_base()

    connexion = duckdb.connect(str(CHEMIN_BASE))

    try:
        salaries = charger_salaries(connexion)
        vider_tables(connexion)
        inserer_sports(connexion)

        activites = []
        pratiques = set()
        id_activite = 1

        while len(activites) < nb_activites_cible:
            id_salarie, date_embauche = random.choice(salaries)
            profil = choisir_profil()
            min_act, max_act = PROFILS[profil]

            nb_activites_salarie = random.randint(min_act, max_act)

            for _ in range(nb_activites_salarie):
                if len(activites) >= nb_activites_cible:
                    break

                id_sport, sport = choisir_sport()
                distance_m, duree_secondes = generer_distance_et_duree(sport)
                date_debut = generer_date_activite(date_embauche)
                date_fin = date_debut + timedelta(seconds=duree_secondes)
                commentaire = generer_commentaire(sport)

                activites.append(
                    (
                        id_activite,
                        id_salarie,
                        id_sport,
                        date_debut,
                        date_fin,
                        distance_m,
                        duree_secondes,
                        commentaire,
                        "simulation_strava",
                    )
                )

                pratiques.add((id_salarie, id_sport))
                id_activite += 1

        connexion.executemany(
            """
            INSERT INTO bronze.raw_pratiques_sportives (
                id_salarie,
                id_sport
            )
            VALUES (?, ?);
            """,
            list(pratiques),
        )

        connexion.executemany(
            """
            INSERT INTO bronze.raw_activites_sportives (
                id_activite,
                id_salarie,
                id_sport,
                date_debut,
                date_fin,
                distance_m,
                duree_secondes,
                commentaire,
                source
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
            """,
            activites,
        )

        prochain_id_log = connexion.execute(
            "SELECT COALESCE(MAX(id_log), 0) + 1 FROM bronze.audit_log;"
        ).fetchone()[0]

        connexion.execute(
            """
            INSERT INTO bronze.audit_log (
                id_log,
                nom_pipeline,
                statut,
                message
            )
            VALUES (?, ?, ?, ?);
            """,
            [
                prochain_id_log,
                "generation_activites_sportives",
                "SUCCES",
                f"{len(activites)} activités sportives générées",
            ],
        )

        print("Génération des activités sportives terminée.")
        print(f"Nombre d'activités générées : {len(activites)}")
        print(f"Nombre de pratiques sportives générées : {len(pratiques)}")
        print("Tables alimentées :")
        print("- bronze.raw_sports")
        print("- bronze.raw_pratiques_sportives")
        print("- bronze.raw_activites_sportives")

    finally:
        connexion.close()


def parser_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Génère des activités sportives simulées."
    )

    parser.add_argument(
        "--nb-activites",
        type=int,
        default=5000,
        help="Nombre d'activités sportives à générer.",
    )

    return parser.parse_args()


if __name__ == "__main__":
    arguments = parser_arguments()
    generer_activites(arguments.nb_activites)