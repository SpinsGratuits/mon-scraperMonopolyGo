import json
import os
import re
from datetime import datetime, timedelta
import cloudscraper
from bs4 import BeautifulSoup

# --- 1. CONFIGURATION ---
url = "https://mosttechs.com/monopoly-go-free-dice/"
filename = "scrapmonopolygo.json"

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
    
    now = datetime.now()
    date_now_str = now.strftime("%d/%m/%Y @ %H:%M")
    heure_actuelle_str = now.strftime("%H:%M")
    
    # Seuil limite à 6 jours maximum
    limite_conservation = now - timedelta(days=6)
    
    json_data = []
    
    entry_content = soup.find(class_="entry-content")
    if not entry_content:
        entry_content = soup
        
    # 3. PARCOURS CHRONOLOGIQUE DES LIGNES (Extraction de la date en fin de ligne)
    # On cherche tous les blocs susceptibles de contenir un lien de dés
    for element in entry_content.find_all(["p", "li"]):
        links = element.find_all("a", href=True)
        
        if not links:
            continue
            
        text_ligne = element.get_text().strip().lower()
        
        # REGEX SPÉCIFIQUE MONOPOLY GO : Cherche une date numérique de type DD.M.YYYY ou D.M.YYYY à la fin du texte
        match_date = re.search(r'(\d{1,2})[\s./](\d{1,2})[\s./](\d{4})', text_ligne)
        
        if match_date:
            jour = match_date.group(1).zfill(2)
            mois = match_date.group(2).zfill(2)
            annee = match_date.group(3)
            current_date_str = f"{jour}/{mois}/{annee}"
        else:
            # Date de secours si la ligne n'a pas de date lisible
            current_date_str = now.strftime("%d/%m/%Y")
            
        for link in links:
            href = link["href"].strip()
            
            # Filtres d'exclusions standards
            if href.startswith("/") or "t.me" in href.lower() or "telegram.me" in href.lower():
                continue
            if any(p in href.lower() for p in ["twitter.com", "facebook.com", "whatsapp", "pinterest", "reddit.com"]):
                continue
                
            # Mots-clés de redirection Monopoly Go (Inclusion de adj.st)
            keywords = ["scope.ly", "monopolygo", "adj.st", "t.co", "bit.ly"]
            if any(key in href.lower() for key in keywords):
                
                # Validation du nettoyage automatique à 6 jours
                try:
                    date_objet = datetime.strptime(current_date_str, "%d/%m/%Y")
                    if date_objet < limite_conservation:
                        continue  # Plus vieux de 6 jours, on ignore
                except:
                    pass
                
                # Éviter les doublons de session
                if any(item["lienurl"] == href for item in json_data):
                    continue
                
                type_recompense = "Dés gratuits"
                
                # --- STRATÉGIE DE RECONSTITUTION AVEC GEL DE L'HISTORIQUE ---
                if href in anciens_liens:
                    # ANCIEN LIEN : On conserve l'ancienne heure de découverte originale sans modification
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
                    # NOUVEAU LIEN : Calcul initial combinant la date extraite de la ligne et l'heure du robot
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

    # Sauvegarde de secours
    if not json_data and anciens_liens:
        json_data = list(anciens_liens.values())

    # --- 4. TRI CHRONOLOGIQUE DES DATES DE PARUTION (Du plus récent au plus ancien) ---
    def extraire_cle_parution(item):
        try:
            date_part = datetime.strptime(item.get("date", ""), "%d/%m/%Y")
            return date_part.timestamp()
        except:
            return 0

    json_data.sort(key=extraire_cle_parution, reverse=True)

    # --- 5. ENREGISTREMENT ---
    with open(filename, mode="w", encoding="utf-8") as json_file:
        json.dump(json_data, json_file, indent=4, ensure_ascii=False)
        
    print(f"[Terminé] Fichier Monopoly Go {filename} généré avec succès ({len(json_data)} liens classés chronologiquement).")
            
else:
    print(f"[Erreur] Échec de la communication réseau avec Mosttechs (Code {status_code}).")
