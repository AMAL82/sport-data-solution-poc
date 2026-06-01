"""
Application des règles métier du POC Avantages Sportifs.

Rôle :
- calculer l'éligibilité à la prime sportive ;
- calculer l'éligibilité aux 5 jours bien-être ;
- détecter les anomalies métier ;
- alimenter les tables gold.avantages, gold.avantages_calcules et gold.anomalies.

Exemple :
    python src/metier/appliquer_regles_metier.py
"""

from pathlib import Path
from datetime import datetime
import duckdb


RACINE_PROJET = Path(__file__).resolve().parents[2]
CHEMIN_BASE = RACINE_PROJET / "data" / "warehouse.duckdb"

TAUX_PRIME = 0.05
SEUIL_ACTIVITES_WELLNESS = 15
NB_JOURS_WELLNESS = 5
NB_JOURS_TRAVAILLES_AN = 220


def verifier_base() -> None:
    if not CHEMIN_BASE.exists():
        raise FileNotFoundError(
            f"Base DuckDB introuvable : {CHEMIN_BASE}"
        )


def initialiser_parametres(connexion: duckdb.DuckDBPyConnection) -> None:
    """
    Insère les paramètres métier par défaut si absents.
    """
    nb_parametres = connexion.execute(
        "SELECT COUNT(*) FROM silver.parametres_regles;"
    ).fetchone()[0]

    if nb_parametres == 0:
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
            VALUES (
                1,
                'v1_prime_5pct',
                0.05,
                15,
                15,
                25,
                CURRENT_DATE,
                NULL,
                'systeme'
            );
            """
        )


def initialiser_avantages(connexion: duckdb.DuckDBPyConnection) -> None:
    """
    Insère les avantages métier si absents.
    """
    connexion.execute("DELETE FROM gold.avantages;")

    connexion.execute(
        """
        INSERT INTO gold.avantages (
            id_avantage,
            libelle,
            description
        )
        VALUES
            (
                1,
                'Prime sportive',
                'Prime de 5% du salaire brut annuel pour les salariés utilisant un mode de transport actif éligible'
            ),
            (
                2,
                'Jours bien-être',
                '5 jours bien-être pour les salariés ayant au moins 15 activités sportives sur 12 mois'
            );
        """
    )


def preparer_tables_gold(connexion: duckdb.DuckDBPyConnection) -> None:
    """
    Vide les résultats précédents.
    """
    connexion.execute("DELETE FROM gold.avantages_calcules;")
    connexion.execute("DELETE FROM gold.anomalies;")


def appliquer_prime_sportive(connexion: duckdb.DuckDBPyConnection) -> None:
    """
    Calcule l'éligibilité à la prime sportive.
    """
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
            ROW_NUMBER() OVER () AS id_avantage_calcule,
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
        CROSS JOIN (
            SELECT *
            FROM silver.parametres_regles
            ORDER BY id_parametre DESC
            LIMIT 1
        ) p;
        """
    )


