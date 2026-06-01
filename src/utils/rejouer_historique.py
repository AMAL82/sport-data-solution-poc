"""
Rejeu historique des KPI avec une nouvelle version de paramètres.

Rôle :
- ajouter une nouvelle version de paramètres métier ;
- recalculer les avantages ;
- recalculer les KPI ;
- permettre la comparaison dans PowerBI.

Exemples :
    python src/utils/rejouer_historique.py --taux-prime 0.02
    python src/utils/rejouer_historique.py --taux-prime 0.07 --seuil-wellness 20
"""

from pathlib import Path
from datetime import datetime
import argparse
import duckdb


RACINE_PROJET = Path(__file__).resolve().parents[2]
CHEMIN_BASE = RACINE_PROJET / "data" / "warehouse.duckdb"


def verifier_base() -> None:
    if not CHEMIN_BASE.exists():
        raise FileNotFoundError(f"Base DuckDB introuvable : {CHEMIN_BASE}")


def ajouter_nouvelle_version_parametres(
    connexion: duckdb.DuckDBPyConnection,
    taux_prime: float,
    seuil_wellness: int,
    max_km_marche: float,
    max_km_velo: float,
) -> int:
    nouvel_id = connexion.execute(
        "SELECT COALESCE(MAX(id_parametre), 0) + 1 FROM silver.parametres_regles;"
    ).fetchone()[0]

    version = f"v{nouvel_id}_prime_{int(taux_prime * 100)}pct"

    connexion.execute(
        """
        INSERT INTO silver.parametres_regles (
            id_parametre,
            version_parametre,
            taux_prime,
            seuil_activites_wellness,
            max_km_marche,
            max_km_velo,
            date_debut_validite,
            date_fin_validite,
            cree_par
        )
        VALUES (?, ?, ?, ?, ?, ?, CURRENT_DATE, NULL, 'rejeu_historique');
        """,
        [
            nouvel_id,
            version,
            taux_prime,
            seuil_wellness,
            max_km_marche,
            max_km_velo,
        ],
    )

    return nouvel_id


def recalculer_avantages_pour_version(
    connexion: duckdb.DuckDBPyConnection,
    id_parametre: int,
) -> None:
    """
    Ajoute les avantages recalculés pour la nouvelle version sans supprimer l'historique.
    """
    max_id = connexion.execute(
        "SELECT COALESCE(MAX(id_avantage_calcule), 0) FROM gold.avantages_calcules;"
    ).fetchone()[0]

    connexion.execute(
        """
        INSERT INTO gold.avantages_calcules (
            id_avantage_calcule,
            id_salarie,
            id_avantage,
            id_parametre,
            date_calcul,
            eligible,
            montant_prime,
            nb_jours_wellness,
            cout_wellness,
            cout_total
        )
        SELECT
            ? + ROW_NUMBER() OVER () AS id_avantage_calcule,
            s.id_salarie,
            1 AS id_avantage,
            p.id_parametre,
            CURRENT_TIMESTAMP AS date_calcul,
            s.transport_eligible AS eligible,
            CASE
                WHEN s.transport_eligible = TRUE
                THEN ROUND(s.salaire_brut_annuel * p.taux_prime, 2)
                ELSE 0
            END AS montant_prime,
            0 AS nb_jours_wellness,
            0 AS cout_wellness,
            CASE
                WHEN s.transport_eligible = TRUE
                THEN ROUND(s.salaire_brut_annuel * p.taux_prime, 2)
                ELSE 0
            END AS cout_total
        FROM silver.salaries s
        INNER JOIN silver.parametres_regles p
            ON p.id_parametre = ?;
        """,
        [max_id, id_parametre],
    )

    max_id = connexion.execute(
        "SELECT COALESCE(MAX(id_avantage_calcule), 0) FROM gold.avantages_calcules;"
    ).fetchone()[0]

    connexion.execute(
        """
        INSERT INTO gold.avantages_calcules (
            id_avantage_calcule,
            id_salarie,
            id_avantage,
            id_parametre,
            date_calcul,
            eligible,
            montant_prime,
            nb_jours_wellness,
            cout_wellness,
            cout_total
        )
        WITH nb_activites AS (
            SELECT
                id_salarie,
                COUNT(*) AS nb_activites_12_mois
            FROM bronze.raw_activites_sportives
            WHERE date_debut >= CURRENT_DATE - INTERVAL '12 months'
            GROUP BY id_salarie
        )
        SELECT
            ? + ROW_NUMBER() OVER () AS id_avantage_calcule,
            s.id_salarie,
            2 AS id_avantage,
            p.id_parametre,
            CURRENT_TIMESTAMP AS date_calcul,
            COALESCE(a.nb_activites_12_mois, 0) >= p.seuil_activites_wellness AS eligible,
            0 AS montant_prime,
            CASE
                WHEN COALESCE(a.nb_activites_12_mois, 0) >= p.seuil_activites_wellness
                THEN 5
                ELSE 0
            END AS nb_jours_wellness,
            CASE
                WHEN COALESCE(a.nb_activites_12_mois, 0) >= p.seuil_activites_wellness
                THEN ROUND((s.salaire_brut_annuel / 220) * 5, 2)
                ELSE 0
            END AS cout_wellness,
            CASE
                WHEN COALESCE(a.nb_activites_12_mois, 0) >= p.seuil_activites_wellness
                THEN ROUND((s.salaire_brut_annuel / 220) * 5, 2)
                ELSE 0
            END AS cout_total
        FROM silver.salaries s
        LEFT JOIN nb_activites a
            ON s.id_salarie = a.id_salarie
        INNER JOIN silver.parametres_regles p
            ON p.id_parametre = ?;
        """,
        [max_id, id_parametre],
    )


