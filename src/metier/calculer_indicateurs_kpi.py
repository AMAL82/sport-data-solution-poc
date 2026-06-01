"""
Calcul des indicateurs KPI du POC Avantages Sportifs.

Rôle :
- alimenter les tables Gold KPI ;
- produire les KPI financiers ;
- produire les KPI de pratique sportive ;
- produire les KPI d'anomalies.

Exemple :
    python src/metier/calculer_indicateurs_kpi.py
"""

from pathlib import Path
from datetime import datetime
import duckdb


RACINE_PROJET = Path(__file__).resolve().parents[2]
CHEMIN_BASE = RACINE_PROJET / "data" / "warehouse.duckdb"


def verifier_base() -> None:
    """
    Vérifie que la base DuckDB existe.
    """
    if not CHEMIN_BASE.exists():
        raise FileNotFoundError(
            f"Base DuckDB introuvable : {CHEMIN_BASE}"
        )


def vider_tables_kpi(connexion: duckdb.DuckDBPyConnection) -> None:
    """
    Vide les tables KPI avant recalcul.
    """
    connexion.execute("DELETE FROM gold.kpi_financiers;")
    connexion.execute("DELETE FROM gold.kpi_pratiques_sportives;")
    connexion.execute("DELETE FROM gold.kpi_anomalies;")


def calculer_kpi_financiers(connexion: duckdb.DuckDBPyConnection) -> None:
    """
    Calcule les KPI financiers globaux.
    """
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
            COALESCE(MAX(p.version_parametre), 'v1') AS version_parametre,

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
        LEFT JOIN silver.parametres_regles p
            ON ac.id_parametre = p.id_parametre;
        """
    )


def calculer_kpi_pratiques_sportives(connexion: duckdb.DuckDBPyConnection) -> None:
    """
    Calcule les KPI liés aux pratiques sportives.
    """
    connexion.execute(
        """
        INSERT INTO gold.kpi_pratiques_sportives (
            type_sport,
            nb_activites,
            distance_totale_km,
            duree_totale_heures,
            nb_salaries_actifs,
            date_calcul
        )
        SELECT
            sp.libelle AS type_sport,

            COUNT(a.id_activite) AS nb_activites,

            ROUND(
                SUM(COALESCE(a.distance_m, 0)) / 1000,
                2
            ) AS distance_totale_km,

            ROUND(
                SUM(COALESCE(a.duree_secondes, 0)) / 3600,
                2
            ) AS duree_totale_heures,

            COUNT(DISTINCT a.id_salarie) AS nb_salaries_actifs,

            CURRENT_TIMESTAMP AS date_calcul

        FROM bronze.raw_activites_sportives a
        LEFT JOIN bronze.raw_sports sp
            ON a.id_sport = sp.id_sport
        GROUP BY sp.libelle;
        """
    )


def calculer_kpi_anomalies(connexion: duckdb.DuckDBPyConnection) -> None:
    """
    Calcule les KPI d'anomalies.
    """
    connexion.execute(
        """
        INSERT INTO gold.kpi_anomalies (
            type_anomalie,
            niveau_gravite,
            nb_anomalies,
            date_calcul
        )
        SELECT
            type_anomalie,
            niveau_gravite,
            COUNT(*) AS nb_anomalies,
            CURRENT_TIMESTAMP AS date_calcul
        FROM gold.anomalies
        GROUP BY
            type_anomalie,
            niveau_gravite;
        """
    )


def ajouter_log_audit(
    connexion: duckdb.DuckDBPyConnection,
    statut: str,
    message: str,
) -> None:
    """
    Ajoute une ligne dans bronze.audit_log.
    """
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
            "calcul_indicateurs_kpi",
            statut,
            message,
            datetime.now(),
        ],
    )


def afficher_synthese(connexion: duckdb.DuckDBPyConnection) -> None:
    """
    Affiche une synthèse des KPI calculés.
    """
    kpi_financiers = connexion.execute(
        """
        SELECT
            cout_total_primes,
            cout_total_wellness,
            cout_global,
            nb_salaries_eligibles_prime,
            nb_salaries_eligibles_wellness
        FROM gold.kpi_financiers
        ORDER BY date_calcul DESC
        LIMIT 1;
        """
    ).fetchone()

    nb_lignes_pratiques = connexion.execute(
        "SELECT COUNT(*) FROM gold.kpi_pratiques_sportives;"
    ).fetchone()[0]

    nb_lignes_anomalies = connexion.execute(
        "SELECT COUNT(*) FROM gold.kpi_anomalies;"
    ).fetchone()[0]

    print("\nSynthèse KPI")
    print("------------")

    if kpi_financiers:
        print(f"Coût total primes : {kpi_financiers[0]} €")
        print(f"Coût total wellness : {kpi_financiers[1]} €")
        print(f"Coût global : {kpi_financiers[2]} €")
        print(f"Salariés éligibles prime : {kpi_financiers[3]}")
        print(f"Salariés éligibles wellness : {kpi_financiers[4]}")

    print(f"Lignes KPI pratiques sportives : {nb_lignes_pratiques}")
    print(f"Lignes KPI anomalies : {nb_lignes_anomalies}")


def calculer_indicateurs_kpi() -> None:
    """
    Exécute le calcul complet des KPI.
    """
    verifier_base()

    connexion = duckdb.connect(str(CHEMIN_BASE))

    try:
        print("Calcul des KPI...")

        vider_tables_kpi(connexion)

        calculer_kpi_financiers(connexion)
        calculer_kpi_pratiques_sportives(connexion)
        calculer_kpi_anomalies(connexion)

        nb_kpi_financiers = connexion.execute(
            "SELECT COUNT(*) FROM gold.kpi_financiers;"
        ).fetchone()[0]

        nb_kpi_pratiques = connexion.execute(
            "SELECT COUNT(*) FROM gold.kpi_pratiques_sportives;"
        ).fetchone()[0]

        nb_kpi_anomalies = connexion.execute(
            "SELECT COUNT(*) FROM gold.kpi_anomalies;"
        ).fetchone()[0]

        message = (
            f"KPI calculés : "
            f"{nb_kpi_financiers} financier(s), "
            f"{nb_kpi_pratiques} pratique(s), "
            f"{nb_kpi_anomalies} anomalie(s)"
        )

        ajouter_log_audit(connexion, "SUCCES", message)

        print("KPI calculés avec succès.")
        print(message)

        afficher_synthese(connexion)

    finally:
        connexion.close()


if __name__ == "__main__":
    calculer_indicateurs_kpi()