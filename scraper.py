import json
import os
import re
from datetime import datetime, timedelta
import cloudscraper
from bs4 import BeautifulSoup

# --- 1. CONFIGURATION ---
url = "https://mosttechs.com/monopoly-go-free-dice/"
filename = "scrapmonopolygo.json"

now = datetime.now()
date_now_str = now.strftime("%d/%m/%Y @ %H:%M")
heure_actuelle_str = now.strftime("%H:%M")
limite_conservation = now - timedelta(days=6)

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
    liens_visites_session = set()  # Optimisation de recherche anti-doublon
    
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
            
            # Filtres d'exclusions standards
            if href.startswith("/") or "t.me" in href.lower() or "telegram.me" in href.lower():
                continue
            if any(p in href.lower() for p in ["twitter.com", "facebook.com", "whatsapp", "pinterest", "reddit.com"]):
                continue
                
            # Mots-clés de redirection Monopoly Go
            keywords = ["scope.ly", "monopolygo", "adj.st", "t.co", "bit.ly"]
            if any(key in href.lower() for key in keywords):
                
                try:
                    date_objet = datetime.strptime(current_date_str, "%d/%m/%Y")
                    if date_objet < limite_conservation:
                        continue  
                except:
                    pass
                
                if href in liens_visites_session:
                    continue
                liens_visites_session.add(href)
                
                type_recompense = "Dés gratuits"
                
                # --- STRATÉGIE DE RECONSTITUTION ET CONSERVATION DU BADGE NEW (6 HEURES) ---
                if href in anciens_liens:
                    date_premier_scraping_str = anciens_liens[href].get("date_scraping", date_now_str)
                    badge_actuel = ""
                    
                    try:
                        date_premier_scraping = datetime.strptime(date_premier_scraping_str, "%d/%m/%Y @ %H:%M")
                        # Conserver le badge si le lien a été enregistré il y a moins de 6 heures
                        if now - date_premier_scraping < timedelta(hours=6):
                            badge_actuel = "NEW"
                    except:
                        badge_actuel = anciens_liens[href].get("badge", "")

                    json_data.append({
                        "date_scraping": date_premier_scraping_str, 
                        "date_scraping1": anciens_liens[href].get("date_scraping1", f"{current_date_str} @ {heure_actuelle_str}"),
                        "date": current_date_str,  
                        "heure": anciens_liens[href].get("heure", "00:00"),
                        "recompense": anciens_liens[href].get("recompense", type_recompense), 
                        "lienurl": href,
                        "badge": badge_actuel
                    })
                else:
                    # Nouveau lien trouvé lors du cycle de scraping actuel
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

    # --- 4. TRI CHRONOLOGIQUE PAR DATE DE PARUTION ---
    def extraire_cle_parution(item):
        try:
            return datetime.strptime(item.get("date", ""), "%d/%m/%Y").timestamp()
        except:
            return 0

    json_data.sort(key=extraire_cle_parution, reverse=True)

    # --- 5. ENREGISTREMENT ---
    with open(filename, mode="w", encoding="utf-8") as json_file:
        json.dump(json_data, json_file, indent=4, ensure_ascii=False)
        
    print(f"[Terminé] Fichier Monopoly Go {filename} mis à jour ({len(json_data)} liens valides).")
            
else:
    print(f"[Erreur] Échec de la communication réseau avec Mosttechs (Code {status_code}).")
    
