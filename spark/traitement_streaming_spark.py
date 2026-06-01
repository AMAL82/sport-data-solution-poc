"""
Traitement streaming Spark des activités sportives.

Rôle :
- lire les événements JSON depuis Redpanda ;
- parser les messages ;
- transformer les données ;
- écrire les résultats en Parquet ;
- préparer les données pour le reporting PowerBI.

Exécution prévue via spark-submit avec le connecteur Kafka :
spark-submit ^
  --packages org.apache.spark:spark-sql-kafka-0-10_2.12:3.5.1 ^
  spark/traitement_streaming_spark.py
"""

import os
from pathlib import Path

from pyspark.sql import SparkSession
from pyspark.sql.functions import (
    col,
    from_json,
    lit,
    round as spark_round,
    to_timestamp,
    when,
)
from pyspark.sql.types import (
    StructType,
    StructField,
    IntegerType,
    StringType,
    DoubleType,
)


RACINE_PROJET = Path(__file__).resolve().parents[1]

REDPANDA_BOOTSTRAP_SERVERS = os.getenv(
    "REDPANDA_BOOTSTRAP_SERVERS",
    "localhost:19092",
)

REDPANDA_TOPIC_ACTIVITES = os.getenv(
    "REDPANDA_TOPIC_ACTIVITES",
    "activites_sportives",
)

DOSSIER_SORTIE_PARQUET = os.getenv(
    "DOSSIER_SORTIE_PARQUET",
    str(RACINE_PROJET / "data" / "silver" / "activites_streaming"),
)

DOSSIER_CHECKPOINT = os.getenv(
    "DOSSIER_CHECKPOINT",
    str(RACINE_PROJET / "data" / "cache" / "checkpoint_spark_activites"),
)


SCHEMA_ACTIVITE = StructType(
    [
        StructField("id_activite", IntegerType(), True),
        StructField("id_salarie", IntegerType(), True),
        StructField("prenom", StringType(), True),
        StructField("nom", StringType(), True),
        StructField("id_sport", IntegerType(), True),
        StructField("sport", StringType(), True),
        StructField("date_debut", StringType(), True),
        StructField("date_fin", StringType(), True),
        StructField("distance_m", DoubleType(), True),
        StructField("duree_secondes", IntegerType(), True),
        StructField("commentaire", StringType(), True),
        StructField("source", StringType(), True),
    ]
)


def creer_session_spark() -> SparkSession:
    """
    Crée la session Spark.
    """
    return (
        SparkSession.builder.appName("traitement-streaming-activites-sportives")
        .config("spark.sql.shuffle.partitions", "2")
        .getOrCreate()
    )


def lire_flux_redpanda(spark: SparkSession):
    """
    Lit le topic Redpanda en streaming.
    """
    return (
        spark.readStream.format("kafka")
        .option("kafka.bootstrap.servers", REDPANDA_BOOTSTRAP_SERVERS)
        .option("subscribe", REDPANDA_TOPIC_ACTIVITES)
        .option("startingOffsets", "latest")
        .load()
    )


def transformer_flux(df_kafka):
    """
    Parse le JSON et applique les transformations utiles.
    """
    df_json = df_kafka.select(
        col("key").cast("string").alias("cle_message"),
        col("value").cast("string").alias("message_json"),
        col("timestamp").alias("date_reception_redpanda"),
    )

    df_parse = df_json.select(
        col("cle_message"),
        from_json(col("message_json"), SCHEMA_ACTIVITE).alias("activite"),
        col("date_reception_redpanda"),
    )

    df_activites = df_parse.select(
        col("cle_message"),
        col("activite.id_activite").alias("id_activite"),
        col("activite.id_salarie").alias("id_salarie"),
        col("activite.prenom").alias("prenom"),
        col("activite.nom").alias("nom"),
        col("activite.id_sport").alias("id_sport"),
        col("activite.sport").alias("sport"),
        to_timestamp(col("activite.date_debut")).alias("date_debut"),
        to_timestamp(col("activite.date_fin")).alias("date_fin"),
        col("activite.distance_m").alias("distance_m"),
        col("activite.duree_secondes").alias("duree_secondes"),
        col("activite.commentaire").alias("commentaire"),
        col("activite.source").alias("source"),
        col("date_reception_redpanda"),
    )

    df_transforme = (
        df_activites.withColumn(
            "distance_km",
            spark_round(col("distance_m") / lit(1000), 2),
        )
        .withColumn(
            "duree_minutes",
            spark_round(col("duree_secondes") / lit(60), 2),
        )
        .withColumn(
            "activite_valide",
            when(col("id_activite").isNull(), lit(False))
            .when(col("id_salarie").isNull(), lit(False))
            .when(col("sport").isNull(), lit(False))
            .when(col("date_debut").isNull(), lit(False))
            .otherwise(lit(True)),
        )
    )

    return df_transforme


def ecrire_parquet(df_transforme):
    """
    Écrit le flux transformé en Parquet.
    """
    return (
        df_transforme.writeStream.format("parquet")
        .option("path", DOSSIER_SORTIE_PARQUET)
        .option("checkpointLocation", DOSSIER_CHECKPOINT)
        .outputMode("append")
        .start()
    )


def main() -> None:
    """
    Lance le traitement streaming.
    """
    spark = creer_session_spark()
    spark.sparkContext.setLogLevel("WARN")

    df_kafka = lire_flux_redpanda(spark)
    df_transforme = transformer_flux(df_kafka)

    requete = ecrire_parquet(df_transforme)

    print("Traitement Spark Streaming démarré.")
    print(f"Topic Redpanda : {REDPANDA_TOPIC_ACTIVITES}")
    print(f"Bootstrap servers : {REDPANDA_BOOTSTRAP_SERVERS}")
    print(f"Sortie Parquet : {DOSSIER_SORTIE_PARQUET}")
    print(f"Checkpoint : {DOSSIER_CHECKPOINT}")

    requete.awaitTermination()


if __name__ == "__main__":
    main()