def appliquer_jours_bien_etre(connexion: duckdb.DuckDBPyConnection) -> None:
    """
    Calcule l'éligibilité aux jours bien-être.
    """
    max_id_avantage = connexion.execute(
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
        CROSS JOIN (
            SELECT *
            FROM silver.parametres_regles
            ORDER BY id_parametre DESC
            LIMIT 1
        ) p;
        """,
        [max_id_avantage],
    )


def detecter_anomalies_transport(connexion: duckdb.DuckDBPyConnection) -> None:
    """
    Détecte les anomalies liées au transport domicile-bureau.
    """
    connexion.execute(
        """
        INSERT INTO gold.anomalies (
            id_anomalie,
            id_salarie,
            id_activite,
            id_parametre,
            type_anomalie,
            description,
            niveau_gravite,
            statut,
            date_detection
        )
        SELECT
            ROW_NUMBER() OVER () AS id_anomalie,
            s.id_salarie,
            NULL AS id_activite,
            p.id_parametre,
            'transport' AS type_anomalie,
            'Mode actif déclaré mais distance domicile-bureau non éligible' AS description,
            'MOYEN' AS niveau_gravite,
            'OUVERTE' AS statut,
            CURRENT_TIMESTAMP AS date_detection
        FROM silver.salaries s
        CROSS JOIN (
            SELECT *
            FROM silver.parametres_regles
            ORDER BY id_parametre DESC
            LIMIT 1
        ) p
        WHERE s.mode_transport_normalise IN ('walking', 'cycling')
          AND s.transport_eligible = FALSE;
        """
    )


def detecter_anomalies_activite(connexion: duckdb.DuckDBPyConnection) -> None:
    """
    Détecte les salariés sans activité sportive.
    """
    max_id_anomalie = connexion.execute(
        "SELECT COALESCE(MAX(id_anomalie), 0) FROM gold.anomalies;"
    ).fetchone()[0]

    connexion.execute(
        """
        INSERT INTO gold.anomalies (
            id_anomalie,
            id_salarie,
            id_activite,
            id_parametre,
            type_anomalie,
            description,
            niveau_gravite,
            statut,
            date_detection
        )
        WITH nb_activites AS (
            SELECT
                id_salarie,
                COUNT(*) AS nb_activites
            FROM bronze.raw_activites_sportives
            GROUP BY id_salarie
        )
        SELECT
            ? + ROW_NUMBER() OVER () AS id_anomalie,
            s.id_salarie,
            NULL AS id_activite,
            p.id_parametre,
            'frequence' AS type_anomalie,
            'Salarié sans activité sportive sur la période' AS description,
            'FAIBLE' AS niveau_gravite,
            'OUVERTE' AS statut,
            CURRENT_TIMESTAMP AS date_detection
        FROM silver.salaries s
        LEFT JOIN nb_activites a
            ON s.id_salarie = a.id_salarie
        CROSS JOIN (
            SELECT *
            FROM silver.parametres_regles
            ORDER BY id_parametre DESC
            LIMIT 1
        ) p
        WHERE COALESCE(a.nb_activites, 0) = 0;
        """,
        [max_id_anomalie],
    )


def detecter_quasi_eligibles_wellness(connexion: duckdb.DuckDBPyConnection) -> None:
    """
    Détecte les salariés proches du seuil wellness.
    """
    max_id_anomalie = connexion.execute(
        "SELECT COALESCE(MAX(id_anomalie), 0) FROM gold.anomalies;"
    ).fetchone()[0]

    connexion.execute(
        """
        INSERT INTO gold.anomalies (
            id_anomalie,
            id_salarie,
            id_activite,
            id_parametre,
            type_anomalie,
            description,
            niveau_gravite,
            statut,
            date_detection
        )
        WITH nb_activites AS (
            SELECT
                id_salarie,
                COUNT(*) AS nb_activites
            FROM bronze.raw_activites_sportives
            WHERE date_debut >= CURRENT_DATE - INTERVAL '12 months'
            GROUP BY id_salarie
        )
        SELECT
            ? + ROW_NUMBER() OVER () AS id_anomalie,
            s.id_salarie,
            NULL AS id_activite,
            p.id_parametre,
            'wellness' AS type_anomalie,
            'Salarié proche du seuil de 15 activités bien-être' AS description,
            'INFO' AS niveau_gravite,
            'OUVERTE' AS statut,
            CURRENT_TIMESTAMP AS date_detection
        FROM silver.salaries s
        INNER JOIN nb_activites a
            ON s.id_salarie = a.id_salarie
        CROSS JOIN (
            SELECT *
            FROM silver.parametres_regles
            ORDER BY id_parametre DESC
            LIMIT 1
        ) p
        WHERE a.nb_activites BETWEEN 12 AND 14;
        """,
        [max_id_anomalie],
    )


def ajouter_log_audit(connexion, statut: str, message: str) -> None:
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
            "application_regles_metier",
            statut,
            message,
            datetime.now(),
        ],
    )


def appliquer_regles_metier() -> None:
    """
    Lance l'application complète des règles métier.
    """
    verifier_base()

    connexion = duckdb.connect(str(CHEMIN_BASE))

    try:
        print("Application des règles métier...")

        initialiser_parametres(connexion)
        initialiser_avantages(connexion)
        preparer_tables_gold(connexion)

        appliquer_prime_sportive(connexion)
        appliquer_jours_bien_etre(connexion)

        detecter_anomalies_transport(connexion)
        detecter_anomalies_activite(connexion)
        detecter_quasi_eligibles_wellness(connexion)

        nb_avantages = connexion.execute(
            "SELECT COUNT(*) FROM gold.avantages_calcules;"
        ).fetchone()[0]

        nb_anomalies = connexion.execute(
            "SELECT COUNT(*) FROM gold.anomalies;"
        ).fetchone()[0]

        cout_total = connexion.execute(
            "SELECT ROUND(SUM(cout_total), 2) FROM gold.avantages_calcules;"
        ).fetchone()[0]

        message = (
            f"{nb_avantages} avantages calculés, "
            f"{nb_anomalies} anomalies détectées, "
            f"coût total = {cout_total} €"
        )

        ajouter_log_audit(connexion, "SUCCES", message)

        print("Règles métier appliquées avec succès.")
        print(message)

    finally:
        connexion.close()


if __name__ == "__main__":
    appliquer_regles_metier()