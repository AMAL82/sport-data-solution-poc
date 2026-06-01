"""
Géocodage des adresses domicile-bureau.

Rôle :
- lire les salariés depuis bronze.raw_salaries ;
- calculer la distance domicile -> entreprise via Google Maps Distance Matrix ;
- utiliser un cache local pour éviter les appels répétés ;
- limiter les appels aux salariés avec un mode actif ;
- alimenter silver.salaries avec distance et transport_eligible.

Exemple :
    python src/metier/geocoder_adresses.py
"""

from pathlib import Path
from datetime import datetime
import json
import os
import unicodedata
import random

import duckdb
import requests
from dotenv import load_dotenv


RACINE_PROJET = Path(__file__).resolve().parents[2]
CHEMIN_BASE = RACINE_PROJET / "data" / "warehouse.duckdb"
CHEMIN_CACHE = RACINE_PROJET / "data" / "cache" / "geocoding_cache.json"

MODES_ACTIFS = {
    "marche": "walking",
    "running": "walking",
    "course": "walking",
    "course a pied": "walking",
    "vélo": "cycling",
    "velo": "cycling",
    "trottinette": "cycling",
    "autres": "cycling",
}

MAX_KM_MARCHE = 15
MAX_KM_VELO = 25


def normaliser_texte(valeur: str) -> str:
    if valeur is None:
        return ""

    texte = str(valeur).strip().lower()
    texte = unicodedata.normalize("NFD", texte)
    texte = "".join(c for c in texte if unicodedata.category(c) != "Mn")
    return texte


def normaliser_mode_transport(mode: str) -> str:
    texte = normaliser_texte(mode)

    for mot_cle, mode_normalise in MODES_ACTIFS.items():
        if normaliser_texte(mot_cle) in texte:
            return mode_normalise

    if "transport" in texte or "commun" in texte:
        return "transit"

    if "voiture" in texte or "vehicule" in texte or "moto" in texte:
        return "motor"

    return "unknown"


def charger_configuration() -> tuple[str | None, str]:
    load_dotenv(RACINE_PROJET / ".env")

    api_key = os.getenv("GOOGLE_MAPS_API_KEY")
    adresse_entreprise = os.getenv(
        "ADRESSE_ENTREPRISE",
        "1362 Av. des Platanes, 34970 Lattes",
    )

    if not api_key:
        print("Aucune clé Google Maps détectée : mode simulation activé.")

    return api_key, adresse_entreprise



def charger_cache() -> dict:
    if CHEMIN_CACHE.exists():
        return json.loads(CHEMIN_CACHE.read_text(encoding="utf-8"))

    return {}


def sauvegarder_cache(cache: dict) -> None:
    CHEMIN_CACHE.parent.mkdir(parents=True, exist_ok=True)
    CHEMIN_CACHE.write_text(
        json.dumps(cache, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def calculer_distance_google_maps(
    adresse_domicile: str,
    adresse_entreprise: str,
    mode_google: str,
    api_key: str,
) -> float | None:
    """
    Simulation de distance domicile-bureau pour le POC.

    Aucun appel réel à Google Maps.
    """

    if mode_google == "walking":
        return round(random.uniform(0.5, 12), 2)

    if mode_google == "cycling":
        return round(random.uniform(2, 25), 2)

    return round(random.uniform(5, 40), 2)


def determiner_eligibilite(mode_normalise: str, distance_km: float | None) -> bool:
    if distance_km is None:
        return False

    if mode_normalise == "walking":
        return distance_km <= MAX_KM_MARCHE

    if mode_normalise == "cycling":
        return distance_km <= MAX_KM_VELO

    return False


def vider_silver_salaries(connexion: duckdb.DuckDBPyConnection) -> None:
    connexion.execute("DELETE FROM silver.salaries;")


def inserer_salarie_silver(
    connexion: duckdb.DuckDBPyConnection,
    salarie: dict,
    mode_normalise: str,
    distance_km: float | None,
    transport_eligible: bool,
) -> None:
    connexion.execute(
        """
        INSERT INTO silver.salaries (
            id_salarie,
            nom,
            prenom,
            date_naissance,
            date_embauche,
            business_unit,
            type_contrat,
            salaire_brut_annuel,
            adresse_domicile,
            mode_transport_declare,
            mode_transport_normalise,
            distance_domicile_km,
            transport_eligible
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
        """,
        [
            salarie["id_salarie"],
            salarie["nom"],
            salarie["prenom"],
            salarie["date_naissance"],
            salarie["date_embauche"],
            salarie["business_unit"],
            salarie["type_contrat"],
            salarie["salaire_brut_annuel"],
            salarie["adresse_domicile"],
            salarie["mode_transport_declare"],
            mode_normalise,
            distance_km,
            transport_eligible,
        ],
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
            "geocodage_adresses",
            statut,
            message,
            datetime.now(),
        ],
    )


def geocoder_adresses() -> None:
    if not CHEMIN_BASE.exists():
        raise FileNotFoundError(
            f"Base DuckDB introuvable : {CHEMIN_BASE}"
        )

    api_key, adresse_entreprise = charger_configuration()
    cache = charger_cache()

    connexion = duckdb.connect(str(CHEMIN_BASE))

    try:
        salaries = connexion.execute(
            """
            SELECT
                id_salarie,
                nom,
                prenom,
                date_naissance,
                date_embauche,
                business_unit,
                type_contrat,
                salaire_brut_annuel,
                adresse_domicile,
                mode_transport_declare
            FROM bronze.raw_salaries;
            """
        ).fetchdf()

        vider_silver_salaries(connexion)

        nb_appels_api = 0
        nb_cache = 0
        nb_actifs = 0
        nb_eligibles = 0

        for _, ligne in salaries.iterrows():
            salarie = ligne.to_dict()

            mode_normalise = normaliser_mode_transport(
                salarie.get("mode_transport_declare")
            )

            distance_km = None

            if mode_normalise in {"walking", "cycling"}:
                nb_actifs += 1

                adresse = str(salarie.get("adresse_domicile") or "").strip()
                cle_cache = f"{adresse}|{adresse_entreprise}|{mode_normalise}"

                if cle_cache in cache:
                    distance_km = cache[cle_cache]
                    nb_cache += 1
                else:
                    distance_km = calculer_distance_google_maps(
                        adresse_domicile=adresse,
                        adresse_entreprise=adresse_entreprise,
                        mode_google=mode_normalise,
                        api_key=api_key,
                    )
                    cache[cle_cache] = distance_km
                    nb_appels_api += 1

            transport_eligible = determiner_eligibilite(
                mode_normalise=mode_normalise,
                distance_km=distance_km,
            )

            if transport_eligible:
                nb_eligibles += 1

            inserer_salarie_silver(
                connexion=connexion,
                salarie=salarie,
                mode_normalise=mode_normalise,
                distance_km=distance_km,
                transport_eligible=transport_eligible,
            )

        sauvegarder_cache(cache)

        message = (
            f"{len(salaries)} salariés traités, "
            f"{nb_actifs} modes actifs, "
            f"{nb_eligibles} transports éligibles, "
            f"{nb_appels_api} appels API, "
            f"{nb_cache} distances depuis cache"
        )

        ajouter_log_audit(connexion, "SUCCES", message)

        print("Géocodage terminé.")
        print(message)

    finally:
        connexion.close()


if __name__ == "__main__":
    geocoder_adresses()