import json
import os
import re
from datetime import datetime, timedelta
import cloudscraper
from bs4 import BeautifulSoup
import firebase_admin
from firebase_admin import credentials, firestore

# --- 1. CONFIGURATION ---
url = "https://gamewave.fr/monopoly-go/monopoly-go-liens-des-lancers-de-de-et-d-argent-gratuits/"
filename = "scrapmonopolygo.json"

now = datetime.now()
date_now_str = now.strftime("%d/%m/%Y @ %H:%M")
heure_actuelle_str = now.strftime("%H:%M")

# Normalisation à minuit pour le calcul des 5 jours (évite le bug d'expiration horaire)
aujourdhui_minuit = now.replace(hour=0, minute=0, second=0, microsecond=0)
limite_conservation = aujourdhui_minuit - timedelta(days=10) 

# --- 1B. INITIALISATION FIREBASE ---
firebase_key_raw = os.environ.get('FIREBASE_KEY')
if not firebase_key_raw:
    raise ValueError("Le secret FIREBASE_KEY est introuvable dans l'environnement.")

if not firebase_admin._apps:
    cred_json = json.loads(firebase_key_raw)
    cred = credentials.Certificate(cred_json)
    firebase_admin.initialize_app(cred)

db = firestore.client()

# --- 2. CHARGEMENT DE L'HISTORIQUE ---
anciens_liens = {}
if os.path.exists(filename):
    try:
        with open(filename, mode="r", encoding="utf-8") as json_file:
            data_chargee = json.load(json_file)
            if isinstance(data_chargee, list):
                for item in data_chargee:
                    if "lienurl" in item:
                        url_cle = item["lienurl"].strip()
                        try:
                            # Extraction de la date pure pour la vérification de la limite de 5 jours
                            date_objet = datetime.strptime(item.get("date", ""), "%d/%m/%Y")
                            if date_objet >= limite_conservation:
                                anciens_liens[url_cle] = item
                        except:
                            # En cas d'erreur de format, on conserve par sécurité
                            anciens_liens[url_cle] = item
    except Exception as e:
        print(f"[Attention] Impossible de lire l'historique JSON : {e}")

# --- 3. SCRAPING DU SITE ---
scraper = cloudscraper.create_scraper(browser={'browser': 'chrome', 'platform': 'windows', 'mobile': False})

try:
    response = scraper.get(url, timeout=15)
    status_code = response.status_code
    html_text = response.text
except Exception as e:
    status_code = 500
    html_text = ""
    print(f"[Erreur] Connexion impossible : {e}")

