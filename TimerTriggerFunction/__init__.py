import datetime
import logging
import azure.functions as func
from azure.communication.email import EmailClient
import lbc
import json
import os
from azure.storage.blob import BlobServiceClient
import time
import random


BLOB_CONNECTION_STRING = os.environ["BLOB_CONNECTION_STRING"]
CONTAINER_NAME = "seen-ads"
BLOB_NAME = "seen_ads.json"
client = lbc.Client()

blob_service_client = BlobServiceClient.from_connection_string(BLOB_CONNECTION_STRING)
container_client = blob_service_client.get_container_client(CONTAINER_NAME)

def load_seen_ids():
    try:
        blob_client = container_client.get_blob_client(BLOB_NAME)
        data = blob_client.download_blob().readall()
        return set(json.loads(data))
    except Exception:
        return set()

def save_seen_ids(ids):
    blob_client = container_client.get_blob_client(BLOB_NAME)
    blob_client.upload_blob(json.dumps(list(ids)), overwrite=True)

def send_new_ad_email(ad, recipient_email, connection_string, sender_address):
    email_client = EmailClient.from_connection_string(connection_string)
    subject = f"Nouvelle annonce : {ad.subject}"
    if ad.images:
        pictures = "".join([f'<img src="{url}" style="max-width:300px; margin:5px;">' for url in ad.images])
    else:
        pictures = "No pictures"
    body_html = f"""
    <h2>{ad.subject}</h2>
    <p>{ad.body}</p>
    <p><strong>Prix :</strong> {ad.price} €</p>
    <p><a href="{ad.url}">Voir l'annonce</a></p>
    <p>
    {pictures}
    </p>
    """

    message = {
        "senderAddress": sender_address,
        "recipients": {
            "to": [{"address": recipient_email}]
        },
        "content": {
            "subject": subject,
            "html": body_html
        }
    }

    try:
        poller = email_client.begin_send(message)
        response = poller.result()
        logging.info(f"Email envoyé, statut : {response['status']}")
    except Exception as ex:
        logging.error(f"Erreur lors de l'envoi : {ex}")




def main(mytimer: func.TimerRequest) -> None:
    # Add a small random delay (0-15 seconds)
    delay = random.randint(0, 10)
    time.sleep(delay)
    if mytimer.past_due:
        logging.info('The timer is past due!')

    # Initialise les clients à l'intérieur de la fonction
    connection_string = os.environ.get("ACS_CONNECTION_STRING")  # À définir dans les paramètres d'application Azure
    sender_address = os.environ.get("ACS_SENDER_ADDRESS")        # À définir dans les paramètres d'application Azure


    if not connection_string or not sender_address:
        logging.error("Les variables d'environnement pour la connexion email ne sont pas définies.")
        return

    # Recherche d'annonces
    location = lbc.City(
        lat=48.85994982004764,
        lng=2.33801967847424,
        radius=0,
        city="Paris"
    )
    try:
        result = client.search(
            locations=[location],
            page=1,
            limit=5,
            limit_alu=0,
            sort=lbc.Sort.NEWEST,
            ad_type=lbc.AdType.OFFER,
            category=lbc.Category.IMMOBILIER_LOCATIONS,
            owner_type=lbc.OwnerType.ALL,
            search_in_title_only=True,
            square=(20, 400),
            price=[900, 1250],
            furnished=['1']
        )
    except Exception as e:
        error_message = f"Erreur lors de l'appel à client.search: {e}"
        logging.error(error_message)
        send_new_ad_email(
            ad=type('ad', (), {'subject': 'Erreur client.search', 'body': error_message, 'price': '', 'url': '', 'images': []})(),
            recipient_email="cuttittalucio@icloud.com",
            connection_string=connection_string,
            sender_address=sender_address
        )
        return

    seen_ids = load_seen_ids()
    new_ids = set()
    for ad in result.ads:
        new_ids.add(ad.id)
        if ad.id not in seen_ids:
            send_new_ad_email(ad, "cuttittalucio@icloud.com", connection_string, sender_address)
            logging.info(f"{ad.id} | {ad.url} | {ad.subject} | {ad.price}€ | Date: {ad.index_date}")
    save_seen_ids(seen_ids.union(new_ids))

    logging.info('Python timer trigger function executed.')