def recalculer_kpi_financier_pour_version(
    connexion: duckdb.DuckDBPyConnection,
    id_parametre: int,
) -> None:
    connexion.execute(
        """
        INSERT INTO gold.kpi_financiers (
            version_parametre,
            cout_total_primes,
            cout_total_wellness,
            cout_global,
            nb_salaries_eligibles_prime,
            nb_salaries_eligibles_wellness,
            date_calcul
        )
        SELECT
            p.version_parametre,

            ROUND(SUM(
                CASE
                    WHEN ac.id_avantage = 1 THEN ac.montant_prime
                    ELSE 0
                END
            ), 2) AS cout_total_primes,

            ROUND(SUM(
                CASE
                    WHEN ac.id_avantage = 2 THEN ac.cout_wellness
                    ELSE 0
                END
            ), 2) AS cout_total_wellness,

            ROUND(SUM(ac.cout_total), 2) AS cout_global,

            COUNT(DISTINCT CASE
                WHEN ac.id_avantage = 1 AND ac.eligible = TRUE
                THEN ac.id_salarie
            END) AS nb_salaries_eligibles_prime,

            COUNT(DISTINCT CASE
                WHEN ac.id_avantage = 2 AND ac.eligible = TRUE
                THEN ac.id_salarie
            END) AS nb_salaries_eligibles_wellness,

            CURRENT_TIMESTAMP AS date_calcul

        FROM gold.avantages_calcules ac
        INNER JOIN silver.parametres_regles p
            ON ac.id_parametre = p.id_parametre
        WHERE ac.id_parametre = ?
        GROUP BY p.version_parametre;
        """,
        [id_parametre],
    )


def ajouter_log_audit(
    connexion: duckdb.DuckDBPyConnection,
    message: str,
) -> None:
    prochain_id = connexion.execute(
        "SELECT COALESCE(MAX(id_log), 0) + 1 FROM bronze.audit_log;"
    ).fetchone()[0]

    connexion.execute(
        """
        INSERT INTO bronze.audit_log (
            id_log,
            nom_pipeline,
            statut,
            message,
            date_execution
        )
        VALUES (?, ?, ?, ?, ?);
        """,
        [
            prochain_id,
            "rejeu_historique",
            "SUCCES",
            message,
            datetime.now(),
        ],
    )


def afficher_comparaison(connexion: duckdb.DuckDBPyConnection) -> None:
    resultats = connexion.execute(
        """
        SELECT
            version_parametre,
            cout_total_primes,
            cout_total_wellness,
            cout_global,
            nb_salaries_eligibles_prime,
            nb_salaries_eligibles_wellness
        FROM gold.kpi_financiers
        ORDER BY date_calcul;
        """
    ).fetchall()

    print("\nComparaison des versions")
    print("------------------------")

    for ligne in resultats:
        print(
            f"{ligne[0]} | "
            f"Primes: {ligne[1]} € | "
            f"Wellness: {ligne[2]} € | "
            f"Global: {ligne[3]} € | "
            f"Eligibles prime: {ligne[4]} | "
            f"Eligibles wellness: {ligne[5]}"
        )


def rejouer_historique(
    taux_prime: float,
    seuil_wellness: int,
    max_km_marche: float,
    max_km_velo: float,
) -> None:
    verifier_base()

    connexion = duckdb.connect(str(CHEMIN_BASE))

    try:
        id_parametre = ajouter_nouvelle_version_parametres(
            connexion=connexion,
            taux_prime=taux_prime,
            seuil_wellness=seuil_wellness,
            max_km_marche=max_km_marche,
            max_km_velo=max_km_velo,
        )

        recalculer_avantages_pour_version(connexion, id_parametre)
        recalculer_kpi_financier_pour_version(connexion, id_parametre)

        message = (
            f"Rejeu effectué avec id_parametre={id_parametre}, "
            f"taux_prime={taux_prime}, "
            f"seuil_wellness={seuil_wellness}"
        )

        ajouter_log_audit(connexion, message)

        print("Rejeu historique terminé avec succès.")
        print(message)

        afficher_comparaison(connexion)

    finally:
        connexion.close()


def parser_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Rejoue les KPI avec une nouvelle version de paramètres."
    )

    parser.add_argument(
        "--taux-prime",
        type=float,
        default=0.02,
        help="Nouveau taux de prime. Exemple : 0.02 pour 2%.",
    )

    parser.add_argument(
        "--seuil-wellness",
        type=int,
        default=15,
        help="Seuil minimum d'activités pour les jours bien-être.",
    )

    parser.add_argument(
        "--max-km-marche",
        type=float,
        default=15,
        help="Distance maximale en km pour la marche/running.",
    )

    parser.add_argument(
        "--max-km-velo",
        type=float,
        default=25,
        help="Distance maximale en km pour vélo/trottinette.",
    )

    return parser.parse_args()


if __name__ == "__main__":
    args = parser_arguments()

    rejouer_historique(
        taux_prime=args.taux_prime,
        seuil_wellness=args.seuil_wellness,
        max_km_marche=args.max_km_marche,
        max_km_velo=args.max_km_velo,
    )