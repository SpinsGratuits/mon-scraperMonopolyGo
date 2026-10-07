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

# MODIFICATION : Passage du seuil limite de conservation à 15 jours glissants
limite_conservation = now - timedelta(days=15)

# --- 1B. INITIALISATION FIREBASE ---
firebase_key_raw = os.environ.get('FIREBASE_KEY')
if not firebase_key_raw:
    raise ValueError("Le secret FIREBASE_KEY est introuvable dans l'environnement.")

# Sécurité multi-script pour éviter les plantages lors d'exécutions simultanées
if not firebase_admin._apps:
    cred_json = json.loads(firebase_key_raw)
    cred = credentials.Certificate(cred_json)
    firebase_admin.initialize_app(cred)

db = firestore.client()

# --- 2. CHARGEMENT & NETTOYAGE DE L'HISTORIQUE ---
anciens_liens = {}
if os.path.exists(filename):
    try:
        with open(filename, mode="r", encoding="utf-8") as json_file:
            data_chargee = json.load(json_file)
            if isinstance(data_chargee, list):
                for item in data_chargee:
                    if "lienurl" in item:
                        try:
                            date_objet = datetime.strptime(item.get("date", ""), "%d/%m/%Y")
                            # Seuls les liens de moins de 15 jours sont conservés au démarrage
                            if date_objet >= limite_conservation:
                                anciens_liens[item["lienurl"]] = item
                        except:
                            anciens_liens[item["lienurl"]] = item
    except Exception as e:
        print(f"[Attention] Impossible de lire l'historique JSON : {e}")

