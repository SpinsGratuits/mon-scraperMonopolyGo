import json
import os
import re
from datetime import datetime, timedelta
import cloudscraper
from bs4 import BeautifulSoup

# --- 1. CONFIGURATION ---
url = "https://mosttechs.com/monopoly-go-free-dice/"
filename = "scrapmonopolygo.json"

# Dictionnaire de traduction des mois pour la conversion en vraies dates Python
mois_en_to_num = {
    "january": "01", "januray": "01", "february": "02", "february ": "02", "march": "03", 
    "april": "04", "may": "05", "june": "06", "july": "07", "august": "08", 
    "september": "09", "october": "10", "november": "11", "december": "12"
}

# --- 2. CHARGEMENT DE L'HISTORIQUE ---
anciens_liens = {}
if os.path.exists(filename):
    try:
        with open(filename, mode="r", encoding="utf-8") as json_file:
            data_chargee = json.load(json_file)
            if isinstance(data_chargee, list):
                for item in data_chargee:
                    if "lienurl" in item:
                        anciens_liens[item["lienurl"]] = item
    except Exception as e:
        print(f"[Attention] Impossible de lire l'historique JSON : {e}")

# Client de contournement anti-bot Cloudflare
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
    
    now = datetime.now()
    date_now_str = now.strftime("%d/%m/%Y @ %H:%M")
    heure_actuelle_str = now.strftime("%H:%M")
    
    # Seuil limite : conservation de l'historique sur 6 jours glissants maximum
    limite_conservation = now - timedelta(days=6)
    
    json_data = []
    
    # Isolement du bloc de contenu pour éviter les menus et liens annexes de Mosttechs
    entry_content = soup.find(class_="entry-content")
    if not entry_content:
        entry_content = soup
        
    # 3. PARCOURS DE LA STRUCTURE TEXTUELLE
    current_date_str = now.strftime("%d/%m/%Y")  # Valeur par défaut
    
    for element in entry_content.find_all(["p", "ul", "ol", "strong"]):
        text = element.get_text().strip().lower()
        
        # Détection d'une ligne de date (Ex: "25.9.2026" ou "31.8.2026")
        match_date = re.search(r'(\d{1,2})[\s./]+([a-z0-9]+)[\s./]+(\d{4})', text)
        if match_date:
            jour = match_date.group(1).zfill(2)
            mois_raw = match_date.group(2)
            annee = match_date.group(3)
            
            # Si le mois extrait est numérique (ex: 9 ou 09)
            if mois_raw.isdigit():
                num_mois = mois_raw.zfill(2)
            else:
                # Normalisation si le mois est textuel
                if mois_raw == "sep":
                    mois_raw = "september"
                elif mois_raw == "feb":
                    mois_raw = "february"
                elif mois_raw == "aug" or mois_raw == "augest":
                    mois_raw = "august"
                num_mois = mois_en_to_num.get(mois_raw, "01")
                
            current_date_str = f"{jour}/{num_mois}/{annee}"
            continue  # Date mise en mémoire, passage aux blocs inférieurs pour isoler les liens
            
        # Extraction des liens de récompense
        links = element.find_all("a", href=True)
        for link in links:
            href = link["href"].strip()
            
            # Filtres sanitaires (Exclusion des partages sociaux et structures de navigation interne)
            if href.startswith("/") or "t.me" in href.lower() or "telegram.me" in href.lower():
                continue
            if any(p in href.lower() for p in ["twitter.com", "facebook.com", "whatsapp", "pinterest", "reddit.com"]):
                continue
                
            # AJOUT DE "adj.st" pour inclure de manière exhaustive toutes les redirections Monopoly Go
            keywords = ["scope.ly", "monopolygo", "adj.st", "t.co", "bit.ly"]
            if any(key in href.lower() for key in keywords):
                
                # Validation de la politique d'auto-nettoyage à 6 jours
                try:
                    date_objet = datetime.strptime(current_date_str, "%d/%m/%Y")
                    if date_objet < limite_conservation:
                        continue  # Lien expiré par rapport au calendrier du site, ignoré
                except:
                    pass
                
                # Éviter la duplication si le même lien apparaît deux fois sur la même page
                if any(item["lienurl"] == href for item in json_data):
                    continue
                
                type_recompense = "Dés gratuits"
                
                # --- STRATÉGIE DE RECONSTITUTION ET DE CONSERVATION DES ANCIENNES HEURES ---
                if href in anciens_liens:
                    # ANCIEN LIEN : Récupération directe de l'historique initial sans altération horaire
                    json_data.append({
                        "date_scraping": anciens_liens[href].get("date_scraping", date_now_str), 
                        "date_scraping1": anciens_liens[href].get("date_scraping1", f"{current_date_str} @ {heure_actuelle_str}"),
                        "date": current_date_str,  
                        "heure": anciens_liens[href].get("heure", "00:00"),
                        "recompense": anciens_liens[href].get("recompense", type_recompense), 
                        "lienurl": href,
                        "badge": "" 
                    })
                else:
                    # NOUVEAU LIEN : Enregistrement initial avec la date du site et l'heure actuelle du robot
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

    # Restauration de l'historique existant en cas de panne temporaire du site distant
    if not json_data and anciens_liens:
        json_data = list(anciens_liens.values())

    # --- 4. TRI DE LA LISTE PAR ORDRE CHRONOLOGIQUE DES PARUTIONS (Le plus récent en haut) ---
    def extraire_cle_parution(item):
        try:
            date_part = datetime.strptime(item.get("date", ""), "%d/%m/%Y")
            return date_part.timestamp()
        except:
            return 0

    # Tri décroissant basé sur l'horodatage du calendrier du site
    json_data.sort(key=extraire_cle_parution, reverse=True)

    # --- 5. ENREGISTREMENT ---
    with open(filename, mode="w", encoding="utf-8") as json_file:
        json.dump(json_data, json_file, indent=4, ensure_ascii=False)
        
    print(f"[Terminé] Fichier Monopoly Go {filename} mis à jour ({len(json_data)} liens classés chronologiquement).")
            