if status_code == 200:
    soup = BeautifulSoup(html_text, "html.parser")
    json_data = []
    liens_visites_session = set()
    nouveaux_liens_detectes = 0
    
    # Recherche du tableau des liens sur la page
    tableau = soup.find("table")
    
    if tableau:
        lignes = tableau.find_all("tr")[1:]
        
        # On parcourt du plus ancien au plus récent présent sur la page
        for ligne in reversed(lignes):
            cellules = ligne.find_all("td")
            if len(cellules) >= 3:
                
                # 1. Extraction et formatage de la date du lien affichée sur le site
                texte_date = cellules[0].get_text().strip().lower()
                
                if "aujourd" in texte_date:
                    current_date_str = now.strftime("%d/%m/%Y")
                else:
                    match_date = re.search(r'(\d{1,2})/(\d{1,2})/(\d{4})', texte_date)
                    if match_date:
                        jour = match_date.group(1).zfill(2)
                        mois = match_date.group(2).zfill(2)
                        annee = match_date.group(3)
                        current_date_str = f"{jour}/{mois}/{annee}"
                    else:
                        current_date_str = now.strftime("%d/%m/%Y")
                
                # 2. Extraction et normalisation de la récompense (Apostrophes standardisés)
                type_recompense = cellules[1].get_text().strip().replace("’", "'")
                if not type_recompense:
                    type_recompense = "Dés gratuits"
                
                # 3. Traitement du lien URL
                lien_tag = cellules[2].find("a", href=True)
                if lien_tag:
                    href = lien_tag["href"].strip()
                    
                    if href in liens_visites_session:
                        continue
                    liens_visites_session.add(href)
                    
                    # --- CONFIGURATION LOGIQUE DU DOUBLON ---
                    if href in anciens_liens:
                        # CONDITION RESPECTÉE : On récupère l'élément d'origine de l'historique JSON
                        ancien_item = anciens_liens[href]
                        
                        # On fige STRICTEMENT l'ancienne date de scraping initial
                        date_premier_scraping_str = ancien_item.get("date_scraping")
                        if not date_premier_scraping_str:
                            date_premier_scraping_str = date_now_str
                        
                        badge_actuel = ""
                        # Gestion dynamique du badge NEW (Disparaît automatiquement après 6 heures réelles)
                        try:
                            date_premier_scraping = datetime.strptime(date_premier_scraping_str, "%d/%m/%Y @ %H:%M")
                            if now - date_premier_scraping < timedelta(hours=6):
                                badge_actuel = "NEW"
                        except:
                            badge_actuel = ""

                        # Reconstruction en gardant TOUTES les anciennes valeurs figées
                        json_data.append({
                            "date_scraping": date_premier_scraping_str,                         # <--- FIGÉ (Pas de mise à jour)
                            "date_scraping1": ancien_item.get("date_scraping1", date_premier_scraping_str), # <--- FIGÉ (Pas de mise à jour)
                            "date": ancien_item.get("date", current_date_str),                  # <--- FIGÉ
                            "heure": ancien_item.get("heure", heure_actuelle_str),              # <--- FIGÉ
                            "recompense": type_recompense, 
                            "lienurl": href,
                            "badge": badge_actuel                                               # S'efface au bout de 6h
                        })
                    else:
                        # VRAI NOUVEAU LIEN détecté pour la première fois
                        nouveaux_liens_detectes += 1
                        date_scraping1_combinee = f"{current_date_str} @ {heure_actuelle_str}"
                        
                        json_data.append({
                            "date_scraping": date_now_str, 
                            "date_scraping1": date_scraping1_combinee,
                            "date": current_date_str,  
                            "heure": heure_actuelle_str,
                            "recompense": type_recompense, 
                            "lienurl": href,
                            "badge": "NEW" 
                        })

    # Sécurité si le tableau est vide lors du scraping
    if not json_data and anciens_liens:
        json_data = list(anciens_liens.values())

    # Tri décroissant du tableau final basé sur la date de parution
    def extraire_cle_parution(item):
        try:
            return datetime.strptime(item.get("date", ""), "%d/%m/%Y").timestamp()
        except:
            return 0

    json_data.sort(key=extraire_cle_parution, reverse=True)

    # Écriture propre du fichier JSON mis à jour
    with open(filename, mode="w", encoding="utf-8") as json_file:
        json.dump(json_data, json_file, indent=4, ensure_ascii=False)
        
    print(f"[Terminé] Fichier Monopoly Go {filename} mis à jour ({len(json_data)} liens indexés).")
    print(f"[Diagnostic] Nombre de nouveaux liens détectés : {nouveaux_liens_detectes}")

    # --- 4. ENVOI DES NOTIFICATIONS (Uniquement si de nouveaux liens réels existent) ---
    if nouveaux_liens_detectes > 0:
        try:
            from firebase_admin import messaging
            
            db.collection("notifications").add({
                "title": "🎩 Board Reward ! 🎁",
                "body": "New free dice have just been added !",
                "nom_du_jeu": "monopoly_go",
                "created_at": firestore.SERVER_TIMESTAMP
            })
            print("[Firebase] Enregistrement d'historique créé pour Monopoly Go.")

            message = messaging.Message(
                notification=messaging.Notification(
                    title="🎩 Board Reward ! 🎁",
                    body="New free dice have just been added !"
                ),
                topic="monopoly_go"
            )
            
            response = messaging.send(message)
            print(f"[Firebase Push] Notification propulsée en direct avec succès ! (ID: {response})")
            
        except Exception as e:
            print(f"[Firebase] [Erreur] Impossible d'écrire ou d'envoyer l'alerte push direct : {e}")
            
else:
    print(f"[Erreur] Échec de la communication réseau avec Gamewave (Code {status_code}).")
