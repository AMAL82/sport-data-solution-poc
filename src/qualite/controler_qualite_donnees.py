"""
Contrôles qualité des données du POC Avantages Sportifs.

Rôle :
- vérifier la qualité des salariés ;
- vérifier la qualité des activités sportives ;
- détecter les incohérences principales ;
- alimenter la table silver.quarantaine_activites ;
- écrire une synthèse dans bronze.audit_log.

Exemple :
    python src/qualite/controler_qualite_donnees.py
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
            f"Base DuckDB introuvable : {CHEMIN_BASE}\n"
            "Lance d'abord : python src/utils/initialiser_entrepot.py"
        )


def executer_controle(
    connexion: duckdb.DuckDBPyConnection,
    nom_controle: str,
    requete: str,
) -> int:
    """
    Exécute une requête de contrôle et retourne le nombre d'anomalies.
    """
    resultat = connexion.execute(requete).fetchone()[0]
    print(f"{nom_controle} : {resultat} anomalie(s)")
    return resultat


def vider_quarantaine(connexion: duckdb.DuckDBPyConnection) -> None:
    """
    Vide la quarantaine avant un nouveau contrôle.
    """
    connexion.execute("DELETE FROM silver.quarantaine_activites;")


def alimenter_quarantaine_activites(connexion: duckdb.DuckDBPyConnection) -> None:
    """
    Ajoute en quarantaine les activités invalides.
    """
    connexion.execute(
        """
        INSERT INTO silver.quarantaine_activites (
            id_activite,
            id_salarie,
            raison_rejet
        )
        SELECT
            a.id_activite,
            a.id_salarie,
            'salarié inexistant'
        FROM bronze.raw_activites_sportives a
        LEFT JOIN bronze.raw_salaries s
            ON a.id_salarie = s.id_salarie
        WHERE s.id_salarie IS NULL;
        """
    )

    connexion.execute(
        """
        INSERT INTO silver.quarantaine_activites (
            id_activite,
            id_salarie,
            raison_rejet
        )
        SELECT
            id_activite,
            id_salarie,
            'date_fin avant date_debut'
        FROM bronze.raw_activites_sportives
        WHERE date_fin < date_debut;
        """
    )

    connexion.execute(
        """
        INSERT INTO silver.quarantaine_activites (
            id_activite,
            id_salarie,
            raison_rejet
        )
        SELECT
            a.id_activite,
            a.id_salarie,
            'sport inconnu'
        FROM bronze.raw_activites_sportives a
        LEFT JOIN bronze.raw_sports sp
            ON a.id_sport = sp.id_sport
        WHERE sp.id_sport IS NULL;
        """
    )

    connexion.execute(
        """
        INSERT INTO silver.quarantaine_activites (
            id_activite,
            id_salarie,
            raison_rejet
        )
        SELECT
            a.id_activite,
            a.id_salarie,
            'distance négative'
        FROM bronze.raw_activites_sportives a
        WHERE a.distance_m < 0;
        """
    )

    connexion.execute(
        """
        INSERT INTO silver.quarantaine_activites (
            id_activite,
            id_salarie,
            raison_rejet
        )
        SELECT
            a.id_activite,
            a.id_salarie,
            'distance manquante pour sport avec distance'
        FROM bronze.raw_activites_sportives a
        INNER JOIN bronze.raw_sports sp
            ON a.id_sport = sp.id_sport
        WHERE sp.libelle IN ('Course à pied', 'Vélo', 'Randonnée', 'Marche', 'Natation')
          AND a.distance_m IS NULL;
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
            "controle_qualite_donnees",
            statut,
            message,
            datetime.now(),
        ],
    )


def controler_qualite_donnees() -> None:
    """
    Lance les contrôles qualité.
    """
    verifier_base()

    connexion = duckdb.connect(str(CHEMIN_BASE))

    try:
        print("Début des contrôles qualité...\n")

        controles = {
            "Salaires négatifs ou nuls": """
                SELECT COUNT(*)
                FROM bronze.raw_salaries
                WHERE salaire_brut_annuel IS NULL
                   OR salaire_brut_annuel <= 0;
            """,
            "Salariés dupliqués": """
                SELECT COUNT(*)
                FROM (
                    SELECT id_salarie
                    FROM bronze.raw_salaries
                    GROUP BY id_salarie
                    HAVING COUNT(*) > 1
                );
            """,
            "Activités avec salarié inexistant": """
                SELECT COUNT(*)
                FROM bronze.raw_activites_sportives a
                LEFT JOIN bronze.raw_salaries s
                    ON a.id_salarie = s.id_salarie
                WHERE s.id_salarie IS NULL;
            """,
            "Distances négatives": """
                SELECT COUNT(*)
                FROM bronze.raw_activites_sportives
                WHERE distance_m < 0;
            """,
            "Dates incohérentes": """
                SELECT COUNT(*)
                FROM bronze.raw_activites_sportives
                WHERE date_fin < date_debut;
            """,
            "Sports inconnus": """
                SELECT COUNT(*)
                FROM bronze.raw_activites_sportives a
                LEFT JOIN bronze.raw_sports sp
                    ON a.id_sport = sp.id_sport
                WHERE sp.id_sport IS NULL;
            """,
            "Distances manquantes pour sports avec distance": """
                SELECT COUNT(*)
                FROM bronze.raw_activites_sportives a
                INNER JOIN bronze.raw_sports sp
                    ON a.id_sport = sp.id_sport
                WHERE sp.libelle IN ('Course à pied', 'Vélo', 'Randonnée', 'Marche', 'Natation')
                  AND a.distance_m IS NULL;
            """,
        }

        total_anomalies = 0

        for nom_controle, requete in controles.items():
            total_anomalies += executer_controle(
                connexion=connexion,
                nom_controle=nom_controle,
                requete=requete,
            )

        vider_quarantaine(connexion)
        alimenter_quarantaine_activites(connexion)

        nb_quarantaine = connexion.execute(
            "SELECT COUNT(*) FROM silver.quarantaine_activites;"
        ).fetchone()[0]

        statut = "SUCCES" if total_anomalies == 0 else "AVEC_ANOMALIES"

        message = (
            f"Contrôles qualité terminés : "
            f"{total_anomalies} anomalie(s), "
            f"{nb_quarantaine} activité(s) en quarantaine"
        )

        ajouter_log_audit(connexion, statut, message)

        print("\nSynthèse qualité")
        print("----------------")
        print(f"Total anomalies : {total_anomalies}")
        print(f"Activités en quarantaine : {nb_quarantaine}")
        print(f"Statut : {statut}")

    finally:
        connexion.close()


if __name__ == "__main__":
    controler_qualite_donnees()