else:
    print(f"[Erreur] Échec de la communication réseau avec Mosttechs (Code {status_code}).")
import json
import os
from datetime import datetime, date
import cloudscraper
from bs4 import BeautifulSoup
import re

# 1. URL du site cible et nom de votre fichier JSON
url = "https://gamewave.fr/monopoly-go/monopoly-go-liens-des-lancers-de-de-et-d-argent-gratuits/"
filename = "scrapmonopolygo.json"

# --- CHARGEMENT DE L'HISTORIQUE PRÉCÉDENT ---
# On crée un dictionnaire indexé par l'URL pour retrouver instantanément les données déjà scrapées
anciens_liens = {}
if os.path.exists(filename):
    try:
        with open(filename, mode="r", encoding="utf-8") as json_file:
            data_chargee = json.load(json_file)
            # On s'assure que c'est une liste valide et qu'elle ne contient pas le message "VIDE"
            if isinstance(data_chargee, list):
                for item in data_chargee:
                    if "lienurl" in item:
                        anciens_liens[item["lienurl"]] = item
    except Exception as e:
        print(f"Impossible de lire le fichier JSON précédent (il sera recréé) : {e}")

# Création d'un scraper imitant un navigateur Chrome sur Windows
scraper = cloudscraper.create_scraper(browser={'browser': 'chrome', 'platform': 'windows', 'mobile': False})

try:
    response = scraper.get(url)
    status_code = response.status_code
    html_text = response.text
except Exception as e:
    status_code = 500
    html_text = ""
    print(f"Erreur lors du contournement du blocage : {e}")

if status_code == 200:
    soup = BeautifulSoup(html_text, "html.parser")
    
    # Variables temporelles de VOTRE machine pour les NOUVEAUX liens uniquement
    now = datetime.now()
    date_now_str = now.strftime("%d/%m/%Y @ %H:%M")
    date_du_jour_str = now.strftime("%d/%m/%Y")
    heure_actuelle_str = now.strftime("%H:%M")
    
    # Liste finale qui sera réécrite dans le JSON
    json_data = []
    
    # 2. Scanner TOUS les liens hypertextes de la page
    all_links = soup.find_all("a", href=True)
    
    for link in all_links:
        href = link["href"]
        
        # Cibler uniquement les liens officiels de récompense mply.io
        if "mply.io" in href:
            # Éviter les doublons stricts au sein d'une même session de scraping
            if any(item["lienurl"] == href for item in json_data):
                continue
                
            # --- EXTRACTION DE LA RÉCOMPENSE ---
            parent_text = link.find_parent().get_text(separator=" ").strip() if link.find_parent() else ""
            if len(parent_text) < 15 and link.find_parent().find_parent():
                parent_text = link.find_parent().find_parent().get_text(separator=" ").strip()
            
            clean_text = " ".join(parent_text.split())
            recompense_match = re.search(r'\d+[\s\w]*(?:tours|spins|pieces|coins|tours\s*&\s*pièces)', clean_text, re.IGNORECASE)
            type_recompense = recompense_match.group(0).strip() if recompense_match else "Tours / Pièces"
            type_recompense = re.sub(r'^(?:Cliquez ici pour recevoir|Récupérer)\s*', '', type_recompense, flags=re.IGNORECASE)
            
            # --- LOGIQUE DE DOUBLE-VÉRIFICATION ET CONSERVATION ---
            if href in anciens_liens:
                # DOUBLON DETECTÉ : On conserve EXACTEMENT toutes les anciennes valeurs temporelles
                json_data.append({
                    "date_scraping": anciens_liens[href].get("date_scraping", date_now_str), 
                    "date": anciens_liens[href].get("date", date_du_jour_str), 
                    "heure": anciens_liens[href].get("heure", "00:00"),
                    "recompense": type_recompense, 
                    "lienurl": href,
                    "badge": ""  # Ancien lien, aucun texte additionnel
                })
            else:
                # NOUVEAU LIEN : On applique la date et l'heure de l'exécution actuelle de votre machine
                json_data.append({
                    "date_scraping": date_now_str, 
                    "date": date_du_jour_str, 
                    "heure": heure_actuelle_str,
                    "recompense": type_recompense, 
                    "lienurl": href,
                    "badge": "NEW"  # Texte "new" pour l'affichage sur votre site
                })

    # 3. Écriture du fichier JSON mis à jour
    if not json_data:
        json_data.append({
            "date_scraping": date_now_str,
            "statut": "VIDE",
            "message": "Aucun lien trouvé sur la page. Vérifiez manuellement le site."
        })
        print("Aucun lien extrait.")
    else:
        print(f"Succès total ! {len(json_data)} liens traités (Anciens préservés + Nouveaux ajoutés).")

    with open(filename, mode="w", encoding="utf-8") as json_file:
        json.dump(json_data, json_file, indent=4, ensure_ascii=False)
            
else:
    print(f"Erreur d'accès réseau (Code {status_code}). Le site bloque toujours.")