# Client anti-bot Cloudflare
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
    liens_visites_session = set()  # Optimisation de recherche anti-doublon super rapide
    nouveaux_liens_detectes = 0  # Compteur dédié au déclenchement des pushs
    
    entry_content = soup.find(class_="entry-content")
    if not entry_content:
        entry_content = soup
        
    # --- 3. PARCOURS CHRONOLOGIQUE DES LIGNES ---
    for element in entry_content.find_all(["p", "li"]):
        links = element.find_all("a", href=True)
        
        if not links:
            continue
            
        text_ligne = element.get_text().strip().lower()
        
        # REGEX MONOPOLY GO : Recherche d'une date au format DD.M.YYYY ou D.M.YYYY dans la ligne
        match_date = re.search(r'(\d{1,2})[\s./](\d{1,2})[\s./](\d{4})', text_ligne)
        
        if match_date:
            jour = match_date.group(1).zfill(2)
            mois = match_date.group(2).zfill(2)
            annee = match_date.group(3)
            current_date_str = f"{jour}/{mois}/{annee}"
        else:
            current_date_str = now.strftime("%d/%m/%Y")
            
        for link in links:
            href = link["href"].strip()
            
            # Filtres d'exclusions standards (Inclusion des exclusions Reddit)
            if href.startswith("/") or "t.me" in href.lower() or "telegram.me" in href.lower() or "reddit" in href.lower():
                continue
            if any(p in href.lower() for p in ["twitter.com", "facebook.com", "whatsapp", "pinterest", "reddit.com"]):
                continue
                
            # Mots-clés de redirection officiels Monopoly Go (Ajout de mply.io)
            keywords = ["scope.ly", "monopolygo", "adj.st", "mply.io", "t.co", "bit.ly"]
            if any(key in href.lower() for key in keywords):
                
                try:
                    date_objet = datetime.strptime(current_date_str, "%d/%m/%Y")
                    # Ignore le lien s'il a plus de 15 jours sur le site
                    if date_objet < limite_conservation:
                        continue  
                except:
                    pass
                
                if href in liens_visites_session:
                    continue
                liens_visites_session.add(href)
                
                type_recompense = "Dés gratuits"
                
                # --- STRATÉGIE DE RECONSTITUTION : PRIORITÉ AU PLUS RÉCENT ---
                if href in anciens_liens:
                    try:
                        ancienne_date = datetime.strptime(anciens_liens[href].get("date", ""), "%d/%m/%Y")
                        nouvelle_date = datetime.strptime(current_date_str, "%d/%m/%Y")
                        
                        # Si le lien est réaffiché sur le site à une date plus récente
                        if nouvelle_date > ancienne_date:
                            date_scraping_finale = date_now_str
                            date_scraping1_finale = f"{current_date_str} @ {heure_actuelle_str}"
                            date_finale = current_date_str
                            heure_finale = heure_actuelle_str
                            badge_actuel = "NEW"
                        else:
                            # Sinon on conserve les informations de l'historique
                            date_scraping_finale = anciens_liens[href].get("date_scraping", date_now_str)
                            date_scraping1_finale = anciens_liens[href].get("date_scraping1", f"{current_date_str} @ {heure_actuelle_str}")
                            date_finale = anciens_liens[href].get("date", current_date_str)
                            heure_finale = anciens_liens[href].get("heure", "00:00")
                            
                            # Contrôle de maintien du badge NEW pendant 6 heures maximum
                            date_premier_scraping = datetime.strptime(date_scraping_finale, "%d/%m/%Y @ %H:%M")
                            badge_actuel = "NEW" if now - date_premier_scraping < timedelta(hours=6) else ""
                    except:
                        date_scraping_finale = anciens_liens[href].get("date_scraping", date_now_str)
                        date_scraping1_finale = anciens_liens[href].get("date_scraping1", f"{current_date_str} @ {heure_actuelle_str}")
                        date_finale = current_date_str
                        heure_finale = anciens_liens[href].get("heure", "00:00")
                        badge_actuel = anciens_liens[href].get("badge", "")

                    json_data.append({
                        "date_scraping": date_scraping_finale, 
                        "date_scraping1": date_scraping1_finale,
                        "date": date_finale,  
                        "heure": heure_finale,
                        "recompense": anciens_liens[href].get("recompense", type_recompense), 
                        "lienurl": href,
                        "badge": badge_actuel
                    })
                else:
                    # Nouveau lien trouvé pour la première fois lors de cette exécution
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

    if not json_data and anciens_liens:
        json_data = list(anciens_liens.values())

    # --- 4. TRI CHRONOLOGIQUE DES DATES DE PARUTION ---
    def extraire_cle_parution(item):
        try:
            return datetime.strptime(item.get("date", ""), "%d/%m/%Y").timestamp()
        except:
            return 0

    json_data.sort(key=extraire_cle_parution, reverse=True)

    # --- 5. ENREGISTREMENT LOCAL ---
    with open(filename, mode="w", encoding="utf-8") as json_file:
        json.dump(json_data, json_file, indent=4, ensure_ascii=False)
        
    print(f"[Terminé] Fichier Monopoly Go {filename} mis à jour via Mosttechs ({len(json_data)} liens valides indexés sur 15 jours).")
    print(f"[Diagnostic] Nombre de nouveaux liens détectés : {nouveaux_liens_detectes}")

    # --- 7. EXPORTATION NOTIFICATION & ENVOI PUSH DIRECT ---
    if nouveaux_liens_detectes > 0:
        try:
            from firebase_admin import messaging
            
            # 1. Écriture de l'historique anonyme dans la collection Firestore commune
            db.collection("notifications").add({
                "title": "🎩 Monopoly Reward ! 🎁",
                "body": "New free dice have just been added !",
                "nom_du_jeu": "monopoly_go",
                "created_at": firestore.SERVER_TIMESTAMP
            })
            print("[Firebase] Enregistrement d'historique créé pour Monopoly Go.")

            # 2. Propulsion du signal direct vers le canal de diffusion
            message = messaging.Message(
                notification=messaging.Notification(
                    title="🎩 Monopoly Reward ! 🎁",
                    body="New free dice have just been added !"
                ),
                topic="monopoly_go"  # Canal écouté par votre application
            )
            
            response = messaging.send(message)
