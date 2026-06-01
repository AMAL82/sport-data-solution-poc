CREATE SCHEMA IF NOT EXISTS gold;

CREATE TABLE IF NOT EXISTS gold.avantages (
    id_avantage INTEGER PRIMARY KEY,
    libelle VARCHAR,
    description VARCHAR
);

CREATE TABLE IF NOT EXISTS gold.avantages_calcules (
    id_avantage_calcule INTEGER,
    id_salarie INTEGER,
    id_avantage INTEGER,
    id_parametre INTEGER,
    date_calcul TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    eligible BOOLEAN,
    montant_prime DOUBLE,
    nb_jours_wellness INTEGER,
    cout_wellness DOUBLE,
    cout_total DOUBLE
);

CREATE TABLE IF NOT EXISTS gold.anomalies (
    id_anomalie INTEGER,
    id_salarie INTEGER,
    id_activite INTEGER,
    id_parametre INTEGER,
    type_anomalie VARCHAR,
    description VARCHAR,
    niveau_gravite VARCHAR,
    statut VARCHAR,
    date_detection TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS gold.messages_slack (
    id_message INTEGER,
    id_activite INTEGER,
    date_envoi TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    contenu_message VARCHAR,
    statut_envoi VARCHAR
);

CREATE TABLE IF NOT EXISTS gold.kpi_financiers (
    version_parametre VARCHAR,
    cout_total_primes DOUBLE,
    cout_total_wellness DOUBLE,
    cout_global DOUBLE,
    nb_salaries_eligibles_prime INTEGER,
    nb_salaries_eligibles_wellness INTEGER,
    date_calcul TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS gold.kpi_pratiques_sportives (
    type_sport VARCHAR,
    nb_activites INTEGER,
    distance_totale_km DOUBLE,
    duree_totale_heures DOUBLE,
    nb_salaries_actifs INTEGER,
    date_calcul TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS gold.kpi_anomalies (
    type_anomalie VARCHAR,
    niveau_gravite VARCHAR,
    nb_anomalies INTEGER,
    date_calcul TